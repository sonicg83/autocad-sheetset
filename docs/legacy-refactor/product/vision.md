---
id: VISION-LR-001
title: Legacy 图纸集生成工具现代 Python 重构愿景
status: accepted
owners:
  - legacy-refactor
created: 2026-08-17
updated: 2026-08-17
related:
  - ARCH-LR-001
  - RES-LR-001
---

# Legacy 图纸集生成工具现代 Python 重构愿景

## 产品愿景

以现代 Python 重构现有图纸集生成工具的编排层，在保留已验证 CAD 能力的前提下，形成可测试、可审计、可演进的生成工作流。

## 能力边界

- Python 负责业务编排、Web/API、Excel 输入处理、任务调度、存储和审计。
- 必须在 AutoCAD 进程内执行的能力继续由 C# 插件承担，并通过受控接口被编排层调用。
- 目标覆盖从输入到 DWG、DST 及伴随成果的完整生成工作流。
- `pyautocad` 可作为局部验证或交互式工具的候选方案，不作为全系统基础。

## 成功方向

新旧链路能够以黄金样本和可追溯的执行记录进行比对；每一步迁移均可独立验证并在需要时回退。
