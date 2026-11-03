# 死区预生成 + checksum 算法修复（2026-08-30）

## 问题1：死区——compression threshold 到 watchdog soft threshold 之间无交接包

### 现象

会话上下文涨到 177K（过了 compression threshold 167K），但 compression 被 cooldown 拦截（`compression is currently blocked (cooldown:20)`）。同时 watchdog soft threshold 是 300K，没到。会话卡在 167K~300K 死区：
- compression 够得着但被 cooldown 拦
- watchdog 归档够不着（没到 300K）
- 不归档 = 不生成交接包
- `/new` → AGENTS.md 没有当前会话的包 → 上下文全丢

### 根因

交接包只有两条路生成：
1. `session_rollover.py` 归档时——但会话没到硬限，不归档
2. watchdog `prebuild_handoff()`——但 prebuild 只在归档前跑，不归档就不跑

缺第三条路：compression 被 cooldown 拦截时，应触发 prebuild 预生成交接包。

### 修复

在 `context_rollover_watchdog.py` 新增 `--prebuild-threshold` 参数（默认 0 禁用）：
- 会话 `input_tokens > prebuild_threshold` 但未触发 soft/hard 阈值时，仅调 `prebuild_handoff()` 预生成交接包，不归档
- 幂等：已有有效包复用不重建
- wrapper 加 `--prebuild-threshold 167000`（对齐 compression threshold 0.16 × 1M ≈ 167K）
- 新增 `prebuilt` 列表追踪 + 输出 `[预生成]` 行
- `any_candidate` 包含 `prebuilt` 触发 injector 刷 AGENTS.md

### 代码位置

- `build_parser()`: 新增 `--prebuild-threshold` 参数
- `main()` 顶部: 新增 `prebuilt = []` 列表
- `main()` 死区逻辑: `if not soft_reason and not hard:` 块内，`grace.clear(sid); continue` 之前
- 输出部分: `prebuilt` 输出块在 `manual_review` 之前

### 验证

```
WATCHDOG: 1 个会话在死区预生成交接包
  [预生成] 20260829_140402_e2f07cf4 tokens=168,289
```

## 问题2：checksum 算法不一致——prebuild 永远 BAD_CHECKSUM

### 现象

死区预生成逻辑加上后 dry-run 无输出。调试发现 `prebuild_handoff()` 对已有包返回 `MANUAL_REVIEW_REQUIRED: BAD_CHECKSUM`，即使包是刚生成的。

### 根因

三处 checksum 算法不一致：

| 位置 | 算法 |
|:--|:--|
| `handoff_builder.py` | `json.dumps(data, ensure_ascii=False, indent=2)` — 不去 checksum，不 sort_keys |
| `handoff_gate.py` | `json.dumps(data_for_hash, ensure_ascii=False, indent=2)` — 去 checksum，不 sort_keys |
| `watchdog validate_checksum` | `json.dumps(data_for_hash, sort_keys=True, separators=(',',':'), ensure_ascii=False)` — 去 checksum，sort_keys，无空格 |

handoff_gate 和 handoff_builder 算法一致（都是 indent=2 不 sort_keys），但 watchdog 用了 sort_keys+separators → 跟 builder 不一致 → prebuild 永远判 BAD_CHECKSUM → 永远走不到 OK 分支。

### 修复

改 watchdog `validate_checksum()` 的 canonical 行：
```python
# 改前（错误）
canonical = json.dumps(data_for_hash, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
# 改后（对齐 handoff_gate）
canonical = json.dumps(data_for_hash, ensure_ascii=False, indent=2)
```

### 验证

修后 `prebuild_handoff()` 对新生成的包返回 `OK`。dry-run 死区预生成正常输出。

## 双机同步

- .py: scp 到广州机 + md5sum 验证一致 + py_compile
- .sh: 广州机 wrapper 加 `--prebuild-threshold 167000`，db 路径不同（customer profile）
- 广州机 3 个巨型会话（120万/186万/252万 token）交接包 checksum 全 OK
- 两机 cron 每 10 分钟跑 watchdog + 每 5 分钟跑 handoff_injector

## 教训

- **checksum 算法必须三处一致**：builder（生成）、gate（校验）、watchdog（预生成校验）用同一个 `json.dumps` 参数。改了 builder 必须同步 gate 和 watchdog。
- **死区是设计盲区**：compression threshold 和 watchdog threshold 之间如果有 gap，会话卡在里面既不压缩也不归档也不生成交接包。`--prebuild-threshold` 填这个盲区。
- **dry-run 无输出 ≠ 无问题**：dry-run 跑了但 prebuilt 列表为空，需要手动 import 模块调 `prebuild_handoff()` 看返回值才能发现 BAD_CHECKSUM。
- **旧 BAD_CHECKSUM 记录已过时**：skill 里之前写「`json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)` 后 sha256」是 watchdog 的算法，不是 builder 的。builder 用 `indent=2` 不 sort_keys。已修正。