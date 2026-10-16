"""Giao diện Telegram: hỗ trợ 2 chế độ Ngắn hạn (Breakout T+) & Dài hạn (vnfinancialdata), SmartScore và biểu đồ."""

from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.craw_data.crawler import DNSEError
from src.craw_data.history import HistoryError
from src.craw_data.realtime import PriceCache
from src.module_bot.analysis import prepare, make_chart
from src.module_bot.position_store import PositionStore
from src.module_bot.settings_store import SettingsStore
from src.module_bot.financial import build_top20_longterm
from src.module_bot.strategy import (
    TERM_SHORT,
    TERM_LONG,
    normalize_term,
    evaluate_strategy,
    open_position,
)


ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)
LINE = "━━━━━━━━━━━━━━━━━━"
NOTICE = "⚠️ Phân tích tự động, không phải khuyến nghị đầu tư."


def keyboard(symbol: str, term: str = TERM_SHORT) -> InlineKeyboardMarkup:
    """Hiển thị nút chọn ngắn/dài hạn cùng các chức năng xem thêm."""
    norm_term = normalize_term(term)
    is_short = (norm_term == TERM_SHORT)
    short_label = "⚡ Ngắn hạn ✅" if is_short else "⚡ Ngắn hạn"
    long_label = "🏛️ Dài hạn ✅" if not is_short else "🏛️ Dài hạn"

    buttons = [
        [
            InlineKeyboardButton(short_label, callback_data=f"term:short:{symbol}"),
            InlineKeyboardButton(long_label, callback_data=f"term:long:{symbol}"),
        ],
        [
            InlineKeyboardButton("⭐ SMARTSCORE", callback_data=f"score:{symbol}:{norm_term}"),
            InlineKeyboardButton("📈 BIỂU ĐỒ", callback_data=f"chart:{symbol}:{norm_term}"),
        ],
    ]

    # Ở chế độ dài hạn bổ sung nút xem nhanh Top 20
    if not is_short:
        buttons.append([
            InlineKeyboardButton("🏆 TOP 20 DÀI HẠN", callback_data="top20"),
        ])

    buttons.append([
        InlineKeyboardButton("🔎 MÃ KHÁC", callback_data="other"),
    ])

    return InlineKeyboardMarkup(buttons)


def mode_selection_keyboard(current_mode: str = TERM_SHORT) -> InlineKeyboardMarkup:
    """Bàn phím chọn chế độ mặc định."""
    norm_mode = normalize_term(current_mode)
    is_short = (norm_mode == TERM_SHORT)
    short_label = "⚡ Ngắn hạn ✅" if is_short else "⚡ Ngắn hạn"
    long_label = "🏛️ Dài hạn ✅" if not is_short else "🏛️ Dài hạn"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(short_label, callback_data="set_mode:short"),
            InlineKeyboardButton(long_label, callback_data="set_mode:long"),
        ]
    ])


def price_text(value, source):
    """Chỉ quy đổi sang đồng khi cấu hình đã xác nhận đơn vị nguồn."""
    multiplier = os.getenv(f"{source}_PRICE_TO_VND", "").strip()
    number = Decimal(str(value))

    if multiplier:
        factor = Decimal(multiplier)
        if not factor.is_finite() or factor <= 0:
            raise ValueError("Hệ số quy đổi giá không hợp lệ.")
        return f"{number * factor:,.0f} đ"

    return f"{number:,.3f}".rstrip("0").rstrip(".")


def format_top20_message() -> str:
    """Tạo bảng xếp hạng Top 20 cổ phiếu dài hạn chất lượng nhất."""
    items = build_top20_longterm()
    lines = [
        "🏆 <b>TOP 20 CỔ PHIẾU DÀI HẠN TỐT NHẤT THỊ TRƯỜNG</b>",
        LINE,
        "<i>Đánh giá sức khỏe tài chính F-Score (vnfinancialdata) & ROE dẫn đầu:</i>\n",
    ]
    for i, it in enumerate(items, 1):
        lines.append(
            f"<b>{i:2d}. {it['ticker']}</b> — F-Score: <b>{it['f_score']}/9</b> | "
            f"ROE: <b>{it['roe']:.1%}</b> | ROA: <b>{it['roa']:.1%}</b> ({it['rating']})"
        )
    lines.extend([
        "",
        "💡 <i>Bộ lọc chọn lọc các doanh nghiệp kinh doanh tăng trưởng bền vững, "
        "đòn bẩy an toàn phục vụ chiến lược tích sản & nắm giữ dài hạn.</i>",
    ])
    return "\n".join(lines)


def brief_strategy(symbol, position=None, term=TERM_SHORT):
    """Tạo tín hiệu mở mới hoặc quản lý vị thế theo chế độ ngắn/dài hạn."""
    norm_term = normalize_term(term)
    result = evaluate_strategy(prepare(symbol), position, term=norm_term, symbol=symbol)
    state = result["state"]

    # ==========================================
    # CHẾ ĐỘ DÀI HẠN
    # ==========================================
    if norm_term == TERM_LONG:
        if position:
            pnl_pct = result.get("pnl_pct", 0.0)
            text = (
                f"🏛️ <b>TRẠNG THÁI: ĐANG NẮM GIỮ (DÀI HẠN)</b>\n\n"
                f"💰 Giá đóng cửa: {price_text(result['close'], 'VNSTOCK')}\n"
                f"📈 Hiệu suất nắm giữ: <b>{pnl_pct:+.2f}%</b>\n"
                f"🛑 Ngưỡng bảo vệ vốn (-15%): {price_text(result['stop'], 'VNSTOCK')}\n"
                f"🎯 Mục tiêu dài hạn (+30%): {price_text(result['target'], 'VNSTOCK')}\n\n"
                f"<i>Đang giám sát vị thế theo chu kỳ dài hạn.</i>"
            )
            return text, result.get("position")

        fin = result.get("fin")
        f_score_str = f"{fin['f_score']}/9 — {fin['rating']}" if fin else "Chưa có BCTC"
        roe_str = f"{fin['roe']:.1%}" if fin else "—"
        roa_str = f"{fin['roa']:.1%}" if fin else "—"
        margin_str = f"{fin['net_margin']:.1%}" if fin else "—"
        debt_str = f"{fin['debt_to_assets']:.1%}" if fin else "—"
        year_str = str(fin['year']) if fin else "2024"

        fin_block = (
            f"📊 <b>SỨC KHỎE DOANH NGHIỆP ({year_str})</b>\n{LINE}\n"
            f"• <b>Piotroski F-Score:</b> {f_score_str}\n"
            f"• <b>Hiệu quả sinh lời:</b> ROE {roe_str} | ROA {roa_str}\n"
            f"• <b>Biên lợi nhuận ròng:</b> {margin_str}\n"
            f"• <b>Đòn bẩy nợ / Tổng tài sản:</b> {debt_str}"
        )

        cond_text = "\n".join(
            f"• {'✅' if passed else '❌'} {label}"
            for label, passed in result.get("conditions", [])
        )

        return (
            f"🏛️ <b>PHÂN TÍCH ĐẦU TƯ DÀI HẠN — {symbol}</b>\n\n"
            f"{fin_block}\n\n"
            f"📈 <b>TIÊU CHÍ KỸ THUẬT & CƠ BẢN</b>\n{LINE}\n{cond_text}\n\n"
            f"📝 <b>NHẬN ĐỊNH</b>\n{html.escape(result.get('comment', ''))}\n\n"
            f"📌 <b>KẾ HOẠCH DÀI HẠN</b>\n{LINE}\n{html.escape(result.get('plan', ''))}\n\n"
            f"<i>Dữ liệu BCTC {year_str}. Nguồn: vnfinancialdata.</i>"
        ), None

    # ==========================================
    # CHẾ ĐỘ NGẮN HẠN (LƯỚT SÓNG T+)
    # ==========================================
    if position:
        labels = {
            "HOLD": "🟡 TRẠNG THÁI: TIẾP TỤC NẮM GIỮ (T+)",
            "EXIT_STOP": "🔴 BÁO BÁN: CHẠM KỶ LUẬT CẮT LỖ -7%",
            "EXIT_MA20": "🔴 BÁO BÁN: GÃY HỖ TRỢ ĐỘNG MA20",
            "EXIT_RSI_DISTRIBUTION": "🔴 BÁO BÁN: RSI CÓ DẤU HIỆU PHÂN PHỐI",
            "EXIT_TARGET": "🟢 BÁO BÁN: ĐẠT MỤC TIÊU CHỐT LỜI R:R 1:2",
        }
        reason = "\n".join(f"• {item}" for item in result.get("reasons", []))
        text = (
            f"{labels.get(result['state'], '🟡 TRẠNG THÁI: ĐANG THEO DÕI')}\n\n"
            f"💰 Giá đóng cửa: {price_text(result['close'], 'VNSTOCK')}\n"
            f"🛑 Ngưỡng Stop-loss (-7%): {price_text(result['stop'], 'VNSTOCK')}\n"
            f"📉 Hỗ trợ động MA20: {price_text(result['sma20'], 'VNSTOCK')}\n"
            f"🎯 Mục tiêu 1 (R:R 1:1.5): {price_text(result['target_1'], 'VNSTOCK')}\n"
            f"🎯 Mục tiêu 2 (R:R 1:2.0): {price_text(result['target'], 'VNSTOCK')}"
        )
        if reason:
            text += f"\n\n{html.escape(reason)}"
        return text, result.get("position")

    if state == "BUY":
        signal = "🟢 TÍN HIỆU: MUA LƯỚT SÓNG (T+)"
        comment = (
            f"Hội tụ đủ 4 yếu tố bùng nổ theo dòng tiền lớn: Xu hướng tăng trên MA20 & MA50, "
            f"khối lượng vượt trội ({result['vol_ratio']:.2f}x TB20), giá tăng dứt khoát "
            f"{result['price_change_pct']:+.2%} và RSI nằm trong vùng lý tưởng 50–65."
        )
    elif state == "READY":
        signal = "🟠 TÍN HIỆU: RADAR THEO DÕI (SẮP ĐẠT ĐIỀU KIỆN)"
        comment = (
            "Cổ phiếu giữ cấu trúc xu hướng tăng tốt và động lượng tích cực. "
            "Chờ dòng tiền bùng nổ (Vol ≥ 1.5x) hoặc phiên tăng dứt khoát ≥ 2% để kích hoạt điểm mua."
        )
    elif state == "AVOID_LIQUIDITY":
        signal = "⚪ TÍN HIỆU: LOẠI BỎ (THIẾU THANH KHOẢN)"
        comment = (
            f"Thanh khoản trung bình 20 phiên chỉ đạt {result['vol20']:,.0f} cp, "
            "chưa đạt ngưỡng tối thiểu 200.000 cp/phiên để giao dịch lướt sóng an toàn."
        )
    elif state == "AVOID_FUNDAMENTAL":
        signal = "⚪ TÍN HIỆU: LOẠI BỎ (ĐẦU CƠ KÉM CHẤT LƯỢNG)"
        comment = (
            f"Sức khỏe tài chính F-Score chỉ đạt {result.get('f_score')}/9 (< 5 điểm). "
            "Hệ thống tự động loại bỏ để bảo vệ an toàn nguồn vốn."
        )
    elif state == "AVOID_TREND":
        signal = "⚪ TÍN HIỆU: TRÁNH MUA (DƯỚI XU HƯỚNG TĂNG)"
        comment = "Đường giá đang dưới MA20 hoặc MA50, chưa xác nhận xu hướng tăng ngắn hạn."
    else:
        signal = "🟡 TÍN HIỆU: CHỜ DÒNG TIỀN / THEO DÕI"
        comment = "Chưa đủ điều kiện kích hoạt lệnh mua theo chiến lược lướt sóng ngắn hạn."

    cond_lines = "\n".join(
        f"• {'✅' if passed else '❌'} {label}"
        for label, passed in result.get("conditions", [])
    )
    safety_lines = "\n".join(
        f"• {'✅' if passed else '❌'} {label}"
        for label, passed in result.get("safety_filters", [])
    )

    plan = (
        f"• Điểm vào lệnh (Entry): {price_text(result['entry_price'], 'VNSTOCK')}\n"
        f"• Mua đuổi tối đa (+1%): {price_text(result['max_entry'], 'VNSTOCK')}\n"
        f"• Cắt lỗ kỷ luật (-7% hoặc gãy MA20): {price_text(result['stop_loss'], 'VNSTOCK')}\n"
        f"• Chốt lời Target 1 (R:R 1:1.5): {price_text(result['target_1'], 'VNSTOCK')} (+10.5%)\n"
        f"• Chốt lời Target 2 (R:R 1:2.0): {price_text(result['target_2'], 'VNSTOCK')} (+14.0%)"
    )

    return (
        f"{signal}\n\n"
        f"📝 <b>NHẬN ĐỊNH RADAR</b>\n{html.escape(comment)}\n\n"
        f"🎯 <b>4 YẾU TỐ KỸ THUẬT</b>\n{LINE}\n{cond_lines}\n\n"
        f"🛡️ <b>BỘ LỌC AN TOÀN TĨNH</b>\n{LINE}\n{safety_lines}\n\n"
        f"📌 <b>KẾ HOẠCH MỞ LỆNH</b>\n{LINE}\n{html.escape(plan)}\n\n"
        f"<i>Phiên {result['date']}. Chiến lược: Lướt sóng T+ (Trend & Breakout).</i>"
    ), None


def compact_score(symbol):
    """Tính SmartScore độc lập, chỉ khi người dùng yêu cầu xem điểm."""
    df = prepare(symbol)
    row, previous = df.iloc[-1], df.iloc[-2]

    above20 = row.Close > row.SMA20
    above50 = row.SMA20 > row.SMA50
    rising = row.SMA50 > df.iloc[-6].SMA50
    macd_up = row.MACD > row.Signal

    details = [
        ("Giá trên SMA20" if above20 else "Giá không trên SMA20",
         12 if above20 else -12),
        ("SMA20 trên SMA50" if above50 else "SMA20 không trên SMA50",
         12 if above50 else -12),
        ("SMA50 tăng" if rising else "SMA50 không tăng",
         8 if rising else -8),
        ("MACD trên Signal" if macd_up else "MACD không trên Signal",
         10 if macd_up else -10),
    ]

    rsi_points = (
        8 if 50 <= row.RSI < 70
        else -8 if row.RSI < 40
        else -4 if row.RSI >= 70
        else 0
    )
    details.append((f"RSI {row.RSI:.1f}", rsi_points))

    ratio = row.Volume / row.VolumeBase if row.VolumeBase > 0 else None
    volume_points = 0

    if ratio is not None and ratio >= 1.2:
        volume_points = (
            10 if row.Close > previous.Close
            else -10 if row.Close < previous.Close
            else 0
        )

    details.append((
        f"Khối lượng {ratio:.2f} lần TB20" if ratio is not None
        else "Chưa đủ dữ liệu khối lượng",
        volume_points,
    ))

    score = max(0, min(100, 50 + sum(point for _, point in details)))
    explanation = "\n".join(
        f"• {label}: {point:+d}" for label, point in details
    )

    return (
        f"⭐ <b>SMARTSCORE — {symbol}</b>\n{LINE}\n\n"
        f"🏆 <b>Tổng điểm: {score}/100</b>\n\n"
        f"Điểm nền: 50\n{html.escape(explanation)}\n\n"
        f"<i>Phiên {row.Date:%d/%m/%Y}. "
        "Điểm được giới hạn trong 0–100; "
        "không thay thế tín hiệu chiến lược.</i>"
    )


def chart_image(symbol):
    """Đọc lịch sử và tạo ảnh khi người dùng bấm biểu đồ (giữ nguyên không đổi)."""
    return make_chart(symbol, prepare(symbol))


async def calculate(context, function, *args):
    """Chạy tính toán ngoài vòng lặp Telegram, tối đa hai tác vụ."""
    async with context.application.bot_data["analysis_gate"]:
        return await asyncio.to_thread(function, *args)


async def deliver(message, context, symbol, action="price", term=None, edit_query=None):
    """Gửi hoặc cập nhật nội dung được chọn, hỗ trợ chuyển đổi giữa Ngắn hạn & Dài hạn."""
    symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol):
        if edit_query:
            await edit_query.answer("Mã cổ phiếu không hợp lệ.")
        elif message:
            await message.reply_text("Nhập mã cổ phiếu, ví dụ FPT.")
        return

    user_id = 0
    if edit_query and edit_query.from_user:
        user_id = edit_query.from_user.id
    elif message and message.from_user:
        user_id = message.from_user.id

    settings = context.application.bot_data.get("settings")
    if term is None:
        if settings and user_id:
            term = await settings.get_mode(user_id)
        else:
            term = TERM_SHORT
    else:
        term = normalize_term(term)

    try:
        if action == "score":
            text = await calculate(context, compact_score, symbol)
            if edit_query and edit_query.message and not edit_query.message.photo:
                with suppress(TelegramError):
                    await edit_query.edit_message_text(
                        text,
                        parse_mode="HTML",
                        reply_markup=keyboard(symbol, term=term),
                    )
                    return
            target_msg = edit_query.message if edit_query else message
            if target_msg:
                await target_msg.reply_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=keyboard(symbol, term=term),
                )
            return

        elif action == "chart":
            image = await calculate(context, chart_image, symbol)
            target_msg = edit_query.message if edit_query else message
            if target_msg:
                with BytesIO(image) as photo:
                    photo.name = f"{symbol}.png"
                    await target_msg.reply_photo(
                        photo=photo,
                        caption=f"📈 {symbol} — Biểu đồ nến ngày, không gồm hôm nay.",
                        reply_markup=keyboard(symbol, term=term),
                    )
            return

        else:
            try:
                quote, _ = await context.application.bot_data["prices"].get(symbol)
                latest = price_text(quote["price"], "DNSE")
                trade_time = html.escape(str(
                    quote.get("trade_time") or "Chưa rõ thời điểm"
                ))
                price_block = (
                    f"💰 <b>Giá khớp gần nhất: {latest}</b>\n"
                    f"<i>{trade_time}</i>"
                )
            except DNSEError:
                price_block = "💰 Giá khớp gần nhất: Tạm chưa có"

            try:
                store = context.application.bot_data["positions"]
                position = await store.get(user_id, symbol)
                strategy, updated = await calculate(
                    context, brief_strategy, symbol, position, term
                )
                if updated:
                    if updated["status"] == "OPEN":
                        await store.save(user_id, updated)
                    else:
                        await store.remove(user_id, symbol)
                        strategy += "\n\n<i>Đã kết thúc theo dõi vị thế này.</i>"
            except HistoryError:
                strategy = (
                    "⚪ TÍN HIỆU: CHƯA ĐÁNH GIÁ\n\n"
                    "Chưa có đủ lịch sử hợp lệ để phân tích. "
                    "Vui lòng thử lại sau."
                )

            term_tag = "⚡ NGẮN HẠN (T+)" if term == TERM_SHORT else "🏛️ DÀI HẠN"
            text = (
                f"📊 <b>PHÂN TÍCH — {symbol} [{term_tag}]</b>\n{LINE}\n\n"
                f"{price_block}\n\n{strategy}\n\n{NOTICE}"
            )

            if edit_query and edit_query.message and not edit_query.message.photo:
                try:
                    await edit_query.edit_message_text(
                        text,
                        parse_mode="HTML",
                        reply_markup=keyboard(symbol, term=term),
                    )
                    return
                except TelegramError as err:
                    if "Message is not modified" in str(err):
                        return

            target_msg = edit_query.message if edit_query else message
            if target_msg:
                await target_msg.reply_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=keyboard(symbol, term=term),
                )

    except HistoryError:
        target_msg = edit_query.message if edit_query else message
        if target_msg:
            await target_msg.reply_text(
                f"Chưa có đủ dữ liệu để xử lý {symbol}. Vui lòng thử lại sau."
            )
    except TelegramError:
        raise
    except Exception as exc:
        import traceback

        LOGGER.error("Xử lý %s: %s", symbol, type(exc).__name__)
        for frame in traceback.extract_tb(exc.__traceback__):
            LOGGER.error("%s:%s — %s", frame.filename, frame.lineno, frame.name)

        target_msg = edit_query.message if edit_query else message
        if target_msg:
            await target_msg.reply_text("Chưa xử lý được yêu cầu. Vui lòng thử lại sau.")


async def mode_command(update, context):
    """Cài đặt hoặc kiểm tra chế độ phân tích mặc định (ngắn hạn / dài hạn)."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    settings = context.application.bot_data["settings"]
    current_mode = await settings.get_mode(user.id)

    if context.args:
        arg = context.args[0].strip().lower()
        new_mode = normalize_term(arg)
        await settings.set_mode(user.id, new_mode)
        mode_label = "⚡ Ngắn hạn (Lướt sóng T+)" if new_mode == TERM_SHORT else "🏛️ Dài hạn (Tích sản & Nắm giữ)"
        await message.reply_text(
            f"✅ Đã đổi chế độ phân tích mặc định sang: <b>{mode_label}</b>.",
            parse_mode="HTML",
            reply_markup=mode_selection_keyboard(new_mode),
        )
        return

    mode_label = "⚡ Ngắn hạn" if current_mode == TERM_SHORT else "🏛️ Dài hạn"
    await message.reply_text(
        f"⚙️ <b>CÀI ĐẶT CHẾ ĐỘ PHÂN TÍCH</b>\n{LINE}\n\n"
        f"Chế độ hiện tại: <b>{mode_label}</b>\n\n"
        f"• <b>Ngắn hạn (T+)</b>: Dòng tiền bùng nổ, Breakout Vol ≥ 1.5x, Tăng ≥ 2%, "
        f"lọc thanh khoản ≥ 200k cp & F-Score ≥ 5. Cắt lỗ 7% hoặc gãy MA20, chốt lời 1:1.5 và 1:2.\n\n"
        f"• <b>Dài hạn</b>: Đánh giá sức khỏe tài chính F-Score (vnfinancialdata), ROE, ROA, "
        f"xu hướng SMA50 và danh mục Top 20 cổ phiếu tốt nhất.\n\n"
        f"<i>Bấm nút bên dưới để đổi chế độ mặc định:</i>",
        parse_mode="HTML",
        reply_markup=mode_selection_keyboard(current_mode),
    )


async def top20_command(update, context):
    """Gửi danh sách Top 20 cổ phiếu dài hạn tốt nhất."""
    message = update.effective_message
    if message:
        text = await calculate(context, format_top20_message)
        await message.reply_text(text, parse_mode="HTML")


async def help_command(update, context):
    """Hướng dẫn sử dụng bot với hai tùy chọn ngắn hạn và dài hạn."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "📊 <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Gửi trực tiếp mã cổ phiếu, ví dụ: <code>FPT</code>, <code>HPG</code>, <code>VCB</code>.\n\n"
            "⚙️ <b>2 TÙY CHỌN CHIẾN LƯỢC:</b>\n"
            "1️⃣ <b>Ngắn hạn (T+)</b>: Lướt sóng bám dòng tiền lớn (Volume Breakout & Trend Following).\n"
            "   • Lọc thanh khoản ≥ 200k cp, F-Score ≥ 5.\n"
            "   • Mua khi giá > MA20 & MA50, Vol ≥ 1.5x, tăng ≥ 2%, RSI 50–65.\n"
            "   • Cắt lỗ kỷ luật 7% hoặc gãy MA20, chốt lời R:R 1:1.5 (+10.5%) và 1:2 (+14%).\n\n"
            "2️⃣ <b>Dài hạn</b>: Đầu tư giá trị & tích sản doanh nghiệp đầu ngành.\n"
            "   • Đánh giá F-Score & BCTC từ vnfinancialdata.\n"
            "   • Bộ lọc Top 20 cổ phiếu tài chính khỏe nhất thị trường (/top20).\n\n"
            "📌 <b>CÁC LỆNH ĐIỀU KHIỂN:</b>\n"
            "/mode — Cài đặt chế độ mặc định (Ngắn/Dài hạn)\n"
            "/top20 — Xem Top 20 cổ phiếu dài hạn tốt nhất\n"
            "/price FPT — Giá & phân tích theo chế độ hiện tại\n"
            "/short FPT — Phân tích Ngắn hạn (T+)\n"
            "/long FPT — Phân tích Dài hạn\n"
            "/score FPT — Xem điểm kỹ thuật SmartScore\n"
            "/chart FPT — Xem biểu đồ nến kỹ thuật\n"
            "/track FPT 65.1 — Lưu vị thế theo dõi\n"
            "/position — Danh sách vị thế đang theo dõi\n"
            "/close FPT — Dừng theo dõi vị thế",
            parse_mode="HTML",
        )


async def track_command(update, context):
    """Lưu vị thế ảo từ giá khớp do người dùng nhập."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if len(context.args) < 2:
        await message.reply_text("Nhập theo mẫu: /track FPT 65.1")
        return

    symbol = context.args[0].strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol):
        await message.reply_text("Mã cổ phiếu không hợp lệ.")
        return
    try:
        entry_price = float(context.args[1].replace(",", "."))
        settings = context.application.bot_data.get("settings")
        user_mode = await settings.get_mode(user.id) if settings else TERM_SHORT
        term = normalize_term(context.args[2]) if len(context.args) > 2 else user_mode

        df = await calculate(context, prepare, symbol)
        row = df.iloc[-1]
        position = open_position(
            symbol=symbol,
            entry_price=entry_price,
            atr_at_entry=float(row["ATR"]),
            entry_date=datetime.now().astimezone().strftime("%d/%m/%Y"),
            term=term,
        )
        await context.application.bot_data["positions"].save(user.id, position)
        term_label = "Ngắn hạn" if term == TERM_SHORT else "Dài hạn"
        await message.reply_text(
            f"✅ Đã theo dõi {symbol} ({term_label})\n"
            f"Giá mua: {price_text(position['entry_price'], 'VNSTOCK')}\n"
            f"Stop-loss: {price_text(position['current_stop'], 'VNSTOCK')}\n"
            f"Mục tiêu 1: {price_text(position['target_1'], 'VNSTOCK')}\n"
            f"Mục tiêu 2: {price_text(position['target'], 'VNSTOCK')}",
            reply_markup=keyboard(symbol, term=term),
        )
    except (ValueError, HistoryError):
        await message.reply_text("Không lưu được vị thế. Kiểm tra mã và giá mua.")


async def position_command(update, context):
    """Liệt kê vị thế ảo hoặc đánh giá một mã cụ thể."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    store = context.application.bot_data["positions"]
    if context.args:
        symbol = context.args[0].strip().upper()
        if await store.get(user.id, symbol) is None:
            await message.reply_text(f"Chưa theo dõi vị thế {symbol}.")
            return
        await deliver(message, context, symbol)
        return

    positions = await store.list_open(user.id)
    if not positions:
        await message.reply_text("Chưa có vị thế nào đang theo dõi.")
        return
    lines = ["📌 VỊ THẾ ĐANG THEO DÕI"]
    for item in sorted(positions, key=lambda value: value["symbol"]):
        item_term = item.get("term", TERM_SHORT)
        term_tag = "⚡" if item_term == TERM_SHORT else "🏛️"
        lines.append(
            f"• {term_tag} {item['symbol']}: mua "
            f"{price_text(item['entry_price'], 'VNSTOCK')} | stop "
            f"{price_text(item['current_stop'], 'VNSTOCK')}"
        )
    await message.reply_text("\n".join(lines))


async def close_command(update, context):
    """Dừng theo dõi một vị thế ảo."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if len(context.args) != 1:
        await message.reply_text("Nhập theo mẫu: /close FPT")
        return
    symbol = context.args[0].strip().upper()
    removed = await context.application.bot_data["positions"].remove(
        user.id, symbol
    )
    await message.reply_text(
        f"Đã dừng theo dõi {symbol}."
        if removed else f"Không có vị thế {symbol} đang theo dõi."
    )


async def command(update, context):
    """Nhận các lệnh: /price, /score, /chart, /short, /long."""
    message = update.effective_message
    if message is None:
        return

    cmd = message.text.split()[0].split("@")[0][1:].lower()
    if not context.args:
        await message.reply_text(f"Nhập theo mẫu: /{cmd} FPT")
        return

    symbol = context.args[0]
    term = None

    if cmd == "short":
        action = "price"
        term = TERM_SHORT
    elif cmd == "long":
        action = "price"
        term = TERM_LONG
    else:
        action = cmd
        if len(context.args) > 1:
            term = normalize_term(context.args[1])

    await deliver(message, context, symbol, action=action, term=term)


async def text_message(update, context):
    """Cho phép nhập trực tiếp mã, ví dụ 'FPT' hoặc 'FPT long'."""
    message = update.effective_message
    if not message or not message.text:
        return

    parts = message.text.strip().split()
    symbol = parts[0]
    term = normalize_term(parts[1]) if len(parts) > 1 else None
    await deliver(message, context, symbol, term=term)


async def button_callback(update, context):
    """Xử lý các nút bấm: đổi chế độ ngắn/dài hạn, top20, smartscore, biểu đồ."""
    query = update.callback_query
    if query is None:
        return

    data = query.data if isinstance(query.data, str) else ""

    if data == "other":
        await query.answer()
        if query.message:
            await query.message.reply_text("🔎 Nhập mã cổ phiếu bạn muốn xem (ví dụ: FPT, HPG, VCB).")
        return

    if data == "top20":
        await query.answer("Đang tải danh sách Top 20...")
        text = await calculate(context, format_top20_message)
        if query.message:
            await query.message.reply_text(text, parse_mode="HTML")
        return

    # Chọn chế độ mặc định từ /mode
    if data.startswith("set_mode:"):
        await query.answer()
        _, _, new_mode = data.partition(":")
        new_mode = normalize_term(new_mode)
        user_id = query.from_user.id if query.from_user else 0
        settings = context.application.bot_data["settings"]
        await settings.set_mode(user_id, new_mode)
        mode_label = "⚡ Ngắn hạn (Lướt sóng T+)" if new_mode == TERM_SHORT else "🏛️ Dài hạn (Tích sản & Nắm giữ)"
        with suppress(TelegramError):
            await query.edit_message_text(
                f"✅ Đã lưu chế độ mặc định của bạn: <b>{mode_label}</b>.\n\n"
                f"Từ bây giờ khi bạn gửi mã cổ phiếu, bot sẽ tự động phân tích theo chế độ này.",
                parse_mode="HTML",
                reply_markup=mode_selection_keyboard(new_mode),
            )
        return

    # Chuyển đổi giữa 2 option trên thẻ cổ phiếu: term:short:FPT hoặc term:long:FPT
    if data.startswith("term:"):
        parts = data.split(":")
        if len(parts) >= 3:
            target_term = normalize_term(parts[1])
            symbol = parts[2].strip().upper()
            label = "⚡ Ngắn hạn" if target_term == TERM_SHORT else "🏛️ Dài hạn"
            await query.answer(f"Chế độ: {label}")
            await deliver(
                query.message,
                context,
                symbol,
                action="price",
                term=target_term,
                edit_query=query,
            )
            return

    # Xử lý các nút score hoặc chart
    parts = data.split(":")
    action = parts[0]
    symbol = parts[1].strip().upper() if len(parts) > 1 else ""
    term = parts[2] if len(parts) > 2 else TERM_SHORT

    if action not in ("score", "chart"):
        await query.answer()
        if query.message:
            await query.message.reply_text("Hãy nhập lại mã cổ phiếu.")
        return

    await query.answer()
    await deliver(
        query.message,
        context,
        symbol,
        action=action,
        term=term,
        edit_query=query if action != "chart" else None,
    )


async def on_start(application):
    """Tạo cache và menu; không tải dữ liệu khi khởi động."""
    cache = PriceCache(ttl=15, max_entries=256)
    application.bot_data["prices"] = cache
    application.bot_data["sweeper"] = asyncio.create_task(cache.sweep())
    application.bot_data["analysis_gate"] = asyncio.Semaphore(2)
    application.bot_data["positions"] = PositionStore(
        ROOT / "stock_cache" / "positions.json"
    )
    application.bot_data["settings"] = SettingsStore(
        ROOT / "stock_cache" / "user_settings.json"
    )

    with suppress(TelegramError):
        await application.bot.set_my_commands([
            BotCommand("mode", "Đổi chế độ ngắn/dài hạn"),
            BotCommand("top20", "Top 20 cổ phiếu dài hạn tốt nhất"),
            BotCommand("price", "Giá và phân tích"),
            BotCommand("short", "Phân tích lướt sóng T+"),
            BotCommand("long", "Phân tích đầu tư dài hạn"),
            BotCommand("score", "SmartScore"),
            BotCommand("chart", "Biểu đồ nến"),
            BotCommand("track", "Lưu vị thế ảo"),
            BotCommand("position", "Vị thế đang theo dõi"),
            BotCommand("close", "Dừng theo dõi"),
            BotCommand("help", "Hướng dẫn sử dụng"),
        ])


async def on_stop(application):
    """Dừng tác vụ nền và giải phóng cache."""
    task = application.bot_data.get("sweeper")
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    cache = application.bot_data.get("prices")
    if cache:
        await cache.close()


async def on_error(update: object, context):
    """Ghi lỗi kỹ thuật và trả thông báo ngắn."""
    LOGGER.error("Lỗi bot: %s", type(context.error).__name__)
    if isinstance(update, Update) and update.effective_message:
        with suppress(TelegramError):
            await update.effective_message.reply_text(
                "Kết nối đang gặp sự cố. Vui lòng thử lại."
            )


def main():
    """Khởi chạy bot bằng môi trường và cấu hình hiện tại."""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Thiếu TELEGRAM_BOT_TOKEN.")
        return

    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(8)
        .post_init(on_start)
        .post_stop(on_stop)
        .build()
    )
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler(["mode", "chedo", "option"], mode_command))
    app.add_handler(CommandHandler("top20", top20_command))
    app.add_handler(CommandHandler(["price", "score", "chart", "short", "long"], command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("position", position_command))
    app.add_handler(CommandHandler("close", close_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.COMMAND, help_command))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, text_message
    ))
    app.add_error_handler(on_error)

    try:
        app.run_polling(allowed_updates=["message", "callback_query"])
    except TelegramError as exc:
        print(f"Không chạy được Telegram: {type(exc).__name__}")


if __name__ == "__main__":
    main()
