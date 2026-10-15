"""網站載入特效：全螢幕覆蓋動畫(dashboard/assets/intro.html)，同一個瀏覽器分頁只在第一次進站時播放。"""

from pathlib import Path

import streamlit.components.v1 as components

_INTRO_HTML = Path(__file__).resolve().parent / "assets" / "intro.html"


def show_intro() -> None:
    components.html(_INTRO_HTML.read_text(encoding="utf-8"), height=0)
