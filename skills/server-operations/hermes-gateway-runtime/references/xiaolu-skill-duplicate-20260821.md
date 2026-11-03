# 小鹿卡住事故完整排查：skill 重名 → Ambiguous → 重写循环（2026-08-21）

## 事故时间线

- 12:03 小鹿开始跑「华合寄卖行」分镜任务（广州机 customer profile）
- 期间用户连发 4 条催促（14:04「跟昨天没区别」/14:05「没用导演思维吧」/14:07「声音情绪动作都没有吧」/14:17「？」）
- 14:05:48 `skill_view('director-thinking')` 报 `Ambiguous skill name: 2 skills match across your local skills dir and external_dirs. Refusing to guess`
- 14:21 任务还在跑（API call #104），全程 2 小时 20 分无回复
- 期间多次 `Tool terminal returned error (420.33s)` = codex 远程调用超时（华合任务派 codex 到新加坡机）

## 诊断序列（实际执行）

1. `ssh -p 2222 ubuntu@127.0.0.1` 确认进程活着（gateway pid 2282982、billing 8080/工厂 8090/AstrBot 6185 全监听）→ 服务 active ≠ 没卡
2. `tail gateway.log`：14:04/14:05/14:07/14:17 有 `Received raw message` + `inbound message`，但之后无 `response ready` → 「只收不发」
3. `grep errors.log`：发现 `Ambiguous skill name 'director-thinking'` → 规则读不到
4. 重名扫描：`find .../customer/skills -name SKILL.md | sed ... | awk -F/ '{print $NF}' | sort | uniq -d` → 3 个重名（director-thinking、character-img2img-workflow、portrait-prompt-engineering）
5. md5 对照：3 组重名 md5 完全相同，时间戳 8/12 01:25-01:27 同一秒批量复制 → 同步脚本无同名检测的产物
6. 新加坡机对照：同 3 个 skill 都只有一份（newmedia-operations/ 下），全量重名扫描无结果 → 问题只在广州机 customer profile

## 根因链

同步脚本（compare_profiles.py 55 行）无同名检测 → 8/12 批量复制同一 skill 落到两个分类目录 →
agent skill_view 遇 Ambiguous 拒绝猜 → 导演思维规则读不到 → 分镜没按导演思维写 →
用户追问 → 卡在重写循环（每次重写又调 codex 超时 420s）→ 2 小时无回复

## 修复动作

1. 停广州机 customer gateway（用户指令「让小鹿先停下来」）
2. 派 codex 排查同类 bug（项目：workflow/projects/xiaolu-bug-sweep/，TASK_TYPE=分析）
   - 范围：重名清理 + 同步脚本加同名检测 + gateway 长任务/回执评估
   - 纪律：只删重复副本、删前备份、不重启 gateway、结论带证据

## 经验沉淀

1. 「只收不发」三类根因：a) 长任务占 turn（tool 序列持续递增）b) 外部依赖超时（tool 停在同一调用反复超时）c) **skill 重名导致规则不可见 + 重写循环**（errors.log 有 Ambiguous + 用户消息是「写得不对」类追问）
2. 架构审计要加「本机内 basename 重名」维度：system_dedup_audit（8/17）按跨机同路径 md5 join 比对，两份在不同路径不会撞一起，恰好漏掉
3. 同步后必跑重名扫描，0 输出才交付
4. codex 容器没有 ~/.ssh → 跨机排查证据由 Hermes 预收集进项目目录，codex 只改新加坡侧，广州机侧 Hermes 执行
