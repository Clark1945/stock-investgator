import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from src.db.repo import insert_manual_entry, query_manual_entries

st.set_page_config(page_title="人工輸入", layout="wide")
st.title("人工輸入 — 無免費結構化來源的項目")

st.markdown(
    """
以下項目沒有免費、穩定的結構化資料來源，改由此頁面手動登記：

- MSCI / FTSE 成分股權重調整公告
- AI 資本支出(CapEx) guidance（北美四大雲端業者法說會）
- 法說會展望重點
- 其他你想追蹤的質化資訊
"""
)

with st.form("manual_entry_form"):
    entry_date = st.date_input("日期", value=date.today())
    category = st.selectbox("類別", ["passive_flows", "fundamentals", "macro_fx", "relative_valuation", "chip_positioning"])
    field_name = st.text_input("項目名稱", placeholder="例如：MSCI季度調整公告 / AWS CapEx guidance")
    value_text = st.text_input("數值/內容", placeholder="例如：+2.5% 上調 / 台積電權重調升0.3%")
    note = st.text_area("備註", placeholder="可貼公告連結或摘要")
    submitted = st.form_submit_button("新增紀錄")
    if submitted:
        if not field_name:
            st.error("請填寫項目名稱")
        else:
            insert_manual_entry(entry_date.strftime("%Y-%m-%d"), category, field_name, value_text, note)
            st.success("已新增")
            st.rerun()

st.header("既有紀錄")
filter_category = st.selectbox(
    "篩選類別", ["全部", "passive_flows", "fundamentals", "macro_fx", "relative_valuation", "chip_positioning"]
)
entries = query_manual_entries(None if filter_category == "全部" else filter_category)
if entries:
    df = pd.DataFrame([dict(r) for r in entries])
    st.dataframe(df[["date", "category", "field_name", "value_text", "note"]], use_container_width=True, hide_index=True)
else:
    st.info("尚無紀錄。")
