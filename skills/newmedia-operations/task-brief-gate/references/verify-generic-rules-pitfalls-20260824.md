# verify_generic 规则文件语义坑（2026-08-24 火龙 V2 校验实测）

`verify_generic.py`（task-brief-gate 的 scripts/）规则文件三坑，写校验规则前先读：

1. **keyword_required vs keyword_forbidden 选反**
   「诚实标注」类检查（要求产物**出现**「未确认/待实测」标注）必须用 `keyword_required`。
   火龙 V2 曾把 R11「景别不禁死机制」写成 `keyword_forbidden + keywords: ["未确认","待实测"]`
   ——结果变成「禁止出现未确认标注」，与意图相反。写每条规则先问：
   这个检查是「要求出现 X」还是「禁止出现 X」？前者 required，后者 forbidden。

2. **YAML 值以 @ 开头报语法错**
   `name: @图3直出` 报 `found character '@' that cannot start any token`。
   修复：@ 开头的值加引号（`name: "图3直出"`，keywords 里 `"@图3"`），或 name 不用 @ 开头。

3. **正则 pattern 误伤时段数字**
   `regex_forbidden patterns: ["10\\.0[1-9]"]` 本意是「口播时长不得超 10s」，
   但命中分段表「0.000-10.050」时段里的 10.05 → 误报 BLOCK。
   先确认检查对象：口播时长字段 vs 生成时段字段；时段数字含 x.05 是正常的。

## 验证方法

规则文件写完后先用真实产物跑一遍本地：
```bash
python3 <项目>/staging/verify_tools/verify_generic.py <产物> <规则文件>
```
看 BLOCK 项是「真问题」还是「规则误报」——误报改规则文件，不派执行器重跑。
