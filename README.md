# AutoCAD 市政图纸集生成工具

## DST Manager MVP

新实现位于 `src/dst_manager`，提供 DST/XML 编解码、AcSm DOM 投影与校验、路径重定位、SQLite 任务/修订索引、可恢复发布、Core Console 边界、FastAPI、CLI 和 Vue 3 操作界面。

### 一键启动

在项目根目录打开 PowerShell，运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

脚本会初始化环境、同步 Python 依赖、构建 Web、升级数据库，并在后台启动 Web/API 和 CAD Worker。服务就绪后默认打开 `http://127.0.0.1:8000`。

```powershell
# 查看状态
.\scripts\start.ps1 -Action Status

# 查看当前运行实例的 UTF-8 日志尾部
.\scripts\start.ps1 -Action Logs

# 停止 API 与 Worker
.\scripts\start.ps1 -Action Stop

# 快速启动：复用现有依赖和 Web 构建
.\scripts\start.ps1 -SkipSync -SkipWebBuild

# 只启动 Web/API，不启动 CAD Worker，也不打开浏览器
.\scripts\start.ps1 -NoWorker -NoBrowser
```

每次启动都会生成独立的 `run_id`，运行日志保存在 `.dst-manager-data/runtime/<run-id>/`，该目录不会提交到仓库。API 健康检查会同时核对 `run_id`，避免端口仍由旧 API 监听时误报新实例成功；重复执行 `Start` 会复用当前实例，不会再创建 API 或 Worker。所有 stdout/stderr 都按严格 UTF-8 写入，Worker stdout 只输出单行任务摘要，完整 payload、文件路径、哈希和逐 DWG 详情仍保存在 SQLite 与工作区修订目录。

### 启动与日志排障

- `Status` 显示“状态文件失效”时，执行 `Stop` 会按规范化项目根目录和精确命令行清理本项目受管进程树；不会终止无关程序。
- 端口被无关程序占用时，`Start` 会显示占用 PID 并失败，不会自动结束对方。关闭或调整该程序后再启动，也可通过 `-Port` 选择其他端口。
- 检测到遗留或重复 Worker 时，必须先执行 `Stop`，确认 `Status` 中 API 与 Worker 均为“未运行”后再启动。
- `Logs` 会安全显示最近运行实例的日志尾部；停止时脚本还会严格检查 UTF-8、NUL 和非法控制字符。
- 每次运行日志独立保留；超过 20 个已停止实例或总大小超过 512 MiB 时，只清理最旧且已停止的实例，不删除当前运行日志。
- 启动会同时核对 Alembic revision 和关键物理表/列。如果出现 `DATABASE_SCHEMA_DRIFT`，测试数据库可删除 `.dst-manager-data/dst-manager.db` 后重新执行 `Start`；不要修改已经发布的 migration，应新增 revision。

### 环境变量与启动

运行 `scripts/setup-env.ps1` 自动设置环境（需在项目根目录点源，使变量保留在当前会话）：

```powershell
. .\scripts\setup-env.ps1   # 生成 .env、注入 UV_LINK_MODE/UV_CACHE_DIR、探测本机 AutoCAD
uv sync
uv run dst-manager doctor
uv run dst-manager open "C:\项目目录\图纸集数据文件.dst"
uv run dst-manager serve
```

脚本会：从 `.env.example` 生成 `.env`（若不存在）、探测本机 AutoCAD 2016/2020 的 `accoreconsole.exe` 写回 `.env`、设置 `UV_LINK_MODE=copy`（OneDrive 建议）与项目独立 `UV_CACHE_DIR`。脚本幂等，只补缺失项，不覆盖已有 `.env` 内容；用 `-Force` 可重建 `.env`。

如需每次打开终端自动生效，可在 PowerShell `$PROFILE` 中加入 `. "C:\Users\sonic\OneDrive\codework\autocad-sheetset\scripts\setup-env.ps1"`（脚本仅在项目根目录生效，不会污染其他项目）。

`.env` 与 `DST_MANAGER_*` 变量说明见根目录 `.env.example`；CAD 控制台/插件路径也可手动在 `.env` 中配置。

Web 开发界面在 `web/`。执行 `npm install`、`npm run build` 后，`dst-manager serve` 会同时提供构建后的页面；开发时可使用 `npm run dev`。服务只允许绑定 `127.0.0.1`；结构性图纸操作需要显式配置匹配版本的 Core Console 和插件。

双版本插件和Worker配置：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
$env:DST_MANAGER_AUTOCAD_2016_CONSOLE = "C:\Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe"
$env:DST_MANAGER_AUTOCAD_2016_PLUGIN = "$PWD\plugins\autocad2016\DstManager.AutoCAD.dll"
$env:DST_MANAGER_AUTOCAD_2020_CONSOLE = "C:\Program Files\Autodesk\AutoCAD 2020\accoreconsole.exe"
$env:DST_MANAGER_AUTOCAD_2020_PLUGIN = "$PWD\plugins\autocad2020\DstManager.AutoCAD.dll"
uv run dst-manager worker
```

控制进程和 CAD Worker 使用同一个 SQLite 队列，应在两个终端分别运行 `dst-manager serve` 与 `dst-manager worker`。结构变更会先返回 `QUEUED`，Web 页面通过 SSE 持续显示 `STAGING/CAD_RUNNING/VERIFYING/PUBLISHING` 等状态。

验证命令：

```powershell
uv run pytest
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad
cd web
npm run build
npm run test:e2e
```

SQLite 使用 SQLAlchemy 运行时模型和 Alembic 迁移：`uv run alembic upgrade head`。项目首次确认执行后，会在项目目录建立 `.dst-manager/`，永久保存 before 快照、输入、执行计划、脚本、日志、发布日志和 manifest；只读打开不会创建该目录。

## 本地保留资料

公开仓库不包含 `legacy/` 旧工具和 `sample/` 工程样本。这两个目录只保留在本地工作区；缺少样本时，黄金样本和真实 AutoCAD 系统测试会自动跳过。

完整的架构、输入格式、生成流程、扩展方法和已知风险见 [开发与交接文档](docs/legacy-refactor/guides/GUIDE-LR-001-legacy-development-handover.md)。

`plugin/` 下 4 个 C# 项目的源码结构、命令契约、构建部署、测试矩阵和已知问题见 [AutoCAD 插件开发与交接文档](docs/PLUGIN_DEVELOPMENT.md)。

AutoCAD 2025/2026 的 .NET 8 迁移、AutoCAD 2027 的 .NET 10 边界、多版本构建和发布策略见 [AutoCAD 2025 及以上版本迁移分析](docs/AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS.md)。

`UtilityClass.DstViewer` 的 DST/XML 字节转换算法、XML 序列化行为、接口边界、风险和测试建议见 [UtilityClass DST/XML 转换实现分析](docs/UTILITYCLASS_DST_XML_ANALYSIS.md)。

`Transform` 插件的四参数矩阵推导、默认参数往返误差、WCS/UCS 与 Z 坐标边界、Autodesk 官方依据和整改建议见 [Transform 插件矩阵运算准确性分析](docs/TRANSFORM_MATRIX_ANALYSIS.md)。

关于是否使用 Python/pyautocad 重构、预期收益、技术边界和推荐迁移路线，见 [Python 与 pyautocad 重构可行性评估](docs/legacy-refactor/research/RES-LR-001-python-refactor-assessment.md)。

## 主要入口

- `src/dst_manager/`：领域、应用、基础设施和接口实现。
- `web/`：Vue 3 本地操作界面。
- `plugins/src/DstManager.AutoCAD/`：AutoCAD 2016/2020 Worker 插件源码。
- `scripts/build_plugins.ps1`：双版本插件构建脚本。
- `docs/DST_MANAGER_MVP_DESIGN.md`：MVP 设计与验收基线。
