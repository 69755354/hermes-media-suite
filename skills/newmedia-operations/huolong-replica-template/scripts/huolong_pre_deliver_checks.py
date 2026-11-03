#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火龙片交付前四项自检（2026-10-11 立）

用户反复纠正的四类问题，落成可执行卡点：
  1. 人物/参考图不得重复（一条一对，同批不复用）
  2. LOGO 必须是官方圆形 PNG 资产，禁止 drawtext 画品牌名占位
  3. 必须有 BGM（快乐马底片不带 BGM -> 合成端 amix 混入曲库）
  4. 定妆/角色图先出样给用户过目（APPROVED 标记文件）

用法:
  python3 huolong_pre_deliver_checks.py --project /path/to/proj \
      [--chars assets/01_甲.jpg,assets/01_乙.jpg] \
      [--compose work/gen/compose_gz.py] [--require-approval] [--approval style_samples/APPROVED.txt]

退出码: 0=PASS, 2=FAIL（逐项列出）
"""
import argparse, hashlib, os, re, sys

FAILS, WARNS = [], []


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def check_chars(project, chars):
    """1. 参考图不得重复：重名或同内容都拦"""
    if not chars:
        WARNS.append("chars: 未传 --chars，跳过人物重复检查（派活前必须传本批全部角色图）")
        return
    seen_name, seen_md5 = {}, {}
    for c in chars:
        p = c if os.path.isabs(c) else os.path.join(project, c)
        base = os.path.basename(c)
        if base in seen_name:
            FAILS.append(f"chars: 重复参考图 {base}（同批出现两次 = 人物复用，必须一条一对）")
        seen_name[base] = True
        if os.path.exists(p):
            m = md5(p)
            if m in seen_md5:
                FAILS.append(f"chars: {base} 与 {seen_md5[m]} 内容完全相同（同图复用）")
            seen_md5[m] = base
        else:
            WARNS.append(f"chars: {base} 文件不存在，跳过内容比对")
    if chars:
        print(f"  [chars] 检查 {len(chars)} 张参考图：重名/同内容均为 0 才过")


def check_logo(project, compose):
    """2. LOGO 必须是真图标资产，禁止 drawtext 画品牌名"""
    if not compose:
        WARNS.append("logo: 未传 --compose，跳过 LOGO 检查")
        return
    p = compose if os.path.isabs(compose) else os.path.join(project, compose)
    if not os.path.exists(p):
        FAILS.append(f"logo: 合成脚本不存在 {p}")
        return
    src = open(p, encoding='utf-8', errors='replace').read()
    has_png = bool(re.search(r'[\w/\\.-]*logo[\w/\\.-]*\.png', src, re.I)) or ('assets/brand' in src)
    brand_text = re.search(r'drawtext[^\n]{0,400}?火龙漫剧', src)
    if not has_png:
        FAILS.append("logo: 合成脚本里找不到 LOGO 的 .png 资产引用（必须用官方圆形图标，不许代码画字）")
    if brand_text:
        FAILS.append("logo: 合成脚本用 drawtext 画「火龙漫剧」当 LOGO —— 用户原话「放几个字在上面什么意思吗？」，必须换官方图标 PNG")
    print("  [logo] 官方图标 PNG 引用=%s；drawtext 画品牌名=%s" % ("有" if has_png else "无", "有" if brand_text else "无"))


def check_bgm(project, compose):
    """3. 必须有 BGM：合成端要有 amix + 曲库目录里有文件"""
    if not compose:
        WARNS.append("bgm: 未传 --compose，跳过 BGM 检查")
        return
    p = compose if os.path.isabs(compose) else os.path.join(project, compose)
    if not os.path.exists(p):
        return  # 已在 logo 检查里报过
    src = open(p, encoding='utf-8', errors='replace').read()
    if 'amix' not in src:
        FAILS.append("bgm: 合成脚本没有 amix —— 快乐马底片不带 BGM，必须在合成端混入")
    if 'bgm' not in src.lower():
        FAILS.append("bgm: 合成脚本里没有 bgm 相关代码")
    m = re.search(r'BGM_DIR\s*=\s*["\']([^"\']+)["\']', src)
    n = None
    if m:
        d = m.group(1)
        if os.path.isdir(d):
            n = len([f for f in os.listdir(d) if f.lower().endswith(('.mp3', '.m4a', '.wav'))])
            if n == 0:
                FAILS.append(f"bgm: 曲库目录是空的 {d}")
        else:
            WARNS.append(f"bgm: 曲库目录本机不可见（{d}，可能在被调用的另一台机器上），本机跳过计数")
    else:
        WARNS.append("bgm: 合成脚本里没写 BGM_DIR，无法自动数曲库")
    print("  [bgm] amix=%s；曲库文件数=%s" % ("有" if 'amix' in src else "无", n if n is not None else "未取到"))


def check_approval(project, approval):
    """4. 角色图必须先经用户过目"""
    p = approval if os.path.isabs(approval) else os.path.join(project, approval)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        print(f"  [approval] 已有用户确认标记 {p}")
    else:
        FAILS.append(f"approval: 没有用户确认标记 {p} —— 角色/定妆图必须先发用户过目、确认后再派片，不许先出片再返工")


def check_desc(project, desc_path):
    """5. 作品描述格式（2026-10-12 用户定）：利益点≤30字 + #火龙漫剧 #漫剧 #腾讯漫剧"""
    if not desc_path:
        WARNS.append("desc: 未传 --desc，跳过作品描述格式检查（交付前必须传 work/bt/descs.json）")
        return
    import json
    p = desc_path if os.path.isabs(desc_path) else os.path.join(project, desc_path)
    if not os.path.exists(p):
        FAILS.append(f"desc: 描述文件不存在 {p}")
        return
    items = json.load(open(p, encoding='utf-8'))
    if isinstance(items, dict):
        items = items.get('items', [])
    tags = ['#火龙漫剧', '#漫剧', '#腾讯漫剧']
    miss_tag, over30, bad_order = [], [], []
    for it in items:
        d = (it.get('描述') or '').strip()
        num = it.get('编号', '?')
        if not all(t in d for t in tags):
            miss_tag.append(num); continue
        if d.index('#火龙漫剧') > d.index('#漫剧') or d.index('#漫剧') > d.index('#腾讯漫剧'):
            bad_order.append(num)
        head = d.split('#火龙漫剧')[0].strip()
        if len(head) > 30:
            over30.append(f"{num}({len(head)}字)")
    if miss_tag:
        FAILS.append(f"desc: {len(miss_tag)} 条缺话题标签（必须同时含 #火龙漫剧 #漫剧 #腾讯漫剧）：{miss_tag[:8]}")
    if bad_order:
        FAILS.append(f"desc: {len(bad_order)} 条标签顺序错（须 #火龙漫剧 → #漫剧 → #腾讯漫剧）：{bad_order[:8]}")
    if over30:
        FAILS.append(f"desc: {len(over30)} 条利益点超 30 字：{over30[:8]}")
    if not (miss_tag or bad_order or over30):
        print(f"  [desc] 检查 {len(items)} 条作品描述：标签齐全、顺序对、利益点均在 30 字内")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--chars', default='')
    ap.add_argument('--compose', default='')
    ap.add_argument('--desc', default='', help='作品描述 JSON（work/bt/descs.json），查标签与30字上限')
    ap.add_argument('--require-approval', action='store_true')
    ap.add_argument('--approval', default='style_samples/APPROVED.txt')
    a = ap.parse_args()
    project = os.path.abspath(a.project)
    if not os.path.isdir(project):
        print(f"FAIL: 项目目录不存在 {project}")
        return 2
    print(f"火龙交付前四项自检: {project}")
    chars = [c.strip() for c in a.chars.split(',') if c.strip()]
    check_chars(project, chars)
    check_logo(project, a.compose)
    check_bgm(project, a.compose)
    if a.require_approval:
        check_approval(project, a.approval)
    check_desc(project, a.desc)
    for w in WARNS:
        print(f"WARN: {w}")
    if FAILS:
        for f in FAILS:
            print(f"FAIL: {f}")
        print(f"==> 不合格：{len(FAILS)} 项，不许派片/交付")
        return 2
    print("==> PASS：四项自检通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
