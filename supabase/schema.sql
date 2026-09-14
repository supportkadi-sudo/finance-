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
    kind text not null check (kind in ('income', 'expense')),
    amount bigint not null check (amount > 0),
    category text,
    account text not null check (account in ('card', 'cash')),
    raw_text text not null,
    created_at timestamptz not null default now()
);

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
    if p_kind not in ('income', 'expense') then
        raise exception 'invalid kind';
    end if;

    if p_account not in ('card', 'cash') then
        raise exception 'invalid account';
    end if;

    if p_amount <= 0 then
        raise exception 'amount must be positive';
    end if;

    select *
      into v_user
      from public.users
     where telegram_id = p_telegram_id
     for update;

    if not found or v_user.initialized_at is null then
        raise exception 'user is not initialized';
    end if;

    v_delta := case when p_kind = 'income' then p_amount else -p_amount end;

    update public.users
       set card_balance = card_balance + case when p_account = 'card' then v_delta else 0 end,
           cash_balance = cash_balance + case when p_account = 'cash' then v_delta else 0 end,
           updated_at = now()
     where telegram_id = p_telegram_id
     returning * into v_user;

    insert into public.transactions (
        telegram_id, kind, amount, category, account, raw_text
    )
    values (
        p_telegram_id, p_kind, p_amount, p_category, p_account, p_raw_text
    )
    returning id into v_transaction_id;

    return query
    select v_transaction_id, v_user.card_balance, v_user.cash_balance;
end;
$$;

revoke all on function public.record_transaction(bigint, text, bigint, text, text, text)
from public, anon, authenticated;

grant execute on function public.record_transaction(bigint, text, bigint, text, text, text)
to service_role;
