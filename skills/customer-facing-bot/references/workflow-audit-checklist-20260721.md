# 工作流审计 + 工具升级四步法（2026-07-21）

## 核心问题

给bot写工作流时经常假设工具存在，实际没有。

**常见陷阱（已验证）：**
- `create_video` → ❌ 不存在于Hermes tools/，是婵镜REST API（`POST /open/v1/create_video`）
- 文生图API（标准工具）→ ❌ 不存在标准工具，需调Seedream REST API
- `consumer-psychology.md` → ❌ 文件不存在
- MCP chanjing → ❌ 配置存在但404不可达
- `image` 参数名 → ❌ Seedream垫图参数是 `image_list` 不是 `image`

## 修复四步法

### Step 0: 预审计（写工作流前必做）

```
grep -r "def <tool_name>" /home/ubuntu/.hermes/hermes-agent/tools/   # 工具存在？
ls -la <file_path>                                                     # 文件存在？
curl -s -o /dev/null -w "%{http_code}" <API_endpoint>                  # API可达？
```

### Step 1: 工作流豁免

在「禁止自作主张」下加工具白名单。

### Step 2: 安全规则豁免

给路径零容忍、禁止读文件、禁止调API等安全规则加内部工作流例外。**这是最容易漏的步骤。** 缺任何一条，bot仍然无法执行。

### Step 3: 重写工作流步骤

将「读文档」改为「`read_file` 读」，「搜数据」改为「`web_search` 搜」。不要在步骤中嵌入文件路径。

### Step 4: 权限控制（替代审批门禁）

用 level 分级（basic/normal/unlimited）+ 每日配额自动控制，不再需要每单人工审批。

## 审计清单

### 1. 工具存在性
工作流中每个引用的工具都要确认是否存在。

### 2. 文件存在性
每个 `read_file` 路径都要确认文件存在。

### 3. API可达性
每个API端点都要测试连通性。

### 4. 安全规则交叉检查
工具白名单必须在所有三层安全规则中都有豁免。

### 5. 路径泄露检查
搜索SOUL.md中的 `wiki/` `/home/ubuntu/` `/tmp/` `*.md` 等路径模式，改为泛化工具引用。

### 6. 工作流逻辑一致性
完整走一遍流程图，确认没有卡点或矛盾。

## Seedream API 参考

完整参数（含image_list图生图、negative_prompt、分辨率规则、prompt模板）见：
`references/seedream-api-details-20260721.md`
