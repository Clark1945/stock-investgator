"""SQLite 資料庫 schema 定義與初始化。"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "invensgator.db"

DDL = """
CREATE TABLE IF NOT EXISTS timeseries (
    date            TEXT NOT NULL,
    indicator_code  TEXT NOT NULL,
    category        TEXT NOT NULL,
    label           TEXT,
    value           REAL,
    unit            TEXT,
    is_proxy        INTEGER DEFAULT 0,
    source          TEXT,
    fetched_at      TEXT,
    PRIMARY KEY (date, indicator_code)
);

CREATE INDEX IF NOT EXISTS idx_timeseries_code ON timeseries(indicator_code);
CREATE INDEX IF NOT EXISTS idx_timeseries_category ON timeseries(category);

CREATE TABLE IF NOT EXISTS taifex_options_chain (
    date            TEXT NOT NULL,
    strike          REAL NOT NULL,
    call_oi         INTEGER,
    put_oi          INTEGER,
    call_volume     INTEGER,
    put_volume      INTEGER,
    fetched_at      TEXT,
    PRIMARY KEY (date, strike)
);

CREATE TABLE IF NOT EXISTS stock_ohlc (
    date            TEXT NOT NULL,
    stock_code      TEXT NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          INTEGER,
    fetched_at      TEXT,
    PRIMARY KEY (date, stock_code)
);

CREATE INDEX IF NOT EXISTS idx_stock_ohlc_code ON stock_ohlc(stock_code);

CREATE TABLE IF NOT EXISTS company_profile (
    stock_code      TEXT PRIMARY KEY,
    name            TEXT,
    industry_code   TEXT,
    industry_name   TEXT,
    fetched_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_company_profile_industry ON company_profile(industry_name);

CREATE TABLE IF NOT EXISTS material_announcements (
    stock_code      TEXT NOT NULL,
    company_name    TEXT,
    date            TEXT NOT NULL,
    time            TEXT,
    subject         TEXT,
    detail          TEXT,
    fetched_at      TEXT,
    PRIMARY KEY (stock_code, date, time)
);

CREATE INDEX IF NOT EXISTS idx_announcements_date ON material_announcements(date);

CREATE TABLE IF NOT EXISTS investor_conferences (
    stock_code      TEXT NOT NULL,
    company_name    TEXT,
    event_date      TEXT NOT NULL,
    event_time      TEXT,
    location        TEXT,
    summary         TEXT,
    pdf_zh_url      TEXT,
    pdf_en_url      TEXT,
    ir_url          TEXT,
    video_info      TEXT,
    fetched_at      TEXT,
    PRIMARY KEY (stock_code, event_date, event_time)
);

CREATE TABLE IF NOT EXISTS manual_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    category        TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    value_text      TEXT,
    note            TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS collector_run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT,
    collector       TEXT,
    status          TEXT,
    detail          TEXT
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"資料庫已初始化: {DB_PATH}")
