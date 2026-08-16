# DST Manager 本地启动、状态查询、日志查看与停止脚本。

[CmdletBinding()]
param(
    [ValidateSet("Start", "Status", "Stop", "Logs")]
    [string]$Action = "Start",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$NoWorker,
    [switch]$NoBrowser,
    [switch]$SkipSync,
    [switch]$SkipWebBuild,
    [ValidateRange(1, 1000)]
    [int]$LogTail = 80
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$runtimeDir = Join-Path $projectRoot ".dst-manager-data\runtime"
$statePath = Join-Path $runtimeDir "processes.json"
$pythonLauncher = Join-Path $projectRoot ".venv\Scripts\python.exe"
$listenHost = "127.0.0.1"

function ConvertTo-NormalizedPath([string]$PathValue) {
    return [System.IO.Path]::GetFullPath($PathValue).TrimEnd('\').ToLowerInvariant()
}

function Quote-ProcessArgument([string]$Value) {
    if ($Value -match '[\s"]') { return '"' + $Value.Replace('"', '\"') + '"' }
    return $Value
}

function Write-JsonFile([string]$PathValue, $Value) {
    $parent = Split-Path -Parent $PathValue
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$PathValue.tmp"
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $PathValue -Force
}

function Read-JsonFile([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $PathValue -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw "运行状态文件无法解析：$PathValue。请检查该文件后重试。" }
}

function Read-ProcessState { return Read-JsonFile $statePath }

function Get-ProcessRecord([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Test-ProjectCommandLine([string]$CommandLine, [ValidateSet("server", "worker")][string]$CommandType) {
    if (-not $CommandLine) { return $false }
    $rootPattern = [Regex]::Escape((ConvertTo-NormalizedPath $projectRoot))
    $normalized = $CommandLine.ToLowerInvariant()
    $modulePattern = if ($CommandType -eq "server") { '-m\s+dst_manager\.interfaces\.cli\s+serve(?:\s|$)' } else { '-m\s+dst_manager\.interfaces\.cli\s+worker(?:\s|$)' }
    $legacyPattern = if ($CommandType -eq "server") { 'dst-manager(?:\.exe)?["'']?\s+serve(?:\s|$)' } else { 'dst-manager(?:\.exe)?["'']?\s+worker(?:\s|$)' }
    return ($normalized -match $rootPattern) -and (($normalized -match $modulePattern) -or ($normalized -match $legacyPattern))
}

function Get-ProjectProcesses([ValidateSet("server", "worker")][string]$CommandType) {
    $matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        Test-ProjectCommandLine -CommandLine $_.CommandLine -CommandType $CommandType
    })
    $matchedIds = @{}
    foreach ($record in $matches) { $matchedIds[[int]$record.ProcessId] = $true }
    return @($matches | Where-Object { -not $matchedIds.ContainsKey([int]$_.ParentProcessId) })
}

function Test-IsDescendant([int]$ProcessId, [int]$RootProcessId) {
    $seen = @{}
    $current = Get-ProcessRecord $ProcessId
    while ($current -and -not $seen.ContainsKey([int]$current.ProcessId)) {
        if ([int]$current.ProcessId -eq $RootProcessId) { return $true }
        $seen[[int]$current.ProcessId] = $true
        if (-not $current.ParentProcessId) { break }
        $current = Get-ProcessRecord ([int]$current.ParentProcessId)
    }
    return $false
}

function Get-ProcessTreeLeaf([int]$RootProcessId, [ValidateSet("server", "worker")][string]$CommandType) {
    $matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        (Test-ProjectCommandLine -CommandLine $_.CommandLine -CommandType $CommandType) -and (Test-IsDescendant ([int]$_.ProcessId) $RootProcessId)
    })
    if (-not $matches.Count) { return $null }
    $parentIds = @{}
    foreach ($record in $matches) { $parentIds[[int]$record.ParentProcessId] = $true }
    return $matches | Where-Object { -not $parentIds.ContainsKey([int]$_.ProcessId) } | Select-Object -First 1
}

function Get-ManagedProcess($Entry) {
    if ($null -eq $Entry -or $null -eq $Entry.process_id -or $null -eq $Entry.command_type) { return $null }
    $record = Get-ProcessRecord ([int]$Entry.process_id)
    if ($null -eq $record -or -not (Test-ProjectCommandLine $record.CommandLine ([string]$Entry.command_type))) { return $null }
    try {
        $process = Get-Process -Id ([int]$Entry.process_id) -ErrorAction Stop
        $expected = if ($Entry.started_at_utc -is [DateTime]) {
            ([DateTime]$Entry.started_at_utc).ToUniversalTime()
        }
        else {
            [DateTimeOffset]::Parse([string]$Entry.started_at_utc).UtcDateTime
        }
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -gt 2) { return $null }
        return $record
    }
    catch { return $null }
}

function Get-PortOwner([int]$TargetPort) {
    $command = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($command) {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $TargetPort -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    }
    foreach ($line in (& netstat.exe -ano -p tcp 2>$null)) {
        if ($line -match "^\s*TCP\s+(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]):$TargetPort\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Get-RunIdFromCommandLine([string]$CommandLine) {
    if ($CommandLine -match '--run-id\s+(?:"([^"]+)"|(\S+))') {
        if ($Matches[1]) { return $Matches[1] }
        return $Matches[2]
    }
    return $null
}

function Test-ApiHealth([int]$HealthPort, [string]$ExpectedRunId) {
    try {
        $response = Invoke-RestMethod -Uri "http://${listenHost}:$HealthPort/api/health" -TimeoutSec 2
        return $response.status -eq "ok" -and [string]$response.run_id -eq $ExpectedRunId
    }
    catch { return $false }
}

function New-ProcessEntry($Record, [string]$CommandType) {
    $process = Get-Process -Id ([int]$Record.ProcessId) -ErrorAction Stop
    return [ordered]@{
        process_id = [int]$Record.ProcessId
        started_at_utc = $process.StartTime.ToUniversalTime().ToString("o")
        command_type = $CommandType
        command_line = [string]$Record.CommandLine
    }
}

function Test-Utf8LogFile([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) { return }
    $bytes = [System.IO.File]::ReadAllBytes($PathValue)
    $decoder = New-Object System.Text.UTF8Encoding($false, $true)
    try { $text = $decoder.GetString($bytes) }
    catch { throw "日志不是严格 UTF-8：$PathValue" }
    foreach ($character in $text.ToCharArray()) {
        $code = [int][char]$character
        if (($code -lt 32 -and $code -notin @(9, 10, 13)) -or $code -eq 127) {
            throw "日志包含非法控制字符 U+$($code.ToString('X4'))：$PathValue"
        }
    }
}

function ConvertTo-SafeLogText([string]$Text) {
    $builder = New-Object System.Text.StringBuilder
    foreach ($character in $Text.ToCharArray()) {
        $code = [int][char]$character
        if (($code -lt 32 -and $code -notin @(9, 10, 13)) -or $code -eq 127) {
            [void]$builder.Append("\x$($code.ToString('x2'))")
        }
        else { [void]$builder.Append($character) }
    }
    return $builder.ToString()
}

function Convert-LegacyRuntimeLogs {
    if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) { return }
    $legacyLogs = @(Get-ChildItem -LiteralPath $runtimeDir -File -Filter "*.log")
    if (-not $legacyLogs.Count) { return }
    $legacyId = "legacy-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $legacyDir = Join-Path $runtimeDir $legacyId
    New-Item -ItemType Directory -Path $legacyDir -Force | Out-Null
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $outputUtf8 = New-Object System.Text.UTF8Encoding($false)
    $ansiCodePage = [Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
    $ansiEncoding = [Text.Encoding]::GetEncoding($ansiCodePage)
    $converted = [ordered]@{}
    foreach ($log in $legacyLogs) {
        if ((ConvertTo-NormalizedPath $log.DirectoryName) -ne (ConvertTo-NormalizedPath $runtimeDir)) { throw "拒绝迁移运行目录边界外的日志：$($log.FullName)" }
        $bytes = [IO.File]::ReadAllBytes($log.FullName)
        try { $text = $strictUtf8.GetString($bytes) }
        catch { $text = $ansiEncoding.GetString($bytes) }
        $text = ConvertTo-SafeLogText $text
        $rawPath = Join-Path $legacyDir ($log.Name + ".legacy.bin")
        $textPath = Join-Path $legacyDir $log.Name
        Move-Item -LiteralPath $log.FullName -Destination $rawPath
        [IO.File]::WriteAllText($textPath, $text, $outputUtf8)
        Test-Utf8LogFile $textPath
        $converted[$log.Name] = $textPath
    }
    $metadata = [ordered]@{
        run_id = $legacyId; status = "stopped"; started_at_utc = [DateTime]::UtcNow.ToString("o")
        stopped_at_utc = [DateTime]::UtcNow.ToString("o"); project_root = $projectRoot; run_dir = $legacyDir
        logs = $converted; server = $null; worker = $null; note = "v0.2.1 自动迁移的旧运行日志；原始字节保留为 .legacy.bin"
    }
    Write-JsonFile (Join-Path $legacyDir "run.json") $metadata
}

function Get-RunLogPaths($State) {
    if ($null -eq $State -or $null -eq $State.logs) { return @() }
    return @($State.logs.startup, $State.logs.server_stdout, $State.logs.server_stderr, $State.logs.worker_stdout, $State.logs.worker_stderr) | Where-Object { $_ }
}

function Get-LatestRunState {
    $current = Read-ProcessState
    if ($current) { return $current }
    if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) { return $null }
    $latest = Get-ChildItem -LiteralPath $runtimeDir -Directory | Sort-Object LastWriteTimeUtc -Descending | ForEach-Object {
        $metadata = Read-JsonFile (Join-Path $_.FullName "run.json")
        if ($metadata) { $metadata; return }
    } | Select-Object -First 1
    return $latest
}

function Show-Logs {
    $state = Get-LatestRunState
    if (-not $state) {
        Write-Host "尚无运行日志。" -ForegroundColor Yellow
        return
    }
    Write-Host "运行：$($state.run_id)"
    Write-Host "日志目录：$($state.run_dir)"
    $active = [bool]((Get-ManagedProcess $state.server) -or (Get-ManagedProcess $state.worker))
    foreach ($path in Get-RunLogPaths $state) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        if (-not $active) { Test-Utf8LogFile $path }
        Write-Host "`n===== $([System.IO.Path]::GetFileName($path)) =====" -ForegroundColor Cyan
        Get-Content -LiteralPath $path -Encoding UTF8 -Tail $LogTail
    }
}

function Show-Status {
    $state = Read-ProcessState
    $statusPort = if ($state -and $state.port) { [int]$state.port } else { $Port }
    $portOwner = Get-PortOwner $statusPort
    $servers = Get-ProjectProcesses "server"
    $workers = Get-ProjectProcesses "worker"
    if (-not $state) {
        Write-Host "项目：$projectRoot"
        if ($servers.Count) {
            Write-Host "API：发现 $($servers.Count) 个本项目遗留实例" -ForegroundColor Red
        }
        elseif ($portOwner) {
            $owner = Get-ProcessRecord $portOwner
            $label = if ($owner -and (Test-ProjectCommandLine $owner.CommandLine "server")) { "端口被本项目遗留 API 占用" } else { "端口被未知进程占用" }
            Write-Host "API：$label（PID $portOwner）" -ForegroundColor Red
        }
        else { Write-Host "API：未运行" -ForegroundColor Yellow }
        Write-Host "Worker：$(if ($workers.Count) { "发现 $($workers.Count) 个遗留实例" } else { "未运行" })" -ForegroundColor $(if ($workers.Count) { "Red" } else { "Yellow" })
        return $false
    }
    $server = Get-ManagedProcess $state.server
    $worker = Get-ManagedProcess $state.worker
    $healthy = $false
    if ($server) { $healthy = Test-ApiHealth ([int]$state.port) ([string]$state.run_id) }
    Write-Host "项目：$projectRoot"
    Write-Host "运行：$($state.run_id)"
    Write-Host "地址：http://${listenHost}:$($state.port)"
    Write-Host "API：$(if ($server) { "运行中（PID $($server.ProcessId)）" } else { "状态文件失效" })" -ForegroundColor $(if ($server -and $healthy) { "Green" } else { "Red" })
    Write-Host "Worker：$(if ($worker) { "运行中（PID $($worker.ProcessId)）" } elseif ($state.worker_disabled) { "已禁用" } else { "状态文件失效" })" -ForegroundColor $(if ($worker -or $state.worker_disabled) { "Green" } else { "Red" })
    if ($servers.Count -gt 1) { Write-Host "异常：存在重复 API（$($servers.Count) 个）。" -ForegroundColor Red }
    if ($workers.Count -gt 1) { Write-Host "异常：存在重复 Worker（$($workers.Count) 个）。" -ForegroundColor Red }
    if ($portOwner -and $server -and -not (Test-IsDescendant ([int]$portOwner) ([int]$server.ProcessId))) { Write-Host "异常：端口由其他 PID $portOwner 监听。" -ForegroundColor Red }
    Write-Host "API 健康检查/run_id：$(if ($healthy) { "通过" } else { "失败" })" -ForegroundColor $(if ($healthy) { "Green" } else { "Red" })
    Write-Host "日志目录：$($state.run_dir)"
    return [bool]($server -and $healthy -and ($worker -or $state.worker_disabled) -and $servers.Count -le 1 -and $workers.Count -le 1)
}

function Stop-ProcessTree($Record, [string]$Name) {
    if (-not $Record) { return }
    Write-Host "正在停止 $Name（PID $($Record.ProcessId)）..."
    & taskkill.exe /PID ([int]$Record.ProcessId) /T /F | Out-Null
    if ($LASTEXITCODE -ne 0 -and (Get-ProcessRecord ([int]$Record.ProcessId))) { throw "无法停止 $Name（PID $($Record.ProcessId)）。" }
}

function Remove-RunDirectorySafely([string]$Target) {
    $resolvedRuntime = ConvertTo-NormalizedPath $runtimeDir
    $resolvedTarget = ConvertTo-NormalizedPath $Target
    if ((Split-Path -Parent $resolvedTarget) -ne $resolvedRuntime) { throw "拒绝清理运行日志边界外的路径：$Target" }
    Remove-Item -LiteralPath $Target -Recurse -Force
}

function Remove-ExpiredRunLogs {
    if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) { return }
    $directories = @(Get-ChildItem -LiteralPath $runtimeDir -Directory | Sort-Object LastWriteTimeUtc -Descending)
    $total = [int64]0
    for ($index = 0; $index -lt $directories.Count; $index++) {
        $directory = $directories[$index]
        $metadata = Read-JsonFile (Join-Path $directory.FullName "run.json")
        $active = $false
        if ($metadata) { $active = [bool]((Get-ManagedProcess $metadata.server) -or (Get-ManagedProcess $metadata.worker)) }
        $size = [int64](Get-ChildItem -LiteralPath $directory.FullName -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
        $total += $size
        if (-not $active -and ($index -ge 20 -or $total -gt 512MB)) { Remove-RunDirectorySafely $directory.FullName }
    }
}

function Stop-Project {
    $state = Read-ProcessState
    $portToCheck = if ($state) { [int]$state.port } else { $Port }
    $targets = @{}
    if ($state) {
        foreach ($entry in @($state.worker, $state.server)) {
            $record = Get-ManagedProcess $entry
            if ($record) { $targets[[int]$record.ProcessId] = $record }
        }
    }
    foreach ($record in @(Get-ProjectProcesses "worker") + @(Get-ProjectProcesses "server")) { $targets[[int]$record.ProcessId] = $record }
    foreach ($record in $targets.Values) {
        $name = if (Test-ProjectCommandLine $record.CommandLine "worker") { "CAD Worker" } else { "Web/API" }
        Stop-ProcessTree $record $name
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline -and ((Get-ProjectProcesses "server").Count -or (Get-ProjectProcesses "worker").Count)) { Start-Sleep -Milliseconds 250 }
    if ((Get-ProjectProcesses "server").Count -or (Get-ProjectProcesses "worker").Count) { throw "停止后仍存在本项目 API 或 Worker 进程。" }
    $owner = Get-PortOwner $portToCheck
    if ($owner -and $targets.ContainsKey([int]$owner)) { throw "停止后端口 $portToCheck 仍未释放。" }
    if ($state) {
        if ($state.PSObject.Properties.Name -contains "status") { $state.status = "stopped" }
        else { $state | Add-Member -NotePropertyName status -NotePropertyValue "stopped" }
        $stoppedAt = [DateTime]::UtcNow.ToString("o")
        if ($state.PSObject.Properties.Name -contains "stopped_at_utc") { $state.stopped_at_utc = $stoppedAt }
        else { $state | Add-Member -NotePropertyName stopped_at_utc -NotePropertyValue $stoppedAt }
        if ($state.run_dir) { Write-JsonFile (Join-Path $state.run_dir "run.json") $state }
        foreach ($path in Get-RunLogPaths $state) { Test-Utf8LogFile $path }
    }
    if (Test-Path -LiteralPath $statePath -PathType Leaf) { Remove-Item -LiteralPath $statePath -Force }
    Remove-ExpiredRunLogs
    Write-Host "DST Manager 已停止，项目 API/Worker 已清空。" -ForegroundColor Green
}

function Start-BackgroundProcess([string[]]$Arguments, [string]$StdoutPath, [string]$StderrPath) {
    New-Item -ItemType File -Path $StdoutPath -Force | Out-Null
    New-Item -ItemType File -Path $StderrPath -Force | Out-Null
    $process = Start-Process -FilePath $pythonLauncher -ArgumentList $Arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Start-Sleep -Milliseconds 400
    if ($process.HasExited) {
        $errorText = Get-Content -LiteralPath $StderrPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        throw "后台进程启动失败（退出码 $($process.ExitCode)）：$errorText"
    }
    return $process
}

function Remove-StalePackageMetadata {
    $sitePackages = Join-Path $projectRoot ".venv\Lib\site-packages"
    if (-not (Test-Path -LiteralPath $sitePackages -PathType Container)) { return }
    $resolvedSitePackages = (Resolve-Path -LiteralPath $sitePackages).Path
    $staleEntries = Get-ChildItem -LiteralPath $resolvedSitePackages -Directory -Filter "autocad_sheetset-*.dist-info" | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $_.FullName "RECORD"))
    }
    foreach ($entry in $staleEntries) {
        $resolved = (Resolve-Path -LiteralPath $entry.FullName).Path
        if ((Split-Path -Parent $resolved) -ne $resolvedSitePackages -or $entry.Name -notlike "autocad_sheetset-*.dist-info") { throw "拒绝清理虚拟环境边界外的路径：$resolved" }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

function Save-StartupFailure([string]$Reason, [string]$RunId, [string]$RunDir, $Logs, [int]$TargetPort, [bool]$WorkerDisabled) {
    "[$([DateTime]::UtcNow.ToString('o'))] 启动失败：$Reason" | Add-Content -LiteralPath $Logs.startup -Encoding UTF8
    $failureState = [ordered]@{
        run_id = $RunId; status = "failed"; started_at_utc = [DateTime]::UtcNow.ToString("o")
        project_root = $projectRoot; host = $listenHost; port = $TargetPort; worker_disabled = $WorkerDisabled
        run_dir = $RunDir; logs = $Logs; server = $null; worker = $null
    }
    Write-JsonFile (Join-Path $RunDir "run.json") $failureState
    Test-Utf8LogFile $Logs.startup
    return "$Reason；启动日志：$($Logs.startup)"
}

function Start-Project {
    Convert-LegacyRuntimeLogs
    $existingState = Read-ProcessState
    if ($existingState) {
        $existingServer = Get-ManagedProcess $existingState.server
        $existingWorker = Get-ManagedProcess $existingState.worker
        $workerReady = [bool]($existingState.worker_disabled -or $existingWorker)
        if ($existingServer -and $workerReady -and (Test-ApiHealth ([int]$existingState.port) ([string]$existingState.run_id))) {
            Write-Host "DST Manager 已启动，本次不创建新进程。" -ForegroundColor Yellow
            Show-Status | Out-Null
            return
        }
        if ($existingServer -or $existingWorker) { throw "状态文件与运行实例不一致，请先执行 -Action Stop；当前运行日志：$($existingState.run_dir)" }
        Remove-Item -LiteralPath $statePath -Force
    }

    $runId = ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
    $runDir = Join-Path $runtimeDir $runId
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $logs = [ordered]@{
        startup = Join-Path $runDir "startup.log"
        server_stdout = Join-Path $runDir "server.stdout.log"
        server_stderr = Join-Path $runDir "server.stderr.log"
        worker_stdout = if ($NoWorker) { $null } else { Join-Path $runDir "worker.stdout.log" }
        worker_stderr = if ($NoWorker) { $null } else { Join-Path $runDir "worker.stderr.log" }
    }
    "[$([DateTime]::UtcNow.ToString('o'))] 开始启动 run_id=$runId" | Set-Content -LiteralPath $logs.startup -Encoding UTF8
    $portOwner = Get-PortOwner $Port
    if ($portOwner) {
        $record = Get-ProcessRecord $portOwner
        if ($record -and (Test-ProjectCommandLine $record.CommandLine "server")) {
            $legacyRunId = Get-RunIdFromCommandLine $record.CommandLine
            if ($legacyRunId -and (Test-ApiHealth $Port $legacyRunId)) {
                $reason = "检测到状态文件缺失的本项目 API（PID $portOwner，run_id=$legacyRunId）；为避免重复实例，请先执行 -Action Stop。"
                throw (Save-StartupFailure $reason $runId $runDir $logs $Port ([bool]$NoWorker))
            }
        }
        $reason = "端口 $Port 已被未知进程占用（PID $portOwner），未终止该进程。"
        throw (Save-StartupFailure $reason $runId $runDir $logs $Port ([bool]$NoWorker))
    }
    $legacyServers = Get-ProjectProcesses "server"
    if ($legacyServers.Count) {
        $reason = "检测到 $($legacyServers.Count) 个本项目遗留 API；拒绝启动第二个 API，请先执行 -Action Stop。"
        throw (Save-StartupFailure $reason $runId $runDir $logs $Port ([bool]$NoWorker))
    }
    $legacyWorkers = Get-ProjectProcesses "worker"
    if ($legacyWorkers.Count) {
        $reason = "检测到 $($legacyWorkers.Count) 个本项目遗留 Worker；拒绝启动第二个 Worker，请先执行 -Action Stop。"
        throw (Save-StartupFailure $reason $runId $runDir $logs $Port ([bool]$NoWorker))
    }
    Push-Location $projectRoot
    try {
        . (Join-Path $PSScriptRoot "setup-env.ps1")
        Get-Command uv -ErrorAction Stop | Out-Null
        if (-not $SkipSync) {
            Write-Host "[1/4] 同步 Python 环境..." -ForegroundColor Cyan
            Remove-StalePackageMetadata
            $env:UV_LINK_MODE = "copy"
            & uv sync --dev
            if ($LASTEXITCODE -ne 0) { throw "uv sync 执行失败。" }
        }
        else { Write-Host "[1/4] 已跳过 Python 环境同步。" -ForegroundColor DarkGray }

        if (-not $SkipWebBuild) {
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

        if (-not (Test-Path -LiteralPath $pythonLauncher -PathType Leaf)) { throw "未找到 $pythonLauncher，请先移除 -SkipSync 或执行 uv sync --dev。" }
        Write-Host "[3/4] 升级并校验数据库..." -ForegroundColor Cyan
        & $pythonLauncher -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败。" }
        & $pythonLauncher -c "from dst_manager.config import Settings; from dst_manager.infrastructure.persistence import Database; Database(Settings().database_url, migrate=False)"
        if ($LASTEXITCODE -ne 0) { throw "数据库 schema 自检失败。" }

        $env:PYTHONUTF8 = "1"
        $env:PYTHONIOENCODING = "utf-8"
        $env:NO_COLOR = "1"
        $env:DST_MANAGER_RUN_ID = $runId
        $common = @("-m", "dst_manager.interfaces.cli")
        $rootArgument = Quote-ProcessArgument $projectRoot
        Write-Host "[4/4] 启动 Web/API$(if ($NoWorker) { '' } else { ' 与 CAD Worker' })..." -ForegroundColor Cyan
        $server = $null
        $worker = $null
        try {
            $server = Start-BackgroundProcess ($common + @("serve", "--host", $listenHost, "--port", "$Port", "--run-id", $runId, "--project-root", $rootArgument)) $logs.server_stdout $logs.server_stderr
            $serverRecord = Get-ProcessRecord $server.Id
            $state = [ordered]@{
                run_id = $runId; status = "running"; started_at_utc = [DateTime]::UtcNow.ToString("o")
                project_root = $projectRoot; host = $listenHost; port = $Port; worker_disabled = [bool]$NoWorker
                run_dir = $runDir; logs = $logs
                server = New-ProcessEntry $serverRecord "server"; worker = $null
            }
            Write-JsonFile $statePath $state
            Write-JsonFile (Join-Path $runDir "run.json") $state
            $ready = $false
            for ($attempt = 0; $attempt -lt 30; $attempt++) {
                if (Test-ApiHealth $Port $runId) { $ready = $true; break }
                if ($server.HasExited) { break }
                Start-Sleep -Seconds 1
            }
            if (-not $ready) { throw "Web/API 在 30 秒内未通过 run_id 健康检查；日志：$($logs.server_stderr)" }
            $listenerPid = Get-PortOwner $Port
            if (-not $listenerPid -or -not (Test-IsDescendant ([int]$listenerPid) ([int]$server.Id))) { throw "无法确认本次 API 的实际端口监听进程。" }
            $state.server = New-ProcessEntry (Get-ProcessRecord ([int]$listenerPid)) "server"
            Write-JsonFile $statePath $state
            Write-JsonFile (Join-Path $runDir "run.json") $state
            if (-not $NoWorker) {
                if ($env:DST_MANAGER_TEST_FAIL_BEFORE_WORKER -eq "1") { throw "TEST_WORKER_START_FAILURE：已按测试要求在 Worker 启动前中止。" }
                $worker = Start-BackgroundProcess ($common + @("worker", "--run-id", $runId, "--project-root", $rootArgument)) $logs.worker_stdout $logs.worker_stderr
                $workerRecord = Get-ProcessTreeLeaf ([int]$worker.Id) "worker"
                if (-not $workerRecord) { throw "无法确认本次 Worker 的实际执行进程。" }
                $state.worker = New-ProcessEntry $workerRecord "worker"
                Write-JsonFile $statePath $state
                Write-JsonFile (Join-Path $runDir "run.json") $state
            }
        }
        catch {
            if ($worker -and -not $worker.HasExited) { Stop-ProcessTree (Get-ProcessRecord $worker.Id) "CAD Worker" }
            if ($server -and -not $server.HasExited) { Stop-ProcessTree (Get-ProcessRecord $server.Id) "Web/API" }
            if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath -Force }
            throw
        }
        Remove-ExpiredRunLogs
        $url = "http://${listenHost}:$Port"
        Write-Host "DST Manager 已启动：$url" -ForegroundColor Green
        Write-Host "run_id：$runId"
        Write-Host "日志目录：$runDir"
        Write-Host "日志命令：.\scripts\start.ps1 -Action Logs"
        "[$([DateTime]::UtcNow.ToString('o'))] 启动成功" | Add-Content -LiteralPath $logs.startup -Encoding UTF8
        if (-not $NoBrowser) { Start-Process $url }
    }
    catch {
        $reason = $_.Exception.Message
        "[$([DateTime]::UtcNow.ToString('o'))] 启动失败：$reason" | Add-Content -LiteralPath $logs.startup -Encoding UTF8
        $failureState = [ordered]@{
            run_id = $runId; status = "failed"; started_at_utc = [DateTime]::UtcNow.ToString("o")
            project_root = $projectRoot; host = $listenHost; port = $Port; worker_disabled = [bool]$NoWorker
            run_dir = $runDir; logs = $logs; server = $null; worker = $null
        }
        Write-JsonFile (Join-Path $runDir "run.json") $failureState
        Test-Utf8LogFile $logs.startup
        throw "$reason；启动日志：$($logs.startup)"
    }
    finally { Pop-Location }
}

switch ($Action) {
    "Start" { Start-Project }
    "Status" { Show-Status | Out-Null }
    "Stop" { Stop-Project }
    "Logs" { Show-Logs }
}
