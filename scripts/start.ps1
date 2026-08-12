# DST Manager 本地启动、状态查询与停止脚本。

[CmdletBinding()]
param(
    [ValidateSet("Start", "Status", "Stop")]
    [string]$Action = "Start",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$NoWorker,
    [switch]$NoBrowser,
    [switch]$SkipSync,
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot ".dst-manager-data\runtime"
$statePath = Join-Path $runtimeDir "processes.json"
$listenHost = "127.0.0.1"

function Read-ProcessState {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "运行状态文件无法解析：$statePath。请检查该文件后重试。"
    }
}

function Get-ManagedProcess($Entry) {
    if ($null -eq $Entry -or $null -eq $Entry.process_id) { return $null }
    $process = Get-Process -Id ([int]$Entry.process_id) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    try {
        $expected = [DateTime]::Parse($Entry.started_at_utc).ToUniversalTime()
        $actual = $process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($actual - $expected).TotalSeconds) -gt 2) { return $null }
    }
    catch { return $null }
    return $process
}

function Test-ApiHealth([int]$HealthPort) {
    try {
        $response = Invoke-RestMethod -Uri "http://${listenHost}:$HealthPort/api/health" -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch { return $false }
}

function Show-Status {
    $state = Read-ProcessState
    if ($null -eq $state) {
        Write-Host "DST Manager 未启动。" -ForegroundColor Yellow
        return $false
    }
    $server = Get-ManagedProcess $state.server
    $worker = Get-ManagedProcess $state.worker
    $healthy = Test-ApiHealth -HealthPort ([int]$state.port)
    Write-Host "项目：$projectRoot"
    Write-Host "地址：http://${listenHost}:$($state.port)"
    Write-Host "API：$(if ($server) { "运行中（PID $($server.Id)）" } else { "未运行" })" -ForegroundColor $(if ($server -and $healthy) { "Green" } else { "Yellow" })
    Write-Host "Worker：$(if ($worker) { "运行中（PID $($worker.Id)）" } elseif ($state.worker_disabled) { "已禁用" } else { "未运行" })" -ForegroundColor $(if ($worker -or $state.worker_disabled) { "Green" } else { "Yellow" })
    Write-Host "API 健康检查：$(if ($healthy) { "通过" } else { "失败" })" -ForegroundColor $(if ($healthy) { "Green" } else { "Red" })
    Write-Host "日志目录：$runtimeDir"
    return [bool]($server -and $healthy -and ($worker -or $state.worker_disabled))
}

function Stop-ManagedProcess($Entry, [string]$Name) {
    $process = Get-ManagedProcess $Entry
    if ($null -eq $process) {
        Write-Host "$Name 未运行或 PID 已失效，跳过。" -ForegroundColor Yellow
        return
    }
    Write-Host "正在停止 $Name（PID $($process.Id)）..."
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "无法停止 $Name（PID $($process.Id)）。" }
}

function Stop-Project {
    $state = Read-ProcessState
    if ($null -eq $state) {
        Write-Host "DST Manager 未启动。" -ForegroundColor Yellow
        return
    }
    Stop-ManagedProcess $state.worker "CAD Worker"
    Stop-ManagedProcess $state.server "Web/API"
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        Remove-Item -LiteralPath $statePath -Force
    }
    Write-Host "DST Manager 已停止。日志仍保留在 $runtimeDir" -ForegroundColor Green
}

function Start-BackgroundProcess([string]$FilePath, [string[]]$Arguments, [string]$StdoutPath, [string]$StderrPath) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Start-Sleep -Milliseconds 300
    if ($process.HasExited) {
        $errorText = if (Test-Path -LiteralPath $StderrPath) { Get-Content -LiteralPath $StderrPath -Raw -Encoding UTF8 } else { "" }
        throw "后台进程启动失败（退出码 $($process.ExitCode)）：$errorText"
    }
    return $process
}

function Remove-StalePackageMetadata {
    $sitePackages = Join-Path $projectRoot ".venv\Lib\site-packages"
    if (-not (Test-Path -LiteralPath $sitePackages -PathType Container)) { return }
    $sitePackages = (Resolve-Path -LiteralPath $sitePackages).Path
    $staleEntries = Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "autocad_sheetset-*.dist-info" |
        Where-Object { $_.Name -ne "autocad_sheetset-0.2.0.dist-info" -and -not (Test-Path -LiteralPath (Join-Path $_.FullName "RECORD")) }
    foreach ($entry in $staleEntries) {
        $resolved = (Resolve-Path -LiteralPath $entry.FullName).Path
        if ((Split-Path -Parent $resolved) -ne $sitePackages -or $entry.Name -notlike "autocad_sheetset-*.dist-info") {
            throw "拒绝清理虚拟环境边界外的路径：$resolved"
        }
        Write-Host "清理缺少 RECORD 的旧包元数据：$($entry.Name)" -ForegroundColor Yellow
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

function Start-Project {
    $existing = Read-ProcessState
    if ($existing -and (Get-ManagedProcess $existing.server)) {
        Write-Host "DST Manager 已在运行；请先执行 .\scripts\start.ps1 -Action Stop。" -ForegroundColor Yellow
        Show-Status | Out-Null
        return
    }

    Push-Location $projectRoot
    try {
        . (Join-Path $PSScriptRoot "setup-env.ps1")
        Get-Command uv -ErrorAction Stop | Out-Null

        if (-not $SkipSync) {
            Write-Host "[1/4] 同步 Python 环境..." -ForegroundColor Cyan
            Remove-StalePackageMetadata
            & uv sync --dev
            if ($LASTEXITCODE -ne 0) { throw "uv sync 执行失败。" }
        }
        else { Write-Host "[1/4] 已跳过 Python 环境同步。" -ForegroundColor DarkGray }

        if (-not $SkipWebBuild) {
            # Windows PowerShell 5.1 下 npm.ps1 会把“& npm ci”误解析为“pm ci”，
            # 因此明确调用 npm.cmd，避免 Node 安装目录中的 PowerShell shim 歧义。
            $npmCommand = (Get-Command npm.cmd -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
            Write-Host "[2/4] 安装并构建 Web 前端..." -ForegroundColor Cyan
            Push-Location (Join-Path $projectRoot "web")
            try {
                & $npmCommand ci
                if ($LASTEXITCODE -ne 0) { throw "npm ci 执行失败。" }
                & $npmCommand run build
                if ($LASTEXITCODE -ne 0) { throw "Web 构建失败。" }
            }
            finally { Pop-Location }
        }
        else { Write-Host "[2/4] 已跳过 Web 构建。" -ForegroundColor DarkGray }

        Write-Host "[3/4] 升级数据库..." -ForegroundColor Cyan
        $alembicLauncher = Join-Path $projectRoot ".venv\Scripts\alembic.exe"
        if (-not (Test-Path -LiteralPath $alembicLauncher -PathType Leaf)) {
            throw "未找到 $alembicLauncher，请先移除 -SkipSync 或执行 uv sync --dev。"
        }
        & $alembicLauncher upgrade head
        if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败。" }

        $workerLabel = if ($NoWorker) { "" } else { " 与 CAD Worker" }
        Write-Host "[4/4] 启动 Web/API${workerLabel}..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        $launcher = Join-Path $projectRoot ".venv\Scripts\dst-manager.exe"
        if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
            throw "未找到 $launcher，请先移除 -SkipSync 或执行 uv sync --dev。"
        }
        $server = Start-BackgroundProcess -FilePath $launcher -Arguments @("serve", "--host", $listenHost, "--port", "$Port") -StdoutPath (Join-Path $runtimeDir "server.stdout.log") -StderrPath (Join-Path $runtimeDir "server.stderr.log")
        $worker = $null
        try {
            if (-not $NoWorker) {
                $worker = Start-BackgroundProcess -FilePath $launcher -Arguments @("worker") -StdoutPath (Join-Path $runtimeDir "worker.stdout.log") -StderrPath (Join-Path $runtimeDir "worker.stderr.log")
            }
            $state = [ordered]@{
                project_root = $projectRoot
                host = $listenHost
                port = $Port
                worker_disabled = [bool]$NoWorker
                server = [ordered]@{ process_id = $server.Id; started_at_utc = $server.StartTime.ToUniversalTime().ToString("o") }
                worker = if ($worker) { [ordered]@{ process_id = $worker.Id; started_at_utc = $worker.StartTime.ToUniversalTime().ToString("o") } } else { $null }
            }
            $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
            $ready = $false
            for ($attempt = 0; $attempt -lt 30; $attempt++) {
                if (Test-ApiHealth -HealthPort $Port) { $ready = $true; break }
                if ($server.HasExited) { break }
                Start-Sleep -Seconds 1
            }
            if (-not $ready) { throw "Web/API 在 30 秒内未通过健康检查，请查看 $runtimeDir\server.stderr.log。" }
        }
        catch {
            if ($worker -and -not $worker.HasExited) { & taskkill.exe /PID $worker.Id /T /F | Out-Null }
            if ($server -and -not $server.HasExited) { & taskkill.exe /PID $server.Id /T /F | Out-Null }
            if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath -Force }
            throw
        }

        $url = "http://${listenHost}:$Port"
        Write-Host "DST Manager 已启动：$url" -ForegroundColor Green
        Write-Host "日志目录：$runtimeDir"
        Write-Host "停止命令：.\scripts\start.ps1 -Action Stop"
        if (-not $NoBrowser) { Start-Process $url }
    }
    finally { Pop-Location }
}

switch ($Action) {
    "Start" { Start-Project }
    "Status" { Show-Status | Out-Null }
    "Stop" { Stop-Project }
}
