# 台股外資動向儀表板 (Stock Invensgator)

依循「外資是否會來台股」五層判斷框架，自動蒐集總經/匯率、相對評價、產業基本面、
被動資金驅動、短期籌碼等資料，並提供 Streamlit Dashboard 檢視。

## 1. 安裝

```bash
pip install -r requirements.txt
```

複製 `config/.env.example` 為 `config/.env`，並填入你的 FRED API Key（免費申請：
https://fred.stlouisfed.org/docs/api/api_key.html ）。若不填，美債殖利率/Fed利率/ISM PMI
這幾項會自動略過，其餘指標不受影響。

## 2. 歷史資料回補（首次使用必跑）

```bash
python -m src.backfill
```

會從 `config/settings.yaml` 的 `backfill_start_date`（預設 2026-01-01）跑到今天。
TWSE/TAIFEX 部分資料是逐日請求，數量較多（約 160+ 交易日 x 多個端點），可能需要
數分鐘到十幾分鐘，並已內建限速避免被官方網站擋下。

回補完成後，可用以下方式檢查有沒有來源抓取失敗：

```bash
python -c "from src.db.repo import query_run_log; [print(dict(r)) for r in query_run_log(50)]"
```

或直接在 Dashboard 首頁看「最近抓取狀態」表格。

## 3. 啟動 Dashboard

```bash
streamlit run dashboard/app.py
```

瀏覽器會自動開啟，左側選單可切換五大分類頁面，另有「人工輸入」頁面可登記無免費
來源的項目（MSCI/FTSE權重調整公告、AI CapEx guidance 等）。

## 4. 設定每日自動更新（Windows 工作排程器）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
```

會建立一個名為 `StockInvensgator_DailyUpdate` 的排程任務，每日 17:30（台股收盤後）
與隔日 06:30（美股收盤後）各執行一次 `python -m src.run_daily`，自動回看最近 5 天
並 upsert（不會產生重複資料，也能補上因機器關機漏掉的資料）。

也可以手動執行單次更新：

```bash
python -m src.run_daily
```

## 資料來源與已知限制

詳見專案內 `config/settings.yaml` 註解，摘要如下：

| 類別 | 可行性 |
|---|---|
| 匯率、DXY、VIX、SOX、KOSPI、三星/海力士、Nasdaq、NVDA、台積電ADR溢價 | 全自動、可回補完整歷史 |
| 美債殖利率、Fed利率目標、ISM PMI | 全自動、可回補，但需自行申請免費 FRED API Key |
| 外資買賣超（外資匯入匯出代理）、MSCI EM/亞洲指數（用EEM/AAXJ價格代理）、EPFR資金流向（用ETF成交量代理） | 近似代理指標，非官方原始數據，Dashboard上會標註 |
| 台股本益比/淨值比 | 自動回補，但為全市場個股簡單平均，非官方加權大盤本益比 |
| 美股/韓股本益比 | 僅能逐日快照累積，無法回補系統啟用前的歷史 |
| 台灣月營收、個股EPS/營收/毛利率 | 官方端點僅提供最新一期，歷史序列會隨每日/每月執行逐步累積 |
| 台指期外資淨部位、期現貨價差、put/call ratio、max pain、融資融券、借券賣出 | 全自動、可回補完整歷史（TAIFEX/TWSE官方公開資料） |
| 台灣50成分股調整、MSCI/FTSE成分股權重明細、ESG評分、法說會展望、AI CapEx guidance | 無免費結構化來源（官網為前端渲染頁面），改用 Dashboard「人工輸入」頁手動記錄 |

## 專案結構

```
config/          設定檔（tickers、API端點、回補起始日）
data/            SQLite 資料庫
src/collectors/  五大類資料收集器
src/db/          資料庫 schema 與存取
src/backfill.py  一次性歷史回補
src/run_daily.py 每日排程入口
dashboard/       Streamlit Dashboard
scripts/         Windows 工作排程器註冊腳本
logs/            每日執行紀錄
```

## 疑難排解

- 若某個 TWSE/TAIFEX 端點格式改版導致解析失敗，該 collector 會記錄 warning 並略過，
  不影響其他來源；請查看 `logs/YYYY-MM-DD.log` 或 Dashboard 首頁的「最近抓取狀態」。
- `taiwan50_constituents`（台灣50成分股）頁面若顯示無資料，通常是證交所頁面改版導致
  `pd.read_html` 解析失敗，需要更新 `src/collectors/passive_flows.py` 的表格比對邏輯。
