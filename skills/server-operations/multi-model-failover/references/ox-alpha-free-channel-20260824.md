# Ox Alpha 免费降级通道（2026-08-24 实测落地）

## 背景

OpenRouter 2026-08-20 上线匿名模型 `stealth/ox-alpha`（中文社区称「牛来」），预览期**完全免费**（$0/$0），1M 上下文、128K 最大输出、支持文本+图片+视频输入。DeepSWE 社区实测 10 任务通过率 80%（Claude Fable 5 = 65%、GLM-5.3/Grok 4.6 = 62%、GPT-5.6 Sol = 52%），目前公开跑分第一梯队。厂商身份未揭晓，技术指纹指向智谱 GLM 系（tokenizer 与 GLM-5.3 完全吻合），也有 DeepMind 研究员暗示 Gemini 新版——匿名预览期，随时可能收费/下线，不能当生产依赖。

## 实测数据（新加坡机直调 OpenRouter）

| 任务 | 耗时 | tokens | 结果 |
|---|---|---|---|
| 中文（长沙话+普通话翻译） | 17.6s | 465 | 地道，还解释方言词义 |
| 代码（Python 去重排序函数） | 23.0s | 908 (被 800 截断) | 类型注解+docstring+保序，规范 |
| 推理（1-50 奇数和） | 2.7s | 146 | 625 正确 |

结论：速度 ≈ codex 级别（甚至略快，因无壳无沙箱），比 DeepSeek 主对话慢（15-23s/次），适合深度任务不适合日常聊天。免费档高峰期 429 限流（`stealth/ox-alpha is temporarily rate-limited upstream`，上游共享池限速），重试即恢复，不是故障。

## 通道落地（新加坡机）

两个文件，全部复用既有规则体系：

1. **`/home/ubuntu/workflow/ox_native_invoke.py`（规则注入版）**
   - `hermes_task_dispatch.py` 已加 `--target ox_native` 路由 + CREATIVE 路由拒绝（创作类强制 codex/claude，与 ds_native 同待遇）
   - token 硬校验 + 任务书 SHA256 防篡改（照 ds_gz_invoke.py validate_token）
   - **规则注入 build_system_prompt(task_type)**：AGENTS.md 铁律 + 基础三件套（content-data-review/content-review-gate）+ 任务类型 skill（TYPE_SKILLS 映射表）+ 合规红线，编译进 system prompt（实测 rule_chars=24250）
   - key 从 `/home/ubuntu/.hermes/.env` 的 `OPENROUTER_API_KEY` 读（剥 export 前缀）
   - max_tokens=30000，产出 PASS 带 model+rule_chars 字段
2. **`/home/ubuntu/workflow/ox_shell.sh`（配套执行壳，照广州 ds_gz_shell.sh）**
   - kb_gate_hard.py 知识库卡点（fail-closed）+ DEGRADED 标记 + 一次性 token 签发（`/home/ubuntu/workflow/gate_tokens`）+ write_attest.sh attestation（通道 ox_sg，role=producer）
   - 用法：`bash ox_shell.sh --type 分析 --project-dir <项目> --out <输出> "任务"`

端到端验证：Ox Alpha 亲口确认收到「执行铁律 + content-data-review + content-review-gate + systematic-thinking + 合规红线」五段规则——规则注入成功，不是裸奔。

## 降级链现状（codex 挂时）

codex 挂 → **ox_shell（免费，规则完整）** → DS Flash（付费兜底）→ claude（点名才用）。Ox Alpha 免费是最大卖点，比 DS 降级省钱。

## 🚨 派 Ox Alpha 写代码的输出格式坑（实测踩过）

Ox Alpha 输出代码时有两个格式问题，**第一版必踩，任务书必须带格式硬约束**：
1. **输出包在 markdown 代码块里**（```python ... ```）→ 直接 py_compile/bash -n 失败
2. **字符串内的 `\n` 写成真换行**（不转义）→ 语法错误，且 sed/正则修起来麻烦（跨行字符串、docstring、单双引号混杂，简单行数猜测修不干净）

**任务书格式硬约束（照抄）：**
```
七、输出格式硬约束（违反 = 任务失败）：
1. 禁止使用 markdown 代码块（不要输出 ```python 和 ``` 标记）——直接输出纯 Python 源码
2. 字符串里的换行必须写成 \n 转义（反斜杠+n 两个字符），禁止输出真换行
3. 禁止在输出末尾附加 OUTPUT 行、注释说明、解释文字——只输出代码本身
4. 产出文件必须是可被 python3 -m py_compile 直接编译通过的完整脚本
```
重派一次带硬约束即成功。教训：模型逻辑能对（改对 API 端点/路径/规则注入），但输出格式不可靠——验收必须 py_compile/bash -n + grep 关键改造点，别信 exit 0。

## OpenRouter 注册与 Mac 网络（踩坑记录）

- openrouter.ai 国内访问时通时断（广州直连实测 1.34-1.76s，但会抖动超时；新加坡 0.07s 稳）
- 注册卡邮箱验证/提交转圈：多半是网络抖动 + 免费档风控，F5 重试或换 GitHub OAuth（Continue with GitHub）绕过邮箱注册
- Mac（<MAC_USER>@<MAC_HOST>）**不能直连新加坡 22 端口**（防火墙），必须经广州跳板；Mac 公钥已加新加坡 + 广州 authorized_keys
- 有用的隧道姿势：`ssh -N -D <port> ubuntu@<GZ_HOST>`（Mac 本地 SOCKS，出口广州）、`ssh -N -D <port> -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>`（跳板到新加坡出口）、`ssh -N -L 1080:127.0.0.1:1080 ubuntu@<GZ_HOST>`（Mac 端口转发到广州机本地端口）
- 端口占用 `Address already in use` = 旧隧道没停干净，换端口或全停重开；一个窗口做两条隧道要 Ctrl+Z 挂起切换
- 免费档模型列表：OpenRouter 419 个模型，`:free` 后缀免费（glm-5.2:free 免费但上下文砍到 256K，限速；ox-alpha 免费全量 1M）
