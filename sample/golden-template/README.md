# 黄金样本模板

本目录是一套用于建立和维护黄金样本的空白模板，不是已经通过验收的生产样本。

## 使用方式

1. 将 `input/` 中的输入文件替换为一次可追溯的真实项目输入。
2. 使用固定版本的 Legacy 工作流运行，并把成功生成的 DST/DWG 复制到 `baseline/legacy/`。
3. 在 `provenance.md` 中填写来源、Legacy 版本、AutoCAD 版本、模板、插件和运行记录；不要填写真实客户隐私、凭据或令牌。
4. 根据最终 DST/DWG 填写 `expected/sheet-manifest.csv` 和 `expected/semantic-summary.json`。
5. 按 `validation-checklist.md` 完成 Legacy、DST/XML、AutoCAD 和新旧语义比较验收。
6. 只有所有阻断项完成并获得人工确认后，才可以把 `manifest.json` 的 `status` 改为 `accepted`，并将 `accepted` 改为 `true`。

## 目录约定

- `input/`：Legacy 的输入和源文件。Excel、源 DWG 等二进制文件目前为空文件占位。
- `baseline/legacy/`：已经确认的 Legacy 输出基线。这里的 DST/DWG 目前为空文件占位。
- `expected/`：与基线成果对应的文本化语义期望，供自动化比较使用。
- `provenance.md`：来源和执行环境记录，便于复现和追溯。
- `validation-checklist.md`：人工及系统验收清单。

## 占位文件说明

当前 `.xlsx`、`.dwg` 和 `.dst` 文件均为 0 字节占位文件，不能被 Excel、AutoCAD 或 DST Manager 当作有效业务文件打开。替换占位文件后，应同步更新 `manifest.json` 中的文件大小和 SHA-256，并删除对应的 `placeholder` 标记。

该目录与现有 `sample/project1`、`sample/project2` 相互独立；测试应复制样本到临时目录后执行，不得修改已确认的原始基线。
