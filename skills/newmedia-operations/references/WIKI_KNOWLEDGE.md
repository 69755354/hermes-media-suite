# 本地 Wiki 知识库（~/wiki/）

## 位置
```
~/wiki/          → 知识库根目录
~/wiki/SCHEMA.md → 完整规范
~/wiki/index.md  → 页面索引
~/wiki/log.md    → 操作日志
```

## 页面类型
| 目录 | 用途 | 示例 |
|:---|:---|:---|
| `concepts/` | 概念/方法论/案例 | `seedance-director-prompt-dual-system.md` |
| `comparisons/` | 对比分析 | `style-conversion-comparison.md` |
| `raw/articles/` | 原始资料 | `seedance-2.0-prompt-guide.md` |

## 写页面前置检查
1. 读 `SCHEMA.md` → 确认 frontmatter 格式和标签体系
2. 读 `index.md` → 看是否有重复/可追加的已有页面
3. 读 `log.md` → 了解最近变更

## 页面后置操作（必须做）
- 更新 `index.md`（pages计数+添加新条目）
- 更新 `log.md`（追加操作记录）

## 标签体系速查
- 方法论: `script`, `hook`, `structure`, `copywriting`, `conversion`
- 平台: `douyin`, `xiaohongshu`, `weixin`
- 行业: `entity-store`, `local-life`, `eye-care`, `catering`, `beauty`
- 技术: `ai-video`, `seedream`, `seedance`, `tts`
- 工作流: `node-0`, `node-2`, `node-3`, `node-4`, `a1-workflow`
- Meta: `comparison`, `benchmark`, `pitfall`

## 与 memory 的分工
| 存 wiki | 存 memory |
|:---|:---|
| 方法论、公式、模板 | 用户偏好、环境细节 |
| 分析报告、案例研究 | 工具配置、临时状态 |
| 可查阅的长期资料 | "这个用户喜欢简洁回复" |
