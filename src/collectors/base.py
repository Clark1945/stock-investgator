"""Collector 共用基礎設施：設定載入、HTTP session、重試/限速、交易日產生、logging。"""

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config" / "settings.yaml"
ENV_PATH = ROOT_DIR / "config" / ".env"
LOG_DIR = ROOT_DIR / "logs"

load_dotenv(ENV_PATH)


def load_settings() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


SETTINGS = load_settings()


def get_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(LOG_DIR / f"{date.today().isoformat()}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
)


RATE_LIMIT_STATUS_CODES = {428, 429}

# 連續遭遇限流(428/429)的次數，跨所有請求共用；用來讓冷卻時間隨連續被擋次數遞增。
_consecutive_blocks = 0


def _cooldown_seconds() -> float:
    return min(15 * _consecutive_blocks, 90)


def _do_request(method: str, url: str, logger: logging.Logger | None = None, **kwargs) -> requests.Response | None:
    """共用請求邏輯：一般錯誤重試+退避；遇到 428/429 限流則不做無謂重試，
    而是立即休息一段隨連續被擋次數遞增的冷卻時間後放棄本次請求，讓呼叫端的
    日期迴圈自然跳過，避免對政府網站的伺服器連續發送注定失敗的請求。
    """
    global _consecutive_blocks
    req_cfg = SETTINGS.get("request", {})
    timeout = req_cfg.get("timeout_seconds", 20)
    retries = req_cfg.get("retry_times", 3)
    backoff = req_cfg.get("retry_backoff_seconds", 2)
    rate_limit = req_cfg.get("rate_limit_seconds", 2.0)

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = _session.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            last_exc = str(e)
            if logger:
                logger.warning(f"{method}請求失敗 (第{attempt}次): {url} -> {last_exc}")
            time.sleep(backoff * attempt)
            continue

        if resp.status_code == 200:
            _consecutive_blocks = 0
            time.sleep(rate_limit)
            return resp

        if resp.status_code in RATE_LIMIT_STATUS_CODES:
            _consecutive_blocks += 1
            cooldown = _cooldown_seconds()
            if logger:
                logger.warning(
                    f"{method}請求遭遇限流 HTTP {resp.status_code}，休息 {cooldown:.0f} 秒後跳過本次請求: {url}"
                )
            time.sleep(cooldown)
            return None

        last_exc = f"HTTP {resp.status_code}"
        if logger:
            logger.warning(f"{method}請求失敗 (第{attempt}次): {url} -> {last_exc}")
        time.sleep(backoff * attempt)

    if logger:
        logger.error(f"{method}請求最終失敗: {url} -> {last_exc}")
    return None


def http_get(url: str, logger: logging.Logger | None = None, **kwargs) -> requests.Response | None:
    """帶重試/限速的 GET，失敗回傳 None（不拋例外，讓呼叫端決定如何處理）。"""
    return _do_request("GET", url, logger=logger, **kwargs)


def http_post(url: str, data: dict, logger: logging.Logger | None = None, **kwargs) -> requests.Response | None:
    """帶重試/限速的 POST，失敗回傳 None。"""
    return _do_request("POST", url, logger=logger, data=data, **kwargs)


def month_chunks(start_date: str, end_date: str) -> list[tuple[date, date]]:
    """將日期區間切成一段段「不跨月」的區間，供只接受單月區間查詢的端點使用。"""
    d0 = datetime.strptime(start_date, "%Y-%m-%d").date()
    d1 = datetime.strptime(end_date, "%Y-%m-%d").date()
    chunks = []
    cur = d0
    while cur <= d1:
        if cur.month == 12:
            next_month_start = date(cur.year + 1, 1, 1)
        else:
            next_month_start = date(cur.year, cur.month + 1, 1)
        chunk_end = min(d1, next_month_start - timedelta(days=1))
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def trading_date_range(start_date: str, end_date: str) -> list[date]:
    """回傳 start~end 之間的平日日期（不含週六日；不含台股行事曆假日，交由呼叫端容忍空資料）。"""
    d0 = datetime.strptime(start_date, "%Y-%m-%d").date()
    d1 = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = []
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def get_fred_api_key() -> str | None:
    import os

    key = os.environ.get("FRED_API_KEY", "").strip()
    return key or None
