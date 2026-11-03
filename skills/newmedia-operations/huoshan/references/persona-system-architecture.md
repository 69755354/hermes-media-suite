# Persona 系统架构（2026-07-19 定稿）

## 三层架构

全局调度（SOUL.md 框架层）
   ↓ 加载 → 卸载
业务人格（wiki/personas/persona-*.md）
   ↓ 引用
知识支撑（wiki/concepts/*.md）

## 节点-人设映射

| 节点 | 人设 | 文件 |
|:----|:----|:-----|
| 0 信息采集 | 信息采集师 | wiki/personas/persona-info-collector.md |
| 1 用户分析 | 用户分析师 | wiki/personas/persona-user-analyst.md |
| 2 爆款拆解 | 内容分析师 | wiki/personas/persona-content-analyst.md |
| 3 选题 | 策略编辑 | wiki/personas/persona-strategy-editor.md |
| 4 文案(含人设) | 创意导演 | wiki/personas/persona-creative-director.md |
| 5 分镜脚本 | 分镜师 | wiki/personas/persona-storyboard-artist.md |
| 6 视觉人设 | 角色设计师 | 待开发 |
| 7 素材汇总 | 框架执行 | 无单独人设 |
| 8 Seedream生图 | AI绘画师 | 待开发 |
| 9 提示词 | 提示词工程师 | 待开发 |
| 10 合规终检 | 审核员 | 待开发 |
| 11 Seedance视频 | 渲染工程师 | 待开发 |
| 12 ffmpeg合成 | 后期剪辑 | 待开发 |
| 13 视频最终检验 | QC质检 | 待开发 |
| 14 交付 | 运营/客服 | 待开发 |
| 15 自动发布 | 发布专员 | 待开发 |
| 16 数据复盘 | 数据分析师 | 待开发 |

## 人设模板（7字段 + 依赖资源）

━━
【岗位】必填
【核心职责】必填，定义任务边界
【核心标尺】必填，验收标准
【表达风格】必填，创意节点自定义/分析节点固定
【工作方法】必填，仅节点独有流程
【输出规范】必填，交付物结构
【禁止行为】必填，本节点专属红线
【依赖资源】必填，知识库文档+工具配置
━━

## 执行规则

来源：全局SOUL.md 1.1/1.2/3.1/3.2

1. 开工前加载 persona + 依赖资源 → 执行 → 写接力文档 → 卸载人设
2. 节点切换走三步：清空→保留框架铁律→加载当前人设
3. 三级质控：第0级静态校验(加载时) → 第1级自检(输出后) → 第2级交叉校验(节点3/4/5/9→节点10合规→节点13QC)
4. 第一性原理铁律：所有输出可溯源至8大底层理论

## 目录结构

wiki/
├── personas/    # 节点人设文件
├── concepts/    # 知识库文档
└── skills/      # 工程规范(SKILL.md)
