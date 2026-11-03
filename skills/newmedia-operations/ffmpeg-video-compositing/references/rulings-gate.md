# 出片必须走口径函数 + 口径断言（禁手写数值）

**触发**：任何 ffmpeg 合成/出片（包括本机直合快路）。

## 铁律
1. **合成脚本一律从 `<项目>/work/records/rulings_config.py` 取值**，禁用命令行手写数字。
   - 贴片尺寸：`R.overlay_card_px(W,H)` → `{'side':'right','h':(768,832),'w':(158,180)}`（竖版）
   - 装入方式：`R.OVERLAY_FIT` = `contain`（**完整装入、不裁切**；用 ffmpeg 的 `force_original_aspect_ratio=decrease`，禁 `increase,crop`）
   - 贴片累计：`R.OVERLAY_APP_TOTAL_MIN_SEC`（≥5s，且 ≤10s）
   - 提现页：`R.withdraw_page_px(W,H)`（竖版 297×135 @ 360,676）
   - 编码：`R.ENCODE`（libx264 medium crf18 / aac 128k / **24fps** / +faststart）
   - LOGO：`R.LOGO_TRIGGER_TEXT='火龙漫剧'`、`R.LOGO_HOLD_SEC=1.5`、`R.LOGO_FADE_SEC=0.4` → **1 次、不常驻**
2. **出片后必须跑口径断言**：`python3 <项目>/work/records/check_rulings.py <成片.mp4> <manifest.json>`；**任一 FAIL 不许交付**。
3. 出片必须同时产出口径清单 manifest（overlay_windows / overlay_fit / overlay_aspect / source_aspect / logo_windows / withdraw），否则断言判 FAIL。

## 为什么
方案早就做成机器可读配置（`rulings_config.py` 有 `overlay_card_px()`、`ENCODE`、`OVERLAY_APP_TOTAL_MIN_SEC` 等），但出片时手写 ffmpeg 命令、没调它 → **方案定了等于没定**。文档靠自觉，卡点不靠自觉。用户原话：「定好的方案又不去遵守，那定了干什么」。

## 自检（禁读代码，只看成片画面）
抽帧确认：贴片内容与口播点名界面一致、贴片只出现在点名句上（**不全片挂**）、框长宽比=素材原比（没被拉长）、字幕/侧边竖排/底部小字在位、LOGO 只在品牌名处出现 1 次。
