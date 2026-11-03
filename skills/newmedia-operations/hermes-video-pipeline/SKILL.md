---
name: hermes-video-pipeline
description: |-
  【一键生成版本1】Hermes 全自动视频流水线。用户发需求→Hermes AI创作→调本地Helper API
  生成视频→返回结果回复用户。30-60秒出片，纯内网，0成本。

  触发词：做视频、生成视频、出片、整一个、跑一遍、试试
---

# 一键生成版本1 · Hermes 全自动视频流水线

## 🚨 Before You Start: Know Your Infrastructure

> **Proactive rule:** This skill has the full Helper API endpoint table below. Scan it before starting. Also load `skill_view(name="huoshan", file_path="references/local-infrastructure.md")` for the complete local infrastructure reference (DeepSeek models, Edge TTS, knowledge base, BK library paths). Do NOT ask the user what's available — check here first.

## 节点分工总表

### 【Hermes 智能体域 · LLM 创作 + 交互】

| 节点 | 任务 | 模型 | 备注 |
|:----|:-----|:-----|:-----|
| **节点0** | 信息采集+字段校验 | 豆包Vision Pro + OCR | 缺字段→自动追问→补全后继续 |
| **节点1** | 用户分析 | DeepSeek V4 Pro (0.2) | 地域/人群/驱动力 |
| **节点2** | 爆款拆解 | content-hunter / web_search | 搜满≥3条有效样本 |
| **节点3** | 选题生成(3组) | DeepSeek V4 Pro (0.7) | 五步链完整执行→用户确认后继续 |
| **节点4** | 剧本创作 | DeepSeek V4 Pro (0.8) | 30秒同城引流 |
| **节点5** | 视觉人设圣经 | DeepSeek Flash (0.1) | 每次新建不复用 |
| **节点6** | 文生图(Seedream) | Seedream 4.5 | 基于分镜+用户实景图 |
| **节点7** | 素材汇总 | JSON合并 | 合并实景图+AI图 |
| **节点8** | 分镜+提示词+配音+BGM | DeepSeek V4 Pro (0.3) | 直接输出完整prompt |
| | **↓ 输出标准化 JSON** | | |
| | **↓ 异步 POST /pipeline** | | |

## ⚠️ DEPRECATED — 请使用 huoshan 或 shuziren

> 本 skill 是 v1 一键生成版本的历史存档。节点结构与最新13节点工作流不兼容。
> ✅ 新项目请使用 `huoshan`（火山引擎通道）或 `shuziren`（婵镜数字人通道）。
> 保留本 skill 仅用于参考历史架构，不应用于新任务。

**⚠️ 节点8提示词写作纪律：** 写任何prompt前，加载 `wiki/concepts/seedance-director-prompt-dual-system.md`（导演双核体系）+ `wiki/concepts/seedance-prompt-template-library.md`（10套模板库）+ `wiki/concepts/seedance-2.0-prompt-formula.md`（九模块公式）。禁止凭感觉写。

### 【Helper API 执行域 · 零 LLM，纯工具调度】

| 节点 | 任务 | 说明 |
|:----|:-----|:-----|
| **节点9** | TTS配音生成 | Edge TTS，WAV 44100Hz单声道（Omni模式）|
| **节点10** | Seedance 视频生成 | 30s轮询+失败重试5次，接收节点9的WAV驱动口型 |
| **节点11** | ffmpeg合成+BGM | 音视频合成+叠BGM+字幕+门店水印 |
| **节点12** | 合规检查 | 违禁词扫描+地址价格校验，不通过自动回传修正 |
| | **↓ 回调 Hermes** | |

### 【交付层】

| 节点 | 任务 | 说明 |
|:----|:-----|:-----|
| **节点13** | 回复用户 | 模板拼接（视频+文案+标签+发布建议） |
| **节点14** | 主动推送飞书客户 | `hermes -p customer send` 出片后直接推客户飞书 DM |

## 主动推送飞书客户（节点14 · 2026-08-05 实测可用）

> ⚠️ **outbound webhook 推不了飞书客户私聊**。正道是 Hermes 自带 `hermes send`——复用 customer profile 的飞书凭证（小鹿身份），零接收端配置。

**命令（客户 DM）：**
```bash
hermes -p customer send --to "feishu:<CLIENT_CHAT_ID>" "视频出片完成 ✅ 门店名+标题"
```

**飞书目标对照（customer profile）：**
| 目标 | 谁 | 用途 |
|:----|:---|:-----|
| `feishu:<ADMIN_CHAT_ID>` | 天行者本人 | 内部通知 |
| `feishu:<CLIENT_CHAT_ID>` | 客户（心理顾问） | 出片交付 |
| `feishu:小鹿运营群` | 运营群 | 群发 |

**要点：**
- **必须带 `-p customer`**（客户在 customer profile 的飞书通道，默认 profile 只有微信）
- 目标格式：`platform:chat_id`（飞书 DM 用 `feishu:oc_xxx`）
- 发图片/视频附件：消息文本里带 `MEDIA:/绝对路径` 即可
- 验证目标列表：`hermes -p customer send --list`
- 跑在 gateway 进程内不影响当前会话（独立命令）

**流水线接入位置：** Helper API 回调成功后、节点13回复前，加一行 `hermes -p customer send` 推送成品。

## 调用方式

```python
import requests

r = requests.post("http://localhost:1888/pipeline", json={
    "task_id": "task_时间戳",
    "store_name": "门店名",
    "script": "完整剧本文案",
    "prompt": "画面描述（AI视频提示词）"
}, timeout=300)
```

## Helper API 端点

| 端点 | 说明 | 超时 |
|:----|:-----|:----:|
| `POST /pipeline` | 全流程一键 | 300s |
| `POST /seedance` | 仅文生视频 | 300s |
| `POST /seedream` | 仅文生图 | 30s |
| `POST /tts` | 仅配音 | 30s |
| `POST /compose` | 仅合成 | 120s |
| `POST /compliance` | 仅合规检查 | 5s |

## 姊妹 Skill

| 版本 | Skill名 | 适用场景 | 视频成本 | 水印 |
|:----|:--------|:---------|:--------:|:----:|
| **实体店版（本 skill）** | `hermes-video-pipeline` | 有实景门店，需店主真人+门店环境固定复用 | ✅ 多场景剧情 | ¥5-8/条 | ✅ 无水印 |
| **数字人版** | `shuziren` | 无实体店、虚拟IP、纯AI数字人口播 | ❌ 仅单场景口播 | **¥0/条**（Agnes AI） | ❌ 小红书水印 |
| **混合版（2026-07-06确认）** | `hermes-video-pipeline` | 有实景门店，需低成本出片 | ✅ Seedream图+Agnes视频 | **¥0/条** | ❌ 视频有水印 |

**数字人版核心差异**：生图用 Agnes Image API（免费）、视频用 Agnes Video API（免费+自带音画同步）、无需 TTS/ffmpeg 合成。详见 `shuziren` skill。

### 混合版工作流

```
Seedream(生图, ¥0, 无水印) → Agnes Video(图生视频+音频, ¥0, 带水印) → ffmpeg(拼接, ¥0)
```

**使用场景**：想用Seedream的高质量无水晶图片，但不介意Agnes视频端的水印。
**水印位置**：右上角"小红书"文字。
**提示**：Agnes Image 生成的图片也有水印，所以混合版只用 Seedream 生图。
**详见**：`huoshan` skill 的 `references/agnes-watermark-known-issue.md`（原 ai-short-video-production skill 未注册，2026-08-09 确认断链，实际水印问题记录在 huoshan）

## 架构总结

```
微信 → Hermes(LLM域:节点0-8)
         ↓ 标准化JSON → POST /pipeline
      Helper API(执行域:节点9-12,零LLM)
         ↓ TTS → Seedance → ffmpeg+BGM → 合规
         ↓ 回调JSON
      Hermes(交付层:节点13) → 回复微信
```
