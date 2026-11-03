# Seedance 样片交付链路坑（2026-08-22 镜1样片实测，新加坡机）

## 1. 飞书发视频到群 = msg_type=media + file_type=mp4（不是 video）

| 尝试 | 结果 |
|:-----|:-----|
| `msg_type=video` 发群 | ❌ `invalid msg_type: video`（code 230001）——video 类型只支持 DM 私聊 |
| `msg_type=file` + file_type=mp4 | ❌ `type of file upload does not match`（code 230055） |
| `msg_type=file` + file_type=stream | ❌ 仍报 230055（mp4 内容不匹配 stream 类型） |
| ✅ `msg_type=media` + file_type=mp4 | ✅ 成功，群里可直接播放 |

正解流程：
1. `POST /im/v1/files` multipart：`file_type=mp4` + 视频文件 → 拿 `file_key`
2. `POST /im/v1/messages?receive_id_type=chat_id`：`msg_type=media` + `content={"file_key": "..."}` → 群里可播放
3. DM 私聊视频仍走 `feishu_send_video.py`（msg_type=video + open_id）

## 2. 新加坡↔广州传大文件（Seedance 视频 6-10MB）scp/rsync 反复断

- 隧道传大文件不稳：scp 截断（ffprobe 报 `moov atom not found`）、rsync Broken pipe
- ✅ 正解：**分块传**
  1. 广州机：`split -b 400k 视频.mp4 /tmp/parts/part_`（6.3MB ≈ 16 块）
  2. 逐个 scp 小块（400k 稳，可用脚本循环 + 跳过已存在）
  3. 本地：`cat /tmp/parts/part_* > 目标.mp4`
  4. `ffprobe` 验证：时长/大小与源一致才完整
- ⚠️ **scp 端口参数是 `-P`（大写）**；`-p`（小写）是 preserve times——ssh 用 `-p`，scp 用 `-P`。混用报 rc=1 且无错误详情
- ⚠️ **split 块名是 2 字符后缀**：`split -b 400k f.mp4 parts/part_` 生成 `part_aa, part_ab, ..., part_ap`（16 块），不是 `part_a`——循环传块时按 2 字符生成（`chr(97+i//26)+chr(97+i%26)`）
- 下载 TOS URL（视频/图片签名链接）新加坡直连不通 → 先广州 `curl -sL` 下载，再传回

## 3. ARK API 成功响应结构（判定坑）

- 成功响应**没有 code 字段**——别写 `if resp.get("code") != 0` 判失败（会把成功当失败，丢掉 URL/图）
- 图片生成（/images/generations）成功：`data` 是 **list**（`data[0].url` 或 `data[0].b64_image`），不是 dict 带 image_list
- 文件上传（/files）成功：返回**顶层** `id`（如 `file-20260822...`），不是 `data.id`
- 判成功标准：有 `data` list / 有 `id` / 有 `url`；以上都没有才是失败
- 生成后 URL 先落盘兜底（写 /tmp/xxx_urls.txt），下载失败也能找回

## 4. 出片自查后再交付

- 抽 1s + 8s 两帧 vision 自查：人物/风格/场景/运镜（对比原片同时间点帧，见 SKILL.md「样片必须跟原片逐帧对比景别」）/无畸形乱码
- 通过后发群（media 类型）+ @派活人说明
