# 人设系统集成说明

> 本次会话（2026-07-19）定稿的全局人设体系，与 huoshan 工作流的集成关系。

## 架构分层

```
SOUL.md（框架层） → 节点调度、流程管控、底线兜底、内外输出隔离
  ↓
wiki/personas/（业务层） → 每个节点的独立 persona 文件
  ↓
wiki/concepts/（知识层） → 知识库文档（理论/数据/案例）
  ↓
huoshan SKILL.md（工程层） → 工具/API/参数/节点步骤
```

三层各司其职，不重叠不冲突：
- SKILL.md 管"做什么"（工具、API、参数、步骤）
- persona 管"用什么身份做"（创作视角、判断标准、输出格式）
- SOUL.md 管"全局规则"（调度、铁律、异常兜底）

## 节点人设映射（与 SOUL.md 对齐）

| 节点 | 人设 | 文件路径 |
|:----|:-----|:---------|
| 节点0 信息采集 | 信息采集师 | wiki/personas/persona-info-collector.md |
| 节点1 用户分析 | 用户分析师 | wiki/personas/persona-user-analyst.md |
| 节点2 爆款拆解 | 内容分析师 | wiki/personas/persona-content-analyst.md |
| 节点3 选题 | 策略编辑 | wiki/personas/persona-strategy-editor.md |
| 节点4 文案 | 创意导演 | wiki/personas/persona-creative-director.md |
| 节点5 分镜 | 分镜师 | wiki/personas/persona-storyboard-artist.md |
| 节点6+ | 待开发 | wiki/personas/ |

## 人设模板标准（7+1字段）

每个 persona 文件包含：
1. 【岗位】— 角色名称
2. 【核心职责】— 任务边界
3. 【核心标尺】— 验收质量标准
4. 【表达风格】— 创意/分析二选一
5. 【工作方法】— 节点独有流程
6. 【输出规范】— 固定输出结构
7. 【禁止行为】— 节点专属红线
8. 【依赖资源】— 知识库文档+工具配置
9. 【资源使用铁律】— 使用约束

## 执行规则

1. 每个节点开工前，先加载对应 persona 文件，按人设规则执行
2. 无单独人设的执行节点（节点7），沿用框架默认规范
3. 节点执行完卸人设，切回纯框架态
