import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df, metric_cards, multi_line_chart

st.set_page_config(page_title="一、總經/匯率層", layout="wide")
st.title("一、總經/匯率層 — 決定「要不要來」")

start_date, end_date = date_range_sidebar()

st.header("匯率與資金流動")
codes = ["usdtwd", "dxy", "foreign_net_buy_sell_proxy"]
df = load_df(codes, start_date, end_date)
metric_cards(df, [("usdtwd", "台幣兌美元"), ("dxy", "美元指數DXY"), ("foreign_net_buy_sell_proxy", "外資買賣超(代理)")])
c1, c2 = st.columns(2)
with c1:
    line_chart(df, "usdtwd")
with c2:
    line_chart(df, "dxy")
line_chart(df, "foreign_net_buy_sell_proxy")

st.header("全球資金風險偏好")
codes2 = ["vix", "us_10y_yield", "us_2y_yield", "us_yield_curve_10y_2y", "fed_rate_upper", "fed_rate_lower"]
df2 = load_df(codes2, start_date, end_date)
metric_cards(df2, [("vix", "VIX"), ("us_yield_curve_10y_2y", "10Y-2Y利差")])
c1, c2 = st.columns(2)
with c1:
    line_chart(df2, "vix")
with c2:
    multi_line_chart(df2, ["us_10y_yield", "us_2y_yield"], "美債10年期/2年期殖利率")
line_chart(df2, "us_yield_curve_10y_2y", "美債殖利率曲線利差(10Y-2Y，負值代表倒掛)")
multi_line_chart(df2, ["fed_rate_upper", "fed_rate_lower"], "Fed 利率目標區間")

if df2.empty:
    st.info("殖利率/Fed利率為 FRED 資料，需在 config/.env 設定 FRED_API_KEY 才能取得。")

st.header("新興市場資金流向（代理指標）")
codes3 = ["msci_em_proxy", "msci_asia_exjp_proxy", "ewt_volume_proxy", "aaxj_volume_proxy"]
df3 = load_df(codes3, start_date, end_date)
c1, c2 = st.columns(2)
with c1:
    line_chart(df3, "msci_em_proxy", "MSCI新興市場指數代理(EEM ETF價格)")
    line_chart(df3, "ewt_volume_proxy", "台股資金流向代理(EWT成交量)")
with c2:
    line_chart(df3, "msci_asia_exjp_proxy", "MSCI亞洲不含日代理(AAXJ ETF價格)")
    line_chart(df3, "aaxj_volume_proxy", "亞洲資金流向代理(AAXJ成交量)")
