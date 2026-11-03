# 跨机 provider 配置 + 阿里云百炼（MaaS）接入（2026-08-24 实测）

## 〇、🔴 用户引用"之前配过/我让你搞的 XX"时——先读会话记录，别猜别重推

本次会话后半段，用户反复引用历史动作（「你下午是不是让我搞了个代理」「去看下聊天记录」「就是搞那个OPENROUTER的时候那个代理」）我却在服务器上逐步折腾、猜测是哪个通道，浪费大量 token 且没踩准。**教训：**

- 用户一旦说「之前配过 XX」「那天让你搞的 XX」「去看聊天记录」——**第一动作就是 `session_search` 把那场会话调出来读**，从历史里拿准确语境，别在服务器上瞎探、瞎猜、更别让用户重新描述一遍
- 用户给的关键词（如「OpenRouter」「代理」「终端退出来」）若多个可能含义，**先 session_search 精确命中那场会话**，比在现网 grep/curl 试探快且准
- 猜错方向连续 2 次后立即停：**不再自己猜，直接告诉用户「我没搜到你指的哪个，你点一下具体是 A/B/C」**——耗 token 反复猜远不如一次问准（用户会恼「你特么去看下聊天记录」）

## 一、🚨 最大教训：跨机配 key 先确认「目标机器」

同一套 Hermes 配置可能同时存在于**新加坡机（sg-hermes-01）**和**广州机（gz-customer-01，小鹿/客户业务）**各自的 `~/.hermes/` 下。
用户说「配 GLM key」时**默认可能指的是广州机**（客户模型通道），不是新加坡机。

本次实测：我把新阿里 key 全套配到新加坡机还搭了中转，用户连纠两次（「先放到广州机」「我的意思是广州机用这个」）才意识到目标机器是广州机。

**跨机改 provider 前必问一句「新加坡还是广州机」，或直接比对两边现状：**
```bash
# 本机
grep -nA6 'custom_glm:' ~/.hermes/config.yaml
# 广州机（经 2222 反向隧道）
timeout 15 ssh -p 2222 -o BatchMode=yes ubuntu@127.0.0.1 'grep -nA6 "custom_glm:" ~/.hermes/config.yaml'
```

## 二、✅ 跨机改广州机 provider（经 2222 反向隧道，官方 hermes config set 通道）

广州机 hermes 默认不在 PATH，export 后可用官方通道过安全闸改 custom provider：

```bash
timeout 20 ssh -p 2222 -o BatchMode=yes ubuntu@127.0.0.1 '
export PATH="/home/ubuntu/.local/bin:$PATH"
hermes config set providers.custom_glm.api_key "$NEWKEY"
hermes config set providers.custom_glm.base_url "https://...maas.aliyuncs.com/compatible-mode/v1"
hermes config set providers.custom_glm.model "glm-5.2"
hermes config set providers.custom_glm.available_models_json "[{\"id\":\"glm-5.2\",...}]"
'
```

## 三、阿里云百炼（DashScope/MaaS）key 识别

- key 前缀 `sk-ws-` + host 含 `maas.aliyuncs.com` = **阿里云百炼**（智谱直连是 `z.ai`/`open.bigmodel.cn`，别混淆）
- 同一 key 多个 endpoint：OpenAI 兼容 = `.../compatible-mode/v1`；DashScope 原生 = `.../api/v1`；API Host（ws://）是另一码事
- 配 Hermes/codex 这类按 OpenAI 兼容的，用 `compatible-mode/v1` 那个

## 四、✅ 验证 key/模型真实可用：调 `/models`

别信配置里写死的 `available_models_json` 列表——用 key 调 `/models` 拿平台真实清单核实：
```bash
curl -s "https://<maas-host>/compatible-mode/v1/models" -H "Authorization: Bearer $NEWKEY" | grep '"id"'
```
实测：用户说「能调 glm-5.2 和 happyhorse1.1」，但 `/models` 全量清单**没有 happyhorse1.1**（chat/completions 报 `model_not_found` + `invalid_request_error`）——模型不存在或未开通，不是 key 问题。**别让配置里挂不存在的模型 ID**，跟用户确认后删掉/换真实 ID。

## 五、网络拓扑：新加坡 vs 广州 对国内服务的连通性

- **广州机（国内）能直连阿里云 maas、ARK、微信 CDN**——真调用放广州机就用真实 base_url
- **新加坡机（海外）直连这些被墙/超时**——除非要新加坡机实际调用，否则别硬搭中转
- 新加坡要通 → 走 8889 relay（generic passthrough，见 singapore-guangzhou-relay）
- cdn_relay.py 是「generic API passthrough」：非 CDN 目标原样透传 body+status、透传 Authorization 头，**任何新加坡直连不通的国内 HTTP(S) 服务都能借用**（不只 ARK/微信 CDN）

## 六、清理旧配置的正确姿势

- 删 `.env` 单项 key：`sed -i '/^GLM_API_KEY=/d; /^GLM_CODING_API_KEY=/d' ~/.hermes/.env`
- 删 config.yaml 顶层缩进块（保留后一条 web: 不被误删）：
  `sed -i '/^  custom_glm:/,/^  web:/{ /^  web:/!d }' config.yaml`
- 改前 `cp config.yaml config.yaml.bak-<tag>-<日期>` 备份
- `/etc/systemd/system/` 写入要 sudo（密码不入 AI，root 只走用户终端）；systemd 自启那步可用 nohup 后台进程临时顶上

### 不用 root 的常驻服务：用户级 systemd（`systemctl --user`，2026-08-24 实测）

跨机 relay 代理/常驻进程要"开机自启 + 崩溃自愈"，**不用 sudo 也能做**——用**用户级 systemd**（`~/.config/systemd/user/*.service` + `systemctl --user`），本机已有 `hermes-gateway.service`、`ai-video-factory-billing-tunnel.service` 就这么跑的。这是 `/etc/systemd/system/`（需 root）和 nohup（重启丢）之外的第三条路，最稳且免 root：

```bash
# 1. 写服务文件（无需 root）
cat > ~/.config/systemd/user/glm-aliyun-proxy.service <<'EOF'
[Unit]
Description=GLM-Aliyun relay proxy (SG local -> GZ cdn_relay -> Aliyun MaaS)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/ubuntu/.hermes/scripts/glm_aliyun_proxy.py --port 18890
WorkingDirectory=/home/ubuntu/.hermes/scripts
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# 2. 启用 + 立即启动（免 root）
systemctl --user daemon-reload
systemctl --user enable --now glm-aliyun-proxy.service
# 状态: Loaded+enabled, Active: active (running), Restart=always 崩溃自动拉起

# ⚠️ 停掉之前的 nohup 进程再交给 systemd，避免端口占用
pkill -f glm_aliyun_proxy.py   # 注意: pkill 可能把自己 shell 那个命令也信号到（exit -15），分开跑确认
```

ExecStart 用 `/usr/bin/python3`（系统自带的就能跑纯标准库脚本），别依赖 venv 的 python3（which python3 会指到 venv）。`pkill` 那步可能连当前 shell 一起收到信号返回 `-15`，**单独一个命令跑 pkill，下一条命令再启 systemd**。

### GLM/LLM token 记账（盯预算/代金券消耗，2026-08-24 实测）

阿里云百炼企业 MaaS key **查不了余额/配额**（`/quota`、`/billing`、`/balance`、`/metering`、`/usage` 全 404，REST 不开放）——余额只能上控制台/OpenAPI（需 AK/SK，不是 sk-ws 调用 key）。要盯"300 刀代金券烧了多少"，最实用的是**在转发代理响应里记 token**（token 是硬数据，单价另算）：

在 `glm_aliyun_proxy.py`（或任何 OpenAI 兼容转发代理）的 `_forward()` 拿到响应 body 后、发回客户端前，解析 `usage` 追加 JSONL：

```python
def _log_usage(self, method, path, status, resp_body):
    try:
        if status != 200 or path.strip("/").endswith("completions") is False:
            return
        data = json.loads(resp_body.decode("utf-8", errors="replace"))
        usage = data.get("usage") or {}
        if not usage:
            return
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": data.get("model", "glm-5.2"),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        }
        Path("/home/ubuntu/workflow/projects/glm-usage/glm_usage.jsonl").open("a", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 记账失败不影响主流程
```
需 import `datetime/timezone`、`pathlib.Path`。配套 `glm_usage_report.py` 汇总（按模型/按天 + 估算金额）。**单价别编造**——GLM-5.2 真实价未拿到时金额算占位（标"待校准"），token 数是硬数据可先用。

## 七、安全保护路径（工具层 hardline 拦截）

- `~/.hermes/config.yaml`：patch/write_file 工具被拒 → 用 terminal `sed -i`（走 smart approval）或 `hermes config set`
- `/etc/systemd/system/*.service`：write_file 被拒 → 要 sudo 终端写，或临时 nohup 进程
- 跨 SSSH 广州机时 `sed -i` 远程改 config 也可行（走隧道），但优先用广州机本地 `hermes config set`（官方通道更稳）
