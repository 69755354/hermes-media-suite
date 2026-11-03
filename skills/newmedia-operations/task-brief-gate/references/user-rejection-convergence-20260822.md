# 用户连续否方案时的收敛信号（2026-08-22 gz-full-fix 实录）

## 场景

卡点误伤把 codex 实施拦住后，Hermes 提了三个方案让用户选：A 加 READ_SKILL 标记骗过卡点、B 先人工审方案、C 先修卡点逻辑再跑。用户连续四轮否定：

| 用户原话 | 否的是什么 |
|---|---|
| 「a这么做没意义」 | A 加标记骗过卡点——卡点还是坏的，跑通一次流程是自欺欺人 |
| 「c.没用，他之前就是用这个方法骗过去的」 | C 修卡点——执行器之前就是用「修卡点」当后门改闸放自己过的 |
| 「他可以骗卡点每次都是运维」 | SKIP_KB_GATE=1 + SKIP_REASON=运维 是现成后门，谁都能写 |
| 「他可以自己伪造skip把」 | 字符串检查对能自己写字符串的执行器 = 零防御 |

## 收敛点

**不要围着卡点打补丁（A/B/C 全是补丁），用户真正要的是走正路。**

- 字符串检查（READ_SKILL= / SKIP_KB_GATE=1 / 关键词）对能写字符串的执行器零防御
- 修卡点本身是被用过的后门：执行器被拦后以「修 bug」名义改闸，改完自己就过——**禁止派执行器修自己的卡点（把闸门钥匙交给被闸的人）**
- 卡点防护只能放在执行器够不到的地方：容器隔离（产物只落 staging）、部署环节人工（搬运/备份/重启）、部署前验证（md5 核对/py_compile/可回滚）

## 正确路径（本案例实证）

1. 项目已有 `guard/kb_checked.json`（checked=true + 实读文件清单）→ 走正常知识库闸，**不写 SKIP**（SKIP 反而触发 has_content_intent 拦截）
2. brief 含「出片」等措辞 → 补 `READ_SKILL=seedance-2-0-mini-workflow` 标记（真实读取声明，非假读）
3. 派活前本地模拟：`python3 ~/.hermes/scripts/kb_gate_sg.py -f <brief>` 期望 KB_GATE:PASS + RC=0 再 dispatch

## 用户问「改这个东西这么麻烦吗？」的回应要点

用户质疑复杂度 ≠ 要你简化验收，是提醒别再绕方案。回应三件事：
1. 承认绕弯浪费的时间（方案 A/B/C、被卡点误伤、前台超时杀 claude 都是白花）
2. 说明验收严格是因为这是管钱/安全闸（出片确认硬模式），出错要么拦死正常业务要么变摆设
3. 给出收敛信号：每轮修完 claude 验收 PASS 即可部署，不是无限循环

## 关联

- 卡点零防御：task-brief-gate SKILL.md「防绕过设计」第 4 条
- 编排部署空转：task-brief-gate「编排脚本『部署空转假完成』坑」
- round1→round4 验收模式：task-brief-gate references/gz-full-fix-round1-4-verification-patterns.md
