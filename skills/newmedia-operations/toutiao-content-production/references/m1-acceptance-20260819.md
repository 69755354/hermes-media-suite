# 头条产线 M1 验收实测（2026-08-19/20）

三篇素材验收实测记录。项目目录：`/home/ubuntu/workflow/projects/toutiao-shoufa-tools/`。

## 三篇成稿实测数据

| 篇 | 领域 | 素材源 | 字数 | 小标题 | 编造 | AI味 | 原创度 | rc |
|---|---|---|---|---|---|---|---|---|
| 宇树科技上市 | 财经养老 | 新浪财经 cj.sina.com.cn 3329字 | 4727 | **0 个** | 5→0 清零 | 26.16 | 97.8% | 3(配图缺) |
| 朱雀三号火箭回收 | 社会民生 | 人民网 finance.people.com.cn 1686字 | 4477 | **0 个** | 1→0 但回炉后 humanize 重引入 1 处「逼到电子」 | 44.07 | 99.2% | 3(编造+配图) |
| 云南低价团通报 | 消费争议 | 头条转载官方通报 1269字 | 3729 | 0 个（含结构标签 1 个） | **0 处（初稿就干净）** | 36.29 | 99.1% | 3(配图缺) |

## 编造闸验证结论（核心成果）

- 三篇全部拦截/清零：50→0（宇树）、1→0（朱雀）、0（云南）——提示词追加「你实际没有联网能力，取不到就不写」约束后，初稿编造数从 50 降到 0-5 处，效果显著
- 编造闸实现：`modules/fabrication.py` + `rules/fabrication_rules.yaml`（词表）+ `prompts/08_fabrication_rewrite.txt`（回炉卡）+ `tools/test_fabrication.py`（21 项断言零 API）
- 已知漏检（宁漏不误杀）：无后缀品牌名（高盛/英伟达）、纯汉字数字编造抓不到
- 事实边界硬约束追加到 5 个提示词末尾（01_outline_step3/02_feed_write/03_selfcheck/04_humanize_10/05_deai_card），原指令一字未改

## 暴露的四个问题（未解决，待改）

1. **小标题一个都没生成**：提示词要求「全文2-4个一级小标题（一、二、三）」，模型完全没执行，三篇正文无一个「一、」——M1 硬指标 FAIL。发布清单的小标题检查把主标题当小标题数，实际小标题为 0
2. **字数没控住**：目标 1800-2000，实际 3700-4700 超一倍。提示词写了「全文1800-2000字」模型不听——与小标题同属「提示词执行力度」问题，需加强硬约束或加检测重写
3. **配图链三篇全 0 张（系统性）**：豆包返回域名（m.toutiao 占大头、finance.people.com.cn、chinaview.cn、yn.gov.cn、ccwb.yunnan.cn、xywb.jjxw.cn 等）全部未配 site_selectors；6 个已配站（chinanews/news.sina/people(www)/news.cn/xinhuanet/fj.news.cn）与豆包实际返回完全对不上。site_selectors 按 netloc 精确匹配，子域不通用（finance.people.com.cn ≠ www.people.com.cn）。B 源 Commons/Pexels 查询 HTTPError 也失败
4. **编造回炉后 humanize 重引入编造**：朱雀篇编造回炉清零后，拟人化/去味环节又引入 1 处新编造 → 撞满 max_rewrites=1 出 rc=3。回炉机制应在编造清零后跳过 ④⑤ 重写，或回炉后重跑检测

## site_selectors 实测结论（2026-08-19 Claude 交付）

已配 6 站带图率：
- www.xinhuanet.com（新华网主域）：**89% 带图**（9 篇 8 篇带图），与 news.cn 同构复用 span#detailContent；有「栏目标识图」700×420 会过清洗门，靠相关性/图注判据挡
- www.news.cn：38% 带图
- fj.news.cn（福建频道）：38% 带图，**带水印图会漏到视觉终判**（watermark_edge_ratio 0.617-1.618 < 2.0 阈值，地方报供图「新华社/XINHUA NEWS」水印）——已知风险，调阈值会连带影响其它站
- robots 404 → deny 不配：cj.sina.com.cn（豆包最高频！）、news.cctv.com；**同族域 robots 不能顶替**（www.cctv.com 200 也不给 news.cctv.com 背书）
- www.stcn.com：阿里云 DDoS 高防屏蔽本机出口（连接超时），网络通了须重测
- m.toutiao.com：A2 走独立实现（is_toutiao 分支 div.pgc-img data-src），但 UA_COMPLIANT 下头条页 302 到静态壳无图（三篇 len 全 72914、`<img>` 0）——illustrate.py 按域名选 UA（UA_IPHONE if is_toutiao）是 M4 待改，配任何 site_selectors 都命中不到

## 标题 bug 修复（存量 bug，第一跑去味提前退出未暴露）

`modules/titler.py` write_titles 打分选优：`for t, s in ((_score_title(t), t) ...)` 变量遮蔽导致元组顺序反了，chosen 拿到的是分数 float（4.0）而非标题 → pipeline 313 行崩溃。修复：`for s, t in`。另加开场白过滤（模型会输出「好的，已收到您的素材……」混入候选）。第一跑没触发是因为去味环节 rc=3 提前退出，从没走到标题。

## 其他

- `--model flash` 参数透传 bug：llm.py 把 "flash" 原样传 API，要求全名 deepseek-v4-flash → HTTP 400。绕开：不传 override 走 config 默认模型
- 锚点池 27 篇（差 3 到 30），5 处 `_calibrated: false`（dry-run 未开真闭环）
- M3 热榜自动选题已派 Claude 实现（2026-08-19 晚，tools/hotlist.py 桩→完整）
