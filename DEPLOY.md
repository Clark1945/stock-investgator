# 部署手冊：從開發機搬遷到 Linux Server (Docker)

這份手冊是給你自己手動操作用的，涵蓋「把整個系統從開發本機搬到 Linux server」的完整流程：
程式碼、機密設定、歷史資料庫、以及每日自動更新排程。

架構回顧：`docker compose up -d` 會啟動兩個 container——
- `dashboard`：跑 Streamlit 網頁，對外開 8501 port
- `scheduler`：`ofelia` 排程，每天 17:30、06:30(台北時間) 自動在 `dashboard` container 裡執行一次 `python -m src.run_daily`

歷史資料庫(`data/invensgator.db`)是掛 volume 進 container 的，**不會**被打包進 git 或 Docker image，
需要你手動搬過去一次（詳見步驟3）。

---

## 前置需求

Server 上要先裝好：
- Docker Engine
- Docker Compose plugin（`docker compose version` 能跑出版本號即可）

以及一組可以 `ssh`/`scp` 連到 server 的帳號。

---

## 步驟 1：把程式碼搬到 server

在 server 上：

```bash
git clone https://github.com/Clark1945/stock-investgator.git
cd stock-investgator
```

`data/`、`logs/`、`config/.env` 都在 `.gitignore` 裡，`git clone` 不會帶到，這是預期行為，
下面步驟會補上。

---

## 步驟 2：補上不在版控內的機密設定

本機的 `config/.env`（裡面是 `FRED_API_KEY`）需要手動複製過去：

```bash
# 在本機執行
scp config/.env your_user@your_server:/path/to/stock-investgator/config/.env
```

若沒有這個檔案，殖利率/Fed利率/ISM PMI 這幾項指標會自動略過，其餘功能不受影響。

---

## 步驟 3：搬歷史資料庫（手動、不走 git）

因為資料庫檔案會一直長大（目前約 420MB），不適合放進 git 或 Docker image，用 **直接複製檔案** 的方式搬過去最簡單可靠。

**3-1. 在本機產生一份「熱備份」**（用 SQLite 的 Online Backup API，就算當下 collector 還在背景寫入也不會拿到損毀的檔案）：

```bash
# 有安裝 sqlite3 CLI 的話：
sqlite3 data/invensgator.db ".backup data/invensgator_seed.db"

# 沒有 sqlite3 CLI 的話，用 Python 內建模組達到同樣效果：
python -c "
import sqlite3
src = sqlite3.connect('data/invensgator.db')
dst = sqlite3.connect('data/invensgator_seed.db')
with dst:
    src.backup(dst)
src.close(); dst.close()
"
```

**3-2. 把備份檔傳到 server**，注意檔名要改回 `invensgator.db`（程式固定讀這個檔名）：

```bash
scp data/invensgator_seed.db your_user@your_server:/path/to/stock-investgator/data/invensgator.db
```

**之後本機又累積了新資料、想同步到 server**，重複這兩個小步驟（backup + scp）覆蓋過去即可，
不需要額外的 dump/restore 流程。

---

## 步驟 4：建置並啟動所有服務

在 server 上：

```bash
cd /path/to/stock-investgator
docker compose up -d --build
```

第一次會需要幾分鐘 build image（安裝 requirements.txt）。

---

## 步驟 5：驗證

1. 瀏覽器打開 `http://<server_ip>:8501`，確認 Dashboard 正常顯示、且能看到步驟3搬過去的歷史資料。
2. 確認排程有正確註冊：

   ```bash
   docker compose logs scheduler
   ```

   應該會看到 ofelia 印出 `job-exec` 相關訊息，列出 `daily-update-evening`／`daily-update-morning` 兩個job。

3. 確認 dashboard container 本身正常：

   ```bash
   docker compose logs -f dashboard
   ```

4. 想確認資料庫抓取狀態，可以直接在 container 裡查：

   ```bash
   docker compose exec dashboard python -c "from src.db.repo import query_run_log; [print(dict(r)) for r in query_run_log(20)]"
   ```

---

## 日常維運

| 想做的事 | 指令 |
|---|---|
| 更新程式碼到最新版 | `git pull && docker compose up -d --build` |
| 同步本機新資料到 server | 重複步驟3的 backup + scp，覆蓋 server 上的 `data/invensgator.db` 即可，**不需要重啟 container**（每次查詢都會重新連線讀檔） |
| 看 dashboard log | `docker compose logs -f dashboard` |
| 看排程執行 log | `docker compose logs -f scheduler` |
| 不等排程、手動立即更新一次 | `docker compose exec dashboard python -m src.run_daily` |
| 全部停止 | `docker compose down` |
| 全部啟動（不重新build） | `docker compose up -d` |
| 重新 build（改了程式碼或 requirements.txt 之後） | `docker compose up -d --build` |

---

## 疑難排解

- **排程時間到了但沒有執行**：先看 `docker compose logs scheduler` 有沒有錯誤訊息；再確認
  `docker inspect stock-invensgator-dashboard` 裡的 `Labels` 有沒有正確帶到 `ofelia.job-exec.*`
  （通常是 `docker-compose.yml` 改過但沒有重新 `up -d` 套用）。
- **瀏覽器連不到 8501**：檢查 server 的防火牆/資安群組(security group)有沒有開放 8501 port 對外。
- **Dashboard 資料是舊的、看不到新抓的資料**：確認 `docker compose exec dashboard ls -la data/` 裡
  `invensgator.db` 的檔案時間是不是最新版本，很可能是步驟3的 scp 忘記做或傳錯路徑。
- **FRED 相關指標(美債殖利率/Fed利率)一直是空的**：確認 `config/.env` 有沒有正確傳到 server，且內容有填 `FRED_API_KEY`。

---

## 備用方案：不用 Docker，改用純 Linux cron

如果之後不想整個用 Docker 包起來，專案裡也準備了純 host 端 cron 的版本：

- [scripts/run_daily_cron.sh](scripts/run_daily_cron.sh)：包裝腳本，自動定位專案路徑、啟用 `.venv`（若有）、執行 `run_daily`
- [scripts/crontab.txt](scripts/crontab.txt)：對應 17:30、06:30 兩個時間點的 crontab 設定片段

這個方式下 Dashboard 本身要另外用 `systemd` service 常駐執行（`streamlit run dashboard/app.py`），
需要的話再跟我說，我可以幫你補一份 `.service` 檔案。
