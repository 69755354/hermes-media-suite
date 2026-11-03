# 跨机部署 task_brief_gate（2026-08-21 广州机同步实测）

## 场景

主对话打包卡点（task_brief_gate.py + gate_config.yaml）已在新加坡机落地后，
用户说「广州那边也这么改」= 把同一套 USER_REQ 强制 + 判断词检查机制部署到广州机。
广州机跑小鹿客户业务（customer profile），不能直接拷文件就完事。

## 部署前侦察（必做，顺序执行）

1. **确认目标机有没有 token 层**：查 `hermes_task_dispatch.py` / `kb_gate_sg.py` / `workflow/gate_tokens/`。
   新加坡 = 有 token 层（统一入口签发一次性 token → 执行器壳校验）。
   广州 = 无 token 层（Hermes 直调 wrapper：codex_remote.sh / claude_remote_wrapper.sh / ds_fallback.sh）。
   → 挂法完全不同：有 token 层走「入口签发+壳校验」；无 token 层只能「wrapper 内嵌直接校验」。

2. **确认目标机已有 gate 机制**：广州机已有 `~/.hermes/scripts/kb_gate_hard.py`
   （知识库物理卡点，挂在 codex_remote.sh generic 分支），但那是「执行器开工前读知识库」的闸，
   跟 task_brief_gate（Hermes 打包任务书闸）是两套东西，不是替代关系，是叠加关系。

3. **查目标机真实任务书格式**（关键！不能盲拷）：
   ```sql
   -- customer profile 会话库（广州机）
   SELECT COUNT(*) FROM messages WHERE content LIKE '%TASK_TYPE%';
   -- 提取 TASK_TYPE 值分布 + PROJECT_DIR / USER_REQ 出现次数
   ```
   广州实测：TASK_TYPE 出现 72 次但值只有「分析」「出片`」（带反引号的脏值），
   PROJECT_DIR 标记为 0，USER_REQ 仅 2 次。→ 盲拷新加坡 gate_config 会导致六类任务里
   广州实际用到的类型配置对不上、脏值直接 BLOCK。

## 关键坑：缺 TASK_TYPE = 硬 BLOCK，不受 mode=WARN 保护

task_brief_gate.py 的 run() 里：
```python
if not task_type or task_type not in config.get("tasks", {}):
    return {"decision": "BLOCK", ...}  # 不走 mode 判断！
```
缺 TASK_TYPE 或值不在六类白名单（复刻/分镜/生图/出片/文案/分析）→ 直接 BLOCK，
**跟 gate_config.yaml 的 mode=WARN 无关**。广州机任务书如果没有 TASK_TYPE 标记，
直接挂上 = 所有任务全被拦。所以跨机部署必须：
- 要么任务书规范到带 TASK_TYPE（广州已部分带，但值有脏「出片`」）
- 要么部署成「观察期包装」：校验结果只记录不拦截

## 推荐挂法：观察期 wrapper（gz_brief_gate_check.sh 模式）

无 token 层机器用「wrapper 内嵌 + 观察期不拦截」：

1. 写公共校验脚本 `scripts/gz_brief_gate_check.sh`：
   - 从 prompt 提取项目目录（PROJECT_DIR= 优先，其次路径正则，**兼容 /tmp/projects/**）
   - `printf '%s' "$PROMPT" | python3 task_brief_gate.py --brief /dev/stdin --project "${PROJ:-/nonexistent}"`
   - **观察期：一律 `exit 0`**（BLOCK 也只记日志不拦，防误伤现有任务书）
   - 切 BLOCK 时取消 `exit $RC` 注释（与新加坡 mode=WARN→BLOCK 的 promotion_policy 对齐）
   - 注意：`--brief` 传真实换行文本，测试时 printf 的 `\n` 是字面量会整串并成一行导致解析失败

2. 三个 wrapper 各插一行（放在 PROMPT 组装/校验之后、真正执行之前）：
   ```bash
   bash /home/ubuntu/workflow/scripts/gz_brief_gate_check.sh "$PROMPT" "$WORKDIR" 2>&1 | grep '\[brief-gate\]' >&2 || true
   ```
   `|| true` 保证观察期绝对不阻断原流程。

3. 部署序列：备份目标 wrapper（.bak-<date>）→ scp task_brief_gate.py + gate_config.yaml
   → scp 修改后的 wrapper → bash -n 语法校验 → 三用例验证。

## 验证用例（部署后必跑）

| 用例 | 期望 |
|---|---|
| 无 TASK_TYPE 的普通任务 | 记录 BLOCK，观察期放行（rc=0） |
| TASK_TYPE=分析 + 真实项目 | WARN/PASS 放行，审计落盘 |
| 缺 USER_REQ | WARN 放行，审计落盘 |

验证后 `tail gate_audit.log` 确认审计日志在目标机落盘（路径由 gate_config.yaml 的 audit_log 指定）。

## 切 BLOCK 前清单（观察期 7 天后）

- 广州任务书补 `USER_REQ=` / `PROJECT_DIR=` 标记，或按广州格式调 gate_config
- 修正 TASK_TYPE 脏值（「出片`」带反引号不在白名单 → BLOCK）
- 广州项目有的无 `guard/` 目录（如 qingfuren 本体）→ 会被判「非真实项目」拦下，需补目录或调配置

## 文件清单（本次部署）

- 新增：`/home/ubuntu/workflow/task_brief_gate.py` + `gate_config.yaml`（新加坡原样）
- 新增：`/home/ubuntu/workflow/scripts/gz_brief_gate_check.sh`
- 修改：`~/.hermes/scripts/codex_remote.sh`、`workflow/scripts/claude_remote_wrapper.sh`、`workflow/scripts/ds_fallback.sh`
- 备份：三个 wrapper 的 `.bak-20260821`
