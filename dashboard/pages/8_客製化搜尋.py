import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from src.db.repo import (
    query_company_profiles,
    query_recent_stock_ohlc_bulk,
    query_stock_ohlc_bulk_range,
    query_timeseries_like,
)

st.set_page_config(page_title="客製化搜尋", layout="wide")
st.title("客製化搜尋")

_profiles = query_company_profiles()
name_map = {r["stock_code"]: r["name"] for r in _profiles}
industry_map = {r["stock_code"]: r["industry_name"] for r in _profiles}

PAGE_SIZE = 20


def _apply_price_volume_filter(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """在「當日股價」「當日交易量(張)」欄位上加輸入框+篩選按鈕，按下前維持顯示全部資料。"""
    state_key = f"applied_filter_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = None  # None 代表尚未套用篩選(顯示全部)

    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 0.6])
    with col1:
        price_min_in = st.number_input("股價下限", value=0.0, step=1.0, key=f"price_min_{key}")
    with col2:
        price_max_in = st.number_input("股價上限", value=0.0, step=1.0, key=f"price_max_{key}")
    with col3:
        vol_min_in = st.number_input("交易量下限(張)", value=0, step=100, key=f"vol_min_{key}")
    with col4:
        vol_max_in = st.number_input("交易量上限(張)", value=0, step=100, key=f"vol_max_{key}")
    with col5:
        st.write("")  # 對齊按鈕與上面輸入框的垂直位置
        if st.button("篩選", key=f"apply_filter_{key}"):
            st.session_state[state_key] = (price_min_in, price_max_in, vol_min_in, vol_max_in)

    if st.session_state[state_key] is None:
        st.caption("股價/交易量上下限留 0 代表該側不限制；輸入完按「篩選」才會套用。")
        return df

    p_min, p_max, v_min, v_max = st.session_state[state_key]
    p_lo, p_hi = p_min, (p_max if p_max > 0 else float("inf"))
    v_lo, v_hi = v_min, (v_max if v_max > 0 else float("inf"))

    filtered = df[df["當日股價"].between(p_lo, p_hi) & df["當日交易量(張)"].between(v_lo, v_hi)]

    st.caption(f"目前套用：股價 {p_lo:g}~{'不限' if p_hi == float('inf') else f'{p_hi:g}'}，"
               f"交易量 {v_lo:g}~{'不限' if v_hi == float('inf') else f'{v_hi:g}'} 張")
    if st.button("清除篩選", key=f"clear_filter_{key}"):
        st.session_state[state_key] = None
        st.rerun()

    return filtered


def _paginate(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """取出目前頁的資料，實際的分頁按鈕由 _render_pagination 在表格下方畫出。"""
    state_key = f"page_{key}"
    total_pages = max(1, (len(df) - 1) // PAGE_SIZE + 1)
    if state_key not in st.session_state:
        st.session_state[state_key] = 1
    st.session_state[state_key] = min(max(1, st.session_state[state_key]), total_pages)
    page = st.session_state[state_key]
    st.caption(f"共 {len(df)} 檔符合，第 {page}/{total_pages} 頁（每頁 {PAGE_SIZE} 筆，點欄位標題可在本頁內排序）")
    start = (page - 1) * PAGE_SIZE
    return df.iloc[start : start + PAGE_SIZE]


def _render_pagination(df: pd.DataFrame, key: str) -> None:
    """在表格下方、區塊右下角畫分頁按鈕(‹ 1 2 3 › 的樣式)。"""
    state_key = f"page_{key}"
    total_pages = max(1, (len(df) - 1) // PAGE_SIZE + 1)
    if total_pages <= 1:
        return
    page = st.session_state.get(state_key, 1)

    n_slots = total_pages + 2  # 上一頁 + 頁碼們 + 下一頁
    cols = st.columns([4] + [0.6] * n_slots)
    with cols[1]:
        if st.button("‹", key=f"prev_{key}", disabled=(page <= 1), use_container_width=True):
            st.session_state[state_key] = max(1, page - 1)
            st.rerun()
    for i, p in enumerate(range(1, total_pages + 1), start=2):
        with cols[i]:
            if st.button(str(p), key=f"pagebtn_{key}_{p}", type=("primary" if p == page else "secondary"), use_container_width=True):
                st.session_state[state_key] = p
                st.rerun()
    with cols[n_slots]:
        if st.button("›", key=f"next_{key}", disabled=(page >= total_pages), use_container_width=True):
            st.session_state[state_key] = min(total_pages, page + 1)
            st.rerun()


def _stock_link(code: str) -> str:
    """連到本專案自己的「個股分析」頁(帶 ?code=xxxx 讓該頁預設選中這檔股票)，
    網址片段(#後面)夾帶顯示文字，靠 LinkColumn 的 display_text 正規表示式抓出來顯示成
    「公司名稱(代號)」，不影響實際導頁用的query string。
    """
    label = f"{name_map.get(code, code)}({code})"
    return f"個股分析?code={code}#{label}"


def _render_table(df: pd.DataFrame, int_cols: list[str], pct_cols: list[str] | None = None, price_cols: list[str] | None = None) -> None:
    """用原生 st.dataframe 呈現，股票欄合併了公司名稱、代號、連到個股分析頁的連結，
    數值欄位(int_cols/pct_cols/price_cols)點欄位標題即可排序。
    """
    column_config = {
        "股票": st.column_config.LinkColumn("股票", display_text=r"#(.+)$"),
    }
    for c in int_cols:
        column_config[c] = st.column_config.NumberColumn(c, format="%,d")
    for c in pct_cols or []:
        column_config[c] = st.column_config.NumberColumn(c, format="%+.2f%%")
    for c in price_cols or []:
        column_config[c] = st.column_config.NumberColumn(c, format="%.2f")
    st.dataframe(
        df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
    )


REVENUE_POSITION_THRESHOLD = 80.0


def _screen_consecutive_positive_revenue_months(n: int) -> None:
    """篩選最近n個月「月營收月增率」皆為正值，且近12個月營收位置(近似創高)達門檻的股票，n=2、3...共用同一套邏輯。"""
    st.caption(
        f"篩選條件：①最近{n}個月的「月營收月增率」皆為正值（代表營收連續{n}個月比上一個月成長）；"
        f"②近12個月營收位置% = (當月營收-近12月最低)/(近12月最高-近12月最低)×100 ≥ {REVENUE_POSITION_THRESHOLD:.0f}%"
        "（排除只是從歷史低基期回升、但尚未真正創高的股票）。"
    )

    mom_rows = query_timeseries_like("monthly_revenue_mom_%")
    if not mom_rows:
        st.info("目前尚無月營收月增率資料。")
        return

    df_mom = pd.DataFrame([dict(r) for r in mom_rows])
    df_mom["stock_code"] = df_mom["indicator_code"].str.replace("monthly_revenue_mom_", "", regex=False)

    target_months = sorted(df_mom["date"].unique())[-n:]
    if len(target_months) < n:
        st.info(f"目前累積的月營收資料不滿{n}個月，無法篩選。")
        return

    pivot_mom = df_mom.pivot(index="stock_code", columns="date", values="value")
    pivot_mom = pivot_mom.reindex(columns=target_months)
    qualifying = pivot_mom.dropna(subset=target_months)
    qualifying = qualifying[(qualifying[target_months] > 0).all(axis=1)]

    if qualifying.empty:
        st.info(f"目前沒有符合「連續{n}個月營收月增率為正」的股票。")
        return

    rev_rows = query_timeseries_like("monthly_revenue_%", start_date=target_months[0], end_date=target_months[-1])
    df_rev = pd.DataFrame([dict(r) for r in rev_rows])
    df_rev = df_rev[~df_rev["indicator_code"].str.contains("_mom_|_yoy_")]
    df_rev["stock_code"] = df_rev["indicator_code"].str.replace("monthly_revenue_", "", regex=False)
    pivot_rev = df_rev.pivot(index="stock_code", columns="date", values="value")
    pivot_rev = pivot_rev.reindex(columns=target_months)

    month_labels = [pd.to_datetime(m).strftime("%Y-%m") for m in target_months]
    rev_col_names = [f"月營收 {m}(千元)" for m in month_labels]
    mom_col_names = [f"月增幅 {m}(%)" for m in month_labels]
    qualifying_codes = [c for c in qualifying.index if c in pivot_rev.index]

    # 近12個月營收位置% = (當月營收-近12月最低)/(近12月最高-近12月最低)×100，
    # 用來排除「歷史基期太低、只是回正而非真正創高」的假訊號（Stochastic %K 概念）。
    window_start = (pd.to_datetime(target_months[-1]) - pd.DateOffset(months=11)).strftime("%Y-%m-%d")
    rev12_rows = query_timeseries_like("monthly_revenue_%", start_date=window_start, end_date=target_months[-1])
    df_rev12 = pd.DataFrame([dict(r) for r in rev12_rows])
    df_rev12 = df_rev12[~df_rev12["indicator_code"].str.contains("_mom_|_yoy_")]
    df_rev12["stock_code"] = df_rev12["indicator_code"].str.replace("monthly_revenue_", "", regex=False)
    pivot_rev12 = df_rev12.pivot(index="stock_code", columns="date", values="value")
    rev12_min = pivot_rev12.min(axis=1)
    rev12_max = pivot_rev12.max(axis=1)

    # 抓最近10個日曆天的OHLC(至少涵蓋2個交易日)，用來算「今日 vs 前一交易日」的漲跌幅。
    lookback_date = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    recent_rows = query_recent_stock_ohlc_bulk(qualifying_codes, lookback_date)
    latest_map: dict[str, dict] = {}
    prev_map: dict[str, dict] = {}
    if recent_rows:
        df_recent = pd.DataFrame([dict(r) for r in recent_rows])
        for code, g in df_recent.groupby("stock_code"):
            g = g.sort_values("date")
            latest_map[code] = g.iloc[-1].to_dict()
            if len(g) >= 2:
                prev_map[code] = g.iloc[-2].to_dict()

    # 抓「一年前」附近(往前抓14天當緩衝，避開週末/假日沒有交易日的情況)最後一筆交易日的收盤價，
    # 用來算股票年增幅：(今日收盤-一年前收盤)/一年前收盤×100。
    year_ago_end = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    year_ago_start = (datetime.today() - timedelta(days=379)).strftime("%Y-%m-%d")
    year_ago_rows = query_stock_ohlc_bulk_range(qualifying_codes, year_ago_start, year_ago_end)
    year_ago_map: dict[str, dict] = {}
    if year_ago_rows:
        df_year_ago = pd.DataFrame([dict(r) for r in year_ago_rows])
        for code, g in df_year_ago.groupby("stock_code"):
            year_ago_map[code] = g.sort_values("date").iloc[-1].to_dict()

    result_rows = []
    for code in qualifying_codes:
        revs = pivot_rev.loc[code, target_months]
        if revs.isna().any():
            continue

        r_min = rev12_min.get(code)
        r_max = rev12_max.get(code)
        if r_min is None or r_max is None or r_max <= r_min:
            continue
        current_rev = revs.iloc[-1]
        position_pct = (current_rev - r_min) / (r_max - r_min) * 100
        if position_pct < REVENUE_POSITION_THRESHOLD:
            continue

        moms = qualifying.loc[code, target_months]
        latest = latest_map.get(code)
        prev = prev_map.get(code)
        close_price = latest["close"] if latest else None
        volume = latest["volume"] if latest else None

        price_chg_pct = None
        if prev and close_price is not None and prev.get("close"):
            price_chg_pct = (close_price - prev["close"]) / prev["close"] * 100
        volume_chg_pct = None
        if prev and volume is not None and prev.get("volume"):
            volume_chg_pct = (volume - prev["volume"]) / prev["volume"] * 100

        year_ago = year_ago_map.get(code)
        price_yoy_pct = None
        if year_ago and close_price is not None and year_ago.get("close"):
            price_yoy_pct = (close_price - year_ago["close"]) / year_ago["close"] * 100

        row = {
            "股票": _stock_link(code),
            "產業別": industry_map.get(code) or "—",
            "當日股價": close_price,
            "股價漲跌(%)": price_chg_pct,
            "股票年增幅(%)": price_yoy_pct,
            "當日交易量(張)": int(volume / 1000) if volume is not None else None,
            "交易量漲跌(%)": volume_chg_pct,
            "近12月營收位置%": position_pct,
        }
        for i in range(n):
            row[rev_col_names[i]] = int(revs.iloc[i])
            row[mom_col_names[i]] = float(moms.iloc[i])
        result_rows.append(row)

    if not result_rows:
        st.info(f"目前沒有符合條件（含近12個月營收位置%≥{REVENUE_POSITION_THRESHOLD:.0f}%）、且{n}個月營收金額都齊全的股票。")
        return

    result_df = pd.DataFrame(result_rows)

    result_df = _apply_price_volume_filter(result_df, key=f"filter_{n}")
    if result_df.empty:
        st.info("目前篩選區間內沒有符合的股票，請調整股價/交易量範圍。")
        return

    # 預設按當日交易量由大到小排序；分頁後每頁內仍可點欄位標題重新排序。
    result_df = result_df.sort_values("當日交易量(張)", ascending=False, na_position="last")
    result_df = result_df.reset_index(drop=True)
    result_df.insert(0, "排名", result_df.index + 1)
    page_key = f"mom_screen_page_{n}"
    page_df = _paginate(result_df, key=page_key)
    _render_table(
        page_df,
        int_cols=["排名", "當日交易量(張)"] + rev_col_names,
        pct_cols=["股價漲跌(%)", "股票年增幅(%)", "交易量漲跌(%)", "近12月營收位置%"] + mom_col_names,
        price_cols=["當日股價"],
    )
    _render_pagination(result_df, key=page_key)


PLACEHOLDER = "請選擇"
SCREENS = ["連續二個月營收正成長股票", "連續三個月營收正成長股票"]
picked_screen = st.selectbox("篩選條件", [PLACEHOLDER] + SCREENS, index=0)
active_screen = picked_screen if picked_screen != PLACEHOLDER else None

st.divider()

if active_screen is None:
    st.info("請先在上方選擇篩選條件。")
elif active_screen in ("連續二個月營收正成長股票", "連續三個月營收正成長股票"):
    n_months = 2 if active_screen == "連續二個月營收正成長股票" else 3
    st.header(active_screen)

    with st.expander("查看篩選結果", expanded=True, key=f"result_expander_{n_months}"):
        _screen_consecutive_positive_revenue_months(n_months)

        st.caption("資料來源同「個股分析」頁的月營收（MOPS 月營收歷史彙總檔），點「股票」欄會跳到本站的「個股分析」頁並自動選中該檔股票。")
