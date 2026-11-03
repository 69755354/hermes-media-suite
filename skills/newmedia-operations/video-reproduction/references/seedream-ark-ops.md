# Seedream/ARK 生图执行经验（2026-08-22 火龙高颜值版三视图实测）

> 复刻类任务生图执行时参考。提示词体系见 seedream-image-generation skill（用户自有，只读）。

## ARK 响应结构判断（踩三次坑）

**ARK 成功响应没有 `code` 字段**——直接是业务数据。用 `if resp.get("code") != 0` 判断会把**成功当失败**（code=None ≠ 0），图已生成但被当错误跳过 = 白烧钱重跑。

- `images/generations` 成功响应：`{"model": ..., "created": ..., "data": [{"url": "https://...tos...jpeg?签名", "size": "..."}], "usage": {...}}`——**data 是 list**（不是 dict 带 image_list）
- `files` 上传成功响应：`{"object": "file", "id": "file-xxx", ...}`——**id 在顶层**（不是 data.id）
- 正确判断：
  ```python
  d = resp.get("data")
  items = d if isinstance(d, list) else (d or {}).get("image_list") or []
  item = items[0] if isinstance(items[0], dict) else {"url": str(items[0])}
  # files 上传：
  fid = resp.get("id") or resp.get("data", {}).get("id") or ""
  ```
- **生成后立即把 URL 存文件兜底**（如 `/tmp/xxx_urls.txt`，追加 `名称\tURL`）——万一下载失败/超时，URL 还能找回，不用重新付费生成

## 新加坡机下载生成图必须走广州（2026-08-22 实测）

ARK 返回的图片 URL 在 `ark-acg-cn-beijing.tos-cn-beijing.volces.com`（国内 TOS），**新加坡机直连下载超时**（跟 ARK API 一样被墙）。方法：

1. 生成后只存 URL，不尝试本地下载（本地下载会卡到超时）
2. 广州机下载：
   ```bash
   ssh -p 2222 -o StrictHostKeyChecking=no -o BatchMode=yes ubuntu@127.0.0.1 "cd /tmp && curl -sL -o 图名.jpeg '<URL>'"
   ```
3. 传回新加坡（**scp 多文件时每个远程路径都要带 `host:` 前缀**，只写一个 host 后跟多个路径会把后几个当本地文件）：
   ```bash
   scp -P 2222 ubuntu@127.0.0.1:/tmp/图1.jpeg ubuntu@127.0.0.1:/tmp/图2.jpeg .
   ```

## 调用链（新加坡机）

- ARK API 走 relay：`http://127.0.0.1:8899/upload?url=<urlencode(ARK_BASE + path)>`，带 `Authorization: Bearer <KEY>` + `Content-Type`
- 图生图：先 `POST /files`（multipart: purpose=user_data + file）拿 file_id → `POST /images/generations` 带 `image_list: [file_id]`
- 模型 `doubao-seedream-5-0-260128`；尺寸 `1440x2560`（9:16）/ `2560x1440`（16:9），必须 ≥368 万像素
- 正负向必须成套传（JSON payload）

## 3D 三视图生成要点（本次实测有效）

- 图生图垫 3D 人设图（`男主_v2.jpeg` 等）锁脸 → 三视图版式 prompt（左侧 1/3 面部特写 + 右侧 2/3 正面/侧面/背面全身，16:9，纯白/浅灰背景，无道具）
- 版式描述写「三张全身像从头顶到脚底完整入镜，人物等高、脚底对齐、间距规整；四个视角同一人，五官/发型/服装/鞋履完全一致，仅观察角度不同」
- 负向必须含「无换人、无视角间材质差异、无裁脚、无伪侧面、无多手多指、无文字边框」
- 生成后 vision 自查：版式齐不齐（4 视角）、同一人、3D 风格（非写实照片非卡通）、无文字水印
