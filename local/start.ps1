$taskPython = if ($env:LABOR_CARD_PYTHON) { $env:LABOR_CARD_PYTHON } elseif (Get-Command pythonw -ErrorAction SilentlyContinue) { (Get-Command pythonw).Source } else { (Get-Command python).Source }
$taskUrl = 'http://127.0.0.1:8766'
try { $taskHealth = Invoke-RestMethod -Uri "$taskUrl/health" -TimeoutSec 2 } catch { $taskHealth = $null }
if ($taskHealth.app -eq 'labor-card-review') {
    Start-Process $taskUrl
} else {
    Start-Process -FilePath $taskPython -ArgumentList @('"' + (Join-Path $PSScriptRoot 'server.py') + '"', '--open') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardError (Join-Path $PSScriptRoot 'server-errors.log')
}
