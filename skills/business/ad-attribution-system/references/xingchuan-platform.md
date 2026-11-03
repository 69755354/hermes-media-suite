# 星川/星广平台细节与调研来源（2026-08 搜索确认）

## 产品关系
- **星川任务** = 巨量星图 × 巨量千川 联合产品（千川后台叫「千川星选」），达人素材投放合作
- **星广联投** = 巨量星图强效果任务模式（客户定预算/出价/视频要求，平台派单达人做素材，oCPM 优化）
- 我们角色：素材供应商 + 自建达人号（达人侧），投稿→审核→发布→按消耗分成

## 分成（官方）
- 星广高潜：`MAX{保底, 投放消耗分成(3%) + 达人自然流量转化(CPA)}`；效果分成 T+1，保底 14 天
- 星川：`投放消耗 × 4% + 自然带货佣金`；T+1 结算，无退货风险
- 电商达人佣金下限 5%（部分类目 1%）

## 审核（官方）
- 星川达人手册：内容审核 6h、相关性 6h、安全 1-3 天、组件相关性 24h-3 天
- 星广：平台审核（合规）+ 服务商审核（3 天内）
- 星图预审通过 ≠ 投放平台最终通过；被拒原因 `star_video_ban_reason_detail`

## 数据字段（巨量开放平台）
- 星广视频数据 API：`v3.0/report/stardelivery/task_video_data/get` → material_id / star_video_status / star_video_delivery_status / 素材标签（低效/首发/优质）
- 星广任务 API 排序字段：stat_cost（营销消耗）、non_ad_stat_cost、star_stat_cost、star_convert_cnt、star_material_stat_cost（基础素材费）、star_sale_material_stat_cost（素材分成费）、in_app_payment_amount_range_t1、star_material_natural_views_t1（自然播放）、star_cpm
- 星图投后报表：`order_overview/get` → five_s_play_rate（rate×100）
- 数据 T+1（次日凌晨产出）；播放量 45 天窗口；历史数据一般不变

## 监测/触点（官方）
- 星广监测：下发**有效触点**用户信息（营销流量=点击+3s播放；自然流量=点击监测），不下发安装/激活
- 转化回传：激活/注册/付费次数/首次付费/7日付费/付费金额等漏斗
- 字节生态默认 Last Click，click_id 21 天有效，窗口 7/14 日

## 发布
- 星川：素材审核通过后**客户账号投放**（默认不在达人主页展示，达人可手动公开）
- 但我们走**自建号发布**路径（用户确认），技术路径=抖音开放平台视频发布 API（上传→finish→video_id→发布）——**待核验能否关联星川任务**

## 调研报告
- `/home/ubuntu/workflow/outputs/归因调研_星广_20260814.md`（codex 产出，461 行，16 个来源）
- 来源：巨量星图帮助中心（xingtu.cn）、巨量引擎开放平台（open.oceanengine.com）、抖音开放平台（open.douyin.com）、社区 Go SDK（bububa/oceanengine）

## 待核验清单（OQ）
- OQ1 自动发布路径（抖音 API 能否关联星川任务）
- OQ2 数据自动拉取（API 权限）
- OQ3 触点=1 语义
- OQ4 分成比例（3% or 4%）
- OQ5 结算周期
- OQ6 行业指标差异
- OQ7 抖音开放平台开发者账号
