# Codex skill 软链可靠性加固（2026-08-13 落地）

> 背景：老板质疑「软链靠谱吗」。Claude 与 codex 各自独立提方案，Hermes 评审合并执行（git 源备份 + 期望清单 + 巡检 timer + 相对路径 + 故障演练）。

## 结论

**软链技术本身可靠，当前「33 条绝对软链 + 手动检查」的运维机制不可靠。** 同机/同盘/本地 ext4 上软链读取稳定、无同步延迟、单一事实源防漂移——但删源/漏链/迁移/静默四个真实风险需要机制封住。**保留软链，升级成「清单驱动的软链投影 + 自动巡检/有限自愈 + 源目录版本化快照」。** 不建议 rsync 双份 / bind mount / git submodule（漂移或复杂度问题）。

## 为什么不用其他方案

- **rsync 双份**：回到「两处内容分叉」老问题（正是当初改软链的原因）
- **bind mount**：系统级可靠但重启要重挂，复杂
- **git submodule**：改起来麻烦，收益不配复杂度
- **inotify 监听**：机器没装 inotify-tools，要常驻进程、递归 watch 上限、`.usage.json` 高频写入疯狂触发——收益不配复杂度

## 五个真实风险 → 封法

| 风险 | 封法 |
|:--|:--|
| 源被删 = 全断死链 | Hermes 源 git 版本控制（`/home/ubuntu/.hermes/skills` git init + 首次提交） |
| 漏链（新增 skill 忘建软链） | **反向孤儿检测**：Hermes 有 SKILL.md 但清单没列/没链 → 报警 |
| 漏删（少了一项不知道） | **期望清单** skill_link_manifest.yaml（33 项基线，校验从清单读不是遍历现有） |
| 迁移断链 | **相对路径软链**（`../../.hermes/skills/creative/xxx`）代替绝对路径 |
| 静默失效 | systemd timer 每 6 小时巡检 + 门禁阻塞 + 状态文件 |

## 关键文件

- `/home/ubuntu/workflow/scripts/skill_link_manifest.yaml` — 期望清单（应投影的 skill name）
- `/home/ubuntu/workflow/scripts/verify_codex_skill_links.py` — 升级版校验器（清单校验 + 反向孤儿 + JSON 状态 + 阻塞退出）
- `/home/ubuntu/.hermes/skills` — git 源（提交 cc235e9，`.gitignore` 排除 `.usage.json`/缓存）
- user systemd timer `skill-links-verify` — 每 6 小时跑，active

## 校验器升级点

1. **从清单校验**（不是遍历当前存在的入口）——删除一项能查出「少了一项」
2. **反向孤儿检测**：Hermes 有 SKILL.md 但清单没列 → 非阻塞报警（122 源 / 33 投影 / 89 未投影是正常的）
3. **JSON 状态文件** `outputs/skill_links_health.json`（时间戳+退出码+失败列表）——区分「没报警」和「根本没在跑」（监控系统最常见的失效方式）
4. **阻塞退出**：断链 → `BLOCKED:SKILL_LINK:xxx`

## 报警三层（都不依赖外部通道）

1. **门禁阻塞** — `BLOCKED:SKILL_LINK:xxx`，人被拦住必然看见
2. **状态文件** — timer 跑完写 `skill_links_health.json`，可查「上次成功校验是什么时候」
3. **`OnFailure=`** — timer 失败触发摘要 append 到日志，`journalctl --user -u skill-links-verify` 可追溯

## 软链健康检查（Hermes 侧，agent 可跑）

```bash
# 查死链
for f in /home/ubuntu/.codex/skills/*; do [ -L "$f" ] || continue; [ -e "$f" ] || echo "❌ 死链 $(basename $f)"; done
# 查总/死链数
total=0; dead=0; for f in /home/ubuntu/.codex/skills/*; do [ -L "$f" ] || continue; total=$((total+1)); [ -e "$f" ] || dead=$((dead+1)); done; echo "$total 总 / $dead 死"
# 通过软链读内容（find 默认不跟随软链，用 cat/ls -la 验证）
cat /home/ubuntu/.codex/skills/<name>/SKILL.md | head -3
```

## 故障演练（codex 做过的）

- 断链演练：删一条软链 → 校验器触发 `BLOCKED:SKILL_LINK` → 恢复 → 33/33 健康
- 全量测试 27/27 通过；相对链 33、绝对链 0、断链 0

## 相对路径转换注意事项

- 转换前先备份 `ls -la` 快照（出问题一行恢复）
- 软链格式：`/home/ubuntu/.codex/skills/<name> -> ../../.hermes/skills/<category>/<name>`（.codex/skills 和 .hermes/skills 都在 /home/ubuntu 下，两级上溯）

## 新 skill 上线 checklist（防漏链）

1. `skill_manage create` → Hermes 源出现
2. `ln -s /home/ubuntu/.hermes/skills/<category>/<name> /home/ubuntu/.codex/skills/<name>`（建软链！否则 codex 读不到）
3. AGENTS.md 加 `@<name>` 引用（codex 干活前读 AGENTS.md 触发加载）
4. 更新期望清单 skill_link_manifest.yaml
5. 验证：`ls -la .codex/skills/<name>` 软链 + `cat SKILL.md` 可读 + `grep -c <name> AGENTS.md`

## 生效确认（无需清缓存）

- Hermes 新 skill：下次会话自动识别（mtime 新触发重扫）；当前会话 `/reload-skills` 可刷新
- codex 侧：无进程缓存，下次调用读最新软链
- tool_discovery_cache.json 是 stat_key 机制（mtime+size 匹配才用缓存，新文件自动重扫）
- 软链/清单/timer 都是文件系统级，即时生效
