# 📈 Telegram Stock Bot - Bot Trợ Lý Phân Tích & Quản Lý Chứng Khoán Việt Nam

> **Bot Telegram thông minh hỗ trợ nhà đầu tư:** Tra cứu giá thời gian thực (DNSE), phân tích kỹ thuật (RSI, MACD, MA, Nến Nhật), đánh giá SmartScore, chiến lược lướt sóng T+ / dài hạn, lọc Top 20 cổ phiếu cơ bản tốt và quản lý danh mục vị thế ảo.
> 
> *(Lưu ý: Dự án này được xây dựng nhằm mục đích học tập và phục vụ môn học trên lớp)*.

---

## 🌟 Tính Năng Nổi Bật

- ⚡ **Dữ liệu thời gian thực (Realtime):** Kết nối trực tiếp API sàn DNSE, cập nhật giá khớp lệnh, khối lượng siêu nhanh.
- 📊 **Phân tích kỹ thuật & Biểu đồ:** Vẽ biểu đồ nến Candlestick kèm chỉ báo kỹ thuật (RSI, MACD, MA20, MA50) gửi trực tiếp qua tin nhắn ảnh Telegram.
- 🎯 **Đánh giá SmartScore:** Chấm điểm toàn diện sức mạnh cổ phiếu theo 2 trường phái:
  - **Lướt sóng ngắn hạn (T+):** Động lượng, điểm vào/cắt lỗ/chốt lời.
  - **Đầu tư dài hạn:** Kết hợp chỉ số tài chính cơ bản (ROIC, Tăng trưởng, Định giá).
- 🏆 **Top 20 Cổ phiếu dài hạn:** Tự động chọn lọc danh sách 20 cổ phiếu cơ bản và tiềm năng nhất thị trường (dựa theo chiến lược đầu tư)
- 💼 **Quản lý danh mục ảo (Paper Trading):** Lưu và theo dõi các vị thế mua ảo, tính toán lãi/lỗ thời gian thực và cảnh báo điểm chốt lời/cắt lỗ.
- ⚡ **Cơ chế Cache thông minh:** Dữ liệu nến lịch sử được lưu đệm tự động, siêu nhẹ (chỉ ~12 KB/mã), tối ưu bộ nhớ và không làm nghẽn mạng.

---

## 🚀 Hướng Dẫn Cài Đặt Dành Cho Người Mới Bắt Đầu (Từng Bước)

### Bước 1: Tải dự án và Cài đặt thư viện

1. Tải mã nguồn về máy tính (bằng cách tải file ZIP trên GitHub hoặc dùng lệnh `git clone`).
2. Mở thư mục dự án.
3. Mở **Command Prompt (cmd)** hoặc **PowerShell** tại thư mục dự án và chạy các lệnh sau:

```bash
# Tạo môi trường ảo riêng biệt
python -m venv .venv

# Kích hoạt môi trường ảo
# Trên Windows:
.venv\Scripts\activate
# Trên macOS / Linux:
source .venv/bin/activate

# Cài đặt tất cả các thư viện cần thiết
pip install -r requirements.txt
```

---

### Bước 2: Cấu hình Khóa API (Bắt buộc)

Dự án có sẵn file mẫu `.env.example`. chỉ cần:

1. **Sao chép** file `.env.example` và **đổi tên** thành `.env` (ngay tại thư mục gốc của dự án).
2. Mở file `.env` bằng Notepad hoặc bất kỳ trình soạn thảo nào và điền các thông tin sau:

```env
# 1. Token bot Telegram (Lấy từ @BotFather)
TELEGRAM_BOT_TOKEN=điền_token_telegram_của_bạn_ở_đây

# 2. Khóa API chứng khoán DNSE (Lấy từ tài khoản DNSE)
DNSE_API_KEY=điền_api_key_của_bạn_ở_đây
DNSE_API_SECRET=điền_api_secret_của_bạn_ở_đây

DEBUG=false
DNSE_PRICE_TO_VND=1000
VNSTOCK_PRICE_TO_VND=1000
```

#### 📌 Cách lấy Token Telegram:
1. Mở ứng dụng Telegram, tìm kiếm bot **`@BotFather`** (có dấu tích xanh).
2. Gõ `/newbot` và gửi.
3. Đặt tên hiển thị cho bot của bạn (ví dụ: `My Stock Bot`).
4. Đặt tên người dùng (username) kết thúc bằng chữ `bot` (ví dụ: `my_stock_assistant_bot`).
5. BotFather sẽ gửi cho bạn một chuỗi **Token HTTP API** (dạng `1234567890:ABCdefGh...`). Hãy copy chuỗi này dán vào dòng `TELEGRAM_BOT_TOKEN` trong `.env`.

#### 📌 Cách lấy API DNSE:
1. Đăng ký/Đăng nhập tài khoản tại sàn [DNSE](https://dnse.com.vn).
2. Vào phần **Cài đặt tài khoản** -> **Quản lý API** -> Tạo mới cặp **API Key** và **API Secret**.
3. Sao chép và dán vào 2 dòng `DNSE_API_KEY` và `DNSE_API_SECRET`.

---

### Bước 3: Khởi chạy Bot

#### 🟢 Cách 1: Nhấp đúp chuột (Dành cho Windows - Tiện lợi nhất)
- Trong thư mục dự án, chỉ cần **nhấp đúp chuột vào file `run.bat`**.
- Cửa sổ đen sẽ tự động nhận diện môi trường ảo và khởi động bot ngay lập tức!

#### 🟡 Cách 2: Chạy bằng dòng lệnh
Mở Terminal/PowerShell trong thư mục dự án và gõ:
```bash
python run.py
```

#### 🔵 Cách 3: Chạy trên Linux / macOS / Máy chủ VPS
```bash
bash run.sh
```

Khi Terminal hiển thị log sẵn sàng và không báo lỗi, bạn mở Telegram, tìm bot của mình và bấm **/start** để bắt đầu sử dụng! 🎉

---

## 📱 Danh Sách Các Lệnh Trực Tiếp Trên Telegram

| Lệnh | Ý nghĩa & Cách dùng |
| :--- | :--- |
| `/start` hoặc `/help` | Xem menu hướng dẫn sử dụng và bảng tra cứu |
| `/price <MÃ>` | Xem giá khớp mới nhất, biên độ, khối lượng (VD: `/price HPG`) |
| `/short <MÃ>` | Phân tích chiến lược lướt sóng ngắn hạn T+ (VD: `/short SSI`) |
| `/long <MÃ>` | Phân tích đầu tư dài hạn & sức khỏe tài chính (VD: `/long VNM`) |
| `/score <MÃ>` | Chấm điểm SmartScore và khuyến nghị hành động |
| `/chart <MÃ>` | Nhận ảnh biểu đồ nến kèm chỉ báo RSI & MACD |
| `/top20` | Xem danh sách 20 mã cổ phiếu dài hạn tốt nhất hiện tại |
| `/mode` | Đổi chế độ phân tích mặc định (Ngắn hạn hoặc Dài hạn) |
| `/track <MÃ> <GIÁ>` | Lưu mã vào danh mục theo dõi ảo (VD: `/track FPT 128.5`) |
| `/position` | Xem toàn bộ danh mục cổ phiếu đang theo dõi kèm lãi/lỗ |
| `/close <MÃ>` | Đóng vị thế và dừng theo dõi mã đó |

Có thể gõ trực tiếp tên mã (ví dụ gõ `HPG`, `FPT`) vào bot

---

## 📂 Cấu Trúc Dự Án

```text
bot_telegram/
│
├── dnse/                     # Gói thư viện kết nối DNSE API
├── src/                      # Toàn bộ mã nguồn chính của Bot
│   ├── craw_data/            # Mô-đun thu thập dữ liệu giá
│   │   ├── crawler.py        # Kết nối lấy giá khớp lệnh từ DNSE
│   │   ├── history.py        # Tải nến lịch sử & quản lý cache nến
│   │   ├── realtime.py       # Bộ nhớ đệm giá realtime và luồng dọn dẹp
│   │   └── universe.py       # Danh sách mã chứng khoán HOSE & HNX
│   │
│   └── module_bot/           # Mô-đun phân tích và xử lý Telegram Bot
│       ├── telegram_bot.py   # Bộ điều khiển chính bot Telegram & xử lý sự kiện
│       ├── analysis.py       # Tính toán kỹ thuật & vẽ biểu đồ nến mplfinance
│       ├── strategy.py       # Thuật toán chấm điểm SmartScore & khuyến nghị
│       ├── financial.py      # Phân tích sức khỏe tài chính & lọc Top 20
│       ├── position_store.py # Lưu trữ danh mục theo dõi ảo của người dùng
│       └── settings_store.py # Lưu cấu hình chế độ (Short/Long) của từng người dùng
│
├── stock_cache/              # Thư mục lưu dữ liệu đệm (Tự sinh khi chạy, nhẹ và tự dọn)
├── .env.example              # File mẫu cấu hình API 
├── requirements.txt          # Danh sách tất cả các thư viện cần cài đặt
├── run.bat                   # Click khởi chạy bot trên Windows
├── run.sh                    # Khởi chạy bot trên Linux/VPS
├── run.py                    # File điểm bắt đầu (Entry Point) của dự án
└── README.md                 # Tài liệu hướng dẫn sử dụng chi tiết 
```

---

## 🔒 Lưu Ý Về An Toàn & Bảo Mật

1. **Tuyệt đối không commit hoặc gửi file `.env` cho bất kỳ ai**, vì trong đó chứa mã khóa tài khoản DNSE và Token Telegram cá nhân của bạn. File `.gitignore` đã được cấu hình sẵn để ngăn chặn vô tình tải `.env` lên GitHub.
2. Dữ liệu trong thư mục `stock_cache/` chỉ là dữ liệu tạm thời, có thể xóa bất cứ lúc nào mà không làm ảnh hưởng đến tính toàn vẹn của mã nguồn.

---

