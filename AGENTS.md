# 双项目仓库协作规范

本文件适用于仓库根目录及全部子目录。后续代理在修改前，应先阅读 `README.md`、`docs/README.md`、相关 scope 的 `README.md`，以及与任务直接相关的文档、源码和测试。涉及 DST Manager 架构或发布安全时，还必须阅读 `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`。

## 沟通与文本

- 始终使用简体中文回复用户。
- 代码注释、文档、变更记录和 Git commit message 使用简体中文。
- 标识符、协议字段、API 路径、错误码以及第三方工具的固定名称保持其原始英文形式。
- 文件统一使用 UTF-8；AutoCAD SCR 等明确要求其他编码的文件除外。

## 文档归档约定

- 文档治理的权威设计是 `docs/integration/architecture/ARCH-INT-001-documentation-organization.md`；本节只保留日常执行约束，出现歧义时以权威设计为准。
- 可长期复用的知识、技术分析、架构说明、开发指南和调研结论按范围保存到 `docs/<scope>/...`。
- scope 只使用 `legacy-refactor`、`dst-manager`、`shared` 和 `integration`：前两者分别归属两条产品线；`shared` 只接收已被两边采用的稳定公共能力；尚在讨论的跨项目契约、提案和合并议题进入 `integration`，不得因“未来可能复用”提前归入 `shared`。
- 长期文档按主要用途归档：Vision 与 PRD 放入 `<project>/product/`，Spec 放入 `<project>/specs/`，Architecture、ADR、Guide 和 Research 放入对应 scope 的同名目录；RFC 只放入 `docs/integration/rfcs/`，稳定 Reference 放入 `docs/shared/reference/`。
- 已立项的实施计划、阶段计划和修复计划保存到 `.planning/plans/`；路线图保存到 `.planning/roadmaps/`。
- 尚未形成正式 Plan 的事项仅保存到 `.planning/todos/`；不要将已归档 Plan 继续放入 Todo。
- 备忘、对话记录、阶段沟通摘要和临时决策记录等记录类文档保存到 `.planning/memos/`。
- `.planning/plans/`、`.planning/todos/` 和 `.planning/memos/` 下继续按四个 scope 分目录；Roadmap 使用 scope 对应的单文件入口。
- 新建文档前先判断生命周期、scope 和文档类型，并搜索同主题权威文档；同一内容只保留一个权威位置，其他位置使用链接，不复制正文。不要将待办或备忘混入 `docs/`，也不要将长期知识文档放入 `.planning/`。
- PRD、Spec、Architecture、ADR、RFC、Roadmap 和 Plan 必须使用 YAML 元数据；正式文档使用永久 ID（类型 + `LR`/`DM`/`SH`/`INT` + 三位序号），编号不得重用。`related` 使用文档 ID，正文仍提供可点击链接。
- 长期文档状态使用 `draft`、`review`、`accepted`、`superseded` 或 `archived`；计划类文档使用 `proposed`、`active`、`completed`、`cancelled` 或 `blocked`。ADR 结论变化时新增 ADR，不静默改写旧决策；Plan 标记 `completed` 前记录实际验证，标记 `blocked` 时记录原因和恢复条件。
- 各级 `README.md` 只承担导航和当前状态摘要，不复制正文；新增、移动、作废或归档正式文档时同步维护相关索引和链接。根 `docs/` 不平铺业务文档，仓库根 `README.md` 不累积完整架构、调研或交接内容。

## 开发环境

- 目标系统为 Windows 11，默认 Shell 为 PowerShell；命令和路径写法必须兼容 PowerShell，不要假设 Bash 可用。
- Python 版本不得低于 3.12，项目统一使用 UV 管理环境和依赖。使用 `uv add`、`uv remove`、`uv sync` 和 `uv run`，不要直接运行 `pip install`。
- 修改 Python 依赖时同时更新 `pyproject.toml` 和 `uv.lock`。
- 仓库位于 OneDrive 时，UV 安装或同步优先设置 `$env:UV_LINK_MODE = "copy"`；如共享缓存被占用，可使用任务专用的 `UV_CACHE_DIR`，不要删除用户的全局缓存。
- Web 前端位于 `web/`，使用 npm、Vue 3、TypeScript 和 Vite；依赖变化必须同步更新 `package.json` 与 `package-lock.json`。
- AutoCAD 插件使用 x64、.NET Framework 4.8，并分别引用 AutoCAD 2016 和 2020 的托管程序集。

## 代码结构与依赖方向

- `src/dst_manager/domain/`：领域模型和确定性规划，不得依赖 FastAPI、SQLAlchemy、文件系统或 AutoCAD 进程。
- `src/dst_manager/application/`：编排工作区、变更预览、任务和 CAD 执行流程。
- `src/dst_manager/infrastructure/`：DST/AcSm、AutoCAD、SQLite、文件锁、发布事务和操作日志适配器。
- `src/dst_manager/interfaces/`：FastAPI 与 Typer 入口；接口层只负责输入输出、状态码和依赖装配，不承载领域规则。
- `web/`：本地操作界面；与后端共享既有 HTTP/SSE 契约，不在前端复制后端的最终校验规则。
- `plugins/src/DstManager.AutoCAD/`：最小 CAD Worker 插件，只实现 Python/Core Console 无法可靠完成的 AutoCAD 数据库操作。
- `migrations/`：Alembic 迁移。模型变化必须同时提供迁移并验证全新数据库升级。

## DST、DWG 与发布安全

- 只读打开工作区不得创建 `.dst-manager/`、修改 DST/DWG，也不得更新文件时间戳。
- DST 修改必须经过 `DST -> XML DOM -> DST` 受控流程；不得用字符串替换 XML，不得丢弃未知节点、未知属性或原有节点顺序。
- 结构性变更必须先生成完整预览并校验基准修订；需要 CAD 的操作只能通过固定命令、固定 SCR 渲染器和匹配版本的 Worker 插件执行。
- 不得把用户提供的任意文本直接拼接成 SCR 命令、Shell 命令或文件路径操作；继续保留危险名称和越界路径校验。
- 正式写入必须保留永久 before 快照，并使用现有的锁、暂存、校验、发布日志和可回滚事务流程；不要绕过发布器直接覆盖原文件。
- 多文件发布失败必须恢复为整批发布前状态。修改发布器时必须覆盖新增、替换、删除、中途故障和启动恢复场景。
- Web 服务在 MVP 阶段只允许监听 `127.0.0.1`。

## 本地私有目录与生成物

- `legacy/`、误拼兼容目录 `lagacy/` 和 `sample/` 只保留在本地，禁止使用 `git add -f` 发布到公开仓库。
- 测试只能读取 `sample/` 或将其复制到临时目录，禁止修改样本原件；公开克隆缺少样本时，对应黄金样本和真实 CAD 测试应跳过。
- 不得提交 `.env`、`.agents/`、`.venv/`、缓存、覆盖率文件、Playwright 结果、`web/dist/`、`web/node_modules/` 或 `.dst-manager-data/`。
- 不得提交 `plugins/autocad2016/`、`plugins/autocad2020/`、`bin/`、`obj/` 等插件构建产物。
- 凭据、API Key、令牌、真实客户路径和其他敏感数据不得写入源码、文档、测试夹具、日志或提交历史。

## 常用验证命令

Python 基线：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
```

数据库迁移：

```powershell
uv run alembic upgrade head
```

Web：

```powershell
Set-Location web
npm ci
npm run build
npm run test:e2e
```

双版本插件：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

真实 AutoCAD 系统测试必须由用户或运行环境显式启用，并要求本机存在对应 Core Console、插件和私有样本：

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad -q
```

## 测试要求

- 根据改动风险运行最小充分测试；交付前至少运行 Ruff 和相关 pytest。
- 修改 API、任务状态或序列化结构时更新集成测试；修改 Web 交互时更新 Playwright 测试并执行生产构建。
- 修改 DST Codec、AcSm DOM、命名规则或发布事务时必须添加回归测试，优先使用最小 XML/临时文件夹夹具。
- 修改 AutoCAD SCR、插件命令或布局重建流程时，先运行非 CAD 单元测试；具备环境时再运行 2016/2020 双版本真实测试。
- 测试不得依赖执行顺序、已有本地数据库或上一次运行遗留文件。

## 变更与 Git 规则

- 每次修改都要更新根目录 `changelog.md`；在当前日期或对应版本章节追加简洁、可核验的记录。
- 修改前检查工作区状态，保留并避开用户已有的无关改动，不得擅自还原、移动或删除。
- 只暂存本任务涉及的文件；公开发布前再次确认忽略目录和敏感信息未进入提交树。
- 禁止未经用户明确授权执行 `git reset --hard`、强制推送、覆盖远程历史或删除分支。
- Commit message 使用简体中文、动词开头并概括结果，例如：`完善 DST 发布事务回滚校验`。
- 完成后报告修改内容、实际执行的验证，以及任何因环境缺失而跳过的检查。
