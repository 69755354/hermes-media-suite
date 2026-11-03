# 壳里模型换成 DeepSeek（codex 官方壳走 DS，2026-09-16 实测通）

## 结论
codex 官方壳（0.153.4）可以直接吃 DeepSeek 模型，保留沙箱 + 工具循环——不是只能走无工具循环的 `ds_native` 直调。

## 落地三处

1. `~/.codex/config.toml` 顶层（必须在所有 `[表]` 之前）：
```toml
model = "deepseek-v4-pro"
model_provider = "deepseek"
```
2. 文件末尾加 provider 块：
```toml
[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```
3. 密钥靠环境变量注入（**不要写进 codex 配置**）：`DEEPSEEK_API_KEY` 从 `/home/ubuntu/.hermes/config.yaml` 的 `model.api_key` 取。
   - `~/.hermes/scripts/codex_sandbox.sh` 已内置该注入 + `docker run -e DEEPSEEK_API_KEY`（容器内 codex 也要能拿到）。
   - 直接在本机跑 `codex exec` 时：`export DEEPSEEK_API_KEY=$(awk '/^  api_key: /{print $2; exit}' /home/ubuntu/.hermes/config.yaml)`。

## 踩坑（都实测撞过）

- **`wire_api = "chat"` 已废弃**：0.153.4 报 `Error loading config.toml: wire_api = "chat" is no longer supported`，只认 `responses`。DeepSeek 支持 Responses 协议（`POST https://api.deepseek.com/v1/responses` → HTTP 200，实测），所以能接。
- **profile 不能写在 config.toml 里**：新版报 `--profile gpt6 cannot be used while config.toml contains legacy [profiles.gpt6]`，必须拆到 `~/.codex/gpt6.config.toml`：
```toml
model = "gpt-6-astra"
model_provider = "openai"
```
  回退实测成功（一次 trivial 调用 tokens used 13,427）。
- **容器缺 key 会报 `Missing environment variable: DEEPSEEK_API_KEY`**：光在宿主机 export 不够，`docker run` 必须 `-e DEEPSEEK_API_KEY`。
- **`codex_exec_gated.sh` 是 root:ubuntu `-r-xr-x---`**，改不动也不用改——它调 `codex_sandbox.sh`，key 在沙箱壳里注入即可。
- **成本提醒**：走 DS 后按 token 计费，实测一次 trivial 调用的 codex 报 `tokens used 233,958`（完整 AGENTS.md + 工具定义进上下文；GPT 侧同题只报 13,427），命中缓存便宜、冷启动贵，要瘦身上下文的话从沙箱挂载的 AGENTS.md 下手。

## 验证命令（照抄可复现）
```bash
export DEEPSEEK_API_KEY=$(awk '/^  api_key: /{print $2; exit}' /home/ubuntu/.hermes/config.yaml)
cd /home/ubuntu/workflow && codex exec --skip-git-repo-check "只回复两个字：可以"   # 默认 → DeepSeek
printf '只回复两个字：可以\n' > /tmp/p.txt
bash /home/ubuntu/.hermes/scripts/codex_sandbox.sh /tmp/p.txt high /home/ubuntu/workflow   # 沙箱内也走 DS
codex exec --profile gpt6 --skip-git-repo-check "只回复两个字：可以"   # 回退 GPT
```
判据：输出里出现 `Model metadata for deepseek-v4-pro` 警告 + 正常回答 = DS 通道生效。

## 壳瘦身：900KB → 52KB（2026-09-16 实测）

**根因**：codex 把 ChatGPT 账号连接的一堆 App（Adobe / GitHub / Linear / Figma / Google Drive / Gmail / Zoom / Trip.com …）的 MCP 工具定义全量塞进**每次**请求 —— 单个请求体 904,574 字节里，`tools` 占 885,432，消息部分只有 25k。切到按 token 计费的 DeepSeek 后这就是真金白银。

**关掉三处（都实测有效）**：
```bash
codex features disable apps          # 最大头：干掉全部 mcp__codex_apps__* 工具（约 850KB）
codex features disable multi_agent   # 干掉 multi_agent_v1 工具（约 10KB；与本机「子代理永久禁用」一致）
# config.toml 里再加：关掉未安装插件推荐清单（约 15KB）
[plugins.recommendations]
mode = "off"
```
结果：请求体 **904,574 → 52,386 字节（-94%）**；codex 自报 tokens **233,958 → 约 7–8k**（沙箱路径约 16k，多出来的是挂载的 AGENTS.md）。

**注意**：`features.enable_mcp_apps=false` 与 `features.tool_search_always_defer_mcp_tools=true` **无效**（前者本来就是 false）；真正的开关是 `apps`。用 `codex features list` 看当前状态，别猜。

**量请求体的办法（可信测量，别信 codex 打印的 tokens）**：codex 在 DeepSeek 通道上打印的 `tokens used` 会因前缀缓存而变成几十~几百，**不能当上下文大小**。要真数就起一个本地 HTTP 代理（记录 Content-Length 并转发到 `https://api.deepseek.com`），再让 codex 指过去：
```bash
codex exec -c model_providers.deepseek.base_url=http://127.0.0.1:8896/v1 "..."
```
缓存目录 `~/.codex/cache/{codex_apps_tools,remote_plugin_catalog}`（共 23MB）在开关生效后可以清掉，实测不再重新长回来。

**残留大头**：`<skills_instructions>` 约 21k 字符（48 个投影 skill 的名字+描述）——codex 靠它挑 skill，属有用上下文，要砍就得缩 skill 投影。
