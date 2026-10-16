"""Kiểm tra phản hồi REST giá gần nhất của DNSE."""

import json

from .crawler import create_client


def main() -> None:
    """Lấy riêng HDB và in phản hồi, không in khóa xác thực."""
    client = create_client()

    try:
        status, body = client.get_latest_trade(
            symbol="HDB",
            board_id="G1",
            dry_run=False,
        )

        print("HTTP:", status)

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            print("Phản hồi không phải JSON hợp lệ.")
            return

        print("JSON giá HDB:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    except Exception as exc:
        print("Loại lỗi:", type(exc).__name__)
    finally:
        client._http.clear()


if __name__ == "__main__":
    main()