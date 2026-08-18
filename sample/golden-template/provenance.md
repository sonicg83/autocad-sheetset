# 来源与复现记录

> 当前状态：模板，尚未绑定真实项目，也未完成生产验收。

## 样本身份

- `sample_id`：`GS-TEMPLATE-001`
- 项目/工程代号：待填写；不得填写客户敏感信息
- 样本用途：Legacy 与 DST Manager 的端到端语义回归
- 来源类型：待填写（真实项目 / 脱敏项目 / 最小合成项目）
- 来源负责人：待填写
- 建立日期：待填写
- 最后确认日期：待填写

## 输入和模板

- 图纸目录：`input/drawing-index.xlsx`
- 材料表：`input/material-schedule.xlsx`
- 源布局或基础 DWG：`input/source-layout.dwg`
- 其他输入/外部参照：待填写；请记录相对路径、用途和 SHA-256
- Legacy 配置或模板版本：待填写

## Legacy 执行环境

- Legacy 提交版本或 Git commit：待填写
- Python / PowerShell 版本：待填写
- AutoCAD 2016 Core Console：待填写
- AutoCAD 2020 Core Console：待填写
- 插件名称、版本和 SHA-256：待填写
- 运行命令或操作入口：待填写
- 执行日志位置：待填写

## 基线成果

- DST：`baseline/legacy/sheetset.dst`
- DWG 成果清单：待填写；`baseline/legacy/sheet-001.dwg` 仅为模板占位
- 输出目录总文件数：待填写
- 总大小：待填写
- 文件清单摘要 SHA-256：待填写
- DST SHA-256：待填写
- DWG 哈希策略：记录文件哈希，但比较时以布局、Handle 关联和业务对象语义为准

## 复现记录

| 日期 | 工作流 | 版本/提交 | CAD 版本 | 结果 | 日志/证据 |
| --- | --- | --- | --- | --- | --- |
| 待填写 | Legacy | 待填写 | 2016 / 2020 | 待执行 | 待填写 |
| 待填写 | DST Manager | 待填写 | 2016 / 2020 | 待执行 | 待填写 |

## 敏感信息规则

不得在本目录写入 API Key、令牌、密码、真实客户路径、未脱敏客户名称或其他凭据。环境记录应使用版本、文件哈希和脱敏后的相对路径。
