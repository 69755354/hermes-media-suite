---
name: huolong-fixed-spec-reuse
description: Use when 火龙开新片/壳或LOGO跟昨天不一样/要复用已定规格。
---

# 火龙「定好的规格」唯一实现 · 复用

## 铁律
**壳 / LOGO / 字幕 / 尾卡 / 段时长只有一份实现。** 新项目**只换素材和台词**，禁止另写 `compose*.py`、禁止自创 plan 格式。每开一个新项目就另写一套合成脚本＝壳和 LOGO 接不过来，这是「为什么跟昨天不一样」的唯一根因。

## 复用包（唯一来源）
`/home/ubuntu/workflow/shared/huolong/`
- `render_final.py`（md5 固定，同 `render_final.py.md5`）＝唯一合成实现：`make_phone_pngs()` 出壳，LOGO 按画面宽 15% 缩放
- `plan_模板_横版.json`＝唯一 plan 格式（`script/kind/frame/segments/timing/stance/logo/overlays/bgm/risk_template/tail_sec`）
- `install_to_project.sh`＝一键装（拷脚本＋md5 校验＋铺公共资产）
- `assets/`＝LOGO 与字幕字体；`复用说明.md`＝接入三步与权威值

## 新项目接入
```bash
bash /home/ubuntu/workflow/shared/huolong/install_to_project.sh <项目绝对路径>
# 照模板填 work/records/plan_<片名>.json（必须同 schema），先干跑验计划闸：
python3 work/records/render_final.py --plan work/records/plan_<片名>.json --name <名> --dry-run
```
壳/LOGO 参考实现（同一份文件，勿改写）：`/home/ubuntu/workflow/projects/huolong-free21-30-20261006/work/records/render_final.py`。

## 权威值（出片报告逐项对，任一不符重出、不交付）
- LOGO：宽＝画面宽 15%（横版 192×192）、水平居中（中心＝画面正中）、y=323、淡入淡出 0.2s、只念「火龙漫剧」时上屏、不常驻
- 壳：内屏＋细描边圆角＋灵动岛；内屏等比 contain 不裁不扫窗；贴右侧、右留边 10px
- 字幕：横版 54px 白字黑描边、禁黑底；尾卡：不做，末尾 0.3s 定格，全片无「应用商店」字样
- 段时长 ≥ 字数÷5.0＋1s，超则拆段绝不截断；出片后必跑 ASR 核末句逐字

## 踩坑
- 新项目自写 plan 是另一套 schema（`sents/spoken/shell/logo_box/total`），喂给 `render_final.py` → `BLOCKED: RENDER_ERROR KeyError: 'segments'`。装脚本 ≠ 复用，**plan 格式也必须同一套**。
- 核查 LOGO 用「ffmpeg 抽帧 + 模板匹配 NCC」，别靠肉眼：抽 `-vf fps=2.5,scale=640:-2`，模板取自已知帧后**必须按扫描分辨率一起缩放**（640 宽下模板＝原尺寸×0.5），否则永不命中；NCC>0.6 才算真命中（<0.5 是噪声，>1 是退化窗口）。
- 自写「模板比对」脚本容易把模板裁断 ⇒ 结果作废；先在同源帧上自校验（应得 1.0）再信数字。
- 老批次（9/30 及更早）压根没上 LOGO；10-06 那批实测达标（x≈534 / 宽 212≈192 / 中心 640）。
