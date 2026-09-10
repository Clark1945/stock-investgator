import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df, metric_cards, multi_line_chart
from src.db.repo import query_options_chain

st.set_page_config(page_title="五、短期籌碼/程式交易層", layout="wide")
st.title("五、短期籌碼/程式交易層 — 日內至數日週期")

start_date, end_date = date_range_sidebar()

st.header("期現貨價差")
codes = ["futures_spot_spread", "taiex_close", "tx_futures_close"]
df = load_df(codes, start_date, end_date)
metric_cards(df, [("futures_spot_spread", "期現貨價差")])
line_chart(df, "futures_spot_spread", "台指期現貨價差(正價差/逆價差)")
multi_line_chart(df, ["taiex_close", "tx_futures_close"], "加權指數 vs 台指期收盤")

st.header("台指期外資淨部位")
df2 = load_df(["foreign_futures_net_position"], start_date, end_date)
metric_cards(df2, [("foreign_futures_net_position", "外資淨部位(口)")])
line_chart(df2, "foreign_futures_net_position")

st.header("選擇權 Put/Call Ratio 與 Max Pain")
df3 = load_df(["put_call_ratio", "options_max_pain"], start_date, end_date)
c1, c2 = st.columns(2)
with c1:
    line_chart(df3, "put_call_ratio")
with c2:
    line_chart(df3, "options_max_pain")

st.subheader("最新一日選擇權未平倉分布（用於 Max Pain 判讀）")
lookup_date = st.date_input("查詢日期", value=date.today() - timedelta(days=1))
chain = query_options_chain(lookup_date.strftime("%Y-%m-%d"))
if chain:
    df_chain = pd.DataFrame([dict(r) for r in chain])
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_chain["strike"], y=df_chain["call_oi"], name="Call OI"))
    fig.add_trace(go.Bar(x=df_chain["strike"], y=df_chain["put_oi"], name="Put OI"))
    fig.update_layout(barmode="group", title=f"{lookup_date} 選擇權未平倉量分布", height=400)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("該日期無選擇權未平倉資料。")

st.header("融資融券 / 借券賣出餘額")
df4 = load_df(["margin_balance", "short_margin_balance", "securities_lending_balance"], start_date, end_date)
c1, c2, c3 = st.columns(3)
with c1:
    line_chart(df4, "margin_balance", "融資餘額")
with c2:
    line_chart(df4, "short_margin_balance", "融券餘額")
with c3:
    line_chart(df4, "securities_lending_balance", "借券賣出餘額")
