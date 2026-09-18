# Windows 工作排程器任務：每週自動重新整理全市場季損益表金額(營業收入/營業毛利/營業利益)
#   每週一 08:00 執行一次
#
# 跟 register_task_scheduler.ps1(每日總經/籌碼面等資料，5分鐘內跑完)分開成獨立任務，
# 是因為這支腳本要對全市場992家公司逐一請求 mopsfin，跑一次要價1小時以上，季報
# 本身也只有每季公告、不需要天天更新，用「每週」頻率重跑即可自動補上新公告的季度。
#
# 使用方式（在專案根目錄以系統管理員身分開啟 PowerShell 執行）：
#   powershell -ExecutionPolicy Bypass -File scripts\register_weekly_financials_task.ps1
#
# 本腳本只會「建立/更新」這個排程任務，不會動到其他既有任務。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = (Get-Command python).Source

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "scripts\backfill_income_statement_all.py" -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 08:00

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName "StockInvensgator_WeeklyIncomeStatement" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "台股外資動向儀表板 - 全市場季損益表金額每週自動重新整理 (StockInvensgator)" `
    -Force

Write-Host "已建立/更新排程任務: StockInvensgator_WeeklyIncomeStatement（每週一 08:00 執行）"
Write-Host "可用「工作排程器」(Task Scheduler) 圖形介面查看，或執行: Get-ScheduledTask -TaskName StockInvensgator_WeeklyIncomeStatement"

