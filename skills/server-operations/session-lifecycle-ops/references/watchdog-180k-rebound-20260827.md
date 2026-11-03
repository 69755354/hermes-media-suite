# Watchdog 180K 阈值反弹：飞书 bot 频繁失忆（2026-08-27）

## 事件

0827 凌晨改完 watchdog（去掉活跃跳过 + hard-ctx 250K→180K + 新增累计 token 硬判据）后，
当天晚上用户报告新加坡机飞书 bot 和广州机小鹿同时频繁失忆。

## 症状

### 新加坡机
- 一天归档 7 个会话，平均每 2-3 小时失忆一次
- watchdog 日志：
  ```
  [OK] 20260826_232722_093a8672 累计token超硬阈(453,579)
  [顺延] 20260827_005302_037eba23 累计token超硬阈(232,470)
  ```
- sessions 表显示 8/26 一天 7 个会话全部 `end_reason=rollover_archived`
- 归档交接包从 7KB 到 403KB 不等，小的交接包恢复后上下文极少

### 广州机
- 同样频繁归档：`handoff_20260826_235311_bad78170_20260827.json`（96KB）
- gateway 崩过一次（`pruning stale sessions.json entry... left by a crashed gateway`）
- relay 报错：`RuntimeError: invalid argument: scope handle is not at the top of the stack`

## 根因

180K hard-ctx 对飞书 bot 会话太低。飞书 bot 会话特点：
- 客户直接交互，每轮对话都加载完整 SOUL.md + memory + skills（约 30-50K token 起步）
- 一个视频生产任务跨多轮工具调用（读 skill、读 wiki、SSH 到广州跑生成、轮询结果），
  轻松烧到 10-20 万 token
- 180K 阈值 = 飞书 bot 干一两个任务就触线被归档

从「永不归档」(活跃跳过) 矫枉过正到「刚过限就归档」(180K + 无活跃跳过)。

## 教训

1. **改归档逻辑后必须观察 24h**：0827 凌晨改完，当天晚上就反弹。灰度不是走过场。
2. **飞书 bot 会话 ≠ CLI 会话**：CLI 可以激进归档（用户不在场等回复），
   飞书 bot 归档 = 客户感知失忆，阈值要更保守
3. **压缩必须先于归档触发**：压缩 threshold 0.12 (12万) 要远低于归档 hard-ctx，
   确保压缩先扛一轮。如果 hard-ctx=180K 而压缩在 120K 触发，中间只有 60K 缓冲，
   一个任务就穿过去了
4. **去掉活跃跳过是对的，但阈值不能同时降低**：两个变量同时改 = 风险叠加

## 建议修复方向（待用户确认）

| 机器 | 当前 hard-ctx | 建议 | 理由 |
|:--:|:--:|:--:|:--:|
| 新加坡 | 180K | 300K | 运营机长链任务多，飞书 DM 有客户交互 |
| 广州小鹿 | 180K | 400K 或排除强制归档 | 客户 bot 归档=客户感知失忆，最保守 |

同时确保压缩 threshold (12万) 先于归档触发，中间留足缓冲。

## 诊断命令

```bash
# 两机 watchdog 日志
tail -20 ~/.hermes/logs/watchdog.log
ssh -p 2222 ubuntu@127.0.0.1 'tail -20 ~/.hermes/logs/watchdog.log'

# 归档历史（一天归档几次）
ls -lt ~/.hermes/archives/ | head -10
ssh -p 2222 ubuntu@127.0.0.1 'ls -lt ~/.hermes/archives/ | head -10'

# 活跃会话 token
python3 -c "
import sqlite3
db = sqlite3.connect('/home/ubuntu/.hermes/state.db')
for r in db.execute('SELECT id,input_tokens FROM sessions WHERE archived=0 ORDER BY input_tokens DESC LIMIT 5'):
    print(f'{r[0]}: {r[1]:,} tokens')
"
```
