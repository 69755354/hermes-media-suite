# video_team · 片级团队看板

一条片子一条记录，从选题走到复盘。每个阶段有唯一负责人和固定产出物，上游不完成下游开不了工。

## 角色
| 角色 | 谁 | 干什么 |
|---|---|---|
| 团长 | Hermes | 拆目标、派活、盯进度、收口 |
| 文案 | Codex/DS | 选题、标题、口播稿 |
| 分镜 | Codex/DS | 分镜表、四层提示词 |
| 剪辑 | Hermes | 素材生成、合成、字幕音轨 |
| 审核 | Codex(独立) | 合规红线、送客词、事实核对 |
| 发布 | 发布助手 | 抖音发布、回读确认 |
| 数据 | 发布助手 | 作品数据、20 列老板表、星图消耗 |

## 阶段链
TOPIC 选题 → COPY 文案 → STORYBOARD 分镜 → MEDIA 生成 → COMPOSE 合成 →
COMPLIANCE 合规 → PUBLISH 发布 → COLLECT 取数 → REVIEW 复盘

## 命令
```bash
python3 team.py add "片名" --batch B01 --account 漫半拍
python3 team.py list
python3 team.py next
python3 team.py start V001
python3 team.py done V001 --artifact /abs/path --note "说明"
python3 team.py show V001
```

## 硬规则
- 除复盘外，每阶段必须交真实存在的产出物路径，否则 BLOCKED
- 上游阶段未 done，下游一律不能 start
- 每次 done 自动生成 handoffs/<片ID>_<阶段>.md 交接单，下游按单开工
