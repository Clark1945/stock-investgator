import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from src.db.repo import query_run_log
from src.db.schema import init_db

st.set_page_config(page_title="台股外資動向儀表板", layout="wide")

init_db()

st.title("台股外資動向儀表板")
st.markdown(
    """
本儀表板依循「外資是否會來台股」的五層判斷框架，請由左側頁面選單切換：

1. **總經/匯率層** — 決定「要不要來」
2. **相對評價層** — 決定「跟誰比」
3. **產業/基本面層** — 決定「買什麼」
4. **被動資金驅動層** — 機械式、規則透明的資金
5. **短期籌碼/程式交易層** — 日內至數日週期

標示「（代理指標）」的項目為付費資料源（EPFR、MSCI/FTSE官方權重明細、ESG評分等）的
免費近似替代，非官方原始數據，解讀時請留意誤差。
"""
)

st.subheader("最近抓取狀態")
logs = query_run_log(limit=30)
if not logs:
    st.info("尚未執行過任何 collector。請先執行：`python -m src.backfill`")
else:
    df = pd.DataFrame([dict(r) for r in logs])
    error_count = (df["status"] == "error").sum()
    if error_count:
        st.warning(f"最近 30 筆執行紀錄中有 {error_count} 筆失敗，請查看下方明細與 logs/ 目錄。")
    st.dataframe(df[["run_at", "collector", "status", "detail"]], use_container_width=True, hide_index=True)
