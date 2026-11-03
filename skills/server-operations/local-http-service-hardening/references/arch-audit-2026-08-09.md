# 全系统架构审计 P0/P1/P2 路线图（2026-08-09 codex 审计）

审计范围：Hermes Agent 本身、微信通道（iLink+广州relay）、18节点工作流、模型分工、服务器资源。

## 系统基线（审计时实测）

- 新加坡机 <SG_HOST>：2核/1.9GB内存/40G盘34%，Hermes v0.20.0
- Hermes gateway Python RSS ~321MiB，历史峰值 1.2GiB → 已进 2GiB 危险区
- codex 单任务相关进程 ~370MiB → 两个并发重任务即 swap/OOM
- 系统已在用 swap（1.9GiB swap，用 ~104MiB）
- 微信：ClawBot → iLink → 新加坡 Hermes；图片上传走广州 relay（SSH反向隧道8899）
- 模型分工：文案/分析=codex exec(gpt-5.6-sol)，生图首选=codex gpt-image-2(quality=high, 自动降级Seedream)，视频=Seedance(经广州relay)，搜索=豆包，主对话=DeepSeek v4-flash
- 工作流：18节点串行，总耗时 28-56分钟/条，优化目标 8-15分钟
- helper_api.py 1888（Seedream/Seedance/TTS/合成/合规）、execute_api.py 1889（视频工作流）

## 关键发现（7 类问题）

1. **内存危险**：1.9GB 两个 codex 重任务并发即 OOM；已在用 swap
2. **高危漏洞**：1889 无鉴权（可制造 ARK 账单/提交任意文件路径）；1888 root 运行+密钥写死源码+task_id 路径逃逸；relay 是开放代理（SSRF）；SSH 开 root+密码登录；UFW 未启用
3. **微信通道脆弱**：8899 隧道是媒体+ARK 共同单点，无自动恢复；token 过期（-14）只休眠600s重试不重新扫码；无 media outbox（隧道断时媒体直接丢）
4. **工作流漂移**：三套实现互相矛盾（WORKFLOW_SPEC.yaml 18节点 / execute_api.py 节点5-13 / helper_api.py 另一套 pipeline），节点编号/模型/门禁全不一致；1889 绕过确认门/数据门/初审/终审
5. **配置不合理**：busy_input_mode:interrupt（新消息中断付费长任务）；max_turns:60/max_tool_calls:50 预算过大；background_process_notifications/long_running_notifications 全关（28-56分钟任务无进度回执）；模型两套真相（顶层 v4-flash，provider 内 v4-pro）
6. **本地补丁未进 git**：weixin.py relay 补丁未提交，pre_update_backup=false → 升级会覆盖
7. **依赖故障**：nemo_relay 缺失每次启动报错；ARK 辅助视觉 401 单次失败等 ~242s；辅助 provider 熔断后压缩/摘要/记忆刷新停止

## 机器耗时瓶颈排序

1. Seedance 六镜串行 12-24 分钟（最大头）
2. 高质量生图单张 2-4 分钟（多张串行累加）
3. codex 多次冷启动（AGENTS/技能/wiki/MCP 重复加载）
4. 节点5/10/11 连续 LLM 调用及重复质检
5. ffmpeg 编码与媒体下载
6. relay 网络延迟（高可用风险，非主要耗时）

## DAG 优化方案（18节点 → 并行）

```
0 信息采集
├── 1 用户分析 ──┐
└── 2 爆款拆解 ──┴→ 3选题 → 4文案/初审 → 确认
                                      ├→ 5分镜 ─┐
                                      └→ 6人设 ─┴→ 8生图 ─────┐
                                                   10提示词/质检 ┤
                                                   TTS/BGM/字幕 ┤
                                                                ↓
                                                   12 六镜并发生成（2并发压测→3）
                                                                ↓
                                                       13 合成（等全部镜头）
                                                    ┌───────────┴───────────┐
                                                 14技术质检            15终审/打法包
                                                    └───────────┬───────────┘
                                                              交付
```
- 节点7/9 素材汇总取消独立阻塞，改 Artifact Registry 状态更新
- 节点11 结构检查本地代码化，语义保真一次批量 judge
- 节点16发布/17复盘移出单条关键路径（16 实际手动，17 发布7天后触发）

## 耗时预算

| 阶段 | 当前 | 第一轮优化 | 完整改造 |
|---|---|---|---|
| 节点1-4 | 9-22分 | 5-10分 | 3-7分 |
| 节点5-11 | 6-13分 | 3-6分 | 1-4分 |
| 生图 | 2-4分 | 0.7-4分 | 缓存命中0分 |
| Seedance 6镜 | 12-24分 | 6-12分(并发2) | 4-8分(并发3) |
| 合成/QC/交付 | 1-3分 | 0.5-2分 | 0.5-1分 |
| **总机器耗时** | **28-56分** | **13-22分** | **8-15分** |

8-15分钟 SLA 前提：已有风格模板 + 客户预授权跳过中间确认 + 无镜头重生成 + Seedance 三并发未限流 + ffmpeg 单任务。

## 模型分工调整建议

- DeepSeek Flash：主对话/意图识别/任务路由/进度摘要（不承担18节点持续编排）
- GPT-5.6 Sol high：仅节点1-4高影响策略/复杂分析/困难改稿
- 低风险结构化任务：Flash 或 Terra/Luna 离线评测达标后切换
- Judge 与创作模型分离（避免自评偏差）
- 生图：先标准质量风格样图确认 → 再并发 high 终稿
- Fallback 只按错误类型切换，降级写入交付元数据（禁静默降级）
- codex exec resume / app-server 复用 session 消冷启动

## 资源结论

- 最低生产规格：4GiB 内存/2核（ffmpeg 单并发、媒体生成外部）
- 推荐架构：新加坡只做控制面（4GiB/2核），广州/独立 worker 做 relay/下载/ffmpeg/媒体缓存
- swap 保留 2-4GiB，swappiness 调低；gateway/codex/ffmpeg 分别 cgroup 限制
- 磁盘 70% 告警/85% 停止接新任务；临时素材 72h 清理

## 执行进度（2026-08-09）

**已完成 ✅**：
- P0-1 密钥轮换+删源码硬编码+文件0600
- P0-2 1888/1889/18888 绑127.0.0.1+UFW启用+鉴权验证
- P0-3 三服务 systemd 化+非root+内存限制
- P0-4 task_id路径校验+请求体20MB限制+正确状态码+ThreadingHTTPServer
- P0-6 sshd 加固配置写好（sshd -t 通过）但**未重启**（需先确认广州机隧道用户/保留已验证通道）

**待办**：
- P0-5 广州 autossh/systemd 隧道守护 + 新加坡 watchdog（需广州配合）
- P0-7 codex 并发锁1 + ffmpeg 锁1
- P0-8 关 nemo_relay + 修 ARK 视觉 401 缩短超时
- P1：持久化 Job API / 单一 DAG 编排器 / Seedance 并发 / 节点并行 / codex session 复用 / 生图预览确认 / media outbox / p50 埋点
- P2：relay allowlist+HMAC 双实例 / weixin relay 补丁提交 git 固定 commit / 新加坡升 4GB
