---
name: content-review-gate
title: 内容评审门禁
description: 发布前质量评审体系：四维打分（钩子/情绪/共鸣/转化）+平台权重+Judge配置+物理卡点。触发：文案产出后（初稿评审≥60）、交付前（终审≥68）。
version: 1.0
---

# 内容评审门禁（2026-08-01 落地）

## 体系来源
豆包App评审法（权重体系+严格锚点）+ 实测校准（DeepSeek 用豆包框架后评分与豆包一致）

## 四维权重（平台差异化）

| 平台 | 钩子 | 情绪 | 共鸣 | 转化 | 状态 |
|:-----|:----:|:----:|:----:|:----:|:----:|
| 公众号长文 | 0.16 | 0.34 | 0.30 | 0.20 | ✅已验证 |
| 小红书图文 | 0.25 | 0.30 | 0.30 | 0.15 | ⚠️待校准 |
| 抖音短视频 | 0.30 | 0.25 | 0.25 | 0.20 | ⚠️待校准 |
| 口播/数字人 | 0.25 | 0.25 | 0.25 | 0.25 | ⚠️待校准 |
| 视频号 | 0.20 | 0.30 | 0.30 | 0.20 | ⚠️待校准 |
| B站 | 0.15 | 0.25 | 0.30 | 0.30 | ⚠️待校准 |
| 快手 | 0.25 | 0.25 | 0.30 | 0.20 | ⚠️待校准 |

## Judge 配置（定案）

```python
payload = {
    "model": "deepseek-v4-flash",
    "temperature": 0.01,          # 关随机
    "max_tokens": 1200,
    "thinking": {"type": "disabled"},  # ⚠️必须显式关！DeepSeek默认thinking开，不关思考链吃满预算content为空
}
```

**评审 prompt 必须带严格锚点**（90+只配极少数顶级内容+档位描述），否则 LLM-as-judge 默认宽容打分虚高（实测：简化prompt给90分，豆包框架给74.6——差15分）。

**已踩坑：**
- ❌ 简化prompt（「按四维打分」无锚点）→ DeepSeek给90，豆包App给76——尺度虚高
- ❌ 不传thinking参数 → 思考链吃满max_tokens，content为空，解析失败
- ❌ 豆包Mini（doubao-seed-2-0-mini-260428看图模型）做评审 → 打分激进，深度不足。看图模型不兼职评审
- ✅ 单Judge（DeepSeek）+黄金样本库漂移监控（每周一cron），不搞双模型交叉验证

## 双门槛

| 评审 | 位置 | 门槛 | 素材 |
|:-----|:-----|:----:|:-----|
| 初稿评审 | 节点4后 | ≥60 | 文案全文（分镜未出时用文案+选题摘要） |
| 成片终审 | 节点15交付前（全分支统一） | ≥68 | 视频=成片/图文=生成图/公众号=文案+封面 |

- 打回重写≤2次，第3次人工介入
- 分数与优化建议分离输出

## 物理卡点（review_gate.py）

```bash
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> node2_verify   # 素材过滤清单存在
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> node3_candidate  # 选题候选方向≥2（内部文件 节点3_候选方向.md，不交付）
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> node4_review   # 三版产出≥3 + 初稿≥60（自备文案：_自备文案.flag 豁免三版检查，评审保留）
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> node12_pre     # 出片前（视频分支）
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> node15_final   # 终审≥68
python3 /home/ubuntu/.hermes/scripts/review_gate.py check <项目目录> all            # 交付总闸
```

⚠️ all 不含 node12_pre（图文/口播/公众号分支不经过节点12，进all误杀——已踩坑）
⚠️ node2_verify 检查过滤清单存在即可，不做新闻级熔断（素材宽松标准）

## 黄金样本库漂移监控

- 库：wiki/concepts/gold-sample-library.md（目标20条，当前2条）
- 基准：DeepSeek同源首评（不能用豆包App分当基准——尺度差12-14分）
- cron：每周一10:00 judge_drift_check.py，平均偏差>10或单条>20触发人工评审

## 验证清单

- [ ] 评审报告含四维分+总分+PASS标记？
- [ ] 文件名：节点4_评审报告.md / 节点15_终审报告.md（不可改，物理卡点依赖）？
- [ ] Judge 用 temp 0.01 + thinking disabled + 严格锚点 prompt？
- [ ] 初稿≥60 进节点5；终审≥68 才交付？
- [ ] 打回≤2次，第3次人工介入？
