"""Lấy danh sách cổ phiếu HOSE và HNX từ danh mục DNSE."""

import json
import time

import urllib3

from .crawler import DNSEError, create_client


MARKETS = {
    "STO": "HOSE",
    "STX": "HNX",
}

PAGE_SIZE = 100


def fetch_stock_universe() -> list[dict]:
    """Đọc đủ các trang danh mục và lọc cổ phiếu HOSE/HNX.

    Lấy danh mục đầy đủ rồi lọc tại chương trình để kiểm tra rõ
    số bản ghi và tránh phụ thuộc vào cách kết hợp bộ lọc của API.

    Nếu phân trang lỗi hoặc danh mục thay đổi giữa lúc tải,
    hàm báo lỗi thay vì trả về một danh sách thiếu.
    """
    client = create_client()
    stocks = {}
    seen_records = set()
    expected_total = None
    received = 0
    page = 1

    try:
        while True:
            try:
                status, body = client.get_instruments(
                    limit=PAGE_SIZE,
                    page=page,
                    dry_run=False,
                )
            except (urllib3.exceptions.HTTPError, OSError):
                raise DNSEError(
                    f"Mất kết nối DNSE khi tải trang {page}. "
                    "Hãy chạy lại."
                ) from None
            except UnicodeError:
                raise DNSEError(
                    f"Không đọc được phản hồi trang {page}."
                ) from None

            if status in (401, 403):
                raise DNSEError(
                    "DNSE từ chối xác thực hoặc quyền truy cập danh mục."
                )

            if status == 429:
                raise DNSEError(
                    "Đã vượt giới hạn gọi API. Hãy chờ rồi chạy lại."
                )

            if status != 200:
                raise DNSEError(
                    f"Lấy trang {page} thất bại: HTTP {status}."
                )

            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                raise DNSEError(
                    f"Trang {page} không phải JSON hợp lệ."
                ) from None

            if not isinstance(payload, dict):
                raise DNSEError("Phản hồi danh mục không đúng cấu trúc.")

            records = payload.get("data")
            total = payload.get("total")
            response_page = payload.get("page")
            page_size = payload.get("pageSize")

            if (
                not isinstance(records, list)
                or type(total) is not int
                or total < 0
                or type(page_size) is not int
                or page_size <= 0
                or response_page != page
            ):
                raise DNSEError(
                    f"Thông tin phân trang không hợp lệ ở trang {page}."
                )

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise DNSEError(
                    "Danh mục DNSE thay đổi trong lúc tải. "
                    "Hãy chạy lại để lấy danh sách nhất quán."
                )

            if len(records) > page_size:
                raise DNSEError("Số bản ghi vượt quá kích thước trang.")

            if not records and received < expected_total:
                raise DNSEError(
                    "DNSE trả trang rỗng trước khi tải đủ danh mục."
                )

            for record in records:
                if not isinstance(record, dict):
                    raise DNSEError("Bản ghi chứng khoán không hợp lệ.")

                symbol = record.get("symbol")
                market = record.get("marketId")
                group = record.get("securityGroupId")

                if not isinstance(symbol, str) or not symbol.strip():
                    raise DNSEError("Có bản ghi thiếu mã chứng khoán.")

                if not isinstance(market, str):
                    raise DNSEError(f"Mã {symbol} thiếu thông tin sàn.")

                symbol = symbol.strip().upper()

                # Phát hiện trang lặp hoặc bản ghi trùng.
                record_key = (market, symbol)
                if record_key in seen_records:
                    # Danh mục có thể chứa bản ghi trùng.
                    # Chỉ giữ lần xuất hiện đầu tiên của cùng mã trên cùng sàn.
                    continue

                seen_records.add(record_key)

                if market not in MARKETS:
                    continue

                if not isinstance(group, str):
                    raise DNSEError(
                        f"Mã {symbol} thiếu loại chứng khoán, "
                        "chưa thể lọc chính xác."
                    )

                if group != "ST":
                    continue

                if symbol in stocks:
                    raise DNSEError(
                        f"Mã {symbol} xuất hiện trên nhiều sàn. "
                        "Cần kiểm tra lại danh mục."
                    )

                stocks[symbol] = {
                    "symbol": symbol,
                    "exchange": MARKETS[market],
                    "marketId": market,
                    "name": record.get("name") or "",
                }

            received += len(records)

            print(
                f"Trang {page}: đã đọc {received}/{expected_total} "
                "bản ghi danh mục."
            )

            if received == expected_total:
                break

            if received > expected_total:
                raise DNSEError("Số bản ghi đã đọc vượt tổng DNSE công bố.")

            if len(records) < page_size:
                raise DNSEError(
                    "Trang chưa đầy nhưng tổng bản ghi chưa đủ. "
                    "Cần kiểm tra lại phân trang DNSE."
                )

            page += 1

            # Giãn các yêu cầu; đây không phải giới hạn chính thức của DNSE.
            time.sleep(0.3)

    finally:
        client._http.clear()

    if not stocks:
        raise DNSEError("Không tìm thấy cổ phiếu HOSE/HNX trong danh mục.")

    return sorted(stocks.values(), key=lambda item: item["symbol"])


def get_all_symbols() -> list[str]:
    """Trả danh sách mã để truyền sang bộ nhận realtime."""
    stocks = fetch_stock_universe()

    for exchange in MARKETS.values():
        count = sum(item["exchange"] == exchange for item in stocks)
        print(f"{exchange}: {count} cổ phiếu")

    print(f"Tổng cộng: {len(stocks)} cổ phiếu")
    return [item["symbol"] for item in stocks]


def main() -> None:
    """Kiểm tra tải đầy đủ danh sách cổ phiếu của hai sàn."""
    try:
        symbols = get_all_symbols()
        print("\nDanh sách mã:")
        print(", ".join(symbols))
    except DNSEError as exc:
        print(f"Lỗi: {exc}")


if __name__ == "__main__":
    main()