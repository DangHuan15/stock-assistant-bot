"""Đánh giá sức khỏe tài chính doanh nghiệp (F-Score & chỉ số) bằng vnfinancialdata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import vnfinancialdata as vf

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
CACHE_FILE = ROOT / "stock_cache" / "financial_cache.json"
TOP20_CACHE_FILE = ROOT / "stock_cache" / "top20_longterm.json"


def _read_cache(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp = file_path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(file_path)


def _safe_float(df, yr: int, codes: list[str]) -> float:
    """Lấy giá trị đầu tiên khớp với một trong các mã chỉ tiêu."""
    if df is None or df.empty:
        return 0.0
    sub = df[(df["year"] == yr) & (df["item_code"].isin(codes))]
    if not sub.empty:
        val = sub["value"].iloc[0]
        return float(val) if val is not None else 0.0

    # Tìm theo tiền tố nếu chưa khớp chính xác
    for c in codes:
        sub2 = df[(df["year"] == yr) & (df["item_code"].str.startswith(c))]
        if not sub2.empty:
            val = sub2["value"].iloc[0]
            return float(val) if val is not None else 0.0
    return 0.0


def calculate_f_score(ticker: str) -> dict[str, Any] | None:
    """Tính điểm Piotroski F-Score (0–9) và các chỉ số tài chính từ vnfinancialdata."""
    ticker = ticker.strip().upper()
    exchanges = ["HSX", "HNX"]

    bs_df, inc_df, cf_df = None, None, None

    for ex in exchanges:
        try:
            bs = vf.get(ticker=ticker, statement="balance_sheet", exchange=ex)
            inc = vf.get(ticker=ticker, statement="income_statement", exchange=ex)
            cf = vf.get(ticker=ticker, statement="cash_flow", exchange=ex)
            if not bs.empty and not inc.empty:
                bs_df, inc_df, cf_df = bs, inc, cf
                break
        except Exception:
            continue

    if bs_df is None or inc_df is None:
        return None

    # Tìm các năm có dữ liệu hợp lệ (ưu tiên các năm đã hoàn tất BCTC kiểm toán)
    years = sorted(list(set(inc_df["year"]).intersection(set(bs_df["year"]))))
    valid_years = []
    for y in years:
        ta = _safe_float(bs_df, y, ["bs_tong_tai_san", "bs_tong_cong_nguon_von"])
        if ta > 0:
            valid_years.append(y)

    if len(valid_years) < 2:
        return None

    # Ưu tiên năm 2024 (năm tài chính hoàn chỉnh gần nhất) nếu có
    if 2024 in valid_years:
        y_curr = 2024
        idx = valid_years.index(2024)
        y_prev = valid_years[idx - 1]
    else:
        y_curr, y_prev = valid_years[-1], valid_years[-2]

    # Mã chỉ tiêu cho từng báo cáo
    ta_c = _safe_float(bs_df, y_curr, ["bs_tong_tai_san", "bs_tong_cong_nguon_von"])
    ta_p = _safe_float(bs_df, y_prev, ["bs_tong_tai_san", "bs_tong_cong_nguon_von"])

    ni_c = _safe_float(inc_df, y_curr, ["is_lai_lo_thuan_sau_thue", "is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_loi_nhuan_sau_thue"])
    ni_p = _safe_float(inc_df, y_prev, ["is_lai_lo_thuan_sau_thue", "is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_loi_nhuan_sau_thue"])

    rev_c = _safe_float(inc_df, y_curr, ["is_doanh_so_thuan", "is_doanh_thu_thuan_ve_hoat_dong_kinh_doanh", "is_doanh_so"])
    rev_p = _safe_float(inc_df, y_prev, ["is_doanh_so_thuan", "is_doanh_thu_thuan_ve_hoat_dong_kinh_doanh", "is_doanh_so"])

    gp_c = _safe_float(inc_df, y_curr, ["is_lai_gop", "is_loi_nhuan_gop"])
    gp_p = _safe_float(inc_df, y_prev, ["is_lai_gop", "is_loi_nhuan_gop"])

    ca_c = _safe_float(bs_df, y_curr, ["bs_tai_san_ngan_han"])
    ca_p = _safe_float(bs_df, y_prev, ["bs_tai_san_ngan_han"])

    cl_c = _safe_float(bs_df, y_curr, ["bs_no_ngan_han"])
    cl_p = _safe_float(bs_df, y_prev, ["bs_no_ngan_han"])

    ltd_c = _safe_float(bs_df, y_curr, ["bs_no_dai_han", "bs_vay_va_no_dai_han"])
    ltd_p = _safe_float(bs_df, y_prev, ["bs_no_dai_han", "bs_vay_va_no_dai_han"])

    equity_c = _safe_float(bs_df, y_curr, ["bs_von_chu_so_huu_4d280b22", "bs_von_va_cac_quy", "bs_von_chu_so_huu_6cda78ae"])
    sh_c = _safe_float(bs_df, y_curr, ["bs_co_phieu_pho_thong", "bs_von_gop"])
    sh_p = _safe_float(bs_df, y_prev, ["bs_co_phieu_pho_thong", "bs_von_gop"])

    cfo_c = _safe_float(cf_df, y_curr, ["cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh", "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh"])

    roa_c = (ni_c / ta_c) if ta_c > 0 else 0.0
    roa_p = (ni_p / ta_p) if ta_p > 0 else 0.0
    roe_c = (ni_c / equity_c) if equity_c > 0 else 0.0

    # 9 Tiêu chí Piotroski F-Score:
    p1 = 1 if roa_c > 0 else 0
    p2 = 1 if cfo_c > 0 else 0
    p3 = 1 if roa_c > roa_p else 0
    p4 = 1 if cfo_c > ni_c else 0

    lev_c = (ltd_c / ta_c) if ta_c > 0 else 0.0
    lev_p = (ltd_p / ta_p) if ta_p > 0 else 0.0
    p5 = 1 if lev_c <= lev_p else 0

    cr_c = (ca_c / cl_c) if cl_c > 0 else 1.0
    cr_p = (ca_p / cl_p) if cl_p > 0 else 1.0
    p6 = 1 if cr_c >= cr_p else 0

    p7 = 1 if (sh_c <= sh_p or sh_c == 0) else 0

    gm_c = (gp_c / rev_c) if rev_c > 0 else 0.0
    gm_p = (gp_p / rev_p) if rev_p > 0 else 0.0
    p8 = 1 if gm_c >= gm_p else 0

    at_c = (rev_c / ta_c) if ta_c > 0 else 0.0
    at_p = (rev_p / ta_p) if ta_p > 0 else 0.0
    p9 = 1 if at_c >= at_p else 0

    total_score = p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9

    if total_score >= 8:
        rating = "Cực kỳ vững mạnh 🌟"
    elif total_score >= 6:
        rating = "Sức khỏe tốt ✅"
    elif total_score >= 5:
        rating = "Ổn định / Đạt chuẩn"
    else:
        rating = "Kém / Đầu cơ rủi ro ⚠️"

    return {
        "ticker": ticker,
        "year": int(y_curr),
        "f_score": total_score,
        "rating": rating,
        "roa": roa_c,
        "roe": roe_c,
        "net_margin": (ni_c / rev_c) if rev_c > 0 else 0.0,
        "gross_margin": gm_c,
        "revenue_vnd": rev_c,
        "net_profit_vnd": ni_c,
        "cfo_vnd": cfo_c,
        "debt_to_assets": lev_c,
        "current_ratio": cr_c,
        "points": [p1, p2, p3, p4, p5, p6, p7, p8, p9],
    }


def get_financial_health(ticker: str) -> dict[str, Any] | None:
    """Lấy dữ liệu sức khỏe tài chính có cache để phản hồi nhanh."""
    ticker = ticker.strip().upper()
    cache = _read_cache(CACHE_FILE)
    if ticker in cache:
        return cache[ticker]

    result = calculate_f_score(ticker)
    if result:
        cache[ticker] = result
        _write_cache(CACHE_FILE, cache)
    return result


BENCHMARK_LONGTERM_STOCKS = [
    "BMP", "CTR", "VNM", "MBB", "ACB", "VCB", "VHC", "TCB",
    "FPT", "PTB", "REE", "HPG", "PNJ", "TLG", "VHM", "GAS",
    "GMD", "MSN", "KDH", "DGC", "SCS", "SSI", "MWG", "VIC"
]


def build_top20_longterm() -> list[dict[str, Any]]:
    """Tạo bảng xếp hạng Top 20 cổ phiếu dài hạn tốt nhất từ dữ liệu tài chính."""
    cached = _read_cache(TOP20_CACHE_FILE)
    if cached and isinstance(cached.get("items"), list) and len(cached["items"]) >= 15:
        return cached["items"]

    items = []
    for sym in BENCHMARK_LONGTERM_STOCKS:
        data = get_financial_health(sym)
        if not data:
            continue
        f_sc = data.get("f_score", 0)
        roe = data.get("roe", 0.0)
        roa = data.get("roa", 0.0)
        composite = f_sc * 10 + roe * 100 + roa * 100
        items.append({
            "ticker": sym,
            "f_score": f_sc,
            "roe": roe,
            "roa": roa,
            "rating": data.get("rating", ""),
            "year": data.get("year", 2024),
            "score_rank": composite,
        })

    items.sort(key=lambda x: (x["f_score"], x["roe"]), reverse=True)
    top20 = items[:20]

    _write_cache(TOP20_CACHE_FILE, {"items": top20})
    return top20
