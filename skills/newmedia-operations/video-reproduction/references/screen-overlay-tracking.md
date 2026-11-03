# 手机屏贴图自动跟踪方案（2026-08-18 火龙漫剧复刻实测）

## 目标

输入 Seedance 生成的竖屏视频（手机屏黑屏占位）+ UI 贴图，自动输出「贴图跟随手机屏移动 + 屏幕质感」的成片。适合 Hermes 工作流调用（ffmpeg 无原生贴纸跟踪，必须 OpenCV）。

## 关键实测结论（踩过的坑）

1. **ffmpeg 无贴纸跟踪滤镜**：6.1.1 只有 `mestimate`（算运动矢量给插帧用）、`minterpolate`（帧率转换），都不是目标跟踪。必须 OpenCV LK 光流 + 定期重检测。
2. **Canny 边缘检测在 Seedance 画面上全程失效**：手机屏圆角 + 反光 + 手指遮挡 → `approxPolyDP` 拟合不出 4 边形（实测 254 个轮廓中合格四边形 = 0）。**换黑屏二值化**：`threshold(gray, 35, 255, THRESH_BINARY_INV)` → 高斯模糊 → findContours → 四边形 + 面积 1200~0.35*wh + **竖长形过滤（高≥宽*1.2，排除桌面/阴影方形暗块）**。
3. **第一帧（0s）手机屏又小又低位，检测失败是常态**：不能从第一帧初始化。**锚点帧策略**：扫描 5-9s（手机举起后）找「区域暗块面积最大」的帧，用黑屏二值化在该帧检测四点（实测 7.5s 帧检测正确，绿框正对手机屏）。
4. **从锚点帧双向跟踪**：锚点 → 结尾（顺向）+ 锚点 → 开头（逆向）。只向前会追不到开头。
5. **手机举起过渡段（约 0-3.5s）直接不贴**：这段手机从低位举起、屏位置剧变，光流易丢且原片 3s 前手机屏本来就是暗的（不显示界面）。CSV 前 72-84 帧标 -1。
6. **丢帧处理用前后有效帧线性插值**，不用 last_valid 硬撑（last_valid 会错位）。

## 核心实现（Python + opencv-python + ultralytics 可选）

```python
# 环境：python3 -m venv /home/ubuntu/workflow/.venv_track
# /home/ubuntu/workflow/.venv_track/bin/pip install ultralytics opencv-python numpy

def detect_phone_screen_corners(frame):
    """黑屏二值化检测手机屏四点，返回 [TL,TR,BR,BL] float32 或 None"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 35, 255, cv2.THRESH_BINARY_INV)
    blur = cv2.GaussianBlur(binary, (5, 5), 0)
    contours, _ = cv2.findContours(blur, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    h, w = frame.shape[:2]
    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.022 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            if 1200 < area < 0.35 * w * h:
                pts = approx.reshape(4, 2)
                ww = pts[:, 0].max() - pts[:, 0].min()
                hh = pts[:, 1].max() - pts[:, 1].min()
                if hh >= ww * 1.2:  # 竖长形手机屏
                    rects.append(pts.astype(np.float32))
    if not rects:
        return None
    rects.sort(key=cv2.contourArea, reverse=True)
    pts = rects[0]
    s = pts.sum(axis=1); diff = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]; br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]; bl = pts[np.argmax(diff)]
    return np.array([tl, tr, br, bl], dtype=np.float32)
```

- 锚点扫描：`region = gray[300:800, 400:720]`（手机举起区域），`binary=(region<100)`，`connectedComponentsWithStats` 找最大暗块面积，取最大帧。
- 光流：`cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts_src, None, winSize=(19,19), maxLevel=4, criteria=(EPS|COUNT, 20, 0.01))`——**maxLevel=4**（举手机大位移需要，3 会跟丢）。
- 位移突变判丢：角点位移 > MAX_DELTA（110px 对 1280 宽）判 lost。
- 定期重初始化：每 90 帧（3s@30fps）重新 `detect_phone_screen_corners` 刷新锚点，抑制黑屏无纹理漂移。
- 连续性熔断：连续丢帧 ≥5 或累计重初始化失败 ≥5 → segment_bad=True，上层重生成分片。

## 屏幕质感（贴图不穿帮的关键）

原片手机屏内容特点（vision 实测原片）：**圆角匹配屏幕 + 玻璃反光 + 顶部刘海/灵动岛留白**。直边矩形贴图 = 一眼假。贴图前处理：

1. **圆角 mask**：`make_screen_mask(w, h)` 生成圆角矩形（radius ≈ 8% 宽）+ 顶部刘海黑条（约 5% 高）+ 2px 高斯羽化。
2. **玻璃反光**：顶部 20% 高度渐亮（`glass[yy,:] *= 1.0 + 0.06*(1-yy/(h*0.2))`）或预生成 `glass_reflect.png`（顶部 220 行白→透明渐变，alpha 70→0）。
3. 合成：`warpPerspective(ui, H)` → 与 mask 逐像素相乘 → `blend_alpha(out, logo_warp, 0.92)` → `blend_alpha(out, ref_warp, 0.12)`。
4. 透视变换：`findHomography(src_ui, corners, RANSAC, 5.0)` 让贴图随手机角度变形（原片手机手持有透视，贴图是平面会违和）。

## 验证方法

- 合成后逐帧验证「贴图跟手机屏同步」：像素检测手机屏暗块中心 vs 贴图高饱和区域中心（限制在屏附近 200px），偏差应 <5px。偏差大 = 跟踪失败/丢帧插值错位。
- 输出视频无音轨（cv2.VideoWriter mp4v 只写视频）→ `ffmpeg -i out_noaudio.mp4 -i src.mp4 -c:v copy -c:a copy -map 0:v:0 -map 1:a:0? final.mp4` 补原音轨。
- 2核4G 跑 YOLO CPU 推理单帧约 100-200ms，单段建议 ≤12s，长视频拆 8s 分片处理再拼接。

## 边界与降级

- 手机严重倾斜 / 被手大面积遮挡 / 屏幕不是黑屏占位 → 检测失败抛异常，上层拆 8s 分片分别处理。
- 用户给的方案（Canny + 每90帧重检）框架可用，但**检测器必须换黑屏二值化**（Canny 在 Seedance 画面 0 四边形），第一帧失败要自动扫描锚点帧。
