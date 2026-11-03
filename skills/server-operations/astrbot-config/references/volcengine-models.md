# 火山引擎 Ark 可用模型（2026-07）

以下模型可通过 `https://ark.cn-beijing.volces.com/api/v3` 访问。

## DeepSeek 系列
- `deepseek-v3-241226`
- `deepseek-v3-250324`
- `deepseek-v3-1-250821`
- `deepseek-v3-2-251201`
- `deepseek-v4-pro-260425`
- `deepseek-v4-flash-260425`
- `deepseek-r1-250120`
- `deepseek-r1-250528`

## 豆包系列（有内置身份）
- `doubao-seed-2-0-pro-260215` — 会自称「豆包」
- `doubao-seed-2-0-mini-260215`
- `doubao-seed-2-0-lite-260215`
- 注意：豆包模型有硬编码的「我是豆包」身份，系统提示词无法完全覆盖

## 注意
- 模型需要先在火山引擎控制台「开通」才能使用
- 直接调用模型名会报错 `not activated`，需要使用已创建的 endpoint ID
- 通过 `POST /api/v3/chat/completions` 测试
