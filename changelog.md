# 变更记录

## 2026-08-12（文档归档约定）

- 更新 `AGENTS.md`，明确计划类、备忘/对话记录类和知识类文档分别归档到 `.planning/todos/`、`.planning/memos/` 和 `docs/`。

## 2026-08-12（v0.2.1 修复计划）

- 新增 `.planning/todos/05-v0.2.1-runtime-logging-and-acsm-hotfix.md`，基于真实测试中发现的缺失 AcSm `Value` 节点、重复 API/Worker、端口误判、混合编码及 NUL 日志问题，制定 P0 修复工作包、实施顺序、测试矩阵和验收标准。
- 根据 AutoCAD 实测修订 AcSm 自定义属性热修复规则：明确空值的规范形式为缺失 `Value`，清空操作应删除 `Value`；将 `Flags=1/2` 分别纳入 SheetSet/Sheet 作用域校验，并补充克隆清空、预览前移、错误码和双版本回归要求。
- 更新待办索引，将 v0.2.1 运行时与兼容性修复设为进入 v0.3 日常编辑器前的阻断条件。

## 2026-08-12（启动脚本）

- 新增 `scripts/start.ps1`：提供 `Start`、`Status`、`Stop` 三种操作，一键完成环境初始化、依赖同步、Web 构建、Alembic 升级、Web/API 与 CAD Worker 后台启动及健康检查；支持跳过同步/构建、禁用 Worker、关闭自动打开浏览器和自定义端口。
- 后台进程状态与标准输出/错误日志保存在 `.dst-manager-data/runtime/`；停止前校验 PID 和启动时间，并按进程树关闭本任务启动的服务，避免误停复用 PID 的其他进程。
- 将 `start.ps1` 与其复用的 `setup-env.ps1` 保存为 UTF-8 BOM，确保 Windows PowerShell 5.1 能正确解析中文注释和输出。
- 修复 Windows PowerShell 5.1 优先调用新版 Node.js `npm.ps1` 时把 `& npm ci` 错误解析为 `pm ci` 的问题；Web 安装和构建现在显式使用 `npm.cmd`。
- 启动同步前仅清理 `.venv/Lib/site-packages` 中缺少 `RECORD` 的旧版项目包元数据，并直接使用同步后的 Alembic 入口执行迁移，消除 v0.1 升级残留警告和重复环境刷新。

## 2026-08-12（DST Manager v0.2）

- 将 SQLite 初始化与升级统一收口到 Alembic，新增 v0.2 迁移、schema 版本闸门，并覆盖空库和既有 MVP 数据库升级。
- 为任务补充 `worker_id`、attempt、租约心跳、起止时间、错误详情和状态时间线；原子领取仅允许 `QUEUED → STAGING`，遗留任务按安全阶段重排队或转人工复核。
- 新增 `DST_MANAGER_CAD_MAX_PARALLEL`（默认 2、范围 1～4），以不可变 DWG 工作单元和有界线程池并行执行 Core Console；源文件先哈希快照，结果由调度线程确定性合并，任一失败时停止提交新组且不进入发布。
- 为逐 DWG 执行记录状态、进度、耗时、哈希、日志和错误，并在任务 API/Web 中提供汇总、时间线、脱敏日志摘要、错误建议、安全重试和 SSE 断线轮询降级。
- 新增按工作区筛选的修订历史、逐文件恢复预览与“恢复为新修订”；当前哈希冲突会阻断恢复，确认恢复继续复用永久 before 快照和可恢复整批发布。
- Web 更新为 v0.2 任务详情和修订恢复界面；增加任务并发/失败停止、原子领取、租约恢复、迁移升级、恢复冲突和 Playwright 交互测试。

## 2026-08-11

- 新增 `.planning/todos/` 后续实施计划：按 v0.2 稳定化与多 DWG 有界并行、v0.3 日常编辑器、v0.4 单人工作流和 v1.0 Windows 产品化拆分目标、工作包、测试矩阵、验收标准与风险边界。
- 新增 `scripts/setup-env.ps1` 与根目录 `.env.example`：自动生成 `.env`、探测本机 AutoCAD 2016/2020 的 `accoreconsole.exe` 写回 `.env`，并注入 `UV_LINK_MODE=copy` 与项目独立 `UV_CACHE_DIR`；脚本幂等、仅在项目根目录生效，支持 `-Force` 重建 `.env`。
- 更新 `README.md` 启动说明：改为先执行 `scripts/setup-env.ps1` 自动设置环境，并说明 `$PROFILE` 集成方式与 `.env` 变量来源。
- 新增 `docs/PROJECT1_DST_XML_ANALYSIS.md`、`docs/project1_sheetset.xml` 和 `docs/project1_sheet_manifest.csv`：使用项目 `DstCodec` 只读解码 `sample/project1` 的 DST，记录 AcSm XML 结构、节点统计、图纸/DWG 布局绑定和受控修改边界，并导出 298 张图纸清单。

## 2026-08-10（DST Manager MVP）

- 完善 `AGENTS.md`：补充语言与环境、架构依赖方向、DST/DWG 发布安全、私有目录、验证命令、测试分层和 Git 协作规范。
- 准备公开 GitHub 仓库：忽略 `legacy`、`lagacy`、`sample`、本地环境和工具缓存；公开克隆缺少私有样本时自动跳过对应测试，并更新启动说明。
- 创建 `src/dst_manager` MVP：实现兼容 legacy 的 DST/XML Codec、AcSm DOM 投影/校验、未知节点保留和DWG路径重定位。
- 新增受控编辑与预览、修订冲突检查、SQLite WAL任务索引、永久before快照和可恢复发布。
- 新增固定SCR渲染、危险参数拒绝、Handle解析、2016/2020能力探针、FastAPI/SSE、CLI和Vue界面。
- 新增黄金样本、Codec、未知XML保留、API执行和修订冲突测试，并更新UV依赖和启动说明。
- 调整打开工作区为文件层只读，只有确认执行时才在项目中创建 `.dst-manager`，确保黄金样本探针不写原件。
- 新增最小 AutoCAD Worker 插件源码及双版本构建脚本，提供受控布局清理与UTF-8布局Handle清单命令。
- 新增结构命令确定性规划、SQLite Worker领队列、DWG暂存重建、二次Handle回读、AcSm结构更新及整批发布链路。
- 新增模板布局检查API、用户根目录路径重绑定、固定源文件哈希快照、Windows写阻断锁和永久脚本/日志/发布清单归档。
- Web表单补齐插入、删除、重排、跨子集移动、模板来源、任务进度、诊断和修订历史流程。
- 新增Playwright主流程测试，覆盖打开工作区、模板新增、变更预览和确认执行。
- 实现图纸集/子集属性命令、批量重编号及 legacy 兼容的布局名、子集名、主DWG文件名同步派生。
- 完善多文件发布的新增/删除/替换回滚、数据库单写任务锁、启动恢复同步、磁盘空间检查和JSON Lines操作日志。
- 增加SQLAlchemy完整元数据表及Alembic初始迁移；XML导入提供对象级语义差异，XML导出纳入任务和永久修订。
- 分别使用AutoCAD 2016和2020通过插件加载、Handle回读、改名、插入、删除、重排、跨子集移动和25布局最大分组真实系统测试。
- 固化黄金项目54个DST/DWG、总字节数和逐文件哈希清单摘要，自动化测试会在解析前拒绝任何样本漂移。
- Web编辑器补齐图纸集名称、图纸集/图纸自定义属性和子集名称/排序编辑，并确保属性随受控命令提交。
- 将 Ruff 固化为 UV 开发依赖，并增加图纸集/图纸已有自定义属性往返测试。
- 新增 `docs/DST_MANAGER_MVP_DESIGN.md`，基于现有现代化重构方案建立DST Manager前期技术验证基线。
- 根据最终确认的 DM-ADR-001 至 DM-ADR-010 重写MVP设计，确定不使用SSO COM，采用 `DST → XML → DST` 与 `accoreconsole` 重建DWG布局的实现路径。
- 审计新增黄金样本 `sample/project1`：确认298张图、45个子集、45个主DWG、8个额外DWG，并把旧绝对路径重定位纳入MVP正式能力。
- 明确新增图纸既可复制已有布局，也可从DWG/DWT模板布局创建空白业务布局；支持插入、删除、重排和跨子集移动。
- 补充整批可恢复发布协议、永久修订目录、XML未知结构保留、双AutoCAD版本测试矩阵、阶段退出条件和可量化验收标准。
- 记录UtilityClass编解码、DWG字段刷新和XML兼容导入的验证边界；早期SSO COM探针结论仅保留为被否决方案，不进入MVP实现。
- 关闭混合拓扑、AutoCAD版本、DST写入方式、DWG同步范围、文件保护、XML契约、历史和锁处理等全部DM-ADR灰区。
- 补充DST Manager领域模型、SQLite元数据表、永久修订目录、本地Web/API骨架及同机CAD Worker边界。

## 2026-08-10

- 新增 `docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md`，记录本地与云端双形态 Python 重构的确定性架构基线。
- 将云端 CAD 执行位置、Python/C# 边界、AutoCAD 版本、插件范围、界面形态、租户模型、文件安全和兼容级别登记为待用户确认的架构决策，避免隐含假设。
- 补充领域模型、端口与适配器、任务状态机、运行隔离、安全、可观测性、分层测试和分阶段迁移门槛。
- 根据用户决策将目标收敛为内网控制面、企业 Windows CAD Worker、统一 Web UI/CLI、自建账号、RustFS、SQLite/达梦双数据库契约，以及 AutoCAD 2016/2020 双版本插件构建。
- 明确 Python 3.12、FastAPI、Vue 3、SQLAlchemy 2、S3 适配器、HTTPS 拉取与数据库租约等技术基线，并登记本地离线、插件形态、权限、保留策略、容量、目标运行环境和 Excel 公式缓存等二级决策。
- 根据第二轮确认关闭离线模式、交互插件、RBAC、安全边界、保留期限、容量和部署平台决策；将 DM8 实例验证设为生产准入门槛。
- 只读分析五个真实 Excel 输入样本，将输入重构为工程表单、图纸分组数据网格、版本化字典/扩展字段、不可变修订和 Excel 兼容桥，并把剩余录入交互登记为 ADR-019。
- 确认多专业/分册工程、Excel 兼容桥、扩展字段、多人乐观锁编辑、项目管理员审批、自动编号、RustFS 资产与成果交付、高密度数据网格；补充稳定图纸 UUID 和可审计插入/删除机制。
- 确认草稿插入/删除自动紧凑重排，正式修订保持不可变，新修订生成图号变更映射并由项目管理员确认。
- 定稿数据库实体、HTTP API、RBAC、错误码、指标与容量基线、全部插件迁移矩阵、DST Windows Worker 边界、Linux Compose/Windows Worker 部署、CI/CD、生命周期、回滚和现有能力追踪矩阵。
- 只读核对本机 RustFS 开发容器为单实例本地卷且当前健康检查失败，将独立备份、恢复演练和 RPO/RTO 设为生产准入条件。
- 关闭最终灾备与本地身份决策：离线模式使用 Windows 隐式身份和一次性浏览器令牌；数据库/审计 RPO 15分钟、对象 RPO 1小时、控制面 RTO 4小时、历史文件 RTO 24小时；独立内网备份位置作为生产部署前置条件后定。
- 将现代化 Python 重构架构文档标记为最终定稿，ADR-001 至 ADR-020 全部关闭。

## 2026-07-15

- 新增 `docs/TRANSFORM_MATRIX_ANALYSIS.md`，结合 Autodesk 官方 `Matrix3d`、WCS/UCS、ADETRANSFORM 和 Map 3D 坐标转换说明，分析 `Transform` 插件的四参数矩阵推导、正反向可逆性、默认参数往返误差、Z 坐标影响、适用边界、运行风险、重构方向和测试矩阵。
- 在 `README.md` 增加 Transform 插件矩阵运算准确性分析文档入口。
- 本次仅新增和更新文档，未修改 Transform 插件源码、配置、项目文件或 DLL。
- 新增 `docs/UTILITYCLASS_DST_XML_ANALYSIS.md`，整理 `UtilityClass.DstViewer` 的 DST/XML 查表转换算法、四个公共接口、XML 序列化行为、PowerShell 集成边界、异常与性能特征、维护风险、重构方向和测试矩阵。
- 在 `README.md` 增加 UtilityClass DST/XML 转换分析文档入口。
- 本次仅新增和更新文档，未修改 PowerShell、C# 源码、项目配置或仓库 DLL。
- 新增 `docs/AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS.md`，分析 AutoCAD 2025/2026 的 .NET 8、AutoCAD 2027 的 .NET 10 迁移边界，以及 4 个插件项目的构建结构、版本化部署、PowerShell 兼容、测试矩阵、风险优先级和推荐实施顺序。
- 在 `README.md` 增加 AutoCAD 2025 及以上版本迁移分析文档入口。
- 本次迁移工作仅新增和更新文档，未修改插件源码、项目配置或仓库 DLL。
- 新增 `docs/PLUGIN_DEVELOPMENT.md`，完整整理 `plugin/` 下 4 个 C# 项目的技术基线、源码结构、AutoCAD 命令、公共 API、配置和持久化契约、主程序集成、构建部署、测试矩阵、已知问题及接手优先级。
- 在 `README.md` 和 `docs/DEVELOPMENT.md` 增加插件开发文档入口，并将 AutoCAD 升级说明更新为当前已有可追溯源码的状态。
- 根据 `Ainsert` 源码修订 `docs/PYTHON_REFACTOR_ASSESSMENT.md`，明确其“向所有图纸布局原点附着同一外参”的实际语义及 COM 替换验证要求。
- 验证 4 个插件项目均可使用 Visual Studio 2022 的 64 位 MSBuild 以 Debug 配置构建；构建输出仅写入系统临时目录，未替换仓库 DLL。
- 新增 `README.md`，说明项目用途、当前接手状态、启动方式和主要入口。
- 新增 `docs/DEVELOPMENT.md`，整理系统架构、运行流程、Excel 输入契约、配置项、模板规则、关键函数、依赖、故障定位、验证方法、扩展手册和技术债。
- 新增 `docs/PYTHON_REFACTOR_ASSESSMENT.md`，记录 Python/pyautocad 重构可行性、功能映射、收益与风险、目标架构、迁移阶段、工作量和验收指标。
- 在 `README.md` 增加 Python/pyautocad 重构评估文档入口。
- 本次仅新增文档，未修改 PowerShell、配置、Excel、DWG 或 DLL。
