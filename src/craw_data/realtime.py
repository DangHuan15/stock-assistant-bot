"""Cache giá DNSE trong RAM, hết hạn sau 15 giây."""

import asyncio
import re
import time
from collections import OrderedDict

from .crawler import DNSEError, fetch_latest_trade


class PriceCache:
    """Lưu giá tạm và gộp các yêu cầu lấy cùng một mã."""

    def __init__(self, ttl: float = 15.0, max_entries: int = 256):
        """Khởi tạo cache và giới hạn số yêu cầu đồng thời."""
        self.ttl = ttl
        self.max_entries = max_entries
        self._cache = OrderedDict()
        self._pending = {}
        self._semaphore = asyncio.Semaphore(4)

    def prune(self) -> None:
        """Xóa giá đã hết hạn, không gọi API."""
        now = time.monotonic()

        expired = [
            symbol
            for symbol, (deadline, _) in self._cache.items()
            if deadline <= now
        ]

        for symbol in expired:
            self._cache.pop(symbol, None)

    async def get(self, value: str) -> tuple[dict, str]:
        """Trả giá từ cache hoặc chờ yêu cầu DNSE cho cùng mã."""
        symbol = value.strip().upper()

        if not re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol):
            raise DNSEError("Mã không hợp lệ. Ví dụ: /price FPT")

        self.prune()

        cached = self._cache.get(symbol)
        if cached is not None:
            _, quote = cached
            self._cache.move_to_end(symbol)
            return quote, "Cache RAM dưới 15 giây"

        task = self._pending.get(symbol)

        # Luôn gán source, kể cả khi dùng yêu cầu đang chạy.
        source = "Dùng chung yêu cầu DNSE đang xử lý"

        if task is None:
            if len(self._pending) >= 32:
                raise DNSEError("Bot đang bận. Hãy thử lại sau.")

            task = asyncio.create_task(self._load(symbol))
            self._pending[symbol] = task
            task.add_done_callback(self._observe_result)
            source = "Vừa lấy từ DNSE"

        quote = await asyncio.shield(task)
        return quote, source
    @staticmethod
    def _observe_result(task: asyncio.Task) -> None:
        """Thu nhận ngoại lệ nếu không còn người chờ tác vụ."""
        if not task.cancelled():
            task.exception()

    async def _load(self, symbol: str) -> dict:
        """Lấy giá ở luồng phụ và lưu kết quả thành công."""
        try:
            async with self._semaphore:
                quote = await asyncio.to_thread(
                    fetch_latest_trade,
                    symbol,
                )

            self.prune()
            self._cache[symbol] = (
                time.monotonic() + self.ttl,
                quote,
            )
            self._cache.move_to_end(symbol)

            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)

            return quote
        finally:
            # Luôn giải phóng yêu cầu đang chờ, kể cả khi API lỗi.
            self._pending.pop(symbol, None)

    async def sweep(self) -> None:
        """Dọn cache mỗi giây; không tự tải thêm giá."""
        while True:
            await asyncio.sleep(1)
            self.prune()

    async def close(self) -> None:
        """Chờ yêu cầu đang chạy rồi giải phóng cache khi dừng."""
        tasks = list(self._pending.values())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._cache.clear()