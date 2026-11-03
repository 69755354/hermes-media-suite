# 旧版 references 文档误导（2026-08-05 实测翻车：飞书答旧版工作流）

## 症状

用户核对最新工作流（三通道/18节点）后问「飞书怎么还没更新」——小鹿回答的仍是旧版（双通道/17节点）。
此时 huoshan SKILL.md 主文件已是新版（md5 主=customer 一致、18节点三通道全在）、system_prompts 缓存也是新版。

## 根因

**huoshan references/ 里有 6 个旧版历史文档没被更新**（主版和 customer 完全一致 = 历史遗留）：

- `dual-branch-architecture.md` ✅ 2026-08-07 已删除
- `dual-channel-workflow.md` ✅ 2026-08-07 已删除
- `dual-channel-workflow-summary.md` ✅ 2026-08-07 已删除
- `dual-channel-persona-mapping.md` ✅ 2026-08-07 已删除
- `persona-architecture.md` ✅ 2026-08-07 已删除
- `user-16node-workflow-analysis.md`（16节点，更旧）✅ 2026-08-07 已删除

小鹿回答工作流问题时加载了这些旧文档 → 答旧版。

**核心认知：主 SKILL.md 新版 ≠ references 全部新版。** SKILL.md 是入口，references 是内容，两个都可能过时。

## 修复步骤

### 1. 旧版 references 加醒目废弃标注（勿删，历史记录保留）

```markdown
> ⚠️ **已废弃/过时（2026-08-05）：** 本文档描述的是旧版双通道/17节点工作流。**当前工作流以 `SKILL.md` 主文件为准：三通道（探店Seedance/剧情Seedance/口播婵镜）+ 18节点(0-17)闭环。** 执行时禁止引用其中的节点编号/通道划分。
```

用脚本批量加（两侧 × 6 文件 = 12 处）：
```python
for side in ['/home/ubuntu/.hermes/skills', '/home/ubuntu/.hermes/profiles/customer/skills']:
    for f in old_files:
        p = os.path.join(side, 'newmedia-operations/huoshan/references', f)
        c = open(p, encoding='utf-8').read()
        if '已废弃' not in c[:200]:
            open(p, 'w', encoding='utf-8').write(note + c)
```

### 2. 主 SKILL.md 里指向旧文档的引用改指新版

实测案例（2026-08-05）：SKILL.md 曾把过时的 `references/persona-architecture.md` 当「人设体系总览」引用 →
已改指 `references/persona-system-summary.md` + `references/persona-template-standard.md`。
（2026-08-07：persona-architecture.md 已删除，新版文件：persona-system-architecture.md / persona-system-integration.md / persona-system-summary.md / persona-template-standard.md）

### 3. 主 + customer 两侧都改，md5 验证一致

customer 侧 SKILL.md 是 chmod 444 只读：`sudo chmod 644` → 改 → 恢复 `sudo chmod 444`。

### 4. 清 system_prompts 缓存 + 重启 gateway

```python
import sqlite3, shutil
shutil.copy2('/home/ubuntu/.hermes/profiles/customer/state.db',
             '/home/ubuntu/.hermes/profiles/customer/state.db.bak-...')
conn = sqlite3.connect('/home/ubuntu/.hermes/profiles/customer/state.db')
c = conn.cursor()
c.execute("DELETE FROM system_prompts")
c.execute("UPDATE sessions SET system_prompt_hash=NULL, system_prompt=NULL")
conn.commit(); conn.close()
```

重启：systemd-run transient unit（见 soul-md-update-protocol 的 systemd-run 方案）。

## 排查顺序补充

「改了文件但输出还是旧版」——**先 grep skill references 目录里的旧关键词**（如「17节点」「双通道」），
别只盯 SKILL.md 主文件。检查命令：

```bash
# 找 references 里含旧关键词的文件
grep -rln "17节点\|双通道" /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/huoshan/references/
# 对比主 vs customer 版本一致性
md5sum /home/ubuntu/.hermes/skills/newmedia-operations/huoshan/references/*.md \
       /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/huoshan/references/*.md
```

## 完整排查链（改了不生效）

① 全库 grep 旧词（欢迎语 5 位置 / 工作流旧文档 references）→ ② 清 skill 缓存 →
③ 查 system_prompts 表是否缓存旧版 → ④ 清缓存+断关联 → ⑤ 重启 gateway → ⑥ 新会话验证。
