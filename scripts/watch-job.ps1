# Watch an ingest job.
#
#   .\scripts\watch-job.ps1                 # discover and follow whatever is running
#   .\scripts\watch-job.ps1 -JobId abc123   # follow a known job
#
# Safe to run at any time: it only reads. Nothing here can disturb a running import.

param(
    [string]$JobId = "",
    [string]$Api = "http://127.0.0.1:8787",
    [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Continue"

function Get-Backend {
    try { return Invoke-RestMethod "$Api/api/health" -TimeoutSec 5 } catch { return $null }
}

function Get-Jobs {
    # /api/jobs was added after the first release; fall back gracefully.
    try { return (Invoke-RestMethod "$Api/api/jobs" -TimeoutSec 5).jobs } catch { return $null }
}

function Show-Phase {
    # What the backend is talking to says which phase it is in, even with no job id.
    $py = Get-Process python* -ErrorAction SilentlyContinue | Sort-Object CPU -Descending | Select-Object -First 1
    if (-not $py) { return "backend process not found" }
    $conns = Get-NetTCPConnection -OwningProcess $py.Id -ErrorAction SilentlyContinue |
             Where-Object { $_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::)' -and $_.RemotePort -in 80,443 }
    if (-not $conns) { return "no outbound calls - local work (scanning, thumbnails or saving)" }
    $hosts = $conns | ForEach-Object {
        try { [System.Net.Dns]::GetHostEntry($_.RemoteAddress).HostName } catch { $_.RemoteAddress }
    } | Select-Object -Unique
    $state = ($conns | Select-Object -ExpandProperty State -Unique) -join ","
    return "talking to $($hosts -join ', ') [$state]"
}

if (-not (Get-Backend)) {
    Write-Host "Backend is not reachable at $Api" -ForegroundColor Red
    exit 1
}

# Find a running job if none was named.
if (-not $JobId) {
    $jobs = Get-Jobs
    if ($jobs) {
        $running = $jobs | Where-Object { $_.status -eq "running" } | Select-Object -First 1
        if ($running) { $JobId = $running.id }
    }
}

if (-not $JobId) {
    Write-Host "No job id." -ForegroundColor Yellow
    Write-Host "  This backend predates /api/jobs, so the id lives only in the browser."
    Write-Host "  DevTools -> Network -> the POST to /api/capsules -> Response -> jobId"
    Write-Host "  Watching the filesystem instead.`n" -ForegroundColor DarkGray
}

$workspace = "$env:USERPROFILE\TravelStudio"
$cache     = "$env:USERPROFILE\.trippo\geocode-cache.sqlite"
$seen      = 0

while ($true) {
    $stamp = Get-Date -Format "HH:mm:ss"

    if ($JobId) {
        try {
            $j = Invoke-RestMethod "$Api/api/jobs/$JobId" -TimeoutSec 10
        } catch {
            Write-Host "$stamp  cannot read job $JobId" -ForegroundColor Red
            Start-Sleep -Seconds $IntervalSeconds; continue
        }
        # Only print what is new, so the log reads like a log.
        if ($j.events.Count -gt $seen) {
            $j.events[$seen..($j.events.Count - 1)] | ForEach-Object {
                $pct = if ($_.total -gt 0) { "{0,3:N0}%" -f (100 * $_.done / $_.total) } else { "    " }
                Write-Host ("{0}  {1} {2,-11} {3}" -f $stamp, $pct, $_.stage, $_.message)
            }
            $seen = $j.events.Count
        }
        if ($j.status -ne "running") {
            $colour = if ($j.status -eq "done") { "Green" } else { "Red" }
            Write-Host "`n$stamp  $($j.status.ToUpper())  $($j.error)" -ForegroundColor $colour
            if ($j.capsuleId) { Write-Host "         capsule: $workspace\$($j.capsuleId)" }
            break
        }
    }

    # Filesystem view: works with or without a job id.
    $caps = Get-ChildItem $workspace -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $capText = if ($caps) {
        $n = (Get-ChildItem $caps.FullName -Recurse -File -ErrorAction SilentlyContinue).Count
        "{0} ({1} files)" -f $caps.Name, $n
    } else { "no capsule written yet" }
    $cacheText = if (Test-Path $cache) {
        "{0:N1} MB, touched {1:HH:mm:ss}" -f ((Get-Item $cache).Length / 1MB), (Get-Item $cache).LastWriteTime
    } else { "none" }

    Write-Host ("{0}  {1}" -f $stamp, (Show-Phase)) -ForegroundColor DarkGray
    Write-Host ("          capsule: {0}   geocode cache: {1}" -f $capText, $cacheText) -ForegroundColor DarkGray

    Start-Sleep -Seconds $IntervalSeconds
}
