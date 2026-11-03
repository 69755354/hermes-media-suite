# 星广/星川 API 字段明细（调研 2026-08-14，来源标注）

> 来源：巨量引擎开放平台官方文档 + 社区 Go SDK（二级证据）+ 巨量星图帮助中心。查不到的明确标注待核验，不编造。

## 1. 星广联投任务视频数据（v3.0/report/stardelivery/task_video_data/get）

- 请求过滤：`star_task_video_range`（默认返回可用于投放的视频）
- 应答字段：
  - `star_task_id`（星广联投任务id）、`material_id`（任务下投稿视频素材id）
  - `star_video_status`：VISIBLE（公开可见/可投）/ UNPUBLISHED（未发布）/ 非公开（已设私/删除）
  - `star_video_delivery_status`（投放状态）、`star_video_ban_reason_detail`（被拒原因详情）、`star_video_cus_approval_time`（客户审批时间）
  - 素材标签（游戏版任务）：低效素材 / 首发素材 / 优质素材（2024-11 更新）
- 数据：视频×日期，item_id、demand_id、达人ID/昵称、播放量、转化数、预估实时消耗、累计结算消耗
- 时效：播放量与结算消耗 T+1 更新（次日 10 点后稳定）；转化和预估消耗实时

## 2. 星广联投数据排序字段（v3.0 报告接口）

- `stat_cost`（营销消耗，实时，默认排序）
- `non_ad_stat_cost`（达人流量消耗及素材费，实时）
- `star_stat_cost`（达人流量消耗，实时）
- `star_convert_cnt`（达人流量转化数，实时）
- `star_material_stat_cost`（基础素材费，实时）
- `star_sale_material_stat_cost`（素材分成费，实时）★ 分成对账关键
- `in_app_stat_cost_range_t1`（预估应用内营销分成）/ `in_app_payment_amount_range_t1`（预估应用内付费金额）
- `star_material_natural_views_t1`（视频自然播放量）/ `star_cpm`（自然CPM）
- 分端：`stat_anaroid_cost` / `stat_ios_cost`、`android_convert_cnt` / `ios_convert_cnt`

## 3. 常规巨量广告素材报表

- 层级：账户 → 项目 project_id → 广告 promotion_id → 素材 material_id（旧后台：广告组-计划-创意，建模时保存原始 ID 和对象类型）
- 素材报表支持按广告主/起止日期/项目/广告/视频素材筛选；时间维度 小时/日/周/月
- 指标：消耗/展示/点击/3秒播放/有效播放/完播/转化 + 计费时间归因转化

## 4. 审核枚举（通用）

- CREATIVE_WORD_STATUS_APPROVE（审核通过）/ REJECT（失败）/ AUDIT（新建审核中）/ REAUDIT（修改审核中）

## 5. 分成/结算规则（巨量星图官方）

- 星广联投高潜任务：收益 = MAX{保底, 投放消耗分成(3%) + 达人自然流量转化(CPA)}；效果分成 T+1，保底 14 天后
- 星川任务（千川星选）：投放消耗分成 4% + 自然带货佣金；T+1 结算，无退货风险
- 星广联投计费周期：任务开始到结束后 T+14 天
- 审核：平台审核（投放+内容合规）+ 服务商审核（创意/转化，3 天内审完）；星图预审 ≠ 投放平台最终通过

## 6. 触点规则（2026-08-14 追加调研，部分解除待核验）

- **星广监测服务（官方帮助中心）**：自然流量支持**点击监测**；营销流量支持**有效触点监测（有效触点=点击+3s播放）**。平台向客户/三方监测下发**有效触点的用户信息**（不是安装/激活等转化数据），三方收触点后自行归因，并把转化回传平台优化模型。
- **字节生态归因（小程序场景，行业资料）**：默认 **Last Click（最后点击归因）模型**，支持 7日/14日归因窗口可配；`click_id` = 广告点击唯一标识（21 天有效）；媒体下发 clickid + ad_id（计划）+ creative_id（素材）+ 用户 IP/UA。
- **点击归因 vs 曝光归因**：CTA=点了广告X天内转化算它；VTA=没点但看到X天内转化也算（比例打折如 30%）。
- **老板「触点=1」最可能语义 = 单触点归因（Last Click 风格）：一次转化/一条消耗只归 1 个素材**，不做多触点分摊。仍建议拿星广后台「触点=1」实际字段/截图核验后写死。

## 7. 视频好坏评判指标（星图官方定义）

- **播放量**：从发布至数据更新日累积播放，最长更新至发布后 **45 天**。
- **完播率**：传播表现模块指标（完整看完 ÷ 播放）；另有 API 字段 `five_s_play_rate`（5秒有效播放率，返回 ×100，如 2750 = 27.5%）。
- **消耗 stat_cost**：平台 oCPM 自动给好素材更多消耗——消耗本身就是平台对素材质量的投票。
- 辅助指标：点赞率/评论率/分享率（互动质量）、CPM/CPE（成本效率）、**流量拆分**（营销流量=客户预算投放 vs 非营销=达人自然流量，可分别看播放/互动/完播）。
- 判断链：消耗高（平台投票）→ 播放高（内容吸引力）→ 完播高（留人）→ top25% = 三者综合靠前。

## 8. 自动发布路径（2026-08-14 追加调研）

- **抖音开放平台视频发布 API**（推荐路径）：分片上传 → `file/upload/video/finish/` 拿 `video_id` → 发布到账号；Access Token 7200s 有效可刷新；需要抖音开放平台开发者应用 + 达人号授权（扫码，一次性）。
- **星川投稿另一条**：抖音发布链路勾选对应任务（半手动，发布+投稿一体）。
- **能否发布时自动关联星川任务 = 待核验**（业务描述标注「应该是抖音发布，不确定」）。

## 9. 待核验项

- 「触点=1」星广后台实际显示：待字段级核验（拿字段名/接口文档/截图后再解释）
- 星广联投视频 API 无法从公开字段确认每条视频的点击/3秒播放/完播（完整漏斗需接常规素材报表）
- ~~API 自动拉取权限/授权：待实际账户核验（不确定）~~ → **0825 已通，见 ## 11**
- 自动发布能否关联星川任务：待核验
- ~~星川转化数据接口~~ → 0825 实测确认服务商 API 自带转化字段（active/register/pay/first_pay/next_day_open），但当前归因不用转化指标，已砍掉

## 11. 实测接入（2026-08-25，真实 API 调通）

> 用户提供星广服务商 API 使用手册 PDF + adwetec 中转平台 token 接口 + star_id。Hermes+codex 完成对接，两个接口实测通过。

### Token 获取（adwetec 中转，非巨量 OAuth 直连）

- **URL**: `POST https://dashboard.adwetec.com/newapi/dashboard/xingtu_token`
- **Header**: `Content-Type: application/json`
- **Body**: `{}`
- **响应**: `body.entity.data` = token 字符串（如 `<REDACTED>`）
- **adwetec 是第三方中转平台**（IP=180.76.97.219，百度云），不是巨量官方 OAuth
- **网络拓扑实测**：
  - `dashboard.adwetec.com` 新加坡机直连不通（TCP timeout）→ **走广州机 SSH relay**（`ssh -p 2222 ubuntu@127.0.0.1`）中转
  - `api.oceanengine.com` 新加坡机直连通（200ms）
  - 结论：token 获取需广州机中转，数据查询接口可从新加坡机直接调
- token 过期机制未确认（adwetec 不提供 refresh_token，先按无过期+23h缓存处理）

### 接口1：获取任务列表（含全部状态任务）

- **URL**: `GET https://api.oceanengine.com/open_api/2/star/mcn/provider_get_participated_task/`
- **Method**: GET
- **Header**: `Access-Token: <token>`
- **请求参数**（从 PDF 提取 + 实测）: `star_id`（服务商ID）, `provider_task_category`, `page`, `page_size`
- **应答结构**:
  ```json
  {"code":0, "message":"OK", "request_id":"...",
   "data":{"data":[{...task objects...}], "page_info":{"has_more":true,"limit":10,"page":1,"total_count":54}}}
  ```
- **任务对象字段**: `demand_id`, `demand_name`, `challenge_status`, `pay_type`, `provider_order_task_status`, `quota_info`（is_activity/max_reward/quota）, `service_provider_profit_rate`, `service_provider_profit_rate_channel`, `create_time`
- **实测**: star_id=1858094343342475 拉到54条任务（含火龙漫剧、泡泡星冰乐、变形金刚等）

### 接口3：获取指定任务达人视频维度相关信息（★ 核心数据接口）

- **URL**: `GET https://api.oceanengine.com/open_api/2/star/mcn/provider_get_task_item_list/`
- **Method**: GET
- **Header**: `Access-Token: <token>`
- **请求参数**: `star_id`, `task_id`（即 demand_id）, `page`, `limit`
- **应答结构**: `data.items[]` 每条含4个子对象：
  - `item_info`: 视频基础信息 + `data` 内含三组指标
    - `data.real_time_effect_data`: **效果数据**（播放/互动）
    - `data.real_time_ad_convert_data`: **广告转化数据**
    - `data.real_time_natural_convert_data`: 自然流量转化数据
  - `star_ad_unite_item_info`: **投放与消耗数据**
  - `item_task_provider_info`: 分成比例
  - `extra_item_info`: 审核链接
- **视频维度字段清单**（实测确认，0825）:

| 字段路径 | 示例值 | 说明 |
|:--|:--|:--|
| `item_info.item_id` | 7673876554438528298 | 视频唯一ID |
| `item_info.title` | 《预见明日的人》 | 视频标题 |
| `item_info.duration` | 146 | 时长（秒） |
| `item_info.aweme_item_status` | 102 | 在线状态：102=审核通过, 141=已发布 |
| `item_info.release_time` | 1786932952 | 发布时间（unix秒） |
| `item_info.create_time` | 1786713626 | 创建时间（unix秒） |
| `item_info.url` | iesdouyin链接 | 视频地址 |
| `item_info.core_user.id` | 7585511369152299034 | 达人ID |
| `item_info.core_user.nick_name` | 萌萌哒推荐 | 达人昵称 |
| `star_ad_unite_item_info.ad_status` | 3 | 广告投放状态：1未创建/2已创建未投放/3投放中 |
| `star_ad_unite_item_info.item_status` | 80 | 视频投放状态：31审核中/32初审未过/80持续计费/3已完成 |
| `star_ad_unite_item_info.est_real_time_ad_cost` | 80 | **实时广告消耗（厘）** |
| `star_ad_unite_item_info.est_real_time_natural_cost` | 0 | 实时自然消耗（厘） |
| `star_ad_unite_item_info.est_real_time_total_cost` | 2920 | **实时总消耗（厘）** |
| `star_ad_unite_item_info.est_provider_reward` | 88 | 预估分成（厘） |
| `star_ad_unite_item_info.provider_settled_reward` | 0 | 已结算分成（厘） |
| `star_ad_unite_item_info.material_id` | null | 素材ID（常为null） |
| `item_task_provider_info.provider_ad_share_ratio` | 300 | 分成比例（300=3%） |
| `data.real_time_effect_data.watch_cnt` | 11 | 播放数 |
| `data.real_time_effect_data.play_rate3s` | 3333 | 3秒播放率（×10000，3333=33.33%） |
| `data.real_time_effect_data.play_rate5s` | 1667 | 5秒播放率（×10000） |
| `data.real_time_effect_data.play_finish_rate` | 0 | 完播率（×10000） |
| `data.real_time_effect_data.finish_rate` | null | 完播率（另一字段，常为null） |
| `data.real_time_effect_data.like_cnt` | 0 | 点赞数 |
| `data.real_time_effect_data.comment_cnt` | 0 | 评论数 |
| `data.real_time_effect_data.share_cnt` | 0 | 分享数 |
| `data.real_time_effect_data.favorite_cnt` | 0 | 收藏数 |
| `data.real_time_effect_data.interact_cnt` | 0 | 互动总数 |
| `data.real_time_effect_data.interact_rate` | 0 | 互动率 |
| `data.real_time_effect_data.avg_watch_dura` | null | 平均观看时长 |
| `data.real_time_ad_convert_data.active_cnt` | 0 | 激活数 |
| `data.real_time_ad_convert_data.register_cnt` | 0 | 注册数 |
| `data.real_time_ad_convert_data.pay_cnt` | 0 | 付费数 |
| `data.real_time_ad_convert_data.first_pay_cnt` | 0 | 首充数 |
| `data.real_time_ad_convert_data.next_day_open_cnt` | 0 | 次日留存 |
| `data.real_time_ad_convert_data.cost_per_active` | 0 | 单次激活成本 |
| `data.real_time_ad_convert_data.cost_per_register` | 0 | 单次注册成本 |
| `data.real_time_ad_convert_data.cost_per_pay` | 0 | 单次付费成本 |

### 金额单位修正（0825 实测定案）

- **之前调研写的「星广 cost = 元×100000」是错误的**（那是 v3 报告接口的口径）
- **服务商 API（provider_get_task_item_list）的消耗单位是厘**（元×1000）
- 验证：est_real_time_total_cost=2920, provider_ad_share_ratio=300(3%) → est_provider_reward=88（2920×0.03=87.6≈88），单位自洽
- **config.yaml 修正**: `unit: "li"`, `accum_scope: "real_time_cumulative"`
- 注意：不同接口的单位可能不同（v3报告接口 vs 服务商API），不能混用

### core_user 分布实测（0825，★ 过滤逻辑关键修正）

- **demand_id 不能当唯一过滤条件**：同一个 demand_id（任务）下混着大量不同达人的视频
- 全量54个任务第一页扫描到 **200+ 个不同 core_user**（达人号），不是只有我们的
- 火龙漫剧8月11日任务（demand_id=7673336625657053222）5条视频全是同一号 `7585511369152299034`（萌萌哒推荐），但其他任务如红果短剧有22个不同达人投稿
- **正确过滤方式**：需要 `core_user.id` 白名单（我们运营的达人号），而非仅靠 demand_id 过滤
- API 字段路径：`item_info.core_user.id` + `item_info.core_user.nick_name`
- **待用户确认**：哪些 core_user.id 是我们自己运营的号（用户尚未提供白名单）
- 过滤逻辑：`demand_id 在我们投稿白名单 AND core_user.id 在我们运营号白名单` 才归因为我们的素材

### 窗口周期扩展（0825 用户定案）

- 用户要求窗口从 D1-D4 扩展到 **D1-D30**
- 含义：每天拉一次快照，连续攒30天，做30天窗口的日维度归因
- 不是一个月拉一次，是**每天拉一次、攒30天**
- 日增量 = 今天累计值 - 昨天累计值
- 代码改动：WINDOW_CODES 从 ("D1","D2","D3","D4") 改为 D1~D30，schema CHECK 约束同步改

### 数据性质：实时累计快照，非按日历史（★ 关键，0825 实测）

- **接口3 返回的是从视频发布到当前时刻的累计值**（累计消耗、累计播放、累计转化），不是某一天的数据
- **不支持按日期拉历史数据**：实测传 `start_date`/`end_date`/`stat_date`/`date_range` 参数，返回结果与不传完全一样（total_count 不变，字段值不变）
- 接口1（任务列表）同样不支持日期过滤，返回所有历史任务
- **做日维度归因的正确方案**：
  1. 每天定时拉一次全量快照，存原始累计值
  2. 计算日增量 = 今天累计值 - 昨天累计值
  3. 用增量值做 D1-D4 窗口归因
- **无法回溯历史日维度数据**——只能从接入日起往前攒
- stat_date 应取当天快照日期（YYYY-MM-DD），release_time（unix timestamp）只用于 publish_instance.published_at
- 注意：同一天多次拉取会得到相同的累计值（或略增），日内多次拉取意义不大；建议每天拉一次

### 其他接口（PDF 文档有，未实测）

- 接口2: `provider_get_task_detail/` — 获取指定任务详情
- 接口4: `provider_get_tag_on_task/` — 任务视频标签查询
- 接口5: `provider_get_task_author_list/` — 获取任务达人列表
- 接口6: `provider_handle_joined_author/` — 服务商审核达人报名（POST，不调）

### 鉴权方式（adwetec 中转 vs 官方 OAuth）

- **adwetec 中转**（当前使用）: POST 空 body 换 token，token 放 `Access-Token` header 调巨量接口。简单但无 refresh_token。
- **官方 OAuth**（PDF 文档描述，未使用）: 注册应用→创建应用拿 AppID/Secret→授权拿 auth_code→换 AccessToken（24h有效）+RefreshToken（30天有效）。标准流程但需要开发者注册。
- 当前用 adwetec 中转，未来如切官方 OAuth 需重写 token 获取逻辑。

## 10. 数据 API 调研（2026-08-15，codex Tavily 全网搜索，来源 URL 见 outputs/巨量星川数据API调研_20260815.md）

> 0815 用 codex Tavily 重新全网调研（0814 的星图版接口是社区/帮助中心口径，这次拿到官方 SDK 源码级事实）。**首选接口变了：v3 自定义报表替代星图 v3.0 报告接口作为主数据源**。

### 巨量引擎开放平台（按素材维度拉数据）

| 接口 | 路径 | 用途 | 凭证 |
|---|---|---|---|
| 自定义报表配置 | `GET /open_api/v3.0/report/custom/config/get/` | 查当前账户可用维度/指标/互斥项（先固化字段字典） | `Access-Token` |
| 自定义报表（**首选主接口**） | `GET /open_api/v3.0/report/custom/get/` | 按选定维度（含 material_id）拉消耗/展示/点击/播放/转化；日/小时维度 | `Access-Token` |
| 创意报表（v2 兼容） | `GET /open_api/2/report/creative/get/` | 创意/素材效果报表，`group_by=STAT_GROUP_BY_MATERIAL_ID`（+`STAT_GROUP_BY_FIELD_STAT_TIME` 要时间序列）；小时/日/周/月 | `Access-Token` |
| OAuth 换/刷 Token | `POST /open_api/oauth2/access_token/`、`/refresh_token/` | 授权码换 access_token；app_id+secret+auth_code | — |

- 常用基础指标：`stat_cost`/`show_cnt`/`click_cnt`/`ctr`/`cpc_platform`/`cpm_platform`；播放：`total_play`/`valid_play`/`play_duration_3s`/`play_25/50/75/99_feed_break`/`play_over_rate`/`average_play_time_per_play`；转化：`convert_cnt`/`conversion_cost`/`conversion_rate`/`deep_convert_cnt`/`deep_convert_cost`/`deep_convert_rate`
- **5秒/互动口径纪律**：v2 明确有 `play_duration_5s_rate`；v3 是否有 5s 次数/比例必须**先读配置接口结果**，不能凭字段名猜；互动若没有统一数，按赞/评/分享/关注分开存，不自行相加冒充官方指标
- **凭证流程**：巨量开放平台注册应用 → 拿 App ID/Secret → 申请数据报表+星图/星川权限 → OAuth 授权拿 auth_code → 换 access_token/refresh_token → 请求头带 `Access-Token`；Secret 只存服务端

### 星广联投（星图版，主数据源）

| 接口 | 路径 | 查询键/粒度 | 返回字段 |
|---|---|---|---|
| 视频维度数据 | `GET /open_api/2/star/star_ad_unite_task_item/list/` | `star_id + demand_id + 起止日期`，按 `item_id + stat_date` | `cost`/`settled_cost`/`show`/`click`/`convert`/`play_cnt`；部分客户有 3s/5s/完播率、互动、赞评转 |
| 任务列表/详情 | `GET /open_api/2/star/star_ad_unite_task/list/`、`/detail/` | `star_id`、任务/日期 | 任务元数据、分端消耗/转化汇总 |

- **金额单位坑**：星广 `cost`/`settled_cost` 单位 = **元 × 100000**（展示需 ÷100000）；`cost/show/click/convert` 实时更新，`play_cnt/settled_cost` T+1
- 3s/5s/完播率、互动及更深转化字段**仅部分客户返回**——字段存在 ≠ 当前账户已获权限，上线前用后台同账户同日期做样本验收

### 星川服务商

| 接口 | 路径 | 返回字段 |
|---|---|---|
| 任务列表 | `GET /open_api/2/star/provider/task/list/` | task_id、状态、总/直播/商品消耗、视频/达人/计划数、预估与结算收益 |
| 视频列表 | `GET /open_api/2/star/provider/task/item/list/` | `item_id`/`material_id`/`ad_cost`（**单位厘**）/分场景消耗展示/`play_cnt`/2s/3s/5s/10s率/`finish_rate`/赞/评 |

- 星川时间参数是**毫秒级时间戳**；2s/3s/5s/10s 与完播字段是**比率不是次数**；`ad_cost` 单位厘
- ⚠️ **星川公开 SDK 响应未见 convert/转化字段**——要按 item_id 拉转化，需向星川平台方索取 API 文档/权限清单/转化接口说明（未查到公开 API 文档：权限、转化口径、更新时间、回补、时区全要书面确认）
- **金额单位纪律**：星川"厘"、星广"元×100000"**禁止直接相加**——建表同时存 raw_value + raw_unit + 统一换算 amount_yuan

### 数据粒度/时区/回补（官方未写死，上线前确认）

- 巨量 v2 支持 HOURLY/DAILY/WEEK/MONTH；v3 可日/小时但组合有限制（以配置接口返回为准）
- **时区/小时切日规则/数据延迟/最终回补 SLA 官方无统一公开承诺**——不得把「北京时间」「T+1 即最终值」写死为平台事实；上线前向巨量技术支持确认 + 后台同账户同日期同归因口径样本验收

### 拉取/建表/对账纪律

- 建表：`dim_material`（source_platform/advertiser_id或star_id/demand_id或task_id/item_id/material_id/creative_id/标题URL/作者/发布时间/状态）+ `fact_material_day`（业务键+stat_date+粒度+消耗/结算消耗/展示/点击/播放/2s/3s/5s/完播/互动拆项/转化/深转化+拉取时间+API版本+原始JSON哈希）
- 唯一键：平台+授权账户+任务/广告主+item/material+统计日期+粒度；素材复用于多广告/项目要保留 ad_id/project_id 防误聚合
- 实时数据**覆盖式 upsert**（多次抓取累计值不相加），保留 pulled_at/请求参数/原始响应；日内按小时抓，T+1 重拉前一日，滚动重拉近 7/30 日吸收迟到转化/结算修正/平台回补
- 每日对账：素材事实表 vs 平台后台同口径；差异区分实时/结算值、币值单位、时区、归因窗口
- **material_id ≠ item_id**：建显式映射表（来源/有效期），映射缺失进隔离表不强行归因
- 首次上线：3 个广告主、连续 7 天双轨校验（行数/金额单位/素材覆盖率/日汇总差异/晚到数据变化量），通过后再启用自动回补与正式归因

### 查国内 API 文档的网络路径

- **新加坡机跨境访问不了巨量开放平台**（developer.oceanengine.com DNS 都解析不了）、web_search 后端（SearXNG）没装、360 搜索没 key——Hermes 直接搜国内 API 资料基本不可行
- **正确姿势：派 codex exec 用 Tavily 搜索**（codex 内置 web 搜索，不受 Hermes 搜索后端影响），prompt 要求「用 Tavily/web 搜索真实资料，标来源 URL，查不到的写『未查到』，禁止编造接口名/字段/文档」——0815 实测能拿到官方 SDK 源码级接口事实
