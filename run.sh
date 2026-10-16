#!/usr/bin/env bash
# Khởi chạy bot trên Linux / macOS / VPS
set -e

cd "$(dirname "$0")"

echo "==================================================="
echo "    Đang khởi chạy Bot Telegram Chứng Khoán..."
echo "==================================================="

if [ -f ".venv/bin/python" ]; then
    echo "[OK] Đang chạy với môi trường ảo .venv..."
    .venv/bin/python run.py
elif [ -f "venv/bin/python" ]; then
    echo "[OK] Đang chạy với môi trường ảo venv..."
    venv/bin/python run.py
elif command -v python3 &>/dev/null; then
    echo "[OK] Đang chạy với python3 hệ thống..."
    python3 run.py
else
    echo "[LỖI] Không tìm thấy Python! Vui lòng cài đặt Python 3.10+."
    exit 1
fi
