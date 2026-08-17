---
id: ROADMAP-LR-001
title: Legacy Python 重构路线图
status: proposed
owners:
  - legacy-refactor
created: 2026-08-17
updated: 2026-08-17
related:
  - ARCH-LR-001
  - RES-LR-001
---

# Legacy Python 重构路线图

本路线图提取自 [ARCH-LR-001](../../docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md) 的迁移方向；各阶段均为提案，不表示已完成或已经验证。

## 目标阶段

1. 黄金样本：冻结现有输入、输出和关键失败场景，建立可重复的行为证据。
2. 纯逻辑：迁移输入解析、图纸展开、命名与计划等不依赖 AutoCAD 的规则，并建立单元测试。
3. Core Console 调度：由 Python 受控调度既有 CAD 与 DST 链路，并用黄金样本进行语义比较。
4. 界面与打包：提供本地 Web/API 或桌面界面、CLI、配置检查、任务进度、日志和可交付安装包。
5. DST 迁移：验证并逐步替换 DST 写入适配器，保留稳定旧实现作为回退路径。
6. pyautocad POC：仅选择受控的小范围 DWG 场景验证其适用性，再决定是否投入后续能力。

## 依赖与退出条件

每个阶段都以前一阶段的可复现实证为输入；进入下一阶段前，应记录黄金样本比对、错误处理、回退策略与适用的 AutoCAD 版本矩阵。
