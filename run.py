"""Điểm khởi chạy (Entry point) cho Bot Telegram Chứng khoán.

Bạn có thể chạy trực tiếp bằng lệnh:
    python run.py
hoặc trên Windows chỉ cần nhấp đúp chuột vào file:
    run.bat
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Đảm bảo đường dẫn gốc của dự án luôn nằm trong sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_prerequisites() -> bool:
    """Kiểm tra file cấu hình trước khi chạy bot."""
    env_file = ROOT / ".env"
    example_file = ROOT / ".env.example"

    if not env_file.exists():
        print("=" * 65)
        print("⚠️  LỖI: CHƯA CÓ FILE CẤU HÌNH '.env'!")
        print("=" * 65)
        if example_file.exists():
            print("👉 Vui lòng tạo file '.env' bằng cách:")
            print("   1. Sao chép file '.env.example' và đổi tên thành '.env'")
            print("   2. Mở file '.env' vừa tạo và điền:")
            print("      - TELEGRAM_BOT_TOKEN")
            print("      - DNSE_API_KEY & DNSE_API_SECRET")
            print("   3. Lưu file lại và chạy lại lệnh này.")
        else:
            print("👉 Vui lòng tạo file '.env' với nội dung:")
            print("   TELEGRAM_BOT_TOKEN=token_cua_ban")
            print("   DNSE_API_KEY=key_dnse_cua_ban")
            print("   DNSE_API_SECRET=secret_dnse_cua_ban")
        print("=" * 65)
        return False

    return True


def main() -> None:
    if not check_prerequisites():
        sys.exit(1)

    from src.module_bot.telegram_bot import main as start_bot

    start_bot()


if __name__ == "__main__":
    main()
