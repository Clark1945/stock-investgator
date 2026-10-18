"""網站載入特效：全螢幕覆蓋動畫(dashboard/assets/intro.html)，同一個瀏覽器分頁只在第一次進站時播放。

為了讓動畫「最早」開始，而不是等 Streamlit 前端載入 → 建立 websocket → 後端跑完頁面程式才出現，
這裡直接改 Streamlit 的 static/index.html：
  1. 在 <head> 放一小段同步腳本：這個分頁還沒播過動畫時，立刻把 App 藏起來、底色塗成動畫第一格的灰色，
     並把動畫(intro-overlay.html)以全螢幕 iframe 直接掛在 <html> 底下，不經過 React、不等後端。
  2. 動畫檔複製到 Streamlit 的 static 目錄(以 /intro-overlay.html 提供)。
動畫在柱子退場(露出頁面)前，會等外層 Streamlit 頁面真的渲染完才退場(見 intro.html 的 pageReady)。

若 index.html 無法寫入(唯讀環境等)，會退回舊作法：由各頁面的 show_intro() 以 components.html 播放，只是開場會慢一點。
"""

import shutil
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_INTRO_HTML = Path(__file__).resolve().parent / "assets" / "intro.html"
_STATIC_NAME = "intro-overlay.html"

_START, _END = "<!--intro-precover-start-->", "<!--intro-precover-end-->"
_HEAD_SNIPPET = (
    _START
    + '<script>try{if(!sessionStorage.getItem("introShown")){'
    'var s=document.createElement("style");s.id="intro-precover";'
    's.textContent="html,body{background:#a9aaa1!important}#root{visibility:hidden}#root iframe{visibility:visible}";'
    "document.head.appendChild(s);"
    'var f=document.createElement("iframe");f.id="intro-overlay";f.title="intro";f.src="/' + _STATIC_NAME + '";'
    'f.setAttribute("style","position:fixed;left:0;top:0;width:100vw;height:100vh;border:0;z-index:1000000;background:transparent");'
    "document.documentElement.appendChild(f);"
    'setTimeout(function(){var e=document.getElementById("intro-precover");e&&e.remove()},20000)}}catch(e){}</script>'
    + _END
)


def _patch_streamlit_static() -> None:
    """冪等地更新 streamlit/static 下的 index.html 與動畫檔；失敗就略過(退回 show_intro 的舊作法)。"""
    try:
        static = Path(st.__file__).resolve().parent / "static"
        index = static / "index.html"
        html = index.read_text(encoding="utf-8")
        if _START in html:  # 已有舊版片段：整段換成目前版本
            head, rest = html.split(_START, 1)
            html_new = head + _HEAD_SNIPPET + rest.split(_END, 1)[1]
        elif "<!--intro-precover-->" in html:  # 更早版本的單行片段
            i = html.index("<!--intro-precover-->")
            j = html.index("</script>", i) + len("</script>")
            html_new = html[:i] + _HEAD_SNIPPET + html[j:]
        else:
            html_new = html.replace("</head>", _HEAD_SNIPPET + "</head>", 1)
        if html_new != html:
            index.write_text(html_new, encoding="utf-8")
        shutil.copyfile(_INTRO_HTML, static / _STATIC_NAME)
    except Exception:
        pass


_patch_streamlit_static()


def show_intro() -> None:
    # 動畫已由 index.html 的覆蓋層播放時，這裡的 iframe 會因為 sessionStorage 已標記而立刻自行隱藏。
    components.html(_INTRO_HTML.read_text(encoding="utf-8"), height=0)
