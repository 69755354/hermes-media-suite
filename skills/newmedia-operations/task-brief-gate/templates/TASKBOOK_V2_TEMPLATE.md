# 任务书 v2 模板（P0-1，2026-08-24 定案）

> 五块固定结构。正文预算 ≤12KB。证据摘要独立为 digest，禁止把内嵌定案写成背景复制。
> SOURCE_MAP 未列出的源默认不读；REREAD 必须写理由。

```text
TASK_TYPE=<分析|分镜|复刻|出片|文案|...>          # 白名单内
READ_SKILL=<skill1>                                # 每行一个，禁止逗号列表（kb_gate 精确匹配）
READ_SKILL=<skill2>
EXEC_CHANNEL=<codex|claude|ds_native>
GATE_SCOPE=<...>
HUMAN_APPROVAL=REQUIRED
SELF_VERIFY=FORBIDDEN

---

# <任务标题>

## 0. 任务边界
| 项 | 值 |
|---|---|
| 风险级别 | 低/中/高 |
| 允许写入 | ... |
| 禁止写入 | ... |
| 禁止动作 | ...（不含任何裁量） |

## 1. USER_REQ（用户原话，不改写）
<原话全文>

## 2. APPROVED_DECISIONS（定案胶囊：只收已批准/权威定案，每条带来源）
| # | 定案内容 | 来源（文件:行号） |
|---|---|---|
| 1 | ... | ... |

## 3. SOURCE_MAP（必读源：文件、行号、读取目的；未列出默认不读）
| 文件 | 必读行号 | 读取目的 |
|---|---|---|
| path/to/file | 1-50, 120-140 | 拿 XXX 定案 |

## 4. OUTPUT_TEMPLATE（最终产物骨架：标题、表格列、必填字段）
<产物骨架，执行器只填内容，一次落盘>

## 5. VERIFY_COMMAND（唯一批量校验入口与通过条件）
```bash
python3 <verify脚本> <产物路径>   # 输出 PASS/FAIL + 失败项编号 + 定位行
```

## 6. 工具预算（软预算，超了必须列原因）
- Read ≤ 12 次，Bash ≤ 25 次，Write/Edit ≤ 6 次
- 同类 Bash 检查合并执行，禁止一个 grep 一轮
- 第二次读同一源必须写 REREAD_REASON

## 7. 自检清单
| # | 检查项 | 通过标准 |
|---|---|---|
| R1 | ... | ... |

## 8. 交付
- OUTPUT: <绝对路径> 一行
- 不自签 reviewer attest
```
