# GLM 代理路由问题：18890→8899 未走广州 SSH（2026-08-31 实测）

## 症状

GLM 调用持续报 502 relay error，但 key 有效（不是 key 过期问题）。

## 根因

GLM 代理链路：
```
codex_glm_fallback.sh
  → glm_native_invoke.py
    → http://127.0.0.1:18890/v1/chat/completions (glm_aliyun_proxy.py)
      → http://127.0.0.1:8899/upload?url=<ARK_URL> (cdn_relay)
        → 直连阿里云北京 (从新加坡)
          → 被墙/超时 → 502
```

**8899 relay 在监听（HTTP 200），但从新加坡直连阿里云北京被墙。** 三条活跃 SSH 隧道转发的是 8080/8890/1889，**没有 8899 的隧道**。

## 与 key 过期 502 的区别

| 症状 | 根因 | 诊断方法 |
|:---|:---|:---|
| 502 relay timeout | key 过期（401 被包装成 502） | 经广州 SSH curl 智谱 API 带 key → 401 令牌已过期 |
| 502 relay timeout | 8899 无 SSH 隧道（直连被墙） | 查 SSH 隧道列表无 8899 → relay 直连阿里云北京 |

两种 502 表现相同但根因不同，先按 `glm-502-diagnosis-20260831.md` 三步法测 key，key 有效再查隧道。

## 修复方向

用户定案方案 B：改 `glm_aliyun_proxy.py` 不走 8899 relay，直接 SSH 到广州执行 curl（跟 `dashscope_video.py` 同模式）。

## 活跃 SSH 隧道（2026-08-31 实测）

| PID | 转发 | 用途 |
|:---|:---|:---|
| 2553359 | 18080→8080 | 广州 HTTP 服务 |
| 2554700 | 18891→8890 | — |
| 3562599 | 11889→1889 | — |

**没有 8899 隧道** = relay 从新加坡直连阿里云北京 = 被墙。

## 教训

- relay 端口在监听 ≠ relay 链路通：监听只说明本地服务活着，上游能不能到是另一回事
- 查 502 时不只查 key，还要查 SSH 隧道覆盖了哪些端口
- `dashscope_video.py` 的模式（SSH 到广州执行 curl）比 relay 转发更可靠——直接绕过 relay 层