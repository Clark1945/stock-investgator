import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from src.db.repo import (
    query_all_stock_ohlc_since,
    query_company_profiles,
    query_recent_stock_ohlc_bulk,
    query_timeseries_like,
)

st.set_page_config(page_title="客製化搜尋", layout="wide")
from dashboard.intro import show_intro
from dashboard.theme import apply_theme

show_intro()
apply_theme()
st.title("客製化搜尋")

_profiles = query_company_profiles()
name_map = {r["stock_code"]: r["name"] for r in _profiles}
industry_map = {r["stock_code"]: r["industry_name"] for r in _profiles}

PAGE_SIZE = 20


def _apply_price_volume_filter(df: pd.DataFrame, key: str, with_yoy: bool = False) -> pd.DataFrame:
    """在「當日股價」「當日交易量(張)」(及選用的「營收年增幅(%)」)欄位上加下限輸入框+篩選按鈕，按下前維持顯示全部資料。"""
    state_key = f"applied_filter_{key}"
    if state_key not in st.session_state or (st.session_state[state_key] is not None and len(st.session_state[state_key]) != 3):
        st.session_state[state_key] = None  # None 代表尚未套用篩選(顯示全部)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 0.6])
    with col1:
        price_min_in = st.number_input("股價下限", value=0.0, step=1.0, key=f"price_min_{key}")
    with col2:
        vol_min_in = st.number_input("交易量下限(張)", value=0, step=100, key=f"vol_min_{key}")
    yoy_min_in = None
    with col3:
        if with_yoy:  # 年增幅可為負值，所以用「留空=不限」而不是 0
            yoy_min_in = st.number_input("營收年增幅下限(%)", value=None, step=5.0, placeholder="不限", key=f"yoy_min_{key}")
    with col4:
        st.write("")  # 對齊按鈕與上面輸入框的垂直位置
        if st.button("篩選", key=f"apply_filter_{key}"):
            st.session_state[state_key] = (price_min_in, vol_min_in, yoy_min_in)

    if st.session_state[state_key] is None:
        st.caption("下限留 0（年增幅留空）代表不限制；輸入完按「篩選」才會套用。")
        return df

    p_min, v_min, y_min = st.session_state[state_key]
    filtered = df[(df["當日股價"] >= p_min) & (df["當日交易量(張)"] >= v_min)]
    if with_yoy and y_min is not None:
        filtered = filtered[filtered["營收年增幅(%)"] >= y_min]

    st.caption(f"目前套用：股價 ≥ {p_min:g}，交易量 ≥ {v_min:g} 張"
               + (f"，營收年增幅 ≥ {y_min:g}%" if with_yoy and y_min is not None else ""))
    if st.button("清除篩選", key=f"clear_filter_{key}"):
        st.session_state[state_key] = None
        st.rerun()

    return filtered


def _apply_global_sort(df: pd.DataFrame, key: str, default_col: str, page_key: str, default_asc: bool = False, flip_cols: tuple = ()) -> pd.DataFrame:
    """對「全部篩選結果」(跨所有分頁)排序，不是只排目前這一頁。
    st.dataframe 點欄位標題只會在前端排序當頁的 20 筆，Streamlit 也拿不到點擊事件，
    所以另外提供排序欄位/方式的選單，在分頁之前就對整份資料排序。
    """
    cols = [c for c in df.columns if c != "股票"]
    c1, c2 = st.columns([2, 1.4])
    with c1:
        col = st.selectbox(
            "排序欄位（對全部結果排序）", cols, index=cols.index(default_col), key=f"sort_col_{key}",
            on_change=lambda: st.session_state.__setitem__(f"page_{page_key}", 1),
        )
    with c2:
        direction = st.radio(
            "排序方式", ["由大到小", "由小到大"], index=1 if default_asc else 0, horizontal=True, key=f"sort_dir_{key}",
            on_change=lambda: st.session_state.__setitem__(f"page_{page_key}", 1),
        )
    ascending = direction == "由小到大"
    if col in flip_cols:  # 跌幅欄位存的是負數，「由大到小」要讓跌最多(最負)的排最前面
        ascending = not ascending
    return df.sort_values(col, ascending=ascending, na_position="last", kind="stable")


def _paginate(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """取出目前頁的資料，實際的分頁按鈕由 _render_pagination 在表格下方畫出。"""
    state_key = f"page_{key}"
    total_pages = max(1, (len(df) - 1) // PAGE_SIZE + 1)
    if state_key not in st.session_state:
        st.session_state[state_key] = 1
    st.session_state[state_key] = min(max(1, st.session_state[state_key]), total_pages)
    page = st.session_state[state_key]
    st.caption(f"共 {len(df)} 檔符合，第 {page}/{total_pages} 頁（每頁 {PAGE_SIZE} 筆；上方選單可對全部結果排序，點欄位標題只會排序本頁）")
    start = (page - 1) * PAGE_SIZE
    return df.iloc[start : start + PAGE_SIZE]


def _render_pagination(df: pd.DataFrame, key: str) -> None:
    """在表格下方、區塊右下角畫分頁按鈕(‹ 1 2 3 › 的樣式)。"""
    state_key = f"page_{key}"
    total_pages = max(1, (len(df) - 1) // PAGE_SIZE + 1)
    if total_pages <= 1:
        return
    page = st.session_state.get(state_key, 1)

    # 頁數很多時只顯示「第一頁、最後一頁、目前頁與前後各一頁」，中間斷開處用「…」，避免按鈕擠成一團。
    shown = sorted({p for p in (1, total_pages, page - 1, page, page + 1) if 1 <= p <= total_pages})
    items: list[int | None] = []
    for p in shown:
        if items and items[-1] is not None and p - items[-1] > 1:
            items.append(None)
        items.append(p)

    with st.container(key=f"pager_{key}"):
        n_slots = len(items) + 2  # 上一頁 + 頁碼們(含省略號) + 下一頁
        cols = st.columns([4] + [0.6] * n_slots)
        with cols[1]:
            if st.button("‹", key=f"prev_{key}", disabled=(page <= 1), use_container_width=True):
                st.session_state[state_key] = max(1, page - 1)
                st.rerun()
        for i, p in enumerate(items, start=2):
            with cols[i]:
                if p is None:
                    st.markdown("<div style='text-align:center;padding-top:0.4rem'>…</div>", unsafe_allow_html=True)
                elif st.button(str(p), key=f"pagebtn_{key}_{p}", type=("primary" if p == page else "secondary"), use_container_width=True):
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


def _screen_consecutive_positive_revenue_months(n: int) -> None:
    """篩選最近n個月「月營收月增率」皆為正值的股票，n=2、3...共用同一套邏輯；
    是否為真正創高、而非低基期回升，改由「股票年增幅(%)」欄位讓使用者自行判斷。"""
    st.caption(f"篩選條件：最近{n}個月的「月營收月增率」皆為正值（代表營收連續{n}個月比上一個月成長）。")

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
    mom_col_names = [f"月增幅 {m}(%)" for m in month_labels]
    qualifying_codes = [c for c in qualifying.index if c in pivot_rev.index]

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

    # 最新月份的官方營收年增率(MOPS已計算好，非自行推算)。
    yoy_rows = query_timeseries_like("monthly_revenue_yoy_%", start_date=target_months[-1], end_date=target_months[-1])
    df_yoy = pd.DataFrame([dict(r) for r in yoy_rows])
    rev_yoy_map: dict[str, float] = {}
    if not df_yoy.empty:
        df_yoy["stock_code"] = df_yoy["indicator_code"].str.replace("monthly_revenue_yoy_", "", regex=False)
        rev_yoy_map = df_yoy.set_index("stock_code")["value"].to_dict()

    result_rows = []
    for code in qualifying_codes:
        revs = pivot_rev.loc[code, target_months]
        if revs.isna().any():
            continue

        moms = qualifying.loc[code, target_months]
        latest = latest_map.get(code)
        prev = prev_map.get(code)
        close_price = latest["close"] if latest else None
        volume = latest["volume"] if latest else None

        price_chg_pct = None
        if prev and close_price is not None and prev.get("close"):
            price_chg_pct = (close_price - prev["close"]) / prev["close"] * 100

        rev_yoy_pct = rev_yoy_map.get(code)

        row = {
            "股票": _stock_link(code),
            "產業別": industry_map.get(code) or "—",
            "當日股價": close_price,
            "股價漲跌(%)": price_chg_pct,
            "當日交易量(張)": int(volume / 1000) if volume is not None else None,
            "當月營收(千元)": int(revs.iloc[-1]),
        }
        for i in range(n):
            row[mom_col_names[i]] = float(moms.iloc[i])
        row["營收年增幅(%)"] = rev_yoy_pct
        result_rows.append(row)

    if not result_rows:
        st.info(f"目前沒有符合條件、且{n}個月營收金額都齊全的股票。")
        return

    result_df = pd.DataFrame(result_rows)

    if st.checkbox(
        "只看破紀錄的成長（最新月增率比上個月的月增率更高，成長在加速）",
        key=f"accel_{n}",
        on_change=lambda: st.session_state.update({f"mom_screen_page_{n}": 1}),
    ):
        result_df = result_df[result_df[mom_col_names[-1]] > result_df[mom_col_names[-2]]]
        if result_df.empty:
            st.info("目前沒有符合「成長加速」的股票。")
            return

    result_df = _apply_price_volume_filter(result_df, key=f"filter_{n}", with_yoy=True)
    if result_df.empty:
        st.info("目前篩選區間內沒有符合的股票，請調整股價/交易量範圍。")
        return

    page_key = f"mom_screen_page_{n}"
    result_df = _apply_global_sort(result_df, key=f"mom_{n}", default_col="當日交易量(張)", page_key=page_key)
    result_df = result_df.reset_index(drop=True)
    result_df.insert(0, "排名", result_df.index + 1)
    page_df = _paginate(result_df, key=page_key)
    _render_table(
        page_df,
        int_cols=["排名", "當日交易量(張)", "當月營收(千元)"],
        pct_cols=["股價漲跌(%)", "營收年增幅(%)"] + mom_col_names,
        price_cols=["當日股價"],
    )
    _render_pagination(result_df, key=page_key)


def _screen_price_drop_ranking() -> None:
    """全部上市普通股「近X個交易日」跌幅排行：今日收盤 vs X個交易日前收盤，只列出下跌的股票，跌最多的排最前面。"""
    x_days = int(st.number_input("X（交易日）", min_value=1, max_value=250, value=5, step=1, key="drop_days"))
    st.caption(f"篩選條件：今日收盤價相較 {x_days} 個交易日前的收盤價下跌的股票，依跌幅由大到小排行。")

    # 日曆天數抓寬一點(交易日約佔日曆天的 5/7，再加假日緩衝)，之後再用「各股倒數第 X+1 筆」取基準日。
    start = (datetime.today() - timedelta(days=int(x_days * 1.5) + 15)).strftime("%Y-%m-%d")
    rows = query_all_stock_ohlc_since(start)
    if not rows:
        st.info("目前尚無股價資料。")
        return

    df = pd.DataFrame([dict(r) for r in rows])
    df = df[df["stock_code"].isin(name_map.keys())]
    df["pos_from_end"] = df.groupby("stock_code").cumcount(ascending=False)
    latest = df[df["pos_from_end"] == 0].set_index("stock_code")
    base = df[df["pos_from_end"] == x_days].set_index("stock_code")
    prev = df[df["pos_from_end"] == 1].set_index("stock_code")

    joined = latest.join(base[["date", "close"]], how="inner", rsuffix="_base")
    joined = joined.join(prev[["close"]].rename(columns={"close": "close_prev"}), how="left")
    joined["day_chg_pct"] = (joined["close"] - joined["close_prev"]) / joined["close_prev"] * 100
    joined = joined[joined["close_base"] > 0]
    joined["drop_pct"] = (joined["close"] - joined["close_base"]) / joined["close_base"] * 100
    joined = joined[joined["drop_pct"] < 0]

    if joined.empty:
        st.info(f"目前沒有近 {x_days} 個交易日下跌的股票，或股價資料不足 {x_days + 1} 個交易日。")
        return

    st.caption(f"比較區間：{joined['date_base'].mode().iloc[0]} → {joined['date'].max()}（以各檔股票自己的最新一筆與倒數第 {x_days + 1} 筆交易日為準）。")

    # 各股最新一個月的官方營收年增率(往前抓3個月，晚公告的公司取它自己最新有資料的月份)。
    yoy_start = (datetime.today() - timedelta(days=100)).strftime("%Y-%m-%d")
    yoy_df = pd.DataFrame([dict(r) for r in query_timeseries_like("monthly_revenue_yoy_%", start_date=yoy_start)])
    rev_yoy_map: dict[str, float] = {}
    if not yoy_df.empty:
        yoy_df["stock_code"] = yoy_df["indicator_code"].str.replace("monthly_revenue_yoy_", "", regex=False)
        rev_yoy_map = yoy_df.sort_values("date").groupby("stock_code")["value"].last().to_dict()

    result_df = pd.DataFrame(
        {
            "股票": [_stock_link(c) for c in joined.index],
            "產業別": [industry_map.get(c) or "—" for c in joined.index],
            "當日股價": joined["close"].values,
            "股價漲跌(%)": joined["day_chg_pct"].values,
            "當日交易量(張)": (joined["volume"] / 1000).round().astype("Int64").values,
            f"{x_days}日前股價": joined["close_base"].values,
            f"{x_days}日跌幅(%)": joined["drop_pct"].values,
            "營收年增幅(%)": [rev_yoy_map.get(c) for c in joined.index],
        }
    )

    reset_page = lambda: st.session_state.update({"drop_screen_page": 1})
    dc1, dc2, _ = st.columns([1, 1, 2.6])
    with dc1:
        drop_lo = st.number_input(f"{x_days}日跌幅下限(%)", value=None, min_value=0.0, step=1.0, placeholder="不限",
                                  key=f"drop_lo_{x_days}", on_change=reset_page, help="跌幅至少要達到這個值，例如 5 代表只看跌 5% 以上")
    with dc2:
        drop_hi = st.number_input(f"{x_days}日跌幅上限(%)", value=None, min_value=0.0, step=1.0, placeholder="不限",
                                  key=f"drop_hi_{x_days}", on_change=reset_page, help="跌幅最多到這個值，例如 20 代表排除跌超過 20% 的")
    drop_col = f"{x_days}日跌幅(%)"
    if drop_lo is not None:
        result_df = result_df[result_df[drop_col] <= -drop_lo]
    if drop_hi is not None:
        result_df = result_df[result_df[drop_col] >= -drop_hi]

    result_df = _apply_price_volume_filter(result_df, key="filter_drop", with_yoy=True)
    if result_df.empty:
        st.info("目前篩選區間內沒有符合的股票，請調整股價/交易量範圍。")
        return

    page_key = "drop_screen_page"
    # 預設跌幅最大(數值最小)的排最前面；跌幅欄位的大小以「跌多少」計
    result_df = _apply_global_sort(result_df, key=f"drop_{x_days}", default_col=f"{x_days}日跌幅(%)", page_key=page_key, flip_cols=(f"{x_days}日跌幅(%)",))
    result_df = result_df.reset_index(drop=True)
    result_df.insert(0, "排名", result_df.index + 1)
    page_df = _paginate(result_df, key=page_key)
    _render_table(
        page_df,
        int_cols=["排名", "當日交易量(張)"],
        pct_cols=["股價漲跌(%)", f"{x_days}日跌幅(%)", "營收年增幅(%)"],
        price_cols=["當日股價", f"{x_days}日前股價"],
    )
    _render_pagination(result_df, key=page_key)


PLACEHOLDER = "請選擇"
DROP_SCREEN = "近X天跌幅排行股票"
SCREENS = ["連續二個月營收正成長股票", "連續三個月營收正成長股票", DROP_SCREEN]
picked_screen = st.selectbox("篩選條件", [PLACEHOLDER] + SCREENS, index=0)
active_screen = picked_screen if picked_screen != PLACEHOLDER else None

st.divider()

if active_screen is None:
    st.info("請先在上方選擇篩選條件。")
elif active_screen == DROP_SCREEN:
    st.header(active_screen)

    with st.expander("查看篩選結果", expanded=True, key="result_expander_drop"):
        _screen_price_drop_ranking()

        st.caption("資料來源同「個股分析」頁的日K（yfinance），點「股票」欄會跳到本站的「個股分析」頁並自動選中該檔股票。")
elif active_screen in ("連續二個月營收正成長股票", "連續三個月營收正成長股票"):
    n_months = 2 if active_screen == "連續二個月營收正成長股票" else 3
    st.header(active_screen)

    with st.expander("查看篩選結果", expanded=True, key=f"result_expander_{n_months}"):
        _screen_consecutive_positive_revenue_months(n_months)

        st.caption("資料來源同「個股分析」頁的月營收（MOPS 月營收歷史彙總檔），點「股票」欄會跳到本站的「個股分析」頁並自動選中該檔股票。")
