# Ox Alpha 规则注入执行壳（2026-08-24 实测）

## 背景

老板注册 OpenRouter（key 在 `~/.hermes/.env` 的 `OPENROUTER_API_KEY`），接入匿名免费模型 `stealth/ox-alpha`（「牛来」）。先做了简单裸调通道（复制 ds_native_invoke.py 改三处），老板看了广州小鹿 `ds_gz_invoke.py` 后定案：**用 Ox Alpha 自己照 ds_gz_invoke.py 的规则注入模式改**。

## 最终落地文件（SG 机）

- `/home/ubuntu/workflow/ox_native_invoke.py` — 规则注入版执行壳（正式版）
- 备份：`ox_native_invoke.py.bak_20260824_simple`（裸调版）
- dispatch 路由：`hermes_task_dispatch.py --target ox_native`（已加）
- 测试项目已清理（ox-channel-check / ox-rule-check / ox-rule-check2 / ox-shell-rework）

## 规则注入结构（build_system_prompt）

```
===== 执行铁律（AGENTS.md，最高优先级）=====
===== 基础规则（content-data-review）=====
===== 基础规则（content-review-gate）=====
===== 任务类型规则（按 TASK_TYPE 注入）=====
===== 合规红线（content-redlines）=====
```

- 路径（SG）：`/home/ubuntu/workflow/AGENTS.md`、`/home/ubuntu/.hermes/skills/newmedia-operations/{content-data-review,content-review-gate,content-redlines}/SKILL.md`
- 任务类型映射表 TYPE_SKILLS：文案→humanizer-zh、分析→systematic-thinking、策略→decision-framework、视频/探店/口播/分镜→video-production/huoshan/ai-image-gen-strategy、长文/网文→long-form-writing-quality、小红书→social-media-operator、生图→ai-image-gen-strategy、运维/机械/校对/格式/摘要→[]
- read_text 截断 60000 字符防单 skill 撑爆 system prompt
- PASS 输出带 `rule_chars` 字段（实测 ~24K chars）

## 端到端验证法

任务书让模型自报：「请确认你收到的系统提示里是否包含执行铁律/合规红线/基础规则段落？收到则写 规则注入确认=成功」。
实测 Ox Alpha 回复成功并列出 5 个段落标题 = 注入生效。rule_chars 字段二次印证。

## ⚠️ Ox Alpha 写代码的输出格式坑（重派两次）

1. **markdown 代码块**：输出包 ```python ... ``` → py_compile 报 invalid syntax at line 1
2. **字符串换行被压成字面 `\n`**：docstring/f-string 全碎（`"..." + "\n..."` 变成真换行）
3. **尾部带 OUTPUT 行/解释文字**

解法：
- 任务书追加「输出格式硬约束」段：禁代码块、字符串换行必须 `\n` 转义、尾部禁解释、产出必须 py_compile 可过
- 逻辑对格式坏时：先 sed 删代码块标记，再处理换行（字面 `\n` 解回真实换行；注意 `\\n` 双写要还原成 `\n`）——多错时重派比重写快

## 小鹿 ds_gz_invoke.py（广州机参考实现）

- `~/.hermes/scripts/ds_gz_invoke.py`（2026-08-24 12:39）+ `ds_gz_shell.sh`
- 与 SG ox_native_invoke.py 同构：token 硬校验 + 任务书 SHA256 防篡改 + 规则注入
- 区别：API 是 DeepSeek（广州直调），key 从 config.yaml providers.custom_custom.api_key 读；token 目录 /tmp/gz_ds_tokens
- 配套 shell 参数：--type/--model flash|pro/--project-dir/--user-req/--task-point/--out

## OpenRouter 注册 / key 配置

- key 放 `~/.hermes/.env`：`OPENROUTER_API_KEY=sk-or-...`
- 验证 key：`curl https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer <key>"` → data.label / is_free_tier
- 免费模型清单：`curl https://openrouter.ai/api/v1/models -H "Authorization: Bearer <key>"` 筛 pricing.prompt=0
- Ox Alpha 实测：中文地道、代码规范、推理准确（1-50 奇数和=625）；速度 15-23s/次（比 DS 慢）；DeepSWE 80% > Claude Fable 5 65% > GLM-5.3/Grok 62% > GPT-5.6 Sol 52%（社区 10 任务小样本）
- glm-5.2:free = 阉割版（256K 上下文 vs 付费 1M + 限速）
