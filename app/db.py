from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from supabase import Client, create_client

from app.config import settings


T = TypeVar("T")


class Database:
    def __init__(self) -> None:
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    async def _run(self, fn: Callable[[], T]) -> T:
        return await asyncio.to_thread(fn)

    async def ensure_user(self, telegram_id: int) -> dict[str, Any]:
        def op():
            self.client.table("users").upsert(
                {"telegram_id": telegram_id},
                on_conflict="telegram_id",
            ).execute()
            result = (
                self.client.table("users")
                .select("*")
                .eq("telegram_id", telegram_id)
                .limit(1)
                .execute()
            )
            return result.data[0]

        return await self._run(op)

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        def op():
            result = (
                self.client.table("users")
                .select("*")
                .eq("telegram_id", telegram_id)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None

        return await self._run(op)

    async def set_initial_balances(self, telegram_id: int, card: int, cash: int) -> dict[str, Any]:
        def op():
            result = (
                self.client.table("users")
                .update(
                    {
                        "card_balance": card,
                        "cash_balance": cash,
                        "initialized_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("telegram_id", telegram_id)
                .execute()
            )
            return result.data[0]

        return await self._run(op)

    async def get_balances(self, telegram_id: int) -> dict[str, int]:
        user = await self.get_user(telegram_id)
        if not user:
            return {"card": 0, "cash": 0}
        return {
            "card": int(user["card_balance"]),
            "cash": int(user["cash_balance"]),
        }

    async def list_categories(self, telegram_id: int) -> list[str]:
        def op():
            result = (
                self.client.table("transactions")
                .select("category")
                .eq("telegram_id", telegram_id)
                .eq("kind", "expense")
                .execute()
            )
            names = {row["category"] for row in result.data if row.get("category")}
            return sorted(names)

        return await self._run(op)

    async def record_transaction(
        self,
        telegram_id: int,
        *,
        kind: str,
        amount: int,
        category: str | None,
        account: str,
        raw_text: str,
    ) -> dict[str, Any]:
        def op():
            result = self.client.rpc(
                "record_transaction",
                {
                    "p_telegram_id": telegram_id,
                    "p_kind": kind,
                    "p_amount": amount,
                    "p_category": category,
                    "p_account": account,
                    "p_raw_text": raw_text,
                },
            ).execute()
            if not result.data:
                raise RuntimeError("Supabase не вернул результат записи.")
            return result.data[0]

        return await self._run(op)

    async def record_transfer(
        self,
        telegram_id: int,
        *,
        amount: int,
        from_account: str,
        to_account: str,
        raw_text: str,
    ) -> dict[str, Any]:
        def op():
            result = self.client.rpc(
                "record_transfer",
                {
                    "p_telegram_id": telegram_id,
                    "p_amount": amount,
                    "p_from_account": from_account,
                    "p_to_account": to_account,
                    "p_raw_text": raw_text,
                },
            ).execute()
            if not result.data:
                raise RuntimeError("Supabase не вернул результат перевода.")
            return result.data[0]

        return await self._run(op)

    async def undo_last_transaction(self, telegram_id: int) -> dict[str, Any] | None:
        def op():
            result = self.client.rpc(
                "undo_last_transaction",
                {"p_telegram_id": telegram_id},
            ).execute()
            if not result.data:
                return None
            return result.data[0]

        return await self._run(op)

    async def transactions_between(
        self,
        telegram_id: int,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        def op():
            result = (
                self.client.table("transactions")
                .select("id,kind,amount,category,account,target_account,raw_text,created_at")
                .eq("telegram_id", telegram_id)
                .gte("created_at", start.isoformat())
                .lt("created_at", end.isoformat())
                .order("created_at", desc=False)
                .execute()
            )
            return result.data

        return await self._run(op)

    async def recent_transactions(self, telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
        def op():
            result = (
                self.client.table("transactions")
                .select("id,kind,amount,category,account,raw_text,created_at")
                .eq("telegram_id", telegram_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data

        return await self._run(op)
