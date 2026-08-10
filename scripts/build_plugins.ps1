[CmdletBinding()]
param(
    [string]$MSBuild = "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$project = Join-Path $projectRoot "plugins\src\DstManager.AutoCAD\DstManager.AutoCAD.csproj"
foreach ($version in @("2016", "2020")) {
    $autoCADDir = "C:\Program Files\Autodesk\AutoCAD $version"
    $output = Join-Path $projectRoot "plugins\autocad$version"
    if (-not (Test-Path -LiteralPath (Join-Path $autoCADDir "AcCoreMgd.dll"))) {
        throw "缺少 AutoCAD $version 托管程序集：$autoCADDir"
    }
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    & $MSBuild $project /nologo /m /t:Rebuild /p:Configuration=Release "/p:AutoCADDir=$autoCADDir" "/p:OutputPath=$output\"
    if ($LASTEXITCODE -ne 0) { throw "AutoCAD $version 插件构建失败" }
}
