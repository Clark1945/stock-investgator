#!/usr/bin/env bash
# Linux cron 用的每日更新包裝腳本，功能對應 Windows 版的 register_task_scheduler.ps1：
# 找到專案根目錄、啟用虛擬環境(若有)、執行 run_daily，並把最上層例外(例如環境本身壞掉、
# import失敗等 run_daily.py 內部 logger 都還沒建立前的錯誤)也導進 cron 專用 log，
# 方便跟 logs/ 內各 collector 自己的每日 log 分開看。
#
# 用法（在 crontab 裡指定完整路徑呼叫即可，不需要先 cd）：
#   /path/to/stock-invensgator/scripts/run_daily_cron.sh

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

mkdir -p "$PROJECT_ROOT/logs"
CRON_LOG="$PROJECT_ROOT/logs/cron.log"

{
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') cron 觸發 run_daily ====="
    # 對應 Windows工作排程器原本設定的 1小時逾時上限(ExecutionTimeLimit)
    timeout 3600 python -m src.run_daily
    exit_code=$?
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') run_daily 執行結束 (exit code ${exit_code}) ====="
    exit "$exit_code"
} >> "$CRON_LOG" 2>&1
