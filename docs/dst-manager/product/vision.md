---
id: VISION-DM-001
title: DST Manager 产品愿景
status: accepted
owners:
  - dst-manager
created: 2026-08-17
updated: 2026-08-17
related:
  - ARCH-DM-001
---

# DST Manager 产品愿景

## 产品愿景

为单人单机真实工程提供可审计、可恢复的 DST/DWG 检查、编辑和发布工具，使每次结构性变更都具有可理解的预览、明确的执行边界和可追溯的结果。

## 写入与运行边界

- 写入必须依次经过完整预览、基准修订校验、受控 CAD Worker 执行、结果验证和整批发布。
- DST 修改保持 `DST → XML DOM → DST` 受控链路；正式发布保留永久 before 快照，并在失败时恢复整批发布前状态。
- 需要 AutoCAD 的数据库操作仅由匹配版本的 CAD Worker 完成，用户输入不得直接拼接为 SCR、Shell 或路径命令。
- MVP 仅监听 `127.0.0.1`，不扩展为多用户、远程任务调度或跨机器 Worker。
