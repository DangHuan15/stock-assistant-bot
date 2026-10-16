"""Lưu cài đặt người dùng (chế độ ngắn/dài hạn) bằng JSON an toàn."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


class SettingsStore:
    """Quản lý cấu hình người dùng an toàn khi nhiều yêu cầu chạy đồng thời."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
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

    async def get_mode(self, user_id: int) -> str:
        """Lấy chế độ ưa thích: 'short' (mặc định) hoặc 'long'."""
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            user_data = data.get(str(user_id), {})
            return user_data.get("mode", "short")

    async def set_mode(self, user_id: int, mode: str) -> None:
        """Lưu chế độ: 'short' hoặc 'long'."""
        normalized = "long" if str(mode).lower() in ("long", "daihan", "dài hạn", "dai_han", "2") else "short"
        async with self._lock:
            data = await asyncio.to_thread(self._read)
            user_data = data.setdefault(str(user_id), {})
            user_data["mode"] = normalized
            await asyncio.to_thread(self._write, data)
