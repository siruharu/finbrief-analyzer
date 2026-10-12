<#
.SYNOPSIS
Registers (or removes) the two Windows Task Scheduler entries that send the briefings.

.DESCRIPTION
  .\scripts\register_tasks.ps1              # register or update finbrief-kr-open, finbrief-us-open
  .\scripts\register_tasks.ps1 -Unregister  # remove both

Times are PC-local (KST). 22:30 KST is 09:30 ET in summer and 08:30 ET in winter;
the briefing carries pre-open data either way. Rationale: docs/02_analysis/2026-10-12_local-schedule.md.
Idempotent: running it again overwrites the entries in place.
#>
[CmdletBinding()]
param(
    [switch]$Unregister,
    [string]$KrOpenAt = '09:00',
    [string]$UsOpenAt = '22:30'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $root 'scripts\run_briefing.cmd'
$tasks = @(
    @{ Name = 'finbrief-kr-open'; Slot = 'kr_open'; At = $KrOpenAt },
    @{ Name = 'finbrief-us-open'; Slot = 'us_open'; At = $UsOpenAt }
)

function Remove-TaskIfPresent([string]$Name) {
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Output "removed $Name"
    }
}

# The one-off experiment from 2026-10-08 never produced a mail; it must not linger.
Remove-TaskIfPresent 'finbrief-us-open-once'

if ($Unregister) {
    foreach ($t in $tasks) { Remove-TaskIfPresent $t.Name }
    return
}

if (-not (Test-Path $launcher)) { throw "launcher not found: $launcher" }

$weekdays = 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'
# WakeToRun: try to wake the laptop. StartWhenAvailable: if it did not wake, run as soon as it does.
# 30 minutes covers a full history refresh; the 20-minute one-off was cut short.
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

foreach ($t in $tasks) {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At $t.At
    # cmd /c ""<launcher>" <slot>" -- the outer quotes keep cmd from stripping the inner ones.
    $argument = '/c ""{0}" {1}"' -f $launcher, $t.Slot
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $argument -WorkingDirectory $root
    Register-ScheduledTask -TaskName $t.Name -Trigger $trigger -Action $action -Settings $settings `
        -Description "finbrief $($t.Slot) briefing, Mon-Fri $($t.At) PC local time" -Force | Out-Null
    Write-Output "registered $($t.Name): Mon-Fri $($t.At)"
}

foreach ($t in $tasks) {
    $task = Get-ScheduledTask -TaskName $t.Name
    $info = $task | Get-ScheduledTaskInfo
    Write-Output ('{0,-18} {1,-8} next run {2}' -f $task.TaskName, $task.State, $info.NextRunTime)
}
