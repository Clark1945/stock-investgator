"""Dashboard 頁面共用工具：sys.path 設定、資料查詢轉 DataFrame、圖表繪製。"""

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.db.repo import query_timeseries


def date_range_sidebar(default_days: int = 240):
    st.sidebar.header("日期區間")
    default_start = date.today() - timedelta(days=default_days)
    start = st.sidebar.date_input("開始日期", value=default_start, key="start_date")
    end = st.sidebar.date_input("結束日期", value=date.today(), key="end_date")
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def load_df(indicator_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    rows = query_timeseries(indicator_codes, start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["date", "indicator_code", "category", "label", "value", "unit", "is_proxy", "source"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def metric_cards(df: pd.DataFrame, codes_labels: list[tuple[str, str]]):
    if df.empty:
        st.info("目前尚無資料，請先執行 backfill 或檢查該來源是否抓取失敗。")
        return
    cols = st.columns(min(len(codes_labels), 5) or 1)
    for i, (code, fallback_label) in enumerate(codes_labels):
        sub = df[df["indicator_code"] == code].sort_values("date")
        col = cols[i % len(cols)]
        if sub.empty:
            col.metric(fallback_label, "無資料")
            continue
        last = sub.iloc[-1]
        delta = None
        if len(sub) > 1:
            prev = sub.iloc[-2]["value"]
            if prev:
                delta = f"{(last['value'] - prev):+.2f}"
        proxy_tag = "（代理指標）" if last.get("is_proxy") else ""
        unit = last.get("unit") or ""
        value_str = f"{last['value']:,.2f}" + (f" {unit}" if unit and unit != "%" else ("%" if unit == "%" else ""))
        col.metric(f"{last['label'] or fallback_label}{proxy_tag}", value_str, delta)


def line_chart(df: pd.DataFrame, code: str, title: str | None = None):
    sub = df[df["indicator_code"] == code].sort_values("date")
    if sub.empty:
        st.caption(f"「{title or code}」目前無資料")
        return
    label = title or sub.iloc[-1]["label"] or code
    is_proxy = bool(sub.iloc[-1].get("is_proxy"))
    unit = sub.iloc[-1].get("unit") or ""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["date"], y=sub["value"], mode="lines+markers", name=label))
    fig.update_xaxes(type="date")
    if unit:
        fig.update_yaxes(title_text=unit)
    if len(sub) < 3:
        # 資料點太少時，plotly 會把 y 軸自動縮放到緊貼數值的極窄區間（甚至縮到小數點後幾位），
        # 看起來像一條「平線」或軸刻度異常，其實只是還沒累積足夠歷史，這裡強制從 0 起算給出正確比例尺。
        v = float(sub.iloc[-1]["value"])
        lo, hi = min(0.0, v), max(0.0, v)
        pad = max(abs(v) * 0.15, 1.0)
        fig.update_yaxes(range=[lo - pad if lo < 0 else 0, hi + pad])
        st.caption(f"目前僅有 {len(sub)} 筆資料點，尚未累積足夠歷史走勢，會隨每日/每月排程逐步增加。")
    fig.update_layout(
        title=f"{label}{'（代理指標，非官方數據）' if is_proxy else ''}",
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)


def multi_line_chart(df: pd.DataFrame, codes: list[str], title: str):
    sub = df[df["indicator_code"].isin(codes)]
    if sub.empty:
        st.caption(f"「{title}」目前無資料")
        return
    fig = go.Figure()
    for code in codes:
        s = sub[sub["indicator_code"] == code].sort_values("date")
        if s.empty:
            continue
        label = s.iloc[-1]["label"] or code
        fig.add_trace(go.Scatter(x=s["date"], y=s["value"], mode="lines+markers", name=label))
    fig.update_xaxes(type="date")
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=40, b=10), height=380)
    st.plotly_chart(fig, use_container_width=True)
