import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df, metric_cards

st.set_page_config(page_title="三、產業/基本面層", layout="wide")
st.title("三、產業/基本面層 — 決定「買什麼」")

start_date, end_date = date_range_sidebar()

st.header("全球 PMI（製造業景氣代理指標）")
df_pmi = load_df(["ism_pmi_proxy"], start_date, end_date)
metric_cards(df_pmi, [("ism_pmi_proxy", "製造業景氣代理指標")])
line_chart(df_pmi, "ism_pmi_proxy")
if df_pmi.empty:
    st.info("此指標來自 FRED，需設定 FRED_API_KEY。")
else:
    st.caption("ISM製造業PMI原始序列已被FRED下架，改用NY Fed Empire State製造業調查現況指數作為免費代理（正值多對應景氣擴張、負值對應緊縮，非0-100的ISM PMI量尺，判讀時請留意）。")

st.info("個股月營收、EPS/稅後淨利已搬到左側選單的「個股分析」頁面，可用下拉搜尋單一個股查詢。")
