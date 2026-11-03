#!/usr/bin/env bash
# bing_search.sh — 必应 HTML 搜索兜底（web_search 后端挂了 / web_extract 只搜不提取时用；海外机可访问必应）
# 用法: bing_search.sh "查询词" [结果数]
# 踩坑：必应 HTML 结构里 <li class="b_algo"> 块内的 h2/a 带属性，先 split b_algo 再逐块正则，别用全局 <h2> 匹配
set -euo pipefail
Q="$1"
N="${2:-6}"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$Q")
curl -s -L -A "$UA" --max-time 25 "https://www.bing.com/search?q=${ENC}&mkt=zh-CN" -o /tmp/bing_r.html
python3 - "$N" <<'EOF'
import re, html, sys
n = int(sys.argv[1])
data = open('/tmp/bing_r.html', encoding='utf-8', errors='replace').read()
blocks = re.split(r'<li class="b_algo"', data)[1:]
for i, blk in enumerate(blocks[:n], 1):
    m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
    if not m:
        continue
    u = m.group(1)
    t = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
    print(f"{i}. {t}\n   {u[:130]}")
    m2 = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S)
    if m2:
        sn = html.unescape(re.sub(r'<[^>]+>', '', m2.group(1))).strip()
        print(f"   摘要: {sn[:150]}")
EOF
