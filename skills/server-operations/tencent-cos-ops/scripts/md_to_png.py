#!/usr/bin/env python3
"""Render a markdown file to segmented PNG images for WeChat delivery.
WeChat adapter only accepts image/video/audio — docx/pdf cannot be delivered.
Usage: python3 md_to_png.py <input.md> [out_dir]   (default out_dir=/tmp/<mdname>_pages)
Requires PIL + a CJK font (tested: /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc).
"""
from PIL import Image, ImageDraw, ImageFont
import re
import os
import sys

MD = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/workflow/outputs/PRD_归因系统_最终完整版_20260814.md"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/{os.path.basename(MD).split('.')[0]}_pages"
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
WIDTH = 1080
PAD = 40
FONT_SIZE = 24
LINE_H = 34
TITLE_SIZE = 32

lines = open(MD, encoding="utf-8").read().splitlines()


def clean(line):
    s = line.rstrip()
    if s.startswith("```"):
        return "```"
    s = re.sub(r"^#{1,6}\s+", "", s)
    s = re.sub(r"^\|?\s*\|?\s*:?-+:?\s*\|?", "", s)
    s = re.sub(r"^\s*[-*]\s+", "· ", s)
    s = re.sub(r"^\s*\d+\.\s+", lambda m: f"{m.group(0).strip()} ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s


def wrap(draw, text, font, max_w):
    cur = ""
    out = []
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out if out else [""]


font = ImageFont.truetype(FONT, FONT_SIZE)
title_font = ImageFont.truetype(FONT, TITLE_SIZE)

pages = []
page = []
page_h = 0
for raw in lines:
    s = clean(raw)
    if not s.strip():
        s = ""
    is_title = raw.startswith("#")
    f = title_font if is_title else font
    max_w = WIDTH - 2 * PAD
    wrapped = wrap(ImageDraw.Draw(Image.new("RGB", (1, 1))), s, f, max_w) if s else [""]
    for wline in wrapped:
        lh = int(LINE_H * 1.2) if is_title else LINE_H
        if page_h + lh > 1700:
            pages.append(page)
            page = []
            page_h = 0
        page.append((wline, f))
        page_h += lh
if page:
    pages.append(page)

os.makedirs(OUT_DIR, exist_ok=True)
paths = []
for i, pg in enumerate(pages):
    h = PAD * 2
    for _, f in pg:
        h += int(LINE_H * 1.2) if f is title_font else LINE_H
    img = Image.new("RGB", (WIDTH, h), "white")
    d = ImageDraw.Draw(img)
    y = PAD
    for text, f in pg:
        d.text((PAD, y), text, fill="black", font=f)
        y += int(LINE_H * 1.2) if f is title_font else LINE_H
    p = f"{OUT_DIR}/p{i+1:02d}.png"
    img.save(p)
    paths.append(p)
print("PAGES:", len(pages))
print("PATHS:", " ".join(paths))
