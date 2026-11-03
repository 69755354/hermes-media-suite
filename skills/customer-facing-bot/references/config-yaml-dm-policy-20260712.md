# Config.yaml DM Policy — 2026-07-12 实测记录

## 背景

客户 bot 「小天」WeChat 网关需要设置 `dm_policy=open` + `allow_all_users=true`。最初在 `.env` 里设了：

```ini
WEIXIN_DM_POLICY=open
WEIXIN_ALLOW_ALL_USERS=true
```

但重启后不生效。

## 根因

检查 gateway 进程环境变量：

```bash
cat /proc/<PID>/environ | tr '\0' '\n' | grep WEIXIN
```

结果：**只有 `HERMES_HOME`，没有 `WEIXIN_DM_POLICY` 或 `WEIXIN_ALLOW_ALL_USERS`。**

对比默认网关（PID 1229）：

```bash
cat /proc/1229/environ | tr '\0' '\n' | grep WEIXIN
# → WEIXIN_DM_POLICY=pairing
# → WEIXIN_ALLOW_ALL_USERS=false
```

默认网关的 .env 被加载了，客户网关的 .env **没被加载**。原因可能是 systemd 的 `EnvironmentFile` 或 Hermes 的 .env 加载机制在 profile 模式下有差异。

## 正确方案

weixin adapter 源码（`gateway/platforms/weixin.py`）：

```python
self._dm_policy = str(extra.get("dm_policy") or os.getenv("WEIXIN_DM_POLICY", "pairing")).strip().lower()
```

优先读 `extra.get("dm_policy")`（来自 config.yaml 的 `platforms.weixin.dm_policy`），fallback 到 `os.getenv("WEIXIN_DM_POLICY")`。

所以在 config.yaml 里设：

```yaml
platforms:
  lightclawbot:
    enabled: true
  weixin:
    enabled: true
    dm_policy: open          # ← 推荐
    allow_all_users: true    # ← 推荐
```

比 .env 更可靠。

## 重启后 WeChat disconnected 的问题

改完 config.yaml 重启后，`gateway_state.json` 可能短暂显示 `weixin: {state: "disconnected"}`。等 10-15 秒后会自动连上。

如果持续 disconnected：
1. 检查 PID 是否变了（确认已重启）
2. 等 15 秒再查
3. 如果还不行，clean restart：
   ```bash
   systemctl --user stop hermes-gateway-customer
   sleep 2
   rm -f .../gateway.lock .../gateway_state.json
   systemctl --user start hermes-gateway-customer
   sleep 15
   ```

## 验证配置生效

改完 config.yaml → 重启 gateway → 发测试消息 → 检查 `channel_directory.json` 是否有新频道。

不要只看 `gateway_state.json` 的 `weixin.state`，还要看 `channel_directory.json` 里 `weixin` 数量 > 0。
