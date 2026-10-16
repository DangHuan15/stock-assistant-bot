"""Tải lịch sử vnstock cho từng mã và lưu cache CSV."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


# history.py nằm tại src/craw_data/. CACHE_DIR trỏ về thư mục stock_cache ở gốc dự án.
CACHE_DIR = Path(__file__).resolve().parents[2] / "stock_cache"
VN_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
LOOKBACK_DAYS = 420

# Khóa cố định để tránh hai yêu cầu cùng ghi file của một mã.
# Không tạo một khóa mới cho mỗi mã nên bộ nhớ không tăng vô hạn.
LOCKS = [threading.Lock() for _ in range(16)]


class HistoryError(Exception):
    """Lỗi lịch sử có thông báo phù hợp để hiển thị trên Telegram."""


def normalize_symbol(value: str) -> str:
    """Kiểm tra mã trước khi dùng làm tham số API và tên file."""
    symbol = value.strip().upper()

    if not re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol):
        raise HistoryError("Mã không hợp lệ. Ví dụ: HDB, VHM, MWG.")

    return symbol


def clean_history(raw: pd.DataFrame, today) -> pd.DataFrame:
    """Chuẩn hóa OHLCV và loại nến ngày hiện tại.

    Không tự sửa giá lỗi hoặc lấp ngày không giao dịch bằng giá giả.
    Không đổi đơn vị và không trộn giá DNSE vào lịch sử vnstock.
    """
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise HistoryError("Nguồn lịch sử không trả dữ liệu.")

    frame = raw.copy()

    aliases = {
        "time": "Date",
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

    frame.columns = [
        aliases.get(str(column).strip().lower(), str(column).strip())
        for column in frame.columns
    ]

    if frame.columns.duplicated().any():
        raise HistoryError("Dữ liệu có tên cột trùng sau chuẩn hóa.")

    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise HistoryError(
            "Lịch sử thiếu cột: "
            + ", ".join(sorted(missing))
            + ". Các cột nhận được: "
            + ", ".join(map(str, frame.columns))
        )

    frame = frame[COLUMNS].copy()

    # Không đoán đơn vị nếu nguồn bất ngờ trả timestamp dạng số.
    if pd.api.types.is_numeric_dtype(frame["Date"]):
        raise HistoryError(
            "Cột ngày đang là số. Cần xác minh đơn vị timestamp."
        )

    try:
        dates = pd.to_datetime(frame["Date"], errors="raise")

        if dates.dt.tz is not None:
            dates = dates.dt.tz_convert(VN_TIMEZONE).dt.tz_localize(None)

        frame["Date"] = dates.dt.normalize()
    except (ValueError, TypeError, AttributeError):
        raise HistoryError("Không đọc được cột ngày lịch sử.") from None

    if frame["Date"].isna().any():
        raise HistoryError("Lịch sử có ngày bị thiếu.")

    start = pd.Timestamp(today - timedelta(days=LOOKBACK_DAYS))
    end = pd.Timestamp(today)

    frame = frame[
        (frame["Date"] >= start)
        & (frame["Date"] < end)
    ].copy()

    if frame.empty:
        raise HistoryError("Chưa có nến ngày đã hoàn tất trong khoảng yêu cầu.")

    for column in COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    values = frame[COLUMNS[1:]].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise HistoryError("Lịch sử có giá hoặc khối lượng thiếu/không hợp lệ.")

    prices = frame[["Open", "High", "Low", "Close"]]

    if (prices <= 0).any().any() or (frame["Volume"] < 0).any():
        raise HistoryError("Giá phải dương và khối lượng không được âm.")

    bad_candles = (
        (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1))
        | (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1))
    )

    if bad_candles.any():
        raise HistoryError("Có nến không thỏa điều kiện High/Low.")

    # Bản ghi trùng hoàn toàn có thể loại; cùng ngày khác giá thì báo lỗi.
    frame = frame.drop_duplicates()

    if frame["Date"].duplicated().any():
        raise HistoryError("Có nhiều nến khác nhau cho cùng một ngày.")

    return frame.sort_values("Date").reset_index(drop=True)


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Ghi qua file tạm rồi thay thế để tránh CSV ghi dở."""
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".tmp",
            prefix=f"{path.stem}_",
            dir=path.parent,
            delete=False,
            encoding="utf-8",
            newline="",
        ) as handle:
            temporary = Path(handle.name)
            frame.to_csv(
                handle,
                index=False,
                date_format="%Y-%m-%d",
            )

        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def get_history(
    symbol: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Lấy lịch sử từ CSV hoặc tải riêng mã đó bằng vnstock.

    Cache được kiểm tra lại mỗi ngày theo giờ Việt Nam.
    Ngày hôm nay luôn bị loại, kể cả khi thị trường đã đóng cửa.
    """
    symbol = normalize_symbol(symbol)
    today = datetime.now(VN_TIMEZONE).date()

    # Gắn nguồn vào tên file để không nhầm cache từ nguồn khác.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{symbol}_vnstock_kbs_1D.csv"

    lock = LOCKS[sum(symbol.encode("ascii")) % len(LOCKS)]

    with lock:
        if path.exists() and not force_refresh:
            saved_date = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=VN_TIMEZONE,
            ).date()

            if saved_date == today:
                try:
                    frame = clean_history(pd.read_csv(path), today)
                    frame.attrs["origin"] = "CSV cache"
                    frame.attrs["provider"] = "vnstock/KBS"
                    return frame
                except (HistoryError, ValueError, OSError):
                    # Cache lỗi thì thử tải lại; không trả dữ liệu hỏng.
                    pass

        start = today - timedelta(days=LOOKBACK_DAYS)

        try:
            # Chỉ import/tải khi cần lịch sử, không tải lúc mở bot.
            from vnstock import Market

            raw = Market().equity(symbol).ohlcv(
                start=start.isoformat(),
                end=today.isoformat(),
                interval="1D",
                count=500,
                source="kbs",
            )
        except Exception as exc:
            raise HistoryError(
                f"Không tải được lịch sử {symbol} "
                f"({type(exc).__name__}). "
                "Kiểm tra mạng, quyền hoặc giới hạn truy cập vnstock."
            ) from None

        frame = clean_history(raw, today)

        try:
            write_csv_atomic(frame, path)
        except OSError:
            raise HistoryError(
                "Đã nhận lịch sử nhưng không ghi được cache CSV. "
                "Kiểm tra quyền thư mục stock_cache."
            ) from None

        frame.attrs["origin"] = "Vừa tải từ vnstock"
        frame.attrs["provider"] = "vnstock/KBS"
        return frame


def main() -> None:
    """Kiểm tra lịch sử một mã từ Terminal."""
    parser = argparse.ArgumentParser(
        description="Tải lịch sử vnstock cho riêng một cổ phiếu."
    )
    parser.add_argument("symbol")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    try:
        frame = get_history(
            args.symbol,
            force_refresh=args.refresh,
        )

        print("\nNguồn:", frame.attrs["origin"])
        print("Nhà cung cấp:", frame.attrs["provider"])
        print("Số phiên thực nhận:", len(frame))
        print("Ngày đầu:", frame["Date"].iloc[0].date())
        print("Ngày cuối:", frame["Date"].iloc[-1].date())
        print("\n5 phiên cuối:")
        print(frame.tail(5).to_string(index=False))

        if len(frame) < 100:
            print(
                "\nLưu ý: chưa đủ 100 phiên cho cấu hình "
                "SmartScore dự kiến."
            )

        print("\nThư mục cache:", CACHE_DIR)

    except HistoryError as exc:
        print(f"Lỗi: {exc}")


if __name__ == "__main__":
    main()