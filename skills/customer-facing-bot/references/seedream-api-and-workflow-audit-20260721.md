# Seedream API + 工作流审计（2026-07-21）

## Seedream 文生图 API

**端点：** `POST https://ark.cn-beijing.volces.com/api/v3/images/generations`
**鉴权：** `Authorization: Bearer <ARK_API_KEY>`
**模型：** `doubao-seedream-4-5-251128`（主力可用）
**备选：** `doubao-seedream-5-0-260128`（部分场景优于4.5）

### 参数要求

```json
{
  "model": "doubao-seedream-4-5-251128",
  "prompt": "描述文字",
  "n": 1,
  "size": "1920x1920"
}
```

- **size 必须 ≥ 3,686,400 像素**（如 1920x1920）。1080x1920=2,073,600 不够，会报 `InvalidParameter`
- **返回格式：** `{"data": [{"url": "..."}], "usage": {...}}`
- **URL 有效期：** 24小时（TOS Expires=86400）
- **成本：** 0.22元/张（Seedream 5.0 Lite），0.25元/张（Seedream 4.5）

### curl 示例

```bash
curl -s "https://ark.cn-beijing.volces.com/api/v3/images/generations" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seedream-4-5-251128","prompt":"描述","n":1,"size":"1920x1920"}'
```

## 工作流审计模式

**问题：** 给bot写工作流时经常假设工具存在，实际没有。比如 `create_video` 不是Hermes标准工具，文生图API也不是。

**修复四步法：**

### Step 0: 预审计（新增步骤）

写任何工作流步骤前，先确认：
1. `grep -r "def <tool_name>" /home/ubuntu/.hermes/hermes-agent/tools/` — 工具是否存在？
2. `ls -la <file_path>` — 文件是否存在？
3. `curl -s -o /dev/null -w "%{http_code}" <API_endpoint>` — API是否可达？

**常见陷阱：**
- `create_video` → ❌ 不存在于Hermes tools/，是婵镜REST API
- 文生图API → ❌ 不存在标准工具，需调Seedream REST API
- `consumer-psychology.md` → ❌ 文件不存在
- MCP chanjing → ❌ 配置存在但404不可达

### Step 1: 工作流豁免

在「禁止自作主张」下加工具白名单。

### Step 2: 安全规则豁免

给路径零容忍、禁止读文件、禁止调API等安全规则加内部工作流例外。

### Step 3: 重写工作流步骤

将「读文档」改为「`read_file` 读」，将「搜数据」改为「`web_search` 搜」。

### Step 4: 权限控制（替代审批门禁）

用 level 分级（basic/normal/unlimited）+ 每日配额自动控制。不再需要每单人工审批。

## 婵镜出片 REST API

**端点：** `POST /open/v1/create_video`
**Base URL：** `https://open-api.chanjing.cc`
**MCP：** `https://open-api.chanjing.cc/mcp`（实测404不可达）
**认证：** 需 CJ_APP_ID + CJ_SECRET_KEY

**注意：** create_video 的 REST API 认证方式可能不同于 MCP。使用前需确认 REST API 的认证头格式（推测是 `X-APP-ID` + `X-SECRET-KEY` 或类似，未实测）。
