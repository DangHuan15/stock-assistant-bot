"""Chỉ báo, SmartScore và biểu đồ dùng chung lịch sử vnstock."""

from io import BytesIO
from threading import Lock

import matplotlib
matplotlib.use("Agg")  # Vẽ nền, không mở cửa sổ trên máy chạy bot.

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

from src.craw_data.history import (
    HistoryError,
    VN_TIMEZONE,
    get_history,
    normalize_symbol,
)


PLOT_LOCK = Lock()


def wilder(series: pd.Series, period: int = 14) -> pd.Series:
    """Làm mượt Wilder, khởi tạo bằng trung bình period giá trị đầu."""
    result = pd.Series(np.nan, index=series.index, dtype=float)
    valid = series.dropna()

    if len(valid) < period:
        return result

    seed = valid.index[period - 1]
    result.loc[seed] = valid.iloc[:period].mean()
    previous = result.loc[seed]

    for index, value in valid.iloc[period:].items():
        previous = (previous * (period - 1) + value) / period
        result.loc[index] = previous

    return result


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Tính SMA, RSI Wilder, MACD, Bollinger Bands và ATR."""
    df = frame.copy()
    close = df["Close"]

    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()

    delta = close.diff()
    gain = wilder(delta.clip(lower=0))
    loss = wilder(-delta.clip(upper=0))
    df["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df.loc[(loss == 0) & (gain > 0), "RSI"] = 100
    df.loc[(loss == 0) & (gain == 0), "RSI"] = 50

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(
        span=9, adjust=False, min_periods=9
    ).mean()

    std = close.rolling(20).std(ddof=0)
    df["BBUpper"] = df["SMA20"] + 2 * std
    df["BBLower"] = df["SMA20"] - 2 * std

    previous_close = close.shift()
    true_range = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - previous_close).abs(),
        (df["Low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = wilder(true_range)

    # So khối lượng phiên mới nhất với 20 phiên TRƯỚC đó.
    df["VolumeBase"] = df["Volume"].shift().rolling(20).mean()
    return df


def prepare(symbol: str) -> pd.DataFrame:
    """Đọc lịch sử và chỉ phân tích khi đủ dữ liệu hợp lệ."""
    df = get_history(symbol)

    if len(df) < 100:
        raise HistoryError(
            f"{symbol} chỉ có {len(df)} phiên; cần ít nhất 100 phiên."
        )

    today = pd.Timestamp.now(tz=VN_TIMEZONE).date()
    age = (today - df["Date"].iloc[-1].date()).days

    # Ngưỡng vận hành của dự án, không phải lịch nghỉ giao dịch chính thức.
    if age > 7:
        raise HistoryError(
            f"Nến gần nhất đã cách {age} ngày. "
            "Tạm không phát tín hiệu; cần kiểm tra dữ liệu/ngày nghỉ."
        )

    df = add_indicators(df)
    required = ["SMA20", "SMA50", "RSI", "MACD", "Signal", "ATR"]

    if not np.isfinite(df.iloc[-1][required].to_numpy(dtype=float)).all():
        raise HistoryError("Chưa đủ dữ liệu hợp lệ để tính chỉ báo.")

    return df


def score_report(symbol: str, df: pd.DataFrame) -> str:
    """Chấm điểm kỹ thuật, không tạo lệnh mua/bán hoặc kế hoạch giá."""
    row, previous = df.iloc[-1], df.iloc[-2]

    rules = [
        (
            "Close > SMA20",
            12 if row.Close > row.SMA20 else -12,
        ),
        (
            "SMA20 > SMA50",
            12 if row.SMA20 > row.SMA50 else -12,
        ),
        (
            "SMA50 tăng so với 5 phiên trước",
            8 if row.SMA50 > df.iloc[-6].SMA50 else -8,
        ),
        (
            "MACD > Signal",
            10 if row.MACD > row.Signal else -10,
        ),
    ]

    rsi_points = (
        8 if 50 <= row.RSI < 70
        else -8 if row.RSI < 40
        else -4 if row.RSI >= 70
        else 0
    )
    rules.append((f"RSI14 = {row.RSI:.1f}", rsi_points))

    ratio = row.Volume / row.VolumeBase if row.VolumeBase > 0 else None
    volume_points = 0

    if ratio is not None and ratio >= 1.2:
        volume_points = (
            10 if row.Close > previous.Close
            else -10 if row.Close < previous.Close
            else 0
        )

    rules.append((
        f"Volume/TB20 trước = {ratio:.2f}x"
        if ratio is not None else "Thiếu khối lượng nền",
        volume_points,
    ))

    score = max(0, min(100, 50 + sum(points for _, points in rules)))
    strength = (
        "Tích cực" if score >= 70
        else "Yếu" if score <= 30
        else "Trung tính"
    )

    lines = [
        f"⭐ SMARTSCORE — {symbol}: {score}/100",
        f"Trạng thái kỹ thuật: {strength}",
        f"Nến ngày: {row.Date:%d/%m/%Y} | vnstock/KBS",
        "",
        "Điểm gốc 50; giới hạn kết quả trong 0–100.",
    ]

    lines.extend(
        f"• {label}: {points:+d}"
        for label, points in rules
    )

    lines.extend([
        "",
        f"SMA20: {row.SMA20:.3f} | SMA50: {row.SMA50:.3f}",
        f"MACD: {row.MACD:.3f} | Signal: {row.Signal:.3f}",
        f"ATR14: {row.ATR:.3f}",
        "",
        "Điểm cao không tự động là tín hiệu mua.",
        "Xem điều kiện giao dịch riêng bằng /price " + symbol,
        "Volume không phải dòng tiền ròng; điểm số chưa được backtest.",
    ])

    return "\n".join(lines)

def make_chart(symbol: str, df: pd.DataFrame) -> bytes:
    """Vẽ PNG trong RAM rồi đóng hình, không lưu ảnh tạm trên đĩa."""
    end = pd.Timestamp.now(tz=VN_TIMEZONE).tz_localize(None).normalize()
    start = end - pd.DateOffset(months=6)
    chart = df[df["Date"] >= start].set_index("Date")

    if len(chart) < 2:
        raise HistoryError("Không đủ nến trong sáu tháng gần nhất.")

    # Matplotlib không an toàn khi nhiều luồng cùng vẽ.
    with PLOT_LOCK:
        figure = None
        try:
            plots = [
                mpf.make_addplot(chart["SMA20"], color="orange"),
                mpf.make_addplot(chart["SMA50"], color="dodgerblue"),
                mpf.make_addplot(chart["BBUpper"], color="gray", alpha=0.5),
                mpf.make_addplot(chart["BBLower"], color="gray", alpha=0.5),
                mpf.make_addplot(
                    chart["RSI"], panel=2, color="purple",
                    ylabel="RSI14", ylim=(0, 100), secondary_y=False,
                ),
            ]
            figure, axes = mpf.plot(
                chart,
                type="candle",
                style="yahoo",
                volume=True,
                volume_panel=1,
                addplot=plots,
                panel_ratios=(3, 1, 1),
                figsize=(12, 8),
                title=f"{symbol} | Daily | vnstock/KBS | {chart.index[-1]:%Y-%m-%d}",
                ylabel="Source price units",
                datetime_format="%d/%m",
                returnfig=True,
            )
            axes[0].text(
                0.01, 0.97, "Orange: SMA20 | Blue: SMA50 | Gray: BB20",
                transform=axes[0].transAxes, va="top", fontsize=9,
            )
            axes[4].axhline(30, color="gray", linestyle="--", linewidth=0.7)
            axes[4].axhline(70, color="gray", linestyle="--", linewidth=0.7)

            with BytesIO() as buffer:
                figure.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
                return buffer.getvalue()
        finally:
            if figure is not None:
                plt.close(figure)


def analyze(symbol: str, chart: bool = False):
    """Điểm vào chung: lấy lịch sử một lần cho phân tích hoặc biểu đồ."""
    symbol = normalize_symbol(symbol)
    df = prepare(symbol)
    return make_chart(symbol, df) if chart else score_report(symbol, df)