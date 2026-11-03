# GitHub 剪映自动化工具生态调研（2026-08-07）

> 来源：GitHub API search（jianying / capcut 关键词）+ 官方 README 实测读取。未逐一实测，标注为调研结论。

## 结论先行

- **能「生成剪映草稿」的工具一大把，但底层几乎全是 pyJianYingDraft 或其变体**——能力上限相同：写草稿 JSON，不能渲染成片。
- **能「草稿 → 成片 mp4」的只有两条路**：
  1. **JyDraft HDraft**（HTWMedia，87★，Apache-2.0）——云端渲染服务 `htwmedia.dpdns.org`，**收费**（邮箱申请 AuthKey，草稿+素材打 ZIP 上传 → 云端渲染 → 下载），素材要上传它家服务器（隐私/传输考量）；HDraft.exe 有 win-x64 / osx-arm64 / osx-x64 三平台
  2. **剪映本地渲染**（现状：Mac 剪映 GUI 手动导出，10.8 不支持自动导出）
- **替代 ffmpeg 合成没有免费路**——ffmpeg 仍是最佳「拼接/字幕/BGM/环境音」方案；要剪映级特效+全自动出片 = JyDraft HDraft（付费）或阿里云云剪辑（付费+OSS 中转）。

## 工具清单（按用途）

| 工具 | Stars | 用途 | 备注 |
|:---|:---:|:---|:---|
| pyJianYingDraft (GuanYixuan) | 4109 | 草稿生成/导出 | **已用**（jy_wrapper 底层）；有 pyCapCut 国际版 |
| jianying-editor-skill (luoluoluo22) | 2669 | Agent 自动剪辑 | **已装**；自动导出只支持剪映 5.9 及以下；Mac 手动导出 |
| capcut-mate (Hommy-master) | 1525 | 剪映 API + 扣子插件 | FastAPI，可直接接 LLM；待验证导出能力 |
| jianying-mcp (hey-jian-wei) | 272 | MCP 服务器 | **底层=pyJianYingDraft**；export_draft 导出的是剪映项目文件不是 mp4；不能替代 ffmpeg |
| capcut-cli (renezander030) | 271 | CLI 编辑项目 | 唯一可能带本地渲染的候选，未深挖 |
| JianYingApi (JianYing-Automation) | 260 | 第三方 API | 逆向工程，UI 自动化大概率 Windows 限定 |
| JianyingDraft.PY (notinmood) | 201 | 资源文件→草稿 | Python |
| JianYingProDraft (xiaoyiv) | 176 | 快速建草稿 | Python |
| isYangs/jianying-editor-skill | 149 | 自然语言全流程 | 文案/配音/字幕/选曲 |
| JyDraft (HTWMedia) | 87 | 草稿+云端渲染导出 | **唯一「无需剪映客户端渲染成片」**；HDraft 命令行工具免费，渲染服务收费 |
| jianying-srt (hhuayuan) | - | 字幕批量导出/改/回导 | 小工具 |
| auto-jy-win (duoec) | - | Windows 自动导出系统 | GUI 自动化，**Windows 专用**，我们是 Mac 不适用 |
| ArcReel | 3901 | AI Agent 视频工作台 | 小说/剧本→分镜/视频/剪映草稿，多供应商；架构参考价值 |
| OpenCut | 81357 | 开源 CapCut 替代 | Web 编辑器，不能调用剪映，功能对标 |

## 阿里云 IMS 云剪辑（对比参照）

- SubmitMediaProducingJob（Timeline 剪辑合成，异步）、CreateEditingProject、SubmitBatchMediaProducingJob（批量混剪）
- **计费**：按成片时长，720P≈0.03 / 1080P≈0.06 / 2K≈0.12 元每分钟（30s 成片≈0.015-0.03 元，几乎可忽略）；失败不收费
- **素材必须 OSS**（明确不支持外部地址/CDN）——素材中转是主要成本/麻烦
- **特效生态弱**：Timeline 配置有转场/滤镜/字幕能力，但数量有限、要写 JSON，没有剪映的可视化素材库——「剪映级特效」它顶不上
- 价值场景：全自动量产 + 简单编排（batch 混剪）；替代不了剪映的特效，也没必要替代 ffmpeg 合成

## 选择建议（针对我们流水线）

1. 现状双轨：ffmpeg 全自动合成（拼接/字幕/BGM/环境音）+ 剪映草稿（可编辑交付物）——免费、已跑通
2. 要「全自动出片」：JyDraft HDraft 最对口（但付费+素材上传），或阿里云云剪辑（全自动但 OSS 中转）
3. 要「剪映级特效」：只能剪映本地（Mac 手动导出）
4. jianying-mcp / capcut-cli 是 MCP/CLI 接入方式候选，能力上限仍是 pyJianYingDraft（草稿，非渲染）
