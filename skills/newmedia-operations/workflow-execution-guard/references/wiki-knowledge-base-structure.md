# 知识库结构速查（2026-07-10 优化后）

> 所有知识库文档位于 `/home/ubuntu/wiki/concepts/`
> 主索引：`/home/ubuntu/wiki/index.md`（当前22篇）

## 按工作流节点分类

| 节点 | 引用文档 | 说明 |
|:----|:---------|:-----|
| 节点1 | `consumer-decision-models-knowledge.md` | 消费者决策5阶段+S-O-R+行为经济学 |
| 节点1 | `behavioral-economics-marketing.md` | 8概念速查+存在主义4要素+话术案例 |
| 节点1 | `china-consumer-sociology.md` | 三线以下消费特征+县城青年+中老年 |
| 节点3 | `50-viral-hook-templates.md` | 10类型×5句式=50个即用模板+实体店范例 |
| 节点3 | `golden-3-seconds.md` | 黄金三秒钩子手法（前置/破墙/耳虫） |
| 节点4 | `entity-store-30s-conversion-script-template.md` | 5套完整口播模板+通用替换指南（含合并的4风格） |
| 节点4 | `copywriting-spec.md` | 口播结构含五段式（合并了five-part-structure） |
| 节点4 | `six-oral-styles.md` | 6种口播风格 |
| 节点5 | `character-five-elements-design.md` | 五要素人设+5原型库+场景融合矩阵 |
| 节点8 | `seedance-director-prompt-dual-system.md` | 导演双核体系（Emily2040+MapleShaw） |
| 节点8 | `seedance-prompt-template-library.md` | 10套通用prompt模板 |
| 节点8 | `seedance-2.0-prompt-formula.md` | 九模块公式 |
| 节点8 | `omni-timestamps-9module-stack.md` | Omni对口型时间轴写法（数字人通道用） |
| 节点8 | `seedance-omni-prompt-templates.md` | 8套Omni对口型模板（数字人通道用） |
| 节点9 | `compliance-checklist.md` | 6类违禁词表+5行业红线+替换对照+限流SOP（合并了根层compliance.md） |
| 节点9 | `seven-pitfalls.md` | AI口播7个避坑线 |
| 节点11 | `ffmpeg-synthesis-guide.md` | 命令速查+30秒全流程+平台参数 |
| 节点11 | `bgm-library.md` | SoundHelix免费BGM曲库 |
| 节点12 | `content-verification-protocol.md` | 6项自动检测+回退策略+数据追踪 |
| 节点13 | `douyin-kuaishou-publishing-strategy.md` | 抖音快手算法+标签+商业化 |
| 节点13 | `xiaohongshu-publishing-strategy.md` | CES算法+爆款结构+冷启动SOP |
| 节点13 | `zhihu-wechat-video-publishing-strategy.md` | 知乎/公众号/视频号+私域闭环 |
| 参考 | `liangtong-case-study.md` | 亮瞳完整生产案例 |

## 通道差异速查

| 维度 | huoshan（火山引擎） | shuziren（婵镜数字人） |
|:----|:------------------|:---------------------|
| 节点6生图 | 彩铅三视图（绕真人检测） | 写实半身像（直传） |
| 节点8prompt | 写「从彩绘还原为真人」 | 写「照片级写实，无CG感」 |
| 节点10通道 | 火山ARK Seedance | 婵镜API |
| 参考图格式 | base64 data URI | 公网URL |
| model_code | `doubao-seedance-2-0-mini-260615` | `seedance-2.0-lite-mini` |

## 基础设施端口

| 端口 | 服务 | 验证命令 |
|:---:|:----|:---------|
| 1888 | Helper API | `systemctl status helper-api` 或 `curl -s -X POST http://localhost:1888/` |
| 5678 | n8n（遗留） | `curl -s http://localhost:5678/` |
| 8888 | Hindsight | — |
| 8899 | 图片服务 | `curl -s http://localhost:8899/` |
| 9222 | Chrome CDP | `curl -s http://127.0.0.1:9222/json/version` |
