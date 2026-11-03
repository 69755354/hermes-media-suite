# 婵镜数字人查询返回status=0排查指南

## 场景

已知数字人ID存在且之前查过是正常状态，但再次查询返回status=0或空数据。

## 排查步骤（按顺序检查）

### 1. Token过期

Token有效期1天。获取新token：

```bash
TOKEN=$(curl -s --max-time 10 "https://open-api.chanjing.cc/open/v1/access_token" \
  -H "Content-Type: application/json" \
  -d '{"app_id": "d01ef4c6", "secret_key": "<CHANJING_SECRET>"}' | \
  python3 -c "import json,sys; print(json.load(sys.stdin).get('data',{}).get('access_token',''))")
```

### 2. APP_ID不对（最常见原因）

**用户有多个婵镜账号，数字人资产不互通。** 用错APP_ID的token查不到数字人。

| 已知账号 | APP_ID | SECRET_KEY | 用途 |
|:--------|:-------|:-----------|:-----|
| 主账号 | `d01ef4c6` | `<CHANJING_SECRET>` | 杨荟视频克隆等核心资产 |
| 副账号 | `d6fda3b0` | 在`.env`中 | 另一组凭证 |

**排查方法：** 分别用两个APP_ID的token查同一个数字人ID，哪个返回status=2说明数字人在哪个账号下。

```bash
# 用账号A查
curl -s "https://open-api.chanjing.cc/open/v1/customised_person?id=C-xxx&source=0" \
  -H "access_token: $TOKEN_A" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'status={d[\"data\"][\"status\"]}')"

# 用账号B查  
curl -s "https://open-api.chanjing.cc/open/v1/customised_person?id=C-xxx&source=0" \
  -H "access_token: $TOKEN_B" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'status={d[\"data\"][\"status\"]}')"
```

### 3. source参数错误

| source值 | 查询范围 |
|:---------|:---------|
| `source=0` | API端创建的数字人（通过`create_customised_person`克隆的） |
| `source=1` | Web端创建的数字人（在chanjing.cc GUI创建的） |

视频克隆提交返回的数字人ID用`source=0`查。`source=1`会返回空。

### 4. 数字人已被删除

查`id`是否在已知已删列表中。删除后查询会返回空。

## 正确查询命令模板

```bash
curl -s "https://open-api.chanjing.cc/open/v1/customised_person?id=C-xxx&source=0" \
  -H "access_token: $TOKEN" | python3 -c "
import json,sys
d = json.load(sys.stdin)
if d.get('code') == 0:
    data = d['data']
    print(f'''状态: {data.get('status','?')}
进度: {data.get('progress','?')}%
数字人ID: {data.get('id','?')}
声纹ID: {data.get('audio_man_id','?')}
预览: {str(data.get('preview_url',''))[:80]}
支持换背景: {data.get('is_support_remove_bg','?')}
名称: {data.get('name','?')}''')
else:
    print(f'API错误: {d.get(\"msg\")}')
"
```
