# Keeps Windows from sleeping while the overnight run is active (no permanent power-plan change).
# Exits when Logs/overnight/DONE exists, or after 10 hours.
param([string]$DoneFile = "D:\Projects\Resume\GraphRag-Supreme Court\Logs\overnight\DONE")

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Awake {
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
}
"@
# ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001)
$end = (Get-Date).AddHours(10)
while ((Get-Date) -lt $end -and -not (Test-Path $DoneFile)) {
    [void][Awake]::SetThreadExecutionState([uint32]2147483649)
    Start-Sleep -Seconds 30
}
[void][Awake]::SetThreadExecutionState([uint32]2147483648)  # release: ES_CONTINUOUS only
