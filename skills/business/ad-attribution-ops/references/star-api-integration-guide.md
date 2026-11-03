# 星广服务商 API 对接指南（0825 实测）

## 1. 网络拓扑

| 域名 | 方向 | 新加坡机 | 广州机 relay |
|:---|:---|:---|:---|
| `dashboard.adwetec.com` (token 中转) | 国内站(百度云 180.76.97.219) | ❌ TCP 超时 | ✅ 可通 |
| `api.oceanengine.com` (数据接口) | 字节跳动 | ✅ 直连 200ms | ✅ |

**结论**：token 获取走广州机 SSH relay，数据查询新加坡机直连。

## 2. Token 获取（adwetec 中转）

```bash
# 通过广州机中转获取 token
ssh -p 2222 ubuntu@127.0.0.1 \
  "curl -s -X POST 'https://dashboard.adwetec.com/newapi/dashboard/xingtu_token' \
  -H 'Content-Type: application/json' -d '{}'"
```

响应结构：
```json
{
    "body": {
        "header": {
            "code": 20000,
            "msg": "请求成功！",
            "reqid": "..."
        },
        "entity": {
            "data": "<TOKEN_STRING>"
        }
    }
}
```

- token 在 `body.entity.data`
- 过期机制未确认（先按无过期处理，后续验证）
- 不走巨量引擎 OAuth 流程，adwetec 是中转代理

## 3. 已知凭证

- **star_id（服务商ID）**: `1858094343342475`
- **token 示例值**: `<REDACTED>`

## 4. API 接口清单（PDF 手册提取）

PDF 原件：`workflow/projects/attribution/星广服务商API使用手册.pdf`

| # | 接口 | 方法 | URL | 用途 |
|:---|:---|:---|:---|:---|
| 1 | 获取任务列表 | GET | `https://api.oceanengine.com/open_api/2/star/mcn/provider_get_participated_task/` | 含全部状态任务 |
| 2 | 获取任务详情 | GET | `https://api.oceanengine.com/open_api/2/star/mcn/provider_get_task_detail/` | 指定任务详情 |
| 3 | 视频维度数据 | GET | `https://api.oceanengine.com/open_api/2/star/mcn/provider_get_task_item_list/` | 最细粒度(视频)，达人/任务可 sum 聚合 |
| 4 | 视频标签查询 | GET | `https://api.oceanengine.com/open_api/2/star/mcn/provider_get_tag_on_task/` | 审核用标签 |
| 5 | 达人列表 | GET | `/open_api/2/star/mcn/provider_get_task_author_list/` | 报名/履约状态 |
| 6 | 审核达人报名 | POST | `/open_api/2/star/mcn/provider_handle_joined_author/` | ❌ 不碰(写接口) |

**只调接口1-3（只读不写）。**

### 接口3说明
- 数据为最细粒度（视频维度）
- 达人粒度：按 `core_user.id` sum 聚合
- 任务粒度：按 `task_id` sum 聚合
- `extra_item_info` 字段可跳转服务商审核页

## 5. OAuth 正规流程（PDF 文档，adwetec 已代理）

1. 注册巨量引擎开放平台
2. 创建应用 → 获取 AppID + Secret
3. 获取授权 URL → 发给星广服务商账户管理者
4. 完成授权 → 回调带 `auth_code`（10分钟有效，一次用）
5. auth_code 换 AccessToken → 查已授权账户 → 拿到星图服务商 id

- Access_Token 有效期 24h
- Refresh_Token 有效期 30d
- 刷新后旧 Refresh_Token 失效

## 6. 枚举值（PDF 提取）

### aweme_item_status（在线状态）
| 值 | 含义 |
|:---|:---|
| 999 | 未发布 |
| 141 | 已发布 |
| 102 | 审核通过 |
| 23 | 审核删除 |
| 22 | 用户删除 |
| 140 | 个人可见 |
| 143 | 朋友可见 |
| 144 | 审核可见 |
| 88 | 相关性审核未通过 |

### ad_status（广告投放状态）
| 值 | 含义 |
|:---|:---|
| 1 | 广告未创建 |
| 2 | 已创建未投放 |
| 3 | 投放中 |

### item_status（视频投放状态）
| 值 | 含义 |
|:---|:---|
| 31 | 平台审核中 |
| 32 | 初审未通过 |
| 33 | 复审未通过 |
| 34 | 确认前自删除 |
| 70 | 服务商确认中 |
| 71 | 服务商已拒绝 |
| 72 | 预热中(已确认待发布) |
| 73 | 服务商超时未确认 |
| 74 | 客户确认中 |
| 75 | 客户已拒绝 |
| 80 | 持续计费中 |
| 81 | 结果公示中 |
| 82 | 计费暂停 |
| 3 | 已完成 |

## 7. PDF 提取踩坑

- 接口1-3的请求参数/应答字段表格是**图片嵌入**的
- pymupdf `get_text()` 对这些页面只返回几行标题（<10字符）
- `find_tables()` 检测到表格但 `extract()` 返回碎片
- `get_images()` 能拿到嵌入图片但分辨率低
- **vision_analyze 对低分辨率表格图片会瞎编字段名**（返回通用 API 模板），不可信
- 可靠路径：让 codex 直接读 PDF、装 tesseract OCR、或找线上 HTML 版

## 8. 对接进度

- [x] token 接口验证通过（广州机中转）
- [x] oceanengine 可达性验证通过（新加坡机直连）
- [x] PDF 全文+表格+图片提取到项目目录
- [ ] codex 实装 `adwetec_client.py`（token 获取+缓存+广州机中转）
- [ ] codex 实装 `api_collector.py._fetch_pages()`（接口1-3数据拉取）
- [ ] codex 更新 `config.yaml`（字段映射）
- [ ] `test_api.py` 实调接口1验证
- [ ] 接口3应答字段明细确认（PDF 图片表格未能提取）
