# Windows 工作排程器任務：每日自動執行 src/run_daily.py 兩次
#   17:30 (台股收盤後)
#   06:30 (美股/美債等總經資料前一晚收盤，隔日台灣時間更新)
#
# 使用方式（在專案根目錄以系統管理員身分開啟 PowerShell 執行）：
#   powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
#
# 本腳本只會「建立/更新」排程任務，不會刪除其他既有任務。
# 執行前請先確認 python 已安裝好 requirements.txt 內的套件。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = (Get-Command python).Source

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m src.run_daily" -WorkingDirectory $ProjectRoot

$Trigger1 = New-ScheduledTaskTrigger -Daily -At 17:30
$Trigger2 = New-ScheduledTaskTrigger -Daily -At 06:30

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "StockInvensgator_DailyUpdate" `
    -Action $Action `
    -Trigger @($Trigger1, $Trigger2) `
    -Settings $Settings `
    -Description "台股外資動向儀表板 - 每日資料自動更新 (StockInvensgator)" `
    -Force

Write-Host "已建立/更新排程任務: StockInvensgator_DailyUpdate（每日 17:30 及 06:30 執行）"
Write-Host "可用「工作排程器」(Task Scheduler) 圖形介面查看，或執行: Get-ScheduledTask -TaskName StockInvensgator_DailyUpdate"
