"""Kết nối DNSE và lấy giá khớp gần nhất theo yêu cầu."""

import json
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import urllib3
from dnse import DNSEClient
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VN_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
MARKETS = {"STO": "HOSE", "STX": "HNX"}


class DNSEError(Exception):
    """Lỗi DNSE có thông báo phù hợp để gửi cho người dùng."""


def create_client() -> DNSEClient:
    """Đọc khóa từ .env và tạo kết nối HTTPS có timeout."""
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=True,
        encoding="utf-8-sig",
    )

    api_key = os.getenv("DNSE_API_KEY", "").strip()
    api_secret = os.getenv("DNSE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        raise DNSEError("Thiếu DNSE_API_KEY hoặc DNSE_API_SECRET.")

    if os.getenv("DEBUG", "").lower() == "true":
        raise DNSEError("Hãy đặt DEBUG=false trong .env.")

    client = DNSEClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://openapi.dnse.com.vn",
    )

    # Adapter cho phiên bản SDK đã copy vào dự án.
    client._http.clear()
    client._http = urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED",
        timeout=urllib3.Timeout(connect=5.0, read=15.0),
        retries=False,
    )

    return client


def fetch_latest_trade(symbol: str) -> dict:
    """Lấy giao dịch gần nhất theo cấu trúc {"trades": [...]}."""
    symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol):
        raise DNSEError("Mã không hợp lệ. Ví dụ: FPT, HDB, VHM.")

    client = create_client()

    try:
        status, body = client.get_latest_trade(
            symbol=symbol,
            board_id="G1",
            dry_run=False,
        )
    except (urllib3.exceptions.HTTPError, OSError):
        raise DNSEError(
            "Không kết nối được DNSE hoặc yêu cầu hết thời gian chờ."
        ) from None
    except UnicodeError:
        raise DNSEError("Không đọc được phản hồi DNSE.") from None
    finally:
        client._http.clear()

    if status in (401, 403):
        raise DNSEError("DNSE từ chối xác thực hoặc quyền dữ liệu.")
    if status == 429:
        raise DNSEError("DNSE đang giới hạn truy cập. Hãy thử lại sau.")
    if status in (204, 404):
        raise DNSEError(f"Chưa tìm thấy giao dịch của {symbol}.")
    if status != 200:
        raise DNSEError(f"DNSE trả lỗi HTTP {status}.")

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        raise DNSEError("Phản hồi DNSE không phải JSON hợp lệ.") from None

    if not isinstance(payload, dict):
        raise DNSEError("Phản hồi DNSE không đúng cấu trúc.")

    trades = payload.get("trades")
    if not isinstance(trades, list):
        raise DNSEError("Phản hồi DNSE thiếu danh sách trades.")

    matches = [
        item
        for item in trades
        if isinstance(item, dict)
        and item.get("symbol") == symbol
        and item.get("boardId") == "G1"
    ]

    if not matches:
        raise DNSEError(f"Chưa có giao dịch của {symbol} trên bảng G1.")

    if len(matches) != 1:
        raise DNSEError("Chưa xác định được một giao dịch gần nhất duy nhất.")

    record = matches[0]
    market_id = record.get("marketId")

    if market_id not in MARKETS:
        raise DNSEError("Bản này chỉ hỗ trợ cổ phiếu HOSE và HNX.")

    try:
        price = Decimal(str(record.get("matchPrice")))
    except (InvalidOperation, ValueError):
        raise DNSEError("Giá khớp DNSE không hợp lệ.") from None

    if not price.is_finite() or price <= 0:
        raise DNSEError("DNSE chưa cung cấp giá khớp hợp lệ.")

    return {
        "symbol": symbol,
        "exchange": MARKETS[market_id],
        "price": str(price),
        "quantity": record.get("matchQtty"),
        "total_volume": record.get("totalVolumeTraded"),
        "open": record.get("openPrice"),
        "high": record.get("highestPrice"),
        "low": record.get("lowestPrice"),
        "trade_time": record.get("time"),
        "fetched_at": datetime.now(VN_TIMEZONE).strftime(
            "%d/%m/%Y %H:%M:%S UTC+7"
        ),
    }