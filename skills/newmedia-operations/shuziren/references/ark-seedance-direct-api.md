# ARK火山引擎 Seedance 直接调用（不经过婵镜代理）

## 发现时间：2026-07-14
## 场景：婵镜蝉豆耗尽后寻找替代通道

## 可用模型

doubao-seedance-2-0-mini-260615（Mini, 4-15秒, 720p）
doubao-seedance-2-0-260128（标准, 4-15秒, 1080p）
doubao-seedance-1-5-pro-251215（高清, 4-12秒）

## API端点

POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks
GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}

## 请求格式

```json
{
  "model": "doubao-seedance-2-0-mini-260615",
  "content": [
    {"type": "image_url", "image_url": {"url": "公网URL"}, "role": "first_frame"},
    {"type": "text", "text": "prompt"}
  ],
  "generate_audio": true,
  "duration": 10,
  "ratio": "9:16",
  "resolution": "720p",
  "watermark": false
}
```

## ⚠️ 已知坑

1. **真人人脸被拦截** → 返回 `InputImageSensitiveContentDetected.PrivacyInformation`。含人脸的图走婵镜代理。
2. **人脸保真度差** → 变脸严重，不适合保人脸的场景
3. **Mini不支持1080p** → 标准版2.0才支持
4. **文件上传后需等processed状态** → 刚上传的file_id直接用报错

## 与婵镜代理对比

婵镜代理：不限真人检测、人脸保真稍好、扣婵豆
ARK直调：拦截真人图（不稳定）、人脸保真更差、扣余额
