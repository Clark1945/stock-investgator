import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.common import render_plotly
from src.db.repo import query_etf_dividends, query_etf_profiles, query_ohlc_for_codes_since, query_stock_ohlc

st.set_page_config(page_title="ETF", layout="wide")
from dashboard.intro import show_intro
from dashboard.theme import apply_theme

show_intro()
apply_theme()
st.title("ETF")

profiles = query_etf_profiles()
if not profiles:
    st.info("目前尚無 ETF 資料，請先執行 `python scripts/backfill_etf.py` 回補。")
    st.stop()

name_map = {r["etf_code"]: r["name"] for r in profiles}
TODAY = date.today()
TODAY_S = TODAY.strftime("%Y-%m-%d")


@st.cache_data(ttl=600)
def load_overview() -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳 (各 ETF 彙總表, 全部配息明細)。"""
    codes = list(name_map)
    since = (TODAY - timedelta(days=400)).strftime("%Y-%m-%d")
    ohlc = pd.DataFrame([dict(r) for r in query_ohlc_for_codes_since(codes, since)])
    div = pd.DataFrame([dict(r) for r in query_etf_dividends()])
    if ohlc.empty:
        return pd.DataFrame(), div

    year_ago = (TODAY - timedelta(days=365)).strftime("%Y-%m-%d")
    rows = []
    for code, g in ohlc.groupby("stock_code"):
        g = g.sort_values("date")
        last, prev = g.iloc[-1], (g.iloc[-2] if len(g) >= 2 else None)
        base = g[g["date"] <= year_ago]
        d = div[div["etf_code"] == code] if not div.empty else div
        actual = d[d["status"] == "actual"] if not d.empty else d
        ttm = actual[(actual["ex_date"] > year_ago) & (actual["ex_date"] <= TODAY_S)] if not actual.empty else actual
        ttm_sum = float(ttm["cash_dividend"].sum()) if len(ttm) else 0.0
        last_ex = actual.iloc[-1] if len(actual) else None
        rows.append({
            "代號": code,
            "名稱": name_map.get(code, ""),
            "最新價": last["close"],
            "股價漲跌(%)": (last["close"] / prev["close"] - 1) * 100 if prev is not None and prev["close"] else None,
            "成交量(張)": int(last["volume"] / 1000) if pd.notna(last["volume"]) else None,
            "近12月配息(元)": ttm_sum if ttm_sum else None,
            "近12月殖利率(%)": ttm_sum / last["close"] * 100 if ttm_sum and last["close"] else None,
            "近12月配息次數": len(ttm) if len(ttm) else None,
            "最近除息日": last_ex["ex_date"] if last_ex is not None else None,
            "最近一次配息(元)": last_ex["cash_dividend"] if last_ex is not None else None,
            "近1年股價報酬(%)": (last["close"] / base.iloc[-1]["close"] - 1) * 100 if len(base) else None,
            "資料日": last["date"],
        })
    return pd.DataFrame(rows), div


overview, all_div = load_overview()
tab_rank, tab_cal, tab_one = st.tabs(["ETF 總覽與配息排行", "除息日曆", "單檔 ETF"])

# ------------------------------------------------------------------ 總覽
with tab_rank:
    st.caption(f"共 {len(overview)} 檔台股 ETF（含債券、槓桿、主動式）。殖利率 = 近 12 個月已除息的配息合計 ÷ 最新收盤價，"
               "成立未滿一年者只計已配的部分，請搭配「配息次數」判讀。")
    c1, c2, c3, c4 = st.columns([1.4, 1, 1, 1])
    with c1:
        kw = st.text_input("搜尋代號或名稱", placeholder="例如 0056、高股息")
    with c2:
        min_yield = st.number_input("殖利率下限(%)", value=None, step=0.5, placeholder="不限")
    with c3:
        min_vol = st.number_input("成交量下限(張)", value=0, step=100)
    with c4:
        st.write("")
        only_div = st.checkbox("只看近12月有配息", value=False)

    df = overview.copy()
    if kw:
        df = df[df["代號"].str.contains(kw, case=False) | df["名稱"].str.contains(kw, case=False)]
    if only_div or min_yield is not None:
        df = df[df["近12月殖利率(%)"].notna()]
    if min_yield is not None:
        df = df[df["近12月殖利率(%)"] >= min_yield]
    if min_vol:
        df = df[df["成交量(張)"].fillna(0) >= min_vol]

    sort_cols = [c for c in df.columns if c not in ("代號", "名稱", "資料日")]
    s1, s2 = st.columns([2, 1.4])
    with s1:
        sort_col = st.selectbox("排序欄位（對全部結果排序）", sort_cols, index=sort_cols.index("近12月殖利率(%)"))
    with s2:
        desc = st.radio("排序方式", ["由大到小", "由小到大"], horizontal=True) == "由大到小"
    df = df.sort_values(sort_col, ascending=not desc, na_position="last", kind="stable").reset_index(drop=True)
    df.insert(0, "排名", df.index + 1)

    st.caption(f"符合 {len(df)} 檔，資料日 {overview['資料日'].max()}")
    st.dataframe(
        df, hide_index=True, use_container_width=True, height=620,
        column_config={
            "最新價": st.column_config.NumberColumn(format="%.2f"),
            "股價漲跌(%)": st.column_config.NumberColumn(format="%+.2f%%"),
            "成交量(張)": st.column_config.NumberColumn(format="%d"),
            "近12月配息(元)": st.column_config.NumberColumn(format="%.3f"),
            "近12月殖利率(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "近12月配息次數": st.column_config.NumberColumn(format="%d"),
            "最近一次配息(元)": st.column_config.NumberColumn(format="%.3f"),
            "近1年股價報酬(%)": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )

# ------------------------------------------------------------------ 除息日曆
with tab_cal:
    if all_div.empty:
        st.info("目前尚無配息資料。")
    else:
        price = overview.set_index("代號")["最新價"].to_dict()
        d = all_div.copy()
        d["名稱"] = d["etf_code"].map(name_map)
        d["最新價"] = d["etf_code"].map(price)
        d["單次殖利率(%)"] = d["cash_dividend"] / d["最新價"] * 100
        cols = {"ex_date": "除息日", "etf_code": "代號", "名稱": "名稱", "cash_dividend": "每單位配息(元)",
                "最新價": "最新價", "單次殖利率(%)": "單次殖利率(%)"}
        cfg = {
            "每單位配息(元)": st.column_config.NumberColumn(format="%.3f"),
            "最新價": st.column_config.NumberColumn(format="%.2f"),
            "單次殖利率(%)": st.column_config.NumberColumn(format="%.2f%%"),
        }
        up = d[d["ex_date"] >= TODAY_S].sort_values(["ex_date", "etf_code"])[list(cols)].rename(columns=cols)
        st.subheader(f"即將除息（{len(up)} 檔）")
        if up.empty:
            st.info("目前沒有已公告的未來除息。")
        else:
            st.dataframe(up, hide_index=True, use_container_width=True, column_config=cfg)
        recent = d[(d["ex_date"] < TODAY_S) & (d["ex_date"] >= (TODAY - timedelta(days=30)).strftime("%Y-%m-%d"))]
        recent = recent.sort_values(["ex_date", "etf_code"], ascending=[False, True])[list(cols)].rename(columns=cols)
        st.subheader(f"近 30 天已除息（{len(recent)} 檔）")
        st.dataframe(recent, hide_index=True, use_container_width=True, column_config=cfg)

# ------------------------------------------------------------------ 單檔
with tab_one:
    options = {f"{r['name']}({r['etf_code']})": r["etf_code"] for r in profiles}
    default = next((k for k, v in options.items() if v == "0056"), list(options)[0])
    q = st.query_params.get("etf")
    if q and q in options.values():
        default = next(k for k, v in options.items() if v == q)
    label = st.selectbox("選擇 ETF", list(options), index=list(options).index(default))
    code = options[label]

    ohlc = pd.DataFrame([dict(r) for r in query_stock_ohlc(code)])
    if ohlc.empty:
        st.info("這檔 ETF 目前沒有股價資料。")
        st.stop()
    ohlc = ohlc.sort_values("date").reset_index(drop=True)
    divs = all_div[all_div["etf_code"] == code].sort_values("ex_date") if not all_div.empty else all_div
    actual = divs[divs["status"] == "actual"] if len(divs) else divs
    row = overview[overview["代號"] == code].iloc[0]

    m = st.columns(4)
    m[0].metric("最新價", f"{row['最新價']:.2f}", f"{row['股價漲跌(%)']:+.2f}%" if pd.notna(row["股價漲跌(%)"]) else None)
    m[1].metric("近12月配息(元)", f"{row['近12月配息(元)']:.3f}" if pd.notna(row["近12月配息(元)"]) else "—")
    m[2].metric("近12月殖利率", f"{row['近12月殖利率(%)']:.2f}%" if pd.notna(row["近12月殖利率(%)"]) else "—")
    m[3].metric("近12月配息次數", f"{int(row['近12月配息次數'])}" if pd.notna(row["近12月配息次數"]) else "—")

    fig = go.Figure(go.Scatter(x=ohlc["date"], y=ohlc["close"], mode="lines", name="收盤價", line=dict(color="#B8913F", width=2)))
    if len(actual):
        px = ohlc.set_index("date")["close"]
        ex = actual[actual["ex_date"].isin(px.index)]
        fig.add_trace(go.Scatter(
            x=ex["ex_date"], y=[px[d] for d in ex["ex_date"]], mode="markers", name="除息日",
            marker=dict(color="#2B2A25", size=9, symbol="diamond"),
            text=[f"配息 {v:.3f} 元" for v in ex["cash_dividend"]], hovertemplate="%{x}<br>%{text}<extra></extra>",
        ))
    fig.update_layout(title=f"{label} 股價走勢與除息日", height=420, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=1.02, x=1, xanchor="right"), hovermode="x unified")
    render_plotly(fig, height=420)

    st.subheader("配息紀錄與填息")
    if divs is None or not len(divs):
        st.info("這檔 ETF 近 3 年沒有配息紀錄（可能是不配息或剛上市）。")
    else:
        recs = []
        for _, r in divs.sort_values("ex_date", ascending=False).iterrows():
            fill, state = None, "預告" if r["status"] == "announced" else "—"
            if r["status"] == "actual" and pd.notna(r["prev_close"]):
                after = ohlc[ohlc["date"] >= r["ex_date"]].reset_index(drop=True)
                hit = after.index[after["close"] >= r["prev_close"]]
                if len(hit):
                    fill, state = int(hit[0]) + 1, "已填息"
                else:
                    state = "未填息"
            recs.append({
                "除息日": r["ex_date"], "每單位配息(元)": r["cash_dividend"], "除息前收盤": r["prev_close"],
                "參考價": r["ref_price"],
                "單次殖利率(%)": r["cash_dividend"] / r["prev_close"] * 100 if pd.notna(r["prev_close"]) else None,
                "填息狀態": state, "填息天數(交易日)": fill,
            })
        st.caption("填息 = 除息日(含)之後，收盤價首次回到除息前收盤價；填息天數以交易日計，當天填息算第 1 天。")
        st.dataframe(pd.DataFrame(recs), hide_index=True, use_container_width=True, column_config={
            "每單位配息(元)": st.column_config.NumberColumn(format="%.3f"),
            "除息前收盤": st.column_config.NumberColumn(format="%.2f"),
            "參考價": st.column_config.NumberColumn(format="%.2f"),
            "單次殖利率(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "填息天數(交易日)": st.column_config.NumberColumn(format="%d"),
        })
