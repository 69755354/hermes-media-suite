#!/usr/bin/env python3
"""DS 原生 API 直调（降级通道，不依赖 claude/codex 壳）。

用法:
  python3 ds_native_chat.py <prompt.md> <output.md> [model]
  默认 model=deepseek-v4-flash（老板 2026-08-18 定案：codex 挂时先提 V4 Pro、随即改口「等等 用FLASH顶」，最终拍板 flash）
  需要 pro 时显式传 deepseek-v4-pro（须老板点名才用）

适用: 纯文本生成类任务（分镜/文案/报告/分析）。任务书必须自包含
（上下文/逐字稿/知识库结论全内嵌），DS 降级时不指望它读文件。

Key 读取: ~/.hermes/config.yaml 的 model.api_key（与 ds_fallback.sh 同源）。

⚠️ 2026-08-18 血泪（白跑两轮）：DS V4 flash/pro 默认开 reasoning，
reasoning_content 会吃光 max_tokens 预算 → content 返回空字符串、落盘 0 字节。
诊断顺序: 先看 finish_reason + usage.completion_tokens_details.reasoning_tokens，
若 reasoning_tokens ≈ max_tokens 且 content 空 = 推理吃光预算，不是模型没干活。
修复方向: max_tokens 拉大（≥30000，DS 输出上限 384K）+ 显式关 thinking
（chat_template_kwargs: {'thinking': False} 或 thinking: {'type': 'disabled'}，
两个写法 0818 在测，未定论——拉大 max_tokens 是已验证方向）。
"""
import json, sys, urllib.request, urllib.error, yaml

if len(sys.argv) < 3:
    print('用法: ds_native_chat.py <prompt.md> <output.md> [model]')
    sys.exit(1)

prompt_file, output_file = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else 'deepseek-v4-flash'

cfg = yaml.safe_load(open('/home/ubuntu/.hermes/config.yaml')) or {}
key = (cfg.get('model') or {}).get('api_key', '')
if not key:
    print('ERROR: 取不到 DS key（config.yaml model.api_key）')
    sys.exit(1)

prompt = open(prompt_file).read()
payload = {
    'model': model,
    'messages': [
        {'role': 'system', 'content': '你是后台内容执行器，产出结果文件内容，不寒暄，只输出干活结果。你的唯一产出是完整结果内容（markdown 全文），输出不完整 = 任务失败。'},
        {'role': 'user', 'content': prompt},
    ],
    # 0818: 8000/16000 都被 reasoning 吃光 → content 空。拉大给推理留余量。
    'max_tokens': 30000,
    'stream': False,
}
req = urllib.request.Request(
    'https://api.deepseek.com/v1/chat/completions',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
)
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read())
    ch = data['choices'][0]
    msg = ch['message']
    content = msg.get('content') or ''
    usage = data.get('usage', {})
    rt = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens', 0)
    # 诊断输出：先验证再落盘，别重复白跑
    print(f'finish_reason: {ch.get("finish_reason")}')
    print(f'usage: {json.dumps(usage, ensure_ascii=False)}')
    print(f'reasoning_tokens: {rt}  content_len: {len(content)}')
    if not content:
        print('ERROR: content 为空（疑似 reasoning 吃光 max_tokens）——拉大 max_tokens 或关 thinking 重跑')
        print('reasoning_content 前 300 字:', repr(msg.get('reasoning_content'))[:300])
        sys.exit(1)
    with open(output_file, 'w') as f:
        f.write(content)
    print(f'OUTPUT: {output_file}')
    print('--- 头 10 行 ---')
    print('\n'.join(content.splitlines()[:10]))
    print('--- 尾 5 行 ---')
    print('\n'.join(content.splitlines()[-5:]))
except urllib.error.HTTPError as e:
    print(f'HTTP {e.code}: {e.read().decode()[:500]}')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
