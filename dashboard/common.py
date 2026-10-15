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
import streamlit.components.v1 as components

from src.db.repo import query_timeseries


# Plotly 預設放大/拖曳 X 軸時 Y 軸不會跟著重算，這段 JS 在 zoom/pan 後依「目前可見的資料點」重新貼合 Y 軸範圍，
# 雙擊還原時則恢復自動範圍。Streamlit 的 st.plotly_chart 沒有開放前端事件，所以改用內嵌 HTML 方式繪製。
_FIT_Y_JS = """
(function () {
  var gd = document.getElementById('{plot_id}'), busy = false;
  function ms(v) { return typeof v === 'number' ? v : new Date(v).getTime(); }
  function fit(x0, x1) {
    var lo = Infinity, hi = -Infinity;
    gd._fullData.forEach(function (t) {
      if (t.visible === false || t.visible === 'legendonly') return;
      var candle = t.type === 'candlestick', a = candle ? t.low : t.y, b = candle ? t.high : t.y, xs = t.x || [];
      if (!a || !b) return;
      for (var i = 0; i < xs.length; i++) {
        var m = ms(xs[i]);
        if (m >= x0 && m <= x1) {
          if (a[i] != null && a[i] < lo) lo = a[i];
          if (b[i] != null && b[i] > hi) hi = b[i];
        }
      }
    });
    if (lo === Infinity) return;
    var pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    busy = true;
    Plotly.relayout(gd, {'yaxis.range': [lo - pad, hi + pad]}).then(function () { busy = false; });
  }
  gd.on('plotly_relayout', function (e) {
    if (busy) return;
    if (e['xaxis.range[0]'] !== undefined) fit(ms(e['xaxis.range[0]']), ms(e['xaxis.range[1]']));
    else if (e['xaxis.range']) fit(ms(e['xaxis.range'][0]), ms(e['xaxis.range'][1]));
    else if (e['xaxis.autorange']) Plotly.relayout(gd, {'yaxis.autorange': true});
  });
})();
"""


def render_plotly(fig: go.Figure, height: int, autofit_y: bool = True) -> None:
    """繪製 Plotly 圖表；autofit_y=True 時，縮放/平移後 Y 軸會自動貼合可見範圍。"""
    # 內嵌版沒有 Streamlit 幫忙留白，邊距太小時刻度文字與軸標題會被切掉，這裡保證最小邊距並開啟 automargin
    m = fig.layout.margin
    fig.update_layout(margin=dict(l=max(m.l or 0, 64), r=max(m.r or 0, 16), t=max(m.t or 0, 44), b=max(m.b or 0, 56)))
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    html = fig.to_html(
        include_plotlyjs="cdn",
        full_html=True,
        default_width="100%",
        default_height=f"{height}px",
        config={"responsive": True, "scrollZoom": True, "displaylogo": False},
        post_script=_FIT_Y_JS if autofit_y else None,
    ).replace("<body>", '<body style="margin:0;background:#fff;border-radius:12px;overflow:hidden">', 1)
    components.html(html, height=height + 4)


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
        title=dict(text=f"{label}{'（代理指標，非官方數據）' if is_proxy else ''}", font=dict(size=14), x=0.02),
        margin=dict(l=10, r=10, t=44, b=10),
        height=320,
        showlegend=False,
    )
    render_plotly(fig, 320, autofit_y=len(sub) >= 3)


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
    fig.update_layout(
        title=dict(text=title, font=dict(size=14), x=0.02),
        margin=dict(l=10, r=10, t=44, b=10),
        height=380,
        legend=dict(orientation="h", yanchor="top", y=-0.12, x=0),  # 圖例放圖下方橫排，手機窄螢幕不會擠壓繪圖區
    )
    render_plotly(fig, 380)
