# 编号/职能修复执行闭环（2026-08-07 huoshan 实战）

> 触发：审计发现「手册与权威脱节」后进入修复执行阶段。本文件记录执行阶段的完整闭环——复查手册（consistency-audit-playbook.md）管「查」，本文件管「修到彻底」。

## 铁律 1：改职能名必须两路扫残留（旧编号 + 旧职能名）

只 grep 旧编号（`节点6_分镜`、`节点11(合规`）不够。改职能名（如「合规终检」→「提示词质检」）后，旧职能名会散布在：
- 流程总述、人设表、职责速查表、两域架构图、平台流程表、三级质控说明
- **guard 等物理卡点的流程图 + 项目文件清单**（本次 guard 流程图 0-16 错位、文件清单缺节点7_素材清单.md、残留节点11_合规检测.md 旧名）
- 参考文档/历史快照（这些是留档，标过时即可，不用改）

验证命令：`grep -rn "旧职能名" ~/.hermes/skills ~/wiki --include="*.md" --include="*.yaml" | grep -v backup_ | grep -v history_archive`

## 铁律 2：判断类修复按 SPEC 权威执行，被挪内容不许丢

- 节点11 按 SPEC 改「提示词质检」（只审转译保真度+格式，不审合规）——合规职责全部归节点4，**行业合规规则表（茶馆/医疗/小红书违禁词）原样从节点11 移入节点4**，资料不丢。
- 补缺失章节（节点7 素材汇总A）内容从 SPEC 节点定义抄：input_deps/pre_checks/post_checks 一一对应，再补一句与上下游的接力铁律。

## 铁律 3：收尾四连（改完必做）

1. **同步 customer**：`chmod 644 customer副本 && cp default→customer && chmod 444`（444 先解锁再锁回）
2. **md5 验证**：default/customer 同名 skill 必须一致
3. **哈希守卫同步**：被 hash-verify.sh 监控的文件定稿后立即同步 `~/.hermes/guard/hashes/<file>.md5`，然后 `bash ~/.hermes/scripts/hash-verify.sh` 必须输出 ALL_OK——漏了 30 分钟内报 HASH_FAIL:MISMATCH 终止任务
4. **计划文档勾选更新**：逐项标 [x] + 日期 + 一句话证据；残留项保持未勾写明原因

## 工具坑：read_file/patch 对超长行 UTF-8 文件误判二进制

文件含超长行（>495 字符，长表格/内嵌 base64/长 URL）时 read_file 和 patch 报 `Binary file - cannot display as text`，但 `file` 命令显示是正常 UTF-8。绕过：
```python
# execute_code 内
content = subprocess.run(["cat", path], capture_output=True, text=True).stdout
# 字符串替换，先 count 命中=1 再写，写完验证残留=0
```
> 不要用 write_file 整文件覆盖（3549 行大文件风险高），用精准字符串替换。

## 本次修复量参考

10 处残留引用一次性清：7 处「合规终检」职能名 + 3 处环境音叠轨误挂节点11（改节点13）+ 3 处旧编号散文引用 + guard 流程图/文件清单。机械类 4 处（编号/模板）先修，判断类 2 项（节点11 职能、节点7 补章节）问用户拍板后修——用户原话「3 按照SPEC节点11来 节点7要补」。
