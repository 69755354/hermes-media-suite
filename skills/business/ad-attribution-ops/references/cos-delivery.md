# 星广文档交付路径（COS 加速 + 短链 + 飞书，0814 实测）

场景：把 Word/md 文档（PRD/归因逻辑/方案）发给老板。交付顺序：**飞书直接发文件 > COS 签名链接（微信）> 核心摘要**。

## 平台能力边界（实测）

- **飞书**：`hermes send -t feishu:<chat_id> "说明文字\n\nMEDIA:<绝对路径>"` 可**直接发 docx 文件**（实测 sent）。Home 频道 `<HOME_CHAT_ID>`。
- **微信**：适配器只支持 image/video/audio——**docx/pdf 永远发不了**（硬限制，MEDIA: 投递直接失败）。图片走 CDN relay（8899，依赖广州机反隧），反隧断则图片也发不出。**微信只能发文本（链接）**。
- 老铁律：交付只发链接禁 MEDIA（用户偏好）、链接后面不加标点。

## COS 上传（新加坡机 → 广州桶，跨境）

- **普通域名**（`<bucket>.cos.ap-guangzhou.myqcloud.com`）：新加坡→广州跨境**超时**，不通。
- **加速域名**（`<bucket>.cos.accelerate.myqcloud.com`）：新加坡能连，但桶必须先在控制台开启**全球加速**：
  - 控制台 → 对象存储 COS → 桶 `sc-1447774428` → 域名与传输管理 → **默认加速域名/全球加速开关**（不是「自定义域名/添加域名」，不用填域名，直接开开关，1-2 分钟生效）。
- **上传命令**：`COS_ACCELERATE=1 python3 ~/.hermes/scripts/cos_manager.py upload <bucket> <local> <key>`（cos_manager.py 已加加速模式：`get_client(bucket)` 用 `Domain=<bucket>.cos.accelerate.myqcloud.com`；普通模式保持原样）。
- 开启加速的请求本身要走 COS endpoint——SDK 无 put_bucket_accelerate_configuration 方法、手动 PUT /?accelerate 也会被服务端认成「未开加速」——**开加速只能用户在控制台操作**，别在代码层死磕。

## 下载链接（私有桶）

- `client.get_presigned_url(Method='GET', Bucket=bucket, Key=key, Expired=7200)` 生成签名 URL（2 小时有效）。
- 用户（国内）用**普通域名**的签名 URL 访问通（境内直连广州）；新加坡机自己 curl 测试会超时（跨境），不要因为本地测不通就以为链接坏了。

## 短链（用户嫌签名 URL 太长时）

- **TinyURL**：`curl "https://tinyurl.com/api-create.php?url=<urlencode 长链接>"` 免费无需注册（实测成功）。
- ⚠️ **TinyURL 国内打不开（0815 实测）**：短链本身有效（curl 返回 301 跳转正常），但 tinyurl.com 在国内被墙，用户反馈「打不开」——生成短链后若用户说打不开，**直接回退 COS 长链接**（用户国内访问普通域名签名 URL 是通的），别再折腾其他海外短链服务。
- **is.gd**：`https://is.gd/create.php?format=simple&url=...` 实测 403 被拒，别用。
- 注意：短链指向签名 URL，签名过期后短链也失效。

## 批量重写后的交付循环

老板反复改口径时（拍板/澄清分批到达）：每次重写文档后要 **pandoc 转 Word → COS_ACCELERATE=1 上传 → 重新生成签名链接**（旧链接指向旧版本）。批量重写能省这轮重复（见 SKILL.md「老板拍板落实 = 一次性重写」）。
