import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df
from src.db.repo import query_manual_entries

st.set_page_config(page_title="四、被動資金驅動層", layout="wide")
st.title("四、被動資金驅動層 — 機械式、規則透明")

start_date, end_date = date_range_sidebar()

st.header("ETF 資金流向（EPFR 代理指標）")
df = load_df(["ewt_volume_proxy", "aaxj_volume_proxy"], start_date, end_date)
c1, c2 = st.columns(2)
with c1:
    line_chart(df, "ewt_volume_proxy", "台股ETF(EWT)成交量代理")
with c2:
    line_chart(df, "aaxj_volume_proxy", "亞洲ETF(AAXJ)成交量代理")

st.header("台灣50成分股調整 / MSCI / FTSE 成分股權重調整公告（人工紀錄）")
st.caption("此類資料查證後確認無穩定的免費結構化來源（官網為前端渲染頁面），請至「人工輸入」頁面登記公告日期與重點。")
entries = query_manual_entries(category="passive_flows")
if entries:
    df_manual = pd.DataFrame([dict(r) for r in entries])
    st.dataframe(df_manual[["date", "field_name", "value_text", "note"]], use_container_width=True, hide_index=True)
else:
    st.info("目前尚無人工紀錄。")
