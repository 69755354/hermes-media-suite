---
name: review-fix-verify-loop
description: 触发：codex修复越改越烂/审查后让codex改/交叉验证修复。用「审查-修复-验证」循环防codex改坏。
author: Hermes curator
license: MIT
version: 1.0
metadata:
  hermes:
    tags: [codex, review, fix, verify, quality, mutation-testing]
    category: software-development
---

# 审查-修复-验证循环（2026-08-12 定案）

## When to Use

触发：codex 修复任务（尤其「越改 bug 越多」时）、Claude/codex 审查后发现问题的修复、任何需要「改代码且不能改坏」的场景。核心原则：**生产者 ≠ 评审者，每步验证，交叉打穿**。

## 为什么需要

codex 单独改代码容易越改越烂——因为它无测试兜底、无 git 回滚、无外部验证（盲改）。本循环给它套安全网：**先实测定位 → 分步改 → 每步测试 → 交叉验证 → 突变打穿**。

## 循环流程

```
① Claude（审）→ 实测定位问题（构造测试/穿越测试，先证明「确实能绕过」）
        ↓ 给修复建议（含：改哪/怎么改/别碰什么）
② codex（改）→ 按建议改 → 每步跑测试 → 绿了才下一步
        ↓ git commit（分块）
③ Claude（再审）→ 验证修复 → 突变测试打穿 → 发现新问题 → 回到①
```

## 5 个关键机制

### 1. 审查者先实测再给建议（不是纸上谈兵）
- Claude 审门禁/代码时**构造测试项目跑穿越测试**（touch 空文件/伪造哈希/三步绕过）
- 先证明「确实能绕过」→ 再告诉 codex 改哪
- **不要**只看代码说「这里可能有问题」——要实测证明

### 2. codex 每步验证 + commit（安全网）
- 改前 git 快照（`git init` + 首次 commit）
- 改后跑测试（typecheck + 单测）→ 全绿才 commit
- 挂了 → `git checkout <file>` 回滚重改
- **没有 git/测试的项目，先搭地基再改**（git + tsconfig strict + 核心单测）

### 3. 交叉验证（不信自证）
- codex 说「修好了」→ 审查者用**突变测试**打穿（构造破坏性用例看抓不抓得住）
- **只信实测，不信 codex 的自述**
- 发现绕过路径没堵死 → 打回重改

### 4. 分块改 + 测试补丁
- 不让 codex 一口气改完——分 P0/P1/P2 批，每批验证
- 每次修复**补回归测试**（守门测试：manual 门不得盖章/未获批上游必 BLOCKED/legacy 适配器仍执行）
- 防下次改坏：回归测试是「已修复」的证明，坏了立刻红

### 5. 执行者分离（生产者 ≠ 评审者）
- codex 改的 → Claude 审；Claude 审的 → codex 改
- **同一个模型既不生产也不自评**——避免「自产自评」盲区
- 双执行器（codex+claude）的价值就在这

## 实测案例（2026-08-11/12）

- **门禁 P0 三步绕过**：Claude 构造三步绕过（G_COPY_READY manual 盖章 → G_CREATIVE_READY 放行垃圾上游）→ codex 修（check_upstream_hashes 断言 ALLOWED + record_gate 写 None）→ Claude 再审 + codex 重放三步验证堵死 ✅
- **v9 分镜突变测试**：Claude 21 例突变（删镜/超时长/语速/台词）→ codex 修 → 9/10 命中率
- **codex 单独改 v11/v12 越改越烂** vs **Claude+codex 循环后稳定**——差别就是有没有安全网

## 踩坑

- **审查者必须实测**：只读代码说「可能有问题」不够——要构造用例证明绕过
- **别信 skill/文件的自我声明**：`video-production` 自称「合并单一入口」但 AGENTS.md 同时强制加载它和它宣称吸收的文件——按实际加载链验证
- **测试盲区**：测试全绿 ≠ 安全——手工预置 ALLOWED 哈希会让守门测试永远测不到绕过路径（P0-3 教训）
- **归档前留原文**：合并/删除 skill 或文件前，先留原文副本（git 或 backups），否则无法验证「没丢内容」

## 相关

- codex-bridge：任务打包规则（谁写谁读知识库/去AI味/执行者标注）
- content-review-gate：质量门（四维评审）
- 门禁体系：workflow_gate.py（G_STRATEGY_BY_CODEX 等）
