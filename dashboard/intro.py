"""網站載入特效：全螢幕覆蓋動畫(dashboard/assets/intro.html)，同一個瀏覽器分頁只在第一次進站時播放。"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_INTRO_HTML = Path(__file__).resolve().parent / "assets" / "intro.html"

# 動畫的 iframe 要等 Streamlit 把頁面腳本跑出來之後才載入，在那之前瀏覽器會先閃出
# Streamlit 自己的載入骨架(白底側邊欄 + 頁面標題)。腳本發出的任何東西都比這個骨架晚，
# 所以只能改 Streamlit 的 index.html：在 <head> 內放一小段同步腳本，若這個分頁還沒播過動畫，
# 就在第一個畫面出現前把 App 藏起來並把底色塗成動畫第一格的灰色；
# intro.html 在柱子退場(或判定不用播)時移除這個 <style id="intro-precover">，20 秒保險也會移除。
_MARK = "<!--intro-precover-->"
_HEAD_SNIPPET = (
    _MARK
    + '<script>try{if(!sessionStorage.getItem("introShown")){var s=document.createElement("style");'
    's.id="intro-precover";s.textContent="html,body{background:#a9aaa1!important}'
    '#root{visibility:hidden}#root iframe{visibility:visible}";document.head.appendChild(s);'
    'setTimeout(function(){var e=document.getElementById("intro-precover");e&&e.remove()},20000)}}catch(e){}</script>'
)


def _patch_streamlit_index() -> None:
    """冪等地把上面的片段寫進 streamlit 的 static/index.html；失敗(唯讀等)就略過，只是開場前可能多閃一下。"""
    try:
        index = Path(st.__file__).resolve().parent / "static" / "index.html"
        html = index.read_text(encoding="utf-8")
        if _MARK in html or "</head>" not in html:
            return
        index.write_text(html.replace("</head>", _HEAD_SNIPPET + "</head>", 1), encoding="utf-8")
    except Exception:
        pass


_patch_streamlit_index()


def show_intro() -> None:
    components.html(_INTRO_HTML.read_text(encoding="utf-8"), height=0)
