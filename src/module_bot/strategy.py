"""Chiến lược đầu tư: Ngắn hạn (Breakout T+, F-Score, MA20/MA50) và Dài hạn (vnfinancialdata)."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.craw_data.history import HistoryError, normalize_symbol
from src.module_bot.analysis import prepare
from src.module_bot.financial import get_financial_health, build_top20_longterm


TERM_SHORT = "short"
TERM_LONG = "long"

# Quy tắc chiến lược Ngắn hạn (T+)
MIN_SESSIONS = 60
LOOKBACK_VOL_DAYS = 20
MIN_AVG_VOLUME = 200_000   # Thanh khoản tối thiểu 200.000 cp/phiên
MIN_F_SCORE = 5            # Loại bỏ hàng đầu cơ kém chất lượng F-Score < 5
VOL_BREAKOUT_RATIO = 1.5   # Khối lượng gấp 1.5 lần TB20
PRICE_GAIN_MIN = 0.02      # Giá tăng dứt khoát trên 2% (+2.0%)
RSI_MIN = 50.0             # RSI tối thiểu 50
RSI_MAX = 65.0             # RSI tối đa 65 (chưa quá mua)
MAX_CHASE_PCT = 0.01       # Mua đuổi tối đa 1%
STOP_LOSS_PCT = 0.07       # Cắt lỗ kỷ luật tuyệt đối 7%
RR_TARGET_1 = 1.5          # Risk:Reward 1:1.5 (+10.5%)
RR_TARGET_2 = 2.0          # Risk:Reward 1:2.0 (+14.0%)


def normalize_term(term: str | None) -> str:
    """Chuẩn hóa tên chế độ về 'short' hoặc 'long'."""
    if not term:
        return TERM_SHORT
    val = str(term).strip().lower()
    if val in ("long", "daihan", "dài hạn", "dai_han", "2"):
        return TERM_LONG
    return TERM_SHORT


# =====================================================================
# 1. CHIẾN LƯỢC LƯỚT SÓNG NGẮN HẠN (T+)
# =====================================================================

def evaluate_entry_short(df, symbol: str) -> dict[str, Any]:
    """Đánh giá tín hiệu Mua ngắn hạn theo bộ lọc an toàn và 4 yếu tố kỹ thuật."""
    if len(df) < MIN_SESSIONS:
        raise HistoryError(f"Cần ít nhất {MIN_SESSIONS} phiên để phân tích kỹ thuật.")

    row = df.iloc[-1]
    prev_row = df.iloc[-2]

    close = float(row["Close"])
    prev_close = float(prev_row["Close"])
    volume = float(row["Volume"])
    sma20 = float(row["SMA20"])
    sma50 = float(row["SMA50"])
    rsi = float(row["RSI"])

    # 1. BỘ LỌC TĨNH AN TOÀN
    # 1.1. Thanh khoản trung bình 20 phiên
    vol20 = float(df["Volume"].iloc[-LOOKBACK_VOL_DAYS - 1:-1].mean())
    liquidity_ok = bool(vol20 >= MIN_AVG_VOLUME)

    # 1.2. Sức khỏe cơ bản (Piotroski F-Score từ vnfinancialdata)
    fin_health = get_financial_health(symbol)
    f_score = fin_health.get("f_score") if fin_health else None
    fundamental_ok = bool(f_score is None or f_score >= MIN_F_SCORE)

    # 2. BỐN YẾU TỐ KỸ THUẬT QUÉT TÍN HIỆU MUA
    # Yếu tố 1: Xu hướng tăng (Giá vượt MA20 và MA50)
    factor_trend = bool(close > sma20 and close > sma50)

    # Yếu tố 2: Dòng tiền lớn xác nhận (Khối lượng gấp 1.5 lần TB20)
    vol_ratio = (volume / vol20) if vol20 > 0 else 0.0
    factor_volume = bool(volume >= VOL_BREAKOUT_RATIO * vol20)

    # Yếu tố 3: Giá tăng dứt khoát trên 2%
    price_change_pct = (close - prev_close) / prev_close if prev_close > 0 else 0.0
    factor_price_gain = bool(price_change_pct >= PRICE_GAIN_MIN)

    # Yếu tố 4: Động lượng RSI trong vùng 50 - 65
    factor_rsi = bool(RSI_MIN <= rsi <= RSI_MAX)

    conditions = [
        (f"Xu hướng tăng (Giá > MA20 & MA50)", factor_trend),
        (f"Dòng tiền xác nhận: Vol ≥ 1.5x TB20 ({vol_ratio:.2f}x)", factor_volume),
        (f"Giá tăng dứt khoát ≥ 2% ({price_change_pct:+.2%})", factor_price_gain),
        (f"RSI đà tăng mạnh 50–65 ({rsi:.1f})", factor_rsi),
    ]

    safety_filters = [
        (f"Thanh khoản TB20 ≥ 200k cp ({vol20:,.0f} cp)", liquidity_ok),
        (f"Chất lượng DN: F-Score ≥ 5 ({f_score if f_score is not None else 'N/A'}/9)", fundamental_ok),
    ]

    all_factors = factor_trend and factor_volume and factor_price_gain and factor_rsi
    is_safe = liquidity_ok and fundamental_ok

    if not liquidity_ok:
        state = "AVOID_LIQUIDITY"
    elif not fundamental_ok:
        state = "AVOID_FUNDAMENTAL"
    elif all_factors:
        state = "BUY"
    elif factor_trend and factor_rsi:
        state = "READY"
    elif not factor_trend:
        state = "AVOID_TREND"
    else:
        state = "WAIT"

    # Kế hoạch mở vị thế
    entry_price = close
    max_entry = entry_price * (1.0 + MAX_CHASE_PCT)
    stop_loss = entry_price * (1.0 - STOP_LOSS_PCT)
    risk = entry_price - stop_loss
    target_1 = entry_price + RR_TARGET_1 * risk
    target_2 = entry_price + RR_TARGET_2 * risk

    return {
        "term": TERM_SHORT,
        "symbol": symbol,
        "state": state,
        "date": row["Date"].strftime("%d/%m/%Y"),
        "close": close,
        "vol20": vol20,
        "f_score": f_score,
        "fin_health": fin_health,
        "vol_ratio": vol_ratio,
        "price_change_pct": price_change_pct,
        "conditions": conditions,
        "safety_filters": safety_filters,
        "entry_price": entry_price,
        "max_entry": max_entry,
        "stop_loss": stop_loss,
        "sma20": sma20,
        "sma50": sma50,
        "target_1": target_1,
        "target_2": target_2,
    }


def evaluate_position_short(df, position: dict[str, Any]) -> dict[str, Any]:
    """Quản lý vị thế T+ và báo lệnh Bán khi vi phạm kỷ luật."""
    row = df.iloc[-1]
    close = float(row["Close"])
    high = float(row["High"])
    low = float(row["Low"])
    sma20 = float(row["SMA20"])
    rsi = float(row["RSI"])

    entry_price = float(position["entry_price"])
    initial_stop = float(position.get("initial_stop", entry_price * (1.0 - STOP_LOSS_PCT)))
    target_1 = float(position.get("target_1", entry_price + RR_TARGET_1 * (entry_price * STOP_LOSS_PCT)))
    target_2 = float(position.get("target", entry_price + RR_TARGET_2 * (entry_price * STOP_LOSS_PCT)))

    reasons: list[str] = []
    state = "HOLD"

    # Kiểm tra phân phối RSI: rớt từ vùng trên 70 xuống dưới 60
    recent_rsi_max = float(df["RSI"].iloc[-6:-1].max()) if len(df) >= 7 else 0.0
    rsi_distribution = bool(recent_rsi_max >= 70.0 and rsi < 60.0)

    # 1. Kỷ luật cắt lỗ tuyệt đối 7%
    if low <= initial_stop:
        state = "EXIT_STOP"
        reasons.append(f"Chạm kỷ luật cắt lỗ tuyệt đối -7% (giá thấp nhất {low:.3f} ≤ {initial_stop:.3f})")

    # 2. Đường giá xuyên thủng MA20
    elif close < sma20:
        state = "EXIT_MA20"
        reasons.append(f"Đường giá đóng cửa xuyên thủng hỗ trợ động MA20 ({close:.3f} < {sma20:.3f})")

    # 3. RSI phân phối (rớt từ >70 xuống <60)
    elif rsi_distribution:
        state = "EXIT_RSI_DISTRIBUTION"
        reasons.append(f"RSI có dấu hiệu phân phối: rớt từ đỉnh {recent_rsi_max:.1f} (>70) xuống {rsi:.1f} (<60)")

    # 4. Đạt mục tiêu chốt lời R:R 1:2
    elif high >= target_2:
        state = "EXIT_TARGET"
        reasons.append(f"Đạt mục tiêu chốt lời tối đa R:R 1:2 (+14%) tại {target_2:.3f}")

    # Cảnh báo chạm Target 1 (1:1.5)
    elif high >= target_1:
        reasons.append(f"Đã đạt mốc chốt lời 1 (R:R 1:1.5 tại {target_1:.3f}); cân nhắc hiện thực hóa 50% lợi nhuận")

    updated_position = dict(position)
    updated_position.update({
        "current_stop": max(initial_stop, sma20 if close > sma20 else initial_stop),
        "status": "CLOSED" if state.startswith("EXIT_") else "OPEN",
    })

    return {
        "term": TERM_SHORT,
        "state": state,
        "date": row["Date"].strftime("%d/%m/%Y"),
        "close": close,
        "entry_price": entry_price,
        "stop": initial_stop,
        "sma20": sma20,
        "target": target_2,
        "target_1": target_1,
        "reasons": reasons,
        "position": updated_position,
    }


def evaluate_strategy_short(df, position: dict[str, Any] | None = None, symbol: str = "") -> dict[str, Any]:
    """Thực thi chiến lược ngắn hạn."""
    sym = symbol or (position.get("symbol", "") if position else "")
    return evaluate_position_short(df, position) if position else evaluate_entry_short(df, sym)


# =====================================================================
# 2. CHIẾN LƯỢC DÀI HẠN (SỨC KHỎE TÀI CHÍNH & TOP 20)
# =====================================================================

def evaluate_entry_long(df, symbol: str) -> dict[str, Any]:
    """Đánh giá cơ hội đầu tư dài hạn dựa trên sức khỏe doanh nghiệp vnfinancialdata."""
    row = df.iloc[-1]
    close = float(row["Close"])
    sma50 = float(row["SMA50"])
    above_sma50 = close > sma50

    fin = get_financial_health(symbol)
    f_score = fin.get("f_score") if fin else None
    roe = fin.get("roe") if fin else 0.0
    roa = fin.get("roa") if fin else 0.0
    rating = fin.get("rating", "Chưa đủ dữ liệu") if fin else "Chưa có dữ liệu BCTC"

    conditions = [
        (f"Xu hướng dài hạn: Giá > SMA50 ({sma50:.3f})", bool(above_sma50)),
        (f"Điểm Piotroski F-Score: {f_score if f_score is not None else 'N/A'}/9 ({rating})", bool(f_score and f_score >= 6)),
        (f"Hiệu quả sinh lời ROE: {roe:.1%}" if fin else "ROE: Chưa có", bool(roe and roe >= 0.15)),
        (f"Hiệu quả sinh lời ROA: {roa:.1%}" if fin else "ROA: Chưa có", bool(roa and roa >= 0.05)),
    ]

    if above_sma50 and f_score and f_score >= 7:
        state = "LONG_EXCELLENT"
        comment = (
            f"Doanh nghiệp có nền tảng tài chính cực kỳ vững mạnh (F-Score {f_score}/9, ROE {roe:.1%}), "
            "đồng thời đường giá giữ vững trên SMA50. Rất phù hợp cho chiến lược tích sản và nắm giữ dài hạn."
        )
    elif above_sma50 and f_score and f_score >= 5:
        state = "LONG_GOOD"
        comment = (
            f"Sức khỏe tài chính ổn định (F-Score {f_score}/9, ROE {roe:.1%}) trên xu hướng tăng dài hạn. "
            "Có thể canh các nhịp điều chỉnh để gom vị thế dài hạn."
        )
    elif not above_sma50:
        state = "LONG_BELOW_TREND"
        comment = (
            f"Giá đang dưới đường SMA50 ({sma50:.3f}). Dù F-Score đạt {f_score if f_score is not None else 'N/A'}/9, "
            "cần chờ đợi dòng tiền xác nhận tạo đáy trung - dài hạn trước khi giải ngân."
        )
    else:
        state = "LONG_WAIT"
        comment = "Chưa đủ tiêu chuẩn tài chính hoặc xu hướng kỹ thuật dài hạn."

    plan = (
        "• Phương pháp: Tích sản & Bám xu hướng dài hạn (Buy & Hold)\n"
        "• Khuyến nghị: Ưu tiên phân bổ vốn vào Top 20 cổ phiếu tài chính khỏe nhất.\n"
        "• Xem danh sách Top 20 bằng lệnh: /top20 hoặc nút bấm bên dưới."
    )

    return {
        "term": TERM_LONG,
        "symbol": symbol,
        "state": state,
        "date": row["Date"].strftime("%d/%m/%Y"),
        "close": close,
        "fin": fin,
        "conditions": conditions,
        "comment": comment,
        "plan": plan,
    }


def evaluate_position_long(df, position: dict[str, Any]) -> dict[str, Any]:
    """Quản lý vị thế nắm giữ dài hạn."""
    row = df.iloc[-1]
    close = float(row["Close"])
    entry_price = float(position.get("entry_price", close))
    pnl_pct = ((close - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0

    state = "HOLD"
    reasons = [
        f"Hiệu suất nắm giữ: {pnl_pct:+.2f}%",
        "Vị thế đầu tư dài hạn đang được giám sát theo xu hướng quý/năm.",
    ]

    stop_val = float(position.get("current_stop", entry_price * 0.85))
    target_val = float(position.get("target", entry_price * 1.30))

    return {
        "term": TERM_LONG,
        "state": state,
        "date": row["Date"].strftime("%d/%m/%Y"),
        "close": close,
        "entry_price": entry_price,
        "pnl_pct": pnl_pct,
        "stop": stop_val,
        "target": target_val,
        "reasons": reasons,
        "position": dict(position),
    }


def evaluate_strategy_long(df, position: dict[str, Any] | None = None, symbol: str = "") -> dict[str, Any]:
    """Thực thi chiến lược dài hạn."""
    sym = symbol or (position.get("symbol", "") if position else "")
    return evaluate_position_long(df, position) if position else evaluate_entry_long(df, sym)


# =====================================================================
# 3. QUẢN LÝ VỊ THẾ & ĐIỀU HƯỚNG TỔNG QUÁT
# =====================================================================

def open_position(
    symbol: str,
    entry_price: float,
    atr_at_entry: float,
    entry_date: str,
    term: str = TERM_SHORT,
) -> dict[str, Any]:
    """Tạo vị thế sau khi có giá khớp thật và áp dụng kỷ luật cắt lỗ/chốt lời."""
    symbol = normalize_symbol(symbol)
    entry_price = float(entry_price)
    norm_term = normalize_term(term)

    if norm_term == TERM_LONG:
        initial_stop = entry_price * 0.85  # -15% cho dài hạn
        target = entry_price * 1.30        # +30% cho dài hạn
        target_1 = entry_price * 1.15
    else:
        # Ngắn hạn: cắt lỗ 7%, chốt lời 1:1.5 (+10.5%) và 1:2 (+14%)
        initial_stop = entry_price * (1.0 - STOP_LOSS_PCT)
        risk = entry_price - initial_stop
        target_1 = entry_price + RR_TARGET_1 * risk
        target = entry_price + RR_TARGET_2 * risk

    if entry_price <= 0 or initial_stop <= 0:
        raise ValueError("Giá khớp không hợp lệ.")

    return {
        "symbol": symbol,
        "term": norm_term,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "initial_stop": initial_stop,
        "current_stop": initial_stop,
        "target_1": target_1,
        "target": target,
        "status": "OPEN",
    }


def evaluate_strategy(
    df,
    position: dict[str, Any] | None = None,
    term: str = TERM_SHORT,
    symbol: str = "",
) -> dict[str, Any]:
    """API chung: điều hướng theo chế độ ngắn hạn hoặc dài hạn."""
    resolved_term = position.get("term") if (position and "term" in position) else term
    sym = symbol or (position.get("symbol", "") if position else "")
    if normalize_term(resolved_term) == TERM_LONG:
        return evaluate_strategy_long(df, position, symbol=sym)
    return evaluate_strategy_short(df, position, symbol=sym)
