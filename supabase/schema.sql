create extension if not exists pgcrypto;

create table if not exists public.users (
    telegram_id bigint primary key,
    card_balance bigint not null default 0,
    cash_balance bigint not null default 0,
    initialized_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.transactions (
    id uuid primary key default gen_random_uuid(),
    telegram_id bigint not null references public.users(telegram_id) on delete cascade,
    kind text not null,
    amount bigint not null check (amount > 0),
    category text,
    account text not null check (account in ('card', 'cash')),
    target_account text,
    raw_text text not null,
    created_at timestamptz not null default now()
);

alter table public.transactions
    add column if not exists target_account text;

alter table public.transactions
    drop constraint if exists transactions_kind_check;

alter table public.transactions
    add constraint transactions_kind_check
    check (kind in ('income', 'expense', 'business_out', 'business_in', 'transfer'));

alter table public.transactions
    drop constraint if exists transactions_target_account_check;

alter table public.transactions
    add constraint transactions_target_account_check
    check (target_account is null or target_account in ('card', 'cash'));

create index if not exists idx_transactions_user_created
    on public.transactions (telegram_id, created_at desc);

create index if not exists idx_transactions_user_kind_created
    on public.transactions (telegram_id, kind, created_at desc);

alter table public.users enable row level security;
alter table public.transactions enable row level security;

create or replace function public.record_transaction(
    p_telegram_id bigint,
    p_kind text,
    p_amount bigint,
    p_category text,
    p_account text,
    p_raw_text text
)
returns table (
    transaction_id uuid,
    card_balance bigint,
    cash_balance bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_user public.users%rowtype;
    v_delta bigint;
    v_transaction_id uuid;
begin
    if p_kind not in ('income', 'expense', 'business_out', 'business_in') then
        raise exception 'invalid kind';
    end if;

    if p_account not in ('card', 'cash') then
        raise exception 'invalid account';
    end if;

    if p_amount <= 0 then
        raise exception 'amount must be positive';
    end if;

    select u.*
      into v_user
      from public.users as u
     where u.telegram_id = p_telegram_id
     for update;

    if not found or v_user.initialized_at is null then
        raise exception 'user is not initialized';
    end if;

    v_delta := case
        when p_kind in ('income', 'business_in') then p_amount
        else -p_amount
    end;

    update public.users as u
       set card_balance = u.card_balance + case when p_account = 'card' then v_delta else 0 end,
           cash_balance = u.cash_balance + case when p_account = 'cash' then v_delta else 0 end,
           updated_at = now()
     where u.telegram_id = p_telegram_id
     returning u.* into v_user;

    insert into public.transactions as t (
        telegram_id, kind, amount, category, account, target_account, raw_text
    )
    values (
        p_telegram_id, p_kind, p_amount, p_category, p_account, null, p_raw_text
    )
    returning t.id into v_transaction_id;

    return query
    select v_transaction_id, v_user.card_balance, v_user.cash_balance;
end;
$$;

create or replace function public.record_transfer(
    p_telegram_id bigint,
    p_amount bigint,
    p_from_account text,
    p_to_account text,
    p_raw_text text
)
returns table (
    transaction_id uuid,
    card_balance bigint,
    cash_balance bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_user public.users%rowtype;
    v_transaction_id uuid;
    v_category text;
begin
    if p_from_account not in ('card', 'cash')
       or p_to_account not in ('card', 'cash')
       or p_from_account = p_to_account then
        raise exception 'invalid transfer accounts';
    end if;

    if p_amount <= 0 then
        raise exception 'amount must be positive';
    end if;

    select u.*
      into v_user
      from public.users as u
     where u.telegram_id = p_telegram_id
     for update;

    if not found or v_user.initialized_at is null then
        raise exception 'user is not initialized';
    end if;

    if p_from_account = 'card' and v_user.card_balance < p_amount then
        raise exception 'insufficient source balance';
    end if;

    if p_from_account = 'cash' and v_user.cash_balance < p_amount then
        raise exception 'insufficient source balance';
    end if;

    update public.users as u
       set card_balance = u.card_balance
            + case when p_to_account = 'card' then p_amount else 0 end
            - case when p_from_account = 'card' then p_amount else 0 end,
           cash_balance = u.cash_balance
            + case when p_to_account = 'cash' then p_amount else 0 end
            - case when p_from_account = 'cash' then p_amount else 0 end,
           updated_at = now()
     where u.telegram_id = p_telegram_id
     returning u.* into v_user;

    v_category := case
        when p_from_account = 'card' then 'Карта → Наличные'
        else 'Наличные → Карта'
    end;

    insert into public.transactions as t (
        telegram_id, kind, amount, category, account, target_account, raw_text
    )
    values (
        p_telegram_id, 'transfer', p_amount, v_category,
        p_from_account, p_to_account, p_raw_text
    )
    returning t.id into v_transaction_id;

    return query
    select v_transaction_id, v_user.card_balance, v_user.cash_balance;
end;
$$;

create or replace function public.undo_last_transaction(
    p_telegram_id bigint
)
returns table (
    undone_transaction_id uuid,
    kind text,
    amount bigint,
    category text,
    account text,
    card_balance bigint,
    cash_balance bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_user public.users%rowtype;
    v_tx public.transactions%rowtype;
    v_reverse_delta bigint;
begin
    select u.*
      into v_user
      from public.users as u
     where u.telegram_id = p_telegram_id
     for update;

    if not found or v_user.initialized_at is null then
        raise exception 'user is not initialized';
    end if;

    select t.*
      into v_tx
      from public.transactions as t
     where t.telegram_id = p_telegram_id
     order by t.created_at desc, t.id desc
     limit 1
     for update;

    if not found then
        return;
    end if;

    if v_tx.kind = 'transfer' then
        if v_tx.target_account is null then
            raise exception 'transfer target account is missing';
        end if;

        update public.users as u
           set card_balance = u.card_balance
                + case when v_tx.account = 'card' then v_tx.amount else 0 end
                - case when v_tx.target_account = 'card' then v_tx.amount else 0 end,
               cash_balance = u.cash_balance
                + case when v_tx.account = 'cash' then v_tx.amount else 0 end
                - case when v_tx.target_account = 'cash' then v_tx.amount else 0 end,
               updated_at = now()
         where u.telegram_id = p_telegram_id
         returning u.* into v_user;
    else
        v_reverse_delta := case
            when v_tx.kind in ('income', 'business_in') then -v_tx.amount
            else v_tx.amount
        end;

        update public.users as u
           set card_balance = u.card_balance + case when v_tx.account = 'card' then v_reverse_delta else 0 end,
               cash_balance = u.cash_balance + case when v_tx.account = 'cash' then v_reverse_delta else 0 end,
               updated_at = now()
         where u.telegram_id = p_telegram_id
         returning u.* into v_user;
    end if;

    delete from public.transactions as t where t.id = v_tx.id;

    return query
    select
        v_tx.id,
        v_tx.kind,
        v_tx.amount,
        v_tx.category,
        v_tx.account,
        v_user.card_balance,
        v_user.cash_balance;
end;
$$;

revoke all on function public.record_transaction(bigint, text, bigint, text, text, text)
from public, anon, authenticated;

revoke all on function public.record_transfer(bigint, bigint, text, text, text)
from public, anon, authenticated;

revoke all on function public.undo_last_transaction(bigint)
from public, anon, authenticated;

grant execute on function public.record_transaction(bigint, text, bigint, text, text, text)
to service_role;

grant execute on function public.record_transfer(bigint, bigint, text, text, text)
to service_role;

grant execute on function public.undo_last_transaction(bigint)
to service_role;
