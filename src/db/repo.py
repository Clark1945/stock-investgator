"""資料存取共用函式：upsert / query。"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.db.schema import DB_PATH, init_db


@contextmanager
def get_connection(db_path: Path = DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_timeseries(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    """rows 每筆需含 date, indicator_code, category, value；label/unit/is_proxy/source 可選。"""
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            if r.get("value") is None:
                continue
            c.execute(
                """
                INSERT INTO timeseries (date, indicator_code, category, label, value, unit, is_proxy, source, fetched_at)
                VALUES (:date, :indicator_code, :category, :label, :value, :unit, :is_proxy, :source, :fetched_at)
                ON CONFLICT(date, indicator_code) DO UPDATE SET
                    value=excluded.value,
                    label=excluded.label,
                    unit=excluded.unit,
                    is_proxy=excluded.is_proxy,
                    source=excluded.source,
                    fetched_at=excluded.fetched_at
                """,
                {
                    "date": r["date"],
                    "indicator_code": r["indicator_code"],
                    "category": r["category"],
                    "label": r.get("label"),
                    "value": r["value"],
                    "unit": r.get("unit"),
                    "is_proxy": int(r.get("is_proxy", 0)),
                    "source": r.get("source"),
                    "fetched_at": _now_iso(),
                },
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def upsert_options_chain(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            c.execute(
                """
                INSERT INTO taifex_options_chain (date, strike, call_oi, put_oi, call_volume, put_volume, fetched_at)
                VALUES (:date, :strike, :call_oi, :put_oi, :call_volume, :put_volume, :fetched_at)
                ON CONFLICT(date, strike) DO UPDATE SET
                    call_oi=excluded.call_oi,
                    put_oi=excluded.put_oi,
                    call_volume=excluded.call_volume,
                    put_volume=excluded.put_volume,
                    fetched_at=excluded.fetched_at
                """,
                {**r, "fetched_at": _now_iso()},
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def upsert_stock_ohlc(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    """rows 每筆需含 date, stock_code, open, high, low, close, volume。"""
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            if r.get("close") is None:
                continue
            c.execute(
                """
                INSERT INTO stock_ohlc (date, stock_code, open, high, low, close, volume, fetched_at)
                VALUES (:date, :stock_code, :open, :high, :low, :close, :volume, :fetched_at)
                ON CONFLICT(date, stock_code) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    fetched_at=excluded.fetched_at
                """,
                {**r, "fetched_at": _now_iso()},
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def query_latest_stock_ohlc_bulk(stock_codes: list[str]):
    """回傳每檔股票「最新一筆」OHLC row，供篩選頁等需要多檔股票各自最新值的情境批次查詢。"""
    if not stock_codes:
        return []
    placeholders = ",".join("?" for _ in stock_codes)
    sql = f"""
        SELECT t.* FROM stock_ohlc t
        INNER JOIN (
            SELECT stock_code, MAX(date) AS max_date FROM stock_ohlc
            WHERE stock_code IN ({placeholders})
            GROUP BY stock_code
        ) latest ON t.stock_code = latest.stock_code AND t.date = latest.max_date
    """
    with get_connection() as c:
        return c.execute(sql, stock_codes).fetchall()


def query_recent_stock_ohlc_bulk(stock_codes: list[str], start_date: str):
    """回傳多檔股票在 start_date 之後的全部OHLC row(依代號、日期排序)，
    供批次計算「今日 vs 前一交易日」漲跌幅等場景使用，避免逐檔股票各自查詢。
    """
    if not stock_codes:
        return []
    placeholders = ",".join("?" for _ in stock_codes)
    sql = f"""
        SELECT * FROM stock_ohlc
        WHERE stock_code IN ({placeholders}) AND date >= ?
        ORDER BY stock_code ASC, date ASC
    """
    with get_connection() as c:
        return c.execute(sql, stock_codes + [start_date]).fetchall()


def query_stock_ohlc(stock_code: str, start_date: str | None = None, end_date: str | None = None):
    sql = "SELECT * FROM stock_ohlc WHERE stock_code=?"
    params: list = [stock_code]
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date ASC"
    with get_connection() as c:
        return c.execute(sql, params).fetchall()


def upsert_company_profile(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    """rows 每筆需含 stock_code, name, industry_code, industry_name。靜態參考資料，非時間序列。"""
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            c.execute(
                """
                INSERT INTO company_profile (stock_code, name, industry_code, industry_name, fetched_at)
                VALUES (:stock_code, :name, :industry_code, :industry_name, :fetched_at)
                ON CONFLICT(stock_code) DO UPDATE SET
                    name=excluded.name,
                    industry_code=excluded.industry_code,
                    industry_name=excluded.industry_name,
                    fetched_at=excluded.fetched_at
                """,
                {**r, "fetched_at": _now_iso()},
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def query_company_profiles(industry_name: str | None = None):
    sql = "SELECT * FROM company_profile"
    params: list = []
    if industry_name:
        sql += " WHERE industry_name = ?"
        params.append(industry_name)
    sql += " ORDER BY stock_code ASC"
    with get_connection() as c:
        return c.execute(sql, params).fetchall()


def upsert_material_announcements(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    """rows 每筆需含 stock_code, company_name, date, time, subject, detail。"""
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            c.execute(
                """
                INSERT INTO material_announcements (stock_code, company_name, date, time, subject, detail, fetched_at)
                VALUES (:stock_code, :company_name, :date, :time, :subject, :detail, :fetched_at)
                ON CONFLICT(stock_code, date, time) DO UPDATE SET
                    company_name=excluded.company_name,
                    subject=excluded.subject,
                    detail=excluded.detail,
                    fetched_at=excluded.fetched_at
                """,
                {**r, "fetched_at": _now_iso()},
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def query_material_announcements(stock_code: str, limit: int = 50):
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM material_announcements WHERE stock_code=? ORDER BY date DESC, time DESC LIMIT ?",
            (stock_code, limit),
        ).fetchall()


def upsert_investor_conferences(rows: Iterable[dict], conn: sqlite3.Connection | None = None) -> int:
    """rows 每筆需含 stock_code, company_name, event_date, event_time, location, summary,
    pdf_zh_url, pdf_en_url, ir_url, video_info。"""
    rows = list(rows)
    if not rows:
        return 0

    def _do(c: sqlite3.Connection) -> int:
        n = 0
        for r in rows:
            c.execute(
                """
                INSERT INTO investor_conferences
                    (stock_code, company_name, event_date, event_time, location, summary,
                     pdf_zh_url, pdf_en_url, ir_url, video_info, fetched_at)
                VALUES
                    (:stock_code, :company_name, :event_date, :event_time, :location, :summary,
                     :pdf_zh_url, :pdf_en_url, :ir_url, :video_info, :fetched_at)
                ON CONFLICT(stock_code, event_date, event_time) DO UPDATE SET
                    company_name=excluded.company_name,
                    location=excluded.location,
                    summary=excluded.summary,
                    pdf_zh_url=excluded.pdf_zh_url,
                    pdf_en_url=excluded.pdf_en_url,
                    ir_url=excluded.ir_url,
                    video_info=excluded.video_info,
                    fetched_at=excluded.fetched_at
                """,
                {**r, "fetched_at": _now_iso()},
            )
            n += 1
        return n

    if conn is not None:
        return _do(conn)
    with get_connection() as c:
        return _do(c)


def query_investor_conferences(stock_code: str, limit: int = 50):
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM investor_conferences WHERE stock_code=? ORDER BY event_date DESC, event_time DESC LIMIT ?",
            (stock_code, limit),
        ).fetchall()


def query_industry_list() -> list[str]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT DISTINCT industry_name FROM company_profile WHERE industry_name IS NOT NULL ORDER BY industry_name"
        ).fetchall()
        return [r["industry_name"] for r in rows]


def insert_manual_entry(date: str, category: str, field_name: str, value_text: str, note: str = "") -> None:
    with get_connection() as c:
        c.execute(
            """
            INSERT INTO manual_entries (date, category, field_name, value_text, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date, category, field_name, value_text, note, _now_iso()),
        )


def log_run(collector: str, status: str, detail: str = "") -> None:
    with get_connection() as c:
        c.execute(
            "INSERT INTO collector_run_log (run_at, collector, status, detail) VALUES (?, ?, ?, ?)",
            (_now_iso(), collector, status, detail),
        )


def query_timeseries(indicator_codes: list[str], start_date: str | None = None, end_date: str | None = None):
    """回傳 list[sqlite3.Row]，供 dashboard 轉 DataFrame 用。"""
    if not indicator_codes:
        return []
    placeholders = ",".join("?" for _ in indicator_codes)
    sql = f"SELECT * FROM timeseries WHERE indicator_code IN ({placeholders})"
    params: list = list(indicator_codes)
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date ASC"
    with get_connection() as c:
        return c.execute(sql, params).fetchall()


def query_timeseries_like(pattern: str, start_date: str | None = None, end_date: str | None = None):
    """依 indicator_code 的 SQL LIKE pattern 批次撈取多檔股票的同一指標，供客製化篩選/掃描使用，
    避免逐檔股票個別查詢資料庫造成上千次往返。"""
    sql = "SELECT * FROM timeseries WHERE indicator_code LIKE ?"
    params: list = [pattern]
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY indicator_code ASC, date ASC"
    with get_connection() as c:
        return c.execute(sql, params).fetchall()


def query_manual_entries(category: str | None = None):
    with get_connection() as c:
        if category:
            return c.execute(
                "SELECT * FROM manual_entries WHERE category=? ORDER BY date DESC", (category,)
            ).fetchall()
        return c.execute("SELECT * FROM manual_entries ORDER BY date DESC").fetchall()


def query_options_chain(date: str):
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM taifex_options_chain WHERE date=? ORDER BY strike ASC", (date,)
        ).fetchall()


def query_indicator_codes_like(pattern: str) -> list[str]:
    """回傳符合 SQL LIKE pattern 的 distinct indicator_code，供動態欄位(如各公司月營收)使用。"""
    with get_connection() as c:
        result = c.execute(
            "SELECT DISTINCT indicator_code FROM timeseries WHERE indicator_code LIKE ?", (pattern,)
        ).fetchall()
        return [r["indicator_code"] for r in result]


def query_indicator_codes_since(pattern: str, since_date: str) -> set[str]:
    """回傳符合 LIKE pattern、且在 since_date(含)之後至少有一筆資料的 distinct indicator_code，
    供「只補還沒有資料的公司/指標」這類補洞回補判斷用。"""
    with get_connection() as c:
        result = c.execute(
            "SELECT DISTINCT indicator_code FROM timeseries WHERE indicator_code LIKE ? AND date >= ?",
            (pattern, since_date),
        ).fetchall()
        return {r["indicator_code"] for r in result}


def query_labels_like(pattern: str) -> dict[str, str]:
    """回傳符合 pattern 的 distinct indicator_code -> 最新一筆的 label，供動態下拉選單(如全上市公司選擇器)使用。"""
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT t.indicator_code, t.label
            FROM timeseries t
            INNER JOIN (
                SELECT indicator_code, MAX(date) AS max_date
                FROM timeseries WHERE indicator_code LIKE ?
                GROUP BY indicator_code
            ) latest ON t.indicator_code = latest.indicator_code AND t.date = latest.max_date
            """,
            (pattern,),
        ).fetchall()
        return {r["indicator_code"]: r["label"] for r in rows}


def query_run_log(limit: int = 100):
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM collector_run_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
