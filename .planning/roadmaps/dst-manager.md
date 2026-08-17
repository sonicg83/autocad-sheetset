---
id: ROADMAP-DM-001
title: DST Manager 路线图
status: proposed
owners:
  - dst-manager
created: 2026-08-17
updated: 2026-08-17
related:
  - ARCH-DM-001
  - PLAN-DM-001
  - PLAN-DM-002
  - PLAN-DM-003
  - PLAN-DM-004
  - PLAN-DM-005
---

# DST Manager 路线图

本路线图以 [ARCH-DM-001](../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 为架构基线；已完成阶段保留验证记录，后续阶段仍为计划，不代表已经实施。

## 目标阶段

| 版本 | 状态 | 目标 | Plan |
| --- | --- | --- | --- |
| v0.2 | 已完成 | 稳定化、修订恢复、任务自救与多 DWG 有界并行 | [PLAN-DM-001](../plans/dst-manager/PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md) |
| v0.2.1 | 已完成 | 运行时、日志与 AcSm 兼容性修复 | [PLAN-DM-005](../plans/dst-manager/PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md) |
| v0.3 | 计划中 | 日常编辑器与人类可读预览 | [PLAN-DM-002](../plans/dst-manager/PLAN-DM-002-v0.3-daily-editor.md) |
| v0.4 | 计划中 | 单人工作流、模板库、健康检查与诊断 | [PLAN-DM-003](../plans/dst-manager/PLAN-DM-003-v0.4-solo-workflow.md) |
| v1.0 | 计划中 | Windows 产品化、升级迁移与完整验收 | [PLAN-DM-004](../plans/dst-manager/PLAN-DM-004-v1.0-windows-productization.md) |

## 退出条件

每一阶段均须保持受控 DST/DWG 写入、整批发布与回滚边界；后续阶段只有在前置阶段的验证证据齐备后才可进入实施。
