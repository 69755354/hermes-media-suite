# 工作流审计实用命令集

做三轮审计时，每轮用以下命令验证，不要凭感觉判断。

## 第一轮：架构一致性（读SOUL.md全文）

```bash
# 读完整个SOUL.md
read_file(path="SOUL.md", limit=N)  # N=文件总行数

# 关键词扫描
grep -n "关键词1\|关键词2" SOUL.md

# 检查矛盾：安全规则禁止vs工作流要求
grep -n "ToolA\|ToolB\|API名" SOUL.md
```

## 第二轮：与现有系统兼容

```bash
# 文件存在性
[ -f "/path/to/file" ] && echo "✅" || echo "❌"

# API连通性
curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://api.endpoint" \
  -H "Authorization: Bearer $KEY" \
  -d '{"model":"...","prompt":"test"}' 2>/dev/null

# MCP服务器
curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://mcp.endpoint" 2>/dev/null

# 工具可用性（Hermes标准工具 vs 自定义工具）
ls /home/ubuntu/.hermes/hermes-agent/tools/ | grep -i "toolname"

# 权限配置文件
cat /home/ubuntu/.hermes/profiles/customer/permissions.json
```

## 第三轮：逻辑合理性

```bash
# 检查审批死锁风险
grep -n "等待\|等.*回复\|等.*审批" SOUL.md

# 检查配额/成本控制
grep -n "配额\|成本\|封顶\|¥" SOUL.md

# 检查失败处理
grep -n "失败\|fallback\|备用\|调度请求" SOUL.md

# 检查路径泄露
grep -n "wiki/concepts\|/home/ubuntu\|/tmp/projects" SOUL.md
```

## 小鹿审计专用

| 检查项 | 命令 |
|:-------|:-----|
| 工具白名单冲突 | `grep -c "terminal\|curl\|read_file\|write_file" SOUL.md` |
| 安全规则覆盖 | 逐条对照触发清单（20+条），检查是否有遗漏的攻击面 |
| 工作流豁免范围 | 检查 `terminal+curl` 的使用场景是否被限定 |
| API成本 | Seedream 0.22元/张，婵镜按秒计费¥50封顶 |
