import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df, metric_cards, multi_line_chart

st.set_page_config(page_title="二、相對評價層", layout="wide")
st.title("二、相對評價層 — 決定「跟誰比」")

start_date, end_date = date_range_sidebar()

st.header("台股估值 vs 美韓股（近似）")
codes = ["tw_market_pe_avg", "tw_market_pb_avg", "us_market_pe_snapshot", "kr_market_pe_snapshot"]
df = load_df(codes, start_date, end_date)
metric_cards(
    df,
    [
        ("tw_market_pe_avg", "台股平均本益比"),
        ("tw_market_pb_avg", "台股平均股價淨值比"),
        ("us_market_pe_snapshot", "美股本益比快照(SPY)"),
        ("kr_market_pe_snapshot", "韓股本益比快照(EWY)"),
    ],
)
c1, c2 = st.columns(2)
with c1:
    line_chart(df, "tw_market_pe_avg")
with c2:
    line_chart(df, "tw_market_pb_avg")
st.caption("美股/韓股本益比僅為即時快照(yfinance無免費歷史API)，會隨每日執行逐日累積，無法回補過去歷史。")

st.header("台積電 ADR 溢價")
codes2 = ["tsm_adr_premium_pct"]
df2 = load_df(codes2, start_date, end_date)
metric_cards(df2, [("tsm_adr_premium_pct", "ADR溢價率")])
line_chart(df2, "tsm_adr_premium_pct", "台積電ADR相對原股溢價率(%)")

st.header("半導體/競品指數")
codes3 = ["sox_index", "kospi_index", "samsung_price", "sk_hynix_price", "nasdaq_index", "nvda_price"]
df3 = load_df(codes3, start_date, end_date)
c1, c2 = st.columns(2)
with c1:
    line_chart(df3, "sox_index")
    line_chart(df3, "kospi_index")
    line_chart(df3, "nasdaq_index")
with c2:
    multi_line_chart(df3, ["samsung_price", "sk_hynix_price"], "三星 / SK海力士股價")
    line_chart(df3, "nvda_price")
