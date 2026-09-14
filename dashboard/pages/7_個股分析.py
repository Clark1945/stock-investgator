import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.common import date_range_sidebar, line_chart, load_df
from src.db.repo import (
    query_company_profiles,
    query_industry_list,
    query_investor_conferences,
    query_labels_like,
    query_material_announcements,
    query_stock_ohlc,
    query_timeseries,
)

st.set_page_config(page_title="個股分析", layout="wide")
st.title("個股分析")

start_date, end_date = date_range_sidebar(default_days=620)

code_to_industry = {r["stock_code"]: r["industry_name"] for r in query_company_profiles()}

industry_options = ["全部產業"] + query_industry_list()
picked_industry = st.selectbox("篩選產業別", industry_options, index=0)

# 月營收已涵蓋全部上市公司，下拉選單直接從資料庫既有的 monthly_revenue_* 指標建立。
rev_labels = query_labels_like("monthly_revenue_%")
stock_options: dict[str, str] = {}  # 顯示文字 -> 股票代號
for code_key, label in rev_labels.items():
    if code_key.startswith("monthly_revenue_yoy_") or code_key.startswith("monthly_revenue_mom_"):
        continue
    stock_code = code_key[len("monthly_revenue_"):]
    if picked_industry != "全部產業" and code_to_industry.get(stock_code) != picked_industry:
        continue
    stock_options[(label or stock_code).replace(" 月營收", "")] = stock_code

options_sorted = sorted(stock_options.keys())

if not options_sorted:
    st.info("此產業別目前尚無任何個股資料。")
    st.stop()

# 若從「客製化搜尋」頁的連結點過來(網址帶 ?code=xxxx)，預設直接選中該檔股票。
default_label = "台積電(2330)"
query_code = st.query_params.get("code")
if query_code:
    matched = next((label for label, c in stock_options.items() if c == query_code), None)
    if matched:
        default_label = matched

default_idx = options_sorted.index(default_label) if default_label in options_sorted else 0
picked = st.selectbox("搜尋個股（輸入代號或名稱）", options_sorted, index=default_idx)

code = stock_options[picked]
st.caption(f"產業別：{code_to_industry.get(code, '未分類')}")


def _latest_value(indicator_code: str) -> float | None:
    rows = query_timeseries([indicator_code])
    return rows[-1]["value"] if rows else None


def _latest_and_change(indicator_code: str) -> tuple[float | None, float | None]:
    """回傳 (最新值, 與上一筆自行計算的變動百分比)，資料不足時對應位置回傳 None。
    僅適用於「本身沒有官方增減率欄位」的指標(如季稅後淨利)；月營收月增率請直接用
    _latest_value 讀取 monthly_revenue_mom_* (MOPS 官方數字)，不要用這裡自算的。
    """
    rows = query_timeseries([indicator_code])
    if not rows:
        return None, None
    latest = rows[-1]["value"]
    if len(rows) < 2 or not rows[-2]["value"]:
        return latest, None
    prev = rows[-2]["value"]
    return latest, (latest - prev) / abs(prev) * 100


st.subheader(f"{picked} 總覽")
col1, col2, col3, col4, col5, col6 = st.columns(6)

ohlc_rows_all = query_stock_ohlc(code)
if ohlc_rows_all:
    latest_price = ohlc_rows_all[-1]["close"]
    prev_price = ohlc_rows_all[-2]["close"] if len(ohlc_rows_all) > 1 else None
    price_change = latest_price - prev_price if prev_price is not None else None
    price_change_pct = (price_change / prev_price * 100) if prev_price else None
    price_delta = (
        f"{price_change:+.2f} ({price_change_pct:+.2f}%)" if price_change is not None else None
    )
    col1.metric(
        "股價(元)",
        f"{latest_price:,.2f}",
        price_delta,
        delta_color="inverse",  # 符合台股慣例：上漲紅色、下跌綠色，跟下方K線配色一致
    )
else:
    col1.metric("股價(元)", "無資料")

if ohlc_rows_all:
    latest_volume = ohlc_rows_all[-1]["volume"]
    prev_volume = ohlc_rows_all[-2]["volume"] if len(ohlc_rows_all) > 1 else None
    volume_delta = None
    if latest_volume is not None and prev_volume:
        volume_delta = f"{(latest_volume - prev_volume) / prev_volume * 100:+.2f}%"
    col5.metric("當日交易量(張)", f"{latest_volume / 1000:,.0f}" if latest_volume is not None else "無資料", volume_delta)
else:
    col5.metric("當日交易量(張)", "無資料")

rev = _latest_value(f"monthly_revenue_{code}")
rev_mom = _latest_value(f"monthly_revenue_mom_{code}")
if rev is not None:
    col2.metric("月營收(億元)", f"{rev / 100000:,.1f}", f"{rev_mom:+.2f}%" if rev_mom is not None else None)
else:
    col2.metric("月營收(億元)", "無資料")

ni, ni_qoq = _latest_and_change(f"net_income_{code}")
if ni is not None:
    col3.metric("季稅後淨利(億元)", f"{ni / 100000:,.1f}", f"{ni_qoq:+.2f}%" if ni_qoq is not None else None)
else:
    col3.metric("季稅後淨利(億元)", "無資料（僅電子業觀察清單7家有此資料）")

eps = _latest_value(f"eps_{code}")
col4.metric("EPS(元)", f"{eps:,.2f}" if eps is not None else "無資料")

holding_rows = query_timeseries([f"foreign_holding_ratio_{code}"])
if holding_rows:
    latest_holding = holding_rows[-1]["value"]
    prev_holding = holding_rows[-2]["value"] if len(holding_rows) > 1 else None
    holding_delta = f"{latest_holding - prev_holding:+.2f}" if prev_holding is not None else None
    col6.metric("外資持股比率(%)", f"{latest_holding:,.2f}", holding_delta)
else:
    col6.metric("外資持股比率(%)", "無資料")

st.caption("總覽卡片一律顯示資料庫中最新一筆數值，不受下方日期區間篩選影響；月增率/季增率為與前一期比較的變動百分比，外資持股比率的增減為與前一日的百分點差。")

st.divider()
st.header(f"{picked} 日K線")
ohlc_rows = query_stock_ohlc(code, start_date, end_date)
if not ohlc_rows:
    st.info("目前尚無K線資料。")
else:
    df_ohlc = pd.DataFrame([dict(r) for r in ohlc_rows])
    df_ohlc["date"] = pd.to_datetime(df_ohlc["date"])
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df_ohlc["date"],
                open=df_ohlc["open"],
                high=df_ohlc["high"],
                low=df_ohlc["low"],
                close=df_ohlc["close"],
                increasing_line_color="#ef4444",
                decreasing_line_color="#22c55e",
                name=picked,
            )
        ]
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
        yaxis_title="股價(元)",
    )
    st.plotly_chart(fig, use_container_width=True)
st.caption("日K線資料來源為 yfinance（台股代號.TW），已涵蓋全部上市公司、回補至 2025-01，並會隨每日執行自動更新。")

st.subheader(f"{picked} 近一週每日交易量")
recent_ohlc = ohlc_rows_all[-5:] if ohlc_rows_all else []
if not recent_ohlc:
    st.info("目前尚無交易量資料。")
else:
    df_vol = pd.DataFrame([dict(r) for r in recent_ohlc])
    df_vol["date"] = pd.to_datetime(df_vol["date"]).dt.strftime("%Y-%m-%d")
    df_vol["volume_lots"] = df_vol["volume"] / 1000
    fig_vol = go.Figure(
        data=[
            go.Bar(
                x=df_vol["date"],
                y=df_vol["volume_lots"],
                marker_color="#60a5fa",
                text=df_vol["volume_lots"].map(lambda v: f"{v:,.0f}"),
                textposition="outside",
            )
        ]
    )
    fig_vol.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=240,
        yaxis_title="成交量(張)",
        xaxis_type="category",
        uniformtext_minsize=10,
    )
    st.plotly_chart(fig_vol, use_container_width=True)

st.divider()
st.header(f"{picked} 三大法人買賣超")
flow_codes = [f"foreign_net_{code}", f"trust_net_{code}", f"dealer_net_{code}", f"institutional_net_{code}"]
df_flow = load_df(flow_codes, start_date, end_date)

if df_flow.empty:
    st.info("此個股目前尚無三大法人買賣超資料。")
else:
    table_flow = pd.DataFrame(
        {
            "外資(張)": df_flow[df_flow["indicator_code"] == f"foreign_net_{code}"].set_index("date")["value"] / 1000,
            "投信(張)": df_flow[df_flow["indicator_code"] == f"trust_net_{code}"].set_index("date")["value"] / 1000,
            "自營商(張)": df_flow[df_flow["indicator_code"] == f"dealer_net_{code}"].set_index("date")["value"] / 1000,
            "三大法人合計(張)": df_flow[df_flow["indicator_code"] == f"institutional_net_{code}"].set_index("date")["value"] / 1000,
        }
    )
    table_flow.index = table_flow.index.strftime("%Y-%m-%d")
    table_flow.index.name = "日期"
    table_flow = table_flow.sort_index(ascending=False).head(20)

    fmt_flow = {c: "{:+,.0f}" for c in table_flow.columns}
    st.dataframe(table_flow.style.format(fmt_flow, na_rep="—"), use_container_width=True)

st.caption(
    "三大法人買賣超資料來源為 TWSE 三大法人買賣超日報，已涵蓋全部上市普通股、回補至 2025-01，"
    "並會隨每日執行自動更新；正值代表買超、負值代表賣超，單位為張（原始股數/1000）。"
)

st.divider()
st.header(f"{picked} 外資及陸資持股比率")
holding_code = f"foreign_holding_ratio_{code}"
df_holding = load_df([holding_code], start_date, end_date)
line_chart(df_holding, holding_code, "外資及陸資持股比率(%)")
st.caption(
    "外資持股比率資料來源為 TWSE 外資及陸資持股比率統計，跟上面的「三大法人買賣超」不同——"
    "買賣超是「當日流量」，這裡是「目前存量」(外資合計持股占已發行股數的百分比)，"
    "已涵蓋全部上市普通股，並會隨每日執行自動更新。"
)

st.divider()
st.header(f"{picked} 月營收")
rev_codes = [f"monthly_revenue_{code}", f"monthly_revenue_mom_{code}", f"monthly_revenue_yoy_{code}"]
df_rev = load_df(rev_codes, start_date, end_date)

if df_rev.empty:
    st.info("目前尚無月營收資料。")
else:
    table = pd.DataFrame(
        {
            "營收(千元)": df_rev[df_rev["indicator_code"] == f"monthly_revenue_{code}"].set_index("date")["value"],
            "月增率(%)": df_rev[df_rev["indicator_code"] == f"monthly_revenue_mom_{code}"].set_index("date")["value"],
            "年增率(%)": df_rev[df_rev["indicator_code"] == f"monthly_revenue_yoy_{code}"].set_index("date")["value"],
        }
    )
    table.index = table.index.strftime("%Y-%m")
    table.index.name = "月份"
    table = table.sort_index(ascending=False)

    fmt = {"營收(千元)": "{:,.0f}", "月增率(%)": "{:+.2f}", "年增率(%)": "{:+.2f}"}
    st.dataframe(table.style.format(fmt, na_rep="—"), use_container_width=True)

st.caption(
    "月營收資料來源為 MOPS 月營收歷史彙總檔，已涵蓋全部上市公司、回補至 2025-01，"
    "並會隨每日/每月執行自動更新最新月份（最新一兩個月若尚未公告，數字會晚幾天才補齊）。"
)

st.divider()
st.header(f"{picked} 季報（毛利率 / 營業利益率 / 稅後淨利 / EPS）")
q_codes = [
    f"gross_margin_{code}",
    f"operating_margin_{code}",
    f"net_income_{code}",
    f"net_income_yoy_{code}",
    f"eps_{code}",
    f"eps_yoy_{code}",
]
df_q = load_df(q_codes, start_date, end_date)

if df_q.empty:
    st.info("此個股目前尚無季報資料——季報歷史目前僅涵蓋電子業觀察清單7家公司+2026年全市場毛利率/營業利益率，尚未完全擴大到全市場。")
else:
    def _quarter_label(d) -> str:
        q = (d.month - 1) // 3 + 1
        return f"{d.year}Q{q}"

    table_q = pd.DataFrame(
        {
            "毛利率(%)": df_q[df_q["indicator_code"] == f"gross_margin_{code}"].set_index("date")["value"],
            "營業利益率(%)": df_q[df_q["indicator_code"] == f"operating_margin_{code}"].set_index("date")["value"],
            "稅後淨利(千元)": df_q[df_q["indicator_code"] == f"net_income_{code}"].set_index("date")["value"],
            "稅後淨利年增率(%)": df_q[df_q["indicator_code"] == f"net_income_yoy_{code}"].set_index("date")["value"],
            "EPS(元)": df_q[df_q["indicator_code"] == f"eps_{code}"].set_index("date")["value"],
            "EPS年增率(%)": df_q[df_q["indicator_code"] == f"eps_yoy_{code}"].set_index("date")["value"],
        }
    )
    table_q.index = [_quarter_label(d) for d in table_q.index]
    table_q.index.name = "季別"
    table_q = table_q.sort_index(ascending=False)

    fmt_q = {
        "毛利率(%)": "{:.2f}",
        "營業利益率(%)": "{:.2f}",
        "稅後淨利(千元)": "{:,.0f}",
        "稅後淨利年增率(%)": "{:+.2f}",
        "EPS(元)": "{:.2f}",
        "EPS年增率(%)": "{:+.2f}",
    }
    st.dataframe(table_q.style.format(fmt_q, na_rep="—"), use_container_width=True)

st.caption(
    "季報資料來源為 MOPS「財務比較e點通」，已回補至 2013Q1 至今的單季數字（毛利率/營業利益率目前僅回補2026年，"
    "其餘年度可再擴大回補），並會隨每日執行自動更新最新一季；本益比因需另外抓取股價並自行換算，暫未提供。"
)

st.divider()
st.header(f"{picked} 重大訊息公告")
announcements = query_material_announcements(code, limit=20)
if not announcements:
    st.info("目前尚無重大訊息資料（此資料從系統開始執行當天起累積，無法回補過去公告）。")
else:
    for a in announcements:
        subject = (a["subject"] or "").replace("\r\n", " ").strip()
        with st.expander(f"{a['date']} {a['time']}　{subject}"):
            st.text((a["detail"] or "").replace("\r\n", "\n"))
st.caption(
    "重大訊息來源為 TWSE 每日重大訊息公告，該端點只提供「當天」全部上市公司公告，"
    "無歷史查詢，因此只會從系統開始執行的那天起逐日累積，看不到更早之前的公告。"
)

st.divider()
st.header(f"{picked} 法人說明會")
conferences = query_investor_conferences(code, limit=20)
if not conferences:
    st.info("此個股目前尚無法人說明會資料——目前僅涵蓋電子業觀察清單7家公司，尚未擴大到全市場。")
else:
    for ev in conferences:
        summary = (ev["summary"] or "").replace("\r\n", " ").strip()
        with st.expander(f"{ev['event_date']} {ev['event_time']}　{ev['location'] or ''}"):
            st.write(summary)
            links = []
            if ev["pdf_zh_url"]:
                links.append(f"[中文簡報PDF]({ev['pdf_zh_url']})")
            if ev["pdf_en_url"]:
                links.append(f"[英文簡報PDF]({ev['pdf_en_url']})")
            if ev["ir_url"] and ev["ir_url"].startswith("http"):
                links.append(f"[公司IR網站]({ev['ir_url']})")
            if links:
                st.markdown(" ｜ ".join(links))
            if ev["video_info"]:
                st.caption(ev["video_info"])
st.caption(
    "法人說明會資料來源為 MOPS 法人說明會一覽表，目前僅涵蓋電子業觀察清單7家公司；"
    "簡報PDF內容本身未解析，僅提供官方下載連結。"
)
