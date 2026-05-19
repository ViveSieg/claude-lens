param(
  [int]$Port = 7456,
  [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "server.pid"
$Script = Join-Path $Root "codex_iris.py"

if (Test-Path -LiteralPath $PidFile) {
  $existing = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($existing) {
    $proc = Get-Process -Id ([int]$existing) -ErrorAction SilentlyContinue
    if ($proc) {
      Write-Output "codex-iris already running at http://${HostAddress}:$Port (pid $existing)"
      exit 0
    }
  }
}

$python = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $python) {
  $python = (Get-Command python -ErrorAction Stop).Source
}

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $python
$psi.Arguments = '"' + $Script + '" --host "' + $HostAddress + '" --port ' + $Port
$psi.WorkingDirectory = $Root
$psi.UseShellExecute = $true
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($psi)

$proc.Id | Set-Content -LiteralPath $PidFile -Encoding ASCII
Start-Sleep -Milliseconds 700

if ((Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
  Write-Output "codex-iris started at http://${HostAddress}:$Port (pid $($proc.Id))"
} else {
  Write-Error "codex-iris failed to start"
}
