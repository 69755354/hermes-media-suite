# 交接卡渲染 64KB 预算：状态分区改造（2026-09-18 沙箱验证）

## 症状
长会话卡生成 READY，但渲染进新会话被拒：
`critical recovery state exceeds budget; explicit state partition required`
（实测卡 1866 KB / `context` 段 1863 KB，预算 `render_budget: 65536`）

## 生效上限怎么算（别只看配置值）
`min(render_budget, (min(model_windows) − 输出预留 8192 − 安全余量 8192) // 10)`
登记窗口 1M → 103,219；`render_budget 65536` 更小 → **实际 64KB**。
查值：`~/.hermes/context/config.json` 的 `render_budget`（每 profile 一份；
小鹿 `profiles/customer/context/config.json` 曾被设成 8000）。

## 根因（`handoff_builder.py` 三处，都是「归档内容内联」）
1. 压缩摘要全量内联进 `unknowns`（一条 1669 KB，占爆量 99.9%）
2. `goals` 无总量上界：722 条 × 240 字缩略 = 180.8 KB
   （`GOALS_INLINE_BUDGET` 只管单条截断，不管条目数）
3. `recent_conversation` 只限条数（40）不限字节，单条长消息仍能撑爆

## 改法：只留引用，正文留在对象里（不删任何数据）
- `unknowns[compression_summary_archives]` → 只留 `count` / `catalog_sha256` /
  每条 `message_id + chars + sha256`；正文按 id 回 transcript 对象捞
- `goals` → `GOALS_MAX_ITEMS = 80`：最近 80 条逐条，其余折叠成一条
  `request_index`（只存 message_id 列表）
- `recent_conversation` → `RECENT_INLINE_BUDGET = 16000` / 单条 400 字

## 实测（真实库副本，最大会话 722 条请求）
| | 改前 | 改后 |
|---|---|---|
| 卡文件 | 1866.1 KB | 61.9 KB |
| goals | 180.8 KB | 27.5 KB |
| unknowns | 1669.2 KB | 18.4 KB |
| 渲染 | 被拒 | 40,311 B（39.4/64 KB，余量 24.6 KB） |
小卡会话复验：11.2 KB → 6.6 KB，无回归。只丢「正文内联」，722 条请求 id 全在。

## 沙箱复现/验证配方（改渲染逻辑必须走）
1. 建沙箱目录：拷 `handoff_*.py` + `handoff_v2/` + `state.db` 副本
2. **必须给沙箱建 `hermes-agent` 符号链接**，否则 `handoff_legacy_gateway.repository()` 报
   `Hermes checkout not found`（它按 `__file__` 的父目录找同级 `hermes-agent/`）
3. `context/config.json` 的 `store_id`/`profile_id`/`node_id` **必须与库里行一致**，
   否则报 `unregistered or mismatched context store`；
   `context_session_links.store_id` 也要匹配（用原 store_id 最省事）
4. 身份别自己拼——直接取 `context_conversations.identity_json` 喂 `attach()`，
   否则 `conversation_id` 对不上报 `source mismatch`
5. 卡文件已存在时 `generate_handoff` 会**直接返回旧行**（不重建）：
   验证新版要 `DELETE FROM context_snapshots` + 清 `current_handoff_id` + 删卡文件

## 部署
- 补丁与脚本：`workflow/projects/context-architecture/patches/`（含 diff + README）
- 目标文件受门禁保护（`/.hermes/scripts/`），**只能人工 sudo 执行**：
  `sudo bash deploy_handoff_builder.sh <补丁文件> ~/.hermes/scripts/handoff_builder.py`
- cron/watchdog 每次重新导入即生效；常驻网关需重启

## 记牢的两条
- **抬上限不是出路**：8KB→64KB 抬了 8 倍照样爆（爆点 1.66MB），治的是「谁在无界内联」
- **归档 ≠ 可渲染**：归档内容该以「引用 + 校验和」进卡，正文留在对象里按 id 回捞

## 预算不是只看 `render_budget`（2026-09-18 实测公式）
```
生效预算 = min(render_budget, (min(登记窗口) − output_reserve − safety_margin) // 10)
```
- 分母的 10 (`RENDER_INPUT_DIVISOR`) 是硬编码安全系数；`output_reserve`/`safety_margin` 各默认 8192
- **窗口是人填的，不是模型自动读的**：`<profile_home>/context/config.json` 的 `model_windows`
- 空 `model_windows` + `render_budget > RENDER_DEFAULT(8000)` → 直接 `input budget unavailable for enlarged render`（**把预算调大却不登记窗口 = 自伤**）
- 卡片数据里没有 `model` 字段时走 `min(windows.values())`；键名写错也不报错（值对就行）
- 真实窗口查法：官网文档 + `POST /v1/chat/completions` 传超大 `max_tokens`（报 `valid range [1, N]`，不花额度）。实测 `deepseek-flash`=DeepSeek-V4.1-Flash，**窗口 1M / 输出上限 384K**

## 启用一台新 profile 的交接（小鹿 2026-09-18 实操清单）
1. 模块对齐：把 `handoff_*.py`（8 个）+ **`handoff_recovery_catalog.json`**（非 .py，漏了报 `history catalog missing or unsafe`）同步过去，逐文件 md5 比对
   - 跨机模块必须是**同一代**，否则 `handoff_gateway.py` 里 `trusted session identity missing` 的兜底缺失 → 会话加载报错
2. `context/config.json`：`enabled`/`ready`/`writers_ready` 置 true，`render_budget` 与 `model_windows` 必须配套
3. 重启该 profile 网关（PID 换新 + `gateway_state.json` 里 feishu connected）
4. 表会在**第一条消息进来**时由 `context_register` 自动建（在此之前 `context*` 表不存在是正常的）
5. 身份绑定不要手拼：生产走 `runtime_source(cfg, SessionSource)`；`legacy_identity` 是死路（它不产 `producer_kind`，必然 `unregistered producer`）

## 彩排必踩的两个坑（2026-09-18 各烧了一轮）
- **同进程自锁**：`generate_handoff` 内部自己取 `build_lock`；外面再 `with store.build_lock(...)` = 同进程同文件二次 flock → **永久卡死**（堆栈停 `handoff_store.py` 的 `fcntl.flock`）。要验证就只管调 `generate_handoff`
- **卡死还会连累后续**：被 `timeout` 杀掉的 ssh 客户端**不会**带走远端 python（孤儿进程继续占锁）→ 下次跑还是卡在同一处。清理：扫 `/proc/*/cmdline` 杀残留
- 彩排 `kind` 只接受 `checkpoint`/`rollover_final`/`recovery`/`transfer_projection`
- 排查卡死用 `faulthandler.dump_traceback_later(45, repeat=True)`；输出重定向时加 `python3 -u`，否则看不到进度

