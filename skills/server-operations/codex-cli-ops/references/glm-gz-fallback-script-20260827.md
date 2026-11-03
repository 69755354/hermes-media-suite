# GLM 广州机 codex_glm_fallback.sh 封装脚本（2026-08-27 实战）

> 适用：广州机 `~/.hermes/scripts/codex_glm_fallback.sh`
> 关联：`glm-gz-shell` skill（user-owned，不可 curator 改）记录了手动调 GLM 流程

## 核心事实

### 脚本自包含，自动签 gate token

`codex_glm_fallback.sh` 是一个完整封装脚本，**调用方不需要手动生成 TASK_GATE_TOKEN**。脚本内部自动完成：

1. 解析 `--type`（白名单：文案/分析/策略/长文/网文/口播/剧情/写作/小说/脚本/分镜/方案/洞察/画像/小红书/视频/探店/运维/环境/机械/校对/格式/摘要）
2. 写任务书到 `/tmp/codex_glm_brief_<ts>.md`（**冒号 KV 格式**，不用等号——等号格式 parse_task_book 解析不到必填字段，rc=2）
3. **自己用 `uuid.uuid4().hex` 生成 gate token**，写 JSON 到 `/home/ubuntu/workflow/gate_tokens/`
4. 用 `TASK_GATE_TOKEN=$TOKEN python3 glm_native_invoke.py` 调 GLM
5. 成功输出 `OUTPUT: <路径>`，失败 exit 5
6. trap cleanup 自动清理任务书和未消费 token

### 用法（从 SG 远程调）

```bash
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  "bash ~/.hermes/scripts/codex_glm_fallback.sh \
   --type 分析 \
   --project-dir /home/ubuntu/workflow/projects/<项目> \
   --user-req '用户原话' \
   --out /tmp/glm_out.txt \
   '任务 prompt 全文'"
```

**不带 `--out` 时**：输出写到 `/tmp/codex_glm_out_<ts>_<pid>.txt`，脚本 stdout 打印 `OUTPUT: <路径>`，调用方按此标记读。

### ⚠️ 名字误导：没有 codex 回退逻辑

脚本叫 `codex_glm_fallback.sh`（名字暗示 codex 挂了 fallback 到 GLM），但实际逻辑是：
- **直接调 GLM**，不先试 codex
- **GLM 失败（含 429）→ exit 5，不自动切 codex**

之前 GLM 429 炸了自动切 codex 的回退发生在**更上层**（SG 侧 Hermes 判断 exit code 后改派 codex），不是这个脚本做的。

### 与手动流程对比

| 维度 | `codex_glm_fallback.sh` | 手动流程（glm-gz-shell skill 记录） |
|:---|:---|:---|
| token | 自动生成 | 手动 uuid4+sha256+写 JSON |
| 任务书 | 自动写（冒号 KV） | 手动 write_file+scp |
| 步骤数 | 一条命令 | 5 步 |
| 适用 | 快速派活、标准任务类型 | 需要精细控制任务书格式/输出路径 |
| 清理 | trap 自动 | 手动 rm |

### dispatch 无 glm_native target

SG 机 `hermes_task_dispatch.py` 只支持 4 个 target：`codex`/`claude`/`ds_native`/`ox_native`。**没有 `glm_native`**。GLM 走 `codex_glm_fallback.sh` 或手动流程，不经 dispatch 统一入口。

如果需要 dispatch 统一管 GLM，要在 `hermes_task_dispatch.py` 的 target 白名单加 `glm_native` + 加对应分支（cmd 指向 glm_native_invoke.py）。目前未做。

## 脚本路径速查

| 文件 | 位置 | 说明 |
|:---|:---|:---|
| `codex_glm_fallback.sh` | GZ `~/.hermes/scripts/` | 一键封装脚本 |
| `glm_native_invoke.py` | GZ `~/.hermes/scripts/` | GLM 执行壳（max_tokens 已修 16384） |
| `gate_tokens/` | GZ `/home/ubuntu/workflow/gate_tokens/` | token JSON 存放目录 |
| `hermes_task_dispatch.py` | SG `/home/ubuntu/workflow/` | 统一派活入口（无 glm_native target） |

## 调用方判断流程

用户说「走 GLM」时：
1. 确认广州机隧道通：`ssh -p 2222 ... "hostname"` → `gz-customer-01`
2. 直接用 `codex_glm_fallback.sh` 一键调（不需要手动生成 token）
3. 看 exit code：0=成功（读 `OUTPUT:` 路径）、5=GLM 失败（看 stderr 日志）
4. **GLM 429 失败时**：不自动切 codex，汇报给用户问是否切通道
