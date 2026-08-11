# 自动设置 DST Manager 环境变量
# 用法（点源，让变量保留在当前会话）：
#   . .\scripts\setup-env.ps1
# 若已加入 $PROFILE，则每次打开终端且位于本项目目录时自动生效。
# 脚本幂等：只写缺失项，不覆盖已有的 .env 内容与已设置的会话变量。

[CmdletBinding()]
param(
    [switch]$Force                     # 强制重建 .env（从 .env.example 重新生成）
)

$ErrorActionPreference = "Stop"

# 仅在项目根目录生效，避免污染其他项目。
$projectRoot = Split-Path -Parent $PSScriptRoot
$expectedName = Split-Path -Leaf $projectRoot
if ((Split-Path -Leaf (Get-Location).Path) -ne $expectedName) {
    Write-Host "setup-env: 当前目录不是项目根目录（$expectedName），跳过自动设置。" -ForegroundColor Yellow
    return
}

# --- 插件产物路径（始终保持相对项目根目录，避免 OneDrive 路径漂移）---
# 控制进程通过 .env 读取 DLL 路径；此处在会话中兜底注入，便于 doctor 探测。
$env:DST_MANAGER_AUTOCAD_2016_PLUGIN = Join-Path $projectRoot "plugins\autocad2016\DstManager.AutoCAD.dll"
$env:DST_MANAGER_AUTOCAD_2020_PLUGIN = Join-Path $projectRoot "plugins\autocad2020\DstManager.AutoCAD.dll"

# --- 探测本机 acad 安装目录，写回 .env ---
function Resolve-AutoCAD-Console([string]$Version) {
    $candidate = Get-ChildItem -Path "C:\Program Files\Autodesk" -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^AutoCAD $Version( |$)" } |
        Select-Object -First 1
    if ($candidate) {
        $console = Join-Path $candidate.FullName "accoreconsole.exe"
        if (Test-Path -LiteralPath $console) { return $console }
    }
    return $null
}

$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath) -or $Force) {
    if (Test-Path -LiteralPath (Join-Path $projectRoot ".env.example")) {
        Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $envPath -Force
        Write-Host "setup-env: 已从 .env.example 生成 .env" -ForegroundColor Green
    }
}

if (Test-Path -LiteralPath $envPath) {
    $lines = @(Get-Content -LiteralPath $envPath)
    $touched = $false
    foreach ($kv in @(
            @{ Key = "DST_MANAGER_AUTOCAD_2016_CONSOLE"; Version = "2016" },
            @{ Key = "DST_MANAGER_AUTOCAD_2020_CONSOLE"; Version = "2020" }
        )) {
        if ($lines -match ("^" + [regex]::Escape($kv.Key) + "=")) { continue }
        $console = Resolve-AutoCAD-Console -Version $kv.Version
        if ($console) {
            $lines += "$($kv.Key)=$console"
            $touched = $true
            Write-Host "setup-env: 已写入 $($kv.Key)=$console" -ForegroundColor Green
        }
    }
    if ($touched) {
        $lines | Set-Content -LiteralPath $envPath -Encoding UTF8
    }
}

# --- uv 相关（必须早于 uv sync 生效；.env 无法覆盖，只能在此设置）---
if (-not $env:UV_LINK_MODE) {
    $env:UV_LINK_MODE = "copy"   # OneDrive 目录建议启用，避免同步冲突
    Write-Host "setup-env: 已设置 UV_LINK_MODE=copy" -ForegroundColor Green
}
if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = "$projectRoot\.uv-cache"
    Write-Host "setup-env: 已设置 UV_CACHE_DIR=$env:UV_CACHE_DIR" -ForegroundColor Green
}

Write-Host "setup-env: 完成。可执行 uv sync 与 uv run dst-manager doctor 验证。" -ForegroundColor Cyan