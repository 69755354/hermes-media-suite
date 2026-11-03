# 热榜源逐源探活 + 自动选题串联（2026-08-30 实测）

> 来源：2026-08-30 Hermes 逐源直连实测（urllib.request + curl）。hotlist.py 代码注释里的 8/19 探活结果已过时，本文件是最新状态。
> 2026-08-30 更新：豆包切 Custom 版 web_search 后，卡点已通。

## 热榜源 2026-08-30 复探（逐源实测）

| 源 | 网络可达 | 数据可取 | robots.txt | 结论 |
|---|---|---|---|---|
| 头条 hot-board | ✅ | ✅ 50条 | ✅ 放行 | **唯一可用** |
| 搜狗 hot_ranks | ✅ | ✅ 30条 | ❌ 404 | 数据活的，卡 robots |
| 新浪 newsapp | ✅ | ✅ 45条 | ❌ 404 | 数据活的，卡 robots |
| 百度 top | ❌ 超时 | — | — | 本机被屏蔽 |
| 微博热搜 | ✅ | ❌ 需登录 | — | m.weibo.cn 返回 Sina Visitor System HTML |
| 知乎热榜 | ✅ | ❌ 401 | — | 需认证 |
| 网易 | ❌ 不可达 | — | — | Network unreachable |
| 腾讯新闻 | ✅ | ❌ 404 | — | API 不可用 |
| 央视网 | ✅ | ❌ JS渲染 | — | 首页是 JS 模板 |

### 数据结构（实测）

**搜狗 hot_ranks**（`https://go.ie.sogou.com/hot_ranks`）：
```json
{"data": [{"type": "hot_ranks", "attributes": {"title": "...", "num": 6221915, "rank": 1, "flag": "热"}}]}
```
30 条/次，flag 有「热」「新」标签。

**新浪 newsapp**（`https://newsapp.sina.cn/api/hotlist`）：
```json
{"data": {"hotList": [{"base": {"base": {"url": "https://so.sina.cn/search/list.d.html?keyword=..."},
  "dynamicName": "标题", "decoration": [{"hotValue": "414万"}]}}]}}
```
45 条/次，hotValue 是中文计数字符串。title 在 `base.dynamicName` 或 `info.title`。

**头条 hot-board**（`https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc`）：
50 条/次，带 Title/QueryWord/HotValue/InterestCategory（数组，13/50 为空）。

### robots 404 处理

config 里 `robots_unavailable_policy: deny` → 查不到 robots 当不允许。搜狗/新浪要启用须改 policy 或等 robots 恢复。hotlist.py 解析器已写好，开关一开即可（`config.yaml` → `hotlist.sources.sogou_hot_ranks/sina_newsapp: true`）。

**⚠️ 不能拿同族域 robots 顶替**：`ie.sogou.com/robots.txt` 返回 200 但内容是 HTML 首页（软 404 假放行）；`go.ie.sogou.com/robots.txt` 返回 404。数据实际所在的域查 robots，不拿同族域的假放行顶替。新浪同理。

## Python import 路径冲突（2026-08-30 实测修复）

**问题**：hotlist.py 第85行 `from tools import anchor` 导入失败——`ImportError: cannot import name 'anchor' from 'tools' (/home/ubuntu/.hermes/hermes-agent/tools/__init__.py)`。

**根因**：PYTHONPATH 里有 `hermes-agent` 目录，Python 先找到 hermes-agent 的 `tools/__init__.py` 包，而不是项目的 `tools/` 目录（项目 tools/ 下没有 `__init__.py`，不是正式包）。

**修复**：在项目 `tools/` 目录下创建空 `__init__.py`：
```bash
touch /home/ubuntu/workflow/projects/toutiao-shoufa-tools/tools/__init__.py
```
创建后 Python 优先匹配项目根的 tools 包（因为 PROJECT_ROOT 在 sys.path[0]）。

**通用启示**：任何项目里 `from tools import X` 失败、报错路径指向 `~/.hermes/hermes-agent/tools/`，都是这个原因——项目 tools/ 缺 `__init__.py`，被 hermes-agent 的同名包遮蔽。

## daily_auto.sh 串联脚本（hotlist → pipeline 一条龙）

脚本位置：`/home/ubuntu/workflow/projects/toutiao-shoufa-tools/daily_auto.sh`

### 功能
1. 跑 `tools/hotlist.py --json` 自动选题 → 产出 `inputs/material_YYYYMMDD_xxx.json`
2. 从 JSON 输出提取 material 路径
3. 跑 `pipeline.py <material.json> --model glm` 出稿
4. 提取 `OUTPUT:` 行的文章路径

### 用法
```bash
bash daily_auto.sh glm    # GLM 免费通道（默认）
bash daily_auto.sh pro    # DS 付费通道
```

### bash 参数坑（实测）
- `MODEL="${1:---model glm}"` 只接 `$1`（`--model`），`glm` 掉了 → 正确写法：`MODEL_NAME="${1:-glm}"` + `MODEL_FLAG="--model ${MODEL_NAME}"`
- `HOTLIST_OUTPUT=$(python3 ... 2>>log)` 吞了 stderr → 用 `2>&1 | tee -a log` 让错误可见
- `set -euo pipefail` + `$(cmd)` 组合：`PIPESTATUS[0]` 才是真正退出码，`$?` 是 tee 的

### 串联前提条件
1. 豆包搜索 Custom 版可用（已切到 web_search endpoint，余额通用）
2. `tools/__init__.py` 存在（否则 import 报错）
3. `PYTHONPATH` 含项目根目录
4. cron 未接——需手动跑或加 crontab

### cron 接法（豆包已通，待接）
```cron
# 每天 8:00 自动选题+出稿（GLM 免费通道）
0 8 * * * cd /home/ubuntu/workflow/projects/toutiao-shoufa-tools && bash daily_auto.sh glm >> logs/cron_daily.log 2>&1
```

## 卡点链路图（2026-08-30 最新状态）

```
头条 hot-board (50条) ──→ hotlist.py 选题打分 (35条eligible) ──→ 豆包 web_search 搜报道
                                                                    │
                                                              ✅ 返回8条结果(带Summary)
                                                                    │
                                                              用Summary组装material.json
                                                                    │
                                                              ✅ 产出material.json
                                                                    │
                                                              ✅ pipeline 出稿
```

**已解决的卡点**：
- ~~豆包免费额度耗尽（10406）~~→ 切到 Custom 版 web_search，余额通用
- ~~搜索返回URL全被skip（域名不在site_selectors里）~~→ 不再抓全文，直接用 Summary 组装 material
- ~~hotlist.py硬约束「不用Snippet拼凑」~~→ 已删除，Custom 版 Summary 是真实报道摘要

**待办**：
- cron 定时调度未接
- daily_auto.sh 实跑验证（搜索已通，全链路待验证）
