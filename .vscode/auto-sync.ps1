$repo = Split-Path -Parent $PSScriptRoot
$watcher = New-Object System.IO.FileSystemWatcher $repo
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

while ($true) {
    $change = $watcher.WaitForChanged([System.IO.WatcherChangeTypes]::All)
    if ($change.Path -match '\\.git\\|\\.vscode\\|\\build\\|__pycache__|\.pyc$|\.db$|\.sqlite') {
        continue
    }

    $status = git -C $repo status --porcelain
    if (-not $status) {
        continue
    }

    git -C $repo add -A
    $message = "Auto-sync changes $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    git -C $repo commit -m $message
    git -C $repo push origin main
}