"""全站視覺主題：版型參考 Invenza 後台(Inter 字型、圓角卡片)，配色取自載入動畫「綠野幻夢」(炭黑、米色、奶白、金)。"""

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700&display=swap');

:root {
  --primary: #B8913F; --primary-dark: #967429; --primary-light: #F3EBD7;
  --dark: #2B2A25; --beige: #BDB5A1; --cream: #F7F5EF;
  --bg: #F7F5EF; --surface: #FFFFFF; --border: #E3DECF;
  --text: #2B2A25; --heading: #1C1B19; --muted: #7A7566;
  --radius-md: 12px; --radius-lg: 16px;
  --shadow-sm: 0 1px 4px rgba(43,42,37,.07); --shadow-md: 0 4px 16px rgba(43,42,37,.12);
}

html, body, [class*="st-"], .stApp, button, input, textarea {
  font-family: Inter, "Noto Sans TC", "Microsoft JhengHei", sans-serif;
}
/* 保留 Material 圖示字型，避免被上面的字型設定蓋掉變成亂碼文字 */
[data-testid="stIconMaterial"], .material-symbols-rounded { font-family: "Material Symbols Rounded" !important; }

.stApp { background: var(--bg); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 1400px; }

/* 標題 */
h1 { color: var(--heading); font-weight: 800; letter-spacing: -.01em; }
h2, h3 { color: var(--heading); font-weight: 700; letter-spacing: -.005em; }
[data-testid="stCaptionContainer"], .stCaption { color: var(--muted); }

/* 側邊欄：炭黑底、米色文字、金色高亮 */
[data-testid="stSidebar"] { background: var(--dark); border-right: 0; }
[data-testid="stSidebar"] * { color: var(--beige); }
[data-testid="stSidebarNavLink"] {
  border-radius: 10px; font-size: 14px; font-weight: 500; padding: .45rem .75rem;
  transition: background .15s, color .15s;
}
[data-testid="stSidebarNavLink"]:hover { background: rgba(247,245,239,.08); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(184,145,63,.2); font-weight: 600; }
[data-testid="stSidebarNavLink"][aria-current="page"] * { color: #E2C16F; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  font-size: 10px; letter-spacing: .8px; color: var(--beige); font-weight: 700; text-transform: uppercase;
}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] [data-baseweb="input"] { color: var(--cream); background: rgba(247,245,239,.08); }

/* 指標卡片 */
[data-testid="stMetric"] {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 1rem 1.1rem; box-shadow: var(--shadow-sm);
}
[data-testid="stMetricLabel"] { color: var(--muted); font-size: 12px; font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--heading); font-weight: 800; font-size: 1.5rem; }
[data-testid="stMetricValue"] > div { text-overflow: clip; overflow: visible; }
[data-testid="stMetric"] { padding: .85rem .9rem; }

/* 圖表、表格、展開區塊、提示框都做成卡片 */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"] {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: .5rem; box-shadow: var(--shadow-sm); overflow: hidden;
}
[data-testid="stExpander"] {
  background: var(--surface); border: 1px solid var(--border) !important; border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
[data-testid="stAlert"] { border-radius: var(--radius-md); border: 1px solid var(--border); }

/* 輸入元件 */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"], [data-testid="stNumberInput"] input {
  border-radius: 10px !important;
}
[data-baseweb="select"] > div, [data-baseweb="input"] { background: var(--surface); border-color: var(--border); }

/* 按鈕 */
.stButton > button, [data-testid="stBaseButton-secondary"] {
  border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-weight: 600;
  transition: border-color .15s, color .15s, box-shadow .15s;
}
.stButton > button:hover { border-color: var(--primary); color: var(--primary); box-shadow: var(--shadow-sm); }
[data-testid="stBaseButton-primary"] {
  border-radius: 10px; background: var(--primary); border: 1px solid var(--primary); color: #fff; font-weight: 600;
}
[data-testid="stBaseButton-primary"]:hover { background: var(--primary-dark); border-color: var(--primary-dark); color: #fff; }

hr { border-color: var(--border); }

/* 頁首橫幅 */
.hero {
  background: linear-gradient(135deg, #2B2A25 0%, #3D3A30 100%); color: var(--cream);
  border-left: 6px solid var(--primary); border-radius: 20px; padding: 1.6rem 1.8rem; margin-bottom: 1.4rem; box-shadow: var(--shadow-md);
}
.hero h1 { color: var(--cream); margin: 0 0 .35rem 0; font-size: 1.75rem; padding: 0; }
.hero p { margin: 0; color: var(--beige); font-size: .95rem; line-height: 1.6; }

/* ---------- RWD ---------- */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stExpander"] {
  box-sizing: border-box; max-width: 100%;
}
/* 分頁按鈕列在任何寬度都維持單行，不被 Streamlit 的手機版自動堆疊成直排 */
[class*="st-key-pager"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }

@media (max-width: 900px) {
  .block-container { padding: 1.4rem 1rem 3rem; }
  h1 { font-size: 1.7rem; } h2 { font-size: 1.35rem; } h3 { font-size: 1.15rem; }
}
@media (max-width: 640px) {
  .block-container { padding: 1rem .75rem 3rem; }
  h1 { font-size: 1.45rem; } h2 { font-size: 1.2rem; } h3 { font-size: 1.05rem; }
  .hero { padding: 1.1rem 1.1rem; border-radius: 16px; }
  .hero h1 { font-size: 1.25rem; } .hero p { font-size: .85rem; }
  /* 手機上欄位改成「一列兩個」而不是一個一列，指標卡片與篩選輸入框才不會變成超長直排 */
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .6rem; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width: calc(50% - .6rem) !important; flex: 1 1 calc(50% - .6rem) !important; }
  [data-testid="stMetric"] { padding: .7rem .75rem; }
  [data-testid="stMetricValue"] { font-size: 1.25rem; }
  [data-testid="stMetricLabel"] { font-size: 11px; }
  [data-testid="stPlotlyChart"], [data-testid="stDataFrame"] { padding: .25rem; border-radius: 12px; }
  /* 分頁列：左邊的空白佔位欄收掉，按鈕平均分攤整列寬度 */
  [class*="st-key-pager"] [data-testid="stHorizontalBlock"] { gap: .3rem; }
  [class*="st-key-pager"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width: 0 !important; flex: 1 1 0 !important; }
  [class*="st-key-pager"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child { display: none; }
}
</style>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "") -> None:
    """綠色漸層頁首橫幅，取代預設的純文字大標題。"""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f'<div class="hero"><h1>{title}</h1>{sub}</div>', unsafe_allow_html=True)
