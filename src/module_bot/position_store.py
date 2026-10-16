"""Lưu vị thế ảo theo người dùng Telegram bằng JSON nhỏ gọn."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


class PositionStore:
    """Kho vị thế an toàn khi nhiều yêu cầu Telegram chạy đồng thời."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    async def get(self, user_id: int, symbol: str) -> dict[str, Any] | None:
        """Đọc một vị thế đang mở."""
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            position = data.get(str(user_id), {}).get(symbol)
            if not isinstance(position, dict) or position.get("status") != "OPEN":
                return None
            return dict(position)

    async def save(self, user_id: int, position: dict[str, Any]) -> None:
        """Thêm hoặc cập nhật vị thế theo mã."""
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            account = data.setdefault(str(user_id), {})
            account[str(position["symbol"])] = dict(position)
            await asyncio.to_thread(self._write, data)

    async def remove(self, user_id: int, symbol: str) -> bool:
        """Xóa vị thế và trả về True nếu vị thế tồn tại."""
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            account = data.get(str(user_id), {})
            existed = symbol in account
            account.pop(symbol, None)
            if not account:
                data.pop(str(user_id), None)
            await asyncio.to_thread(self._write, data)
            return existed

    async def list_open(self, user_id: int) -> list[dict[str, Any]]:
        """Liệt kê các vị thế đang mở của một người dùng."""
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            account = data.get(str(user_id), {})
            return [
                dict(position)
                for position in account.values()
                if isinstance(position, dict) and position.get("status") == "OPEN"
            ]
