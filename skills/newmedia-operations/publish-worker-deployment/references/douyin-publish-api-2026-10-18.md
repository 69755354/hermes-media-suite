# 抖音创作中心发布接口真值（2026-10-18 真号实测）

环境：广州 gz-customer-01，真实账号「天行者」，Chromium 156 + CDP，Playwright 驱动。
测试片：720x1280 / 15s / 974408B，标题「测试视频，请忽略」。发布成功后作品 ID `7697788370725899529`，后台状态「已发布」，发布时间 2026年10月18日 07:50，之后已删除。

## 关键结论

1. 发布唯一接口：`POST https://creator.douyin.com/web/api/media/aweme/create_v2/`
2. **成功回执带 item_id**，返回体（实测原文）：

```json
{"extra":{"logid":"20261018075026091480758536E7C4DC3E","now":1792281026000},"item_id":"7697788370725899529","status_code":0}
```

3. **成功判据**：HTTP 200 + `status_code == 0` + `item_id` 为 19 位 ASCII 数字。三者齐备才算成功。
4. **本人验证前的那次调用返回 HTTP 200 但 body 为空字符串**（实测）。空 body 必须判为「未完成/待验证」，绝不能当成功，也不能当失败去重试。
5. 请求体里可用于绑定本次上传的字段（实测原文片段）：
   - `item.common.creation_id`：每次点击发布生成，如 `7omqj7mc1792280912094`
   - `item.common.video_id`：本次上传资源 ID，如 `v0200fg10000dba0iknog65ute470ht0`
   - `item.common.item_title` / `text`：本次标题
6. 因此「回执绑定资源」有确定实现路径：点击发布前记录本次 `creation_id`（若由前端生成，可在请求发出时抓 `post_data` 提取），响应对应同一个 request 对象；再用 `creation_id` + `video_id` 建立本次提交的唯一键，写入账本。
7. 作品管理页（`/creator-micro/content/manage`）显示「已发布」和精确发布时间，可作事后二次确认，但**不得**作为唯一成功证据。

## 发布链路（实测顺序）

1. `content/upload` 选文件 → 转码 → 落到 `content/post/video?enter_from=publish_page`
2. 填标题（`input[placeholder*="作品标题"]`）→ 点「发布」
3. 首次 `create_v2` 调用返回 200 空 body；页面弹「为确保是本人操作」验证框
4. 点「获取验证码」→ 短信（页面出现 `58s` 倒计时）→ 填 6 位码 → 点验证
5. 验证通过后**再次** `create_v2`，返回 `status_code:0` + `item_id`，页面跳 `content/manage?enter_from=publish`

## 交互坑（实测）

- 验证弹窗的「验证」是 `DIV`（x=720,y=430,w=172,h=36），不是 button；按 role=button 找不到。用坐标点或按文本+可见性定位。
- 「获取验证码」同样是文本节点，点之前要先关掉新手引导浮层，否则点击被吞。
- 发布页标题输入是 `input[placeholder*="作品标题"]`，不是「作品描述」。
- 删除路径：管理页「删除作品」→ 确认弹窗「确定」→ 列表变「没有更多作品」。
