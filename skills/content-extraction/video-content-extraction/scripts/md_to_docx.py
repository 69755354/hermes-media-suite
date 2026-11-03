#!/usr/bin/env python3
"""Markdown → DOCX 转换器（2026-08-26 实测，火龙漫剧拆解报告+生产方案）

把 codex 产出的 markdown 报告转成 docx 发飞书群。
处理：标题(##/###)、表格(|)、列表(- / 1.)、加粗(**)、引用(>)、代码块跳过。
不处理：图片、HTML 标签、嵌套列表。

用法：python3 md_to_docx.py <input.md> <output.docx>
"""
import re, sys
from docx import Document
from docx.shared import Pt, Inches

def add_table(doc, rows):
    if not rows or len(rows) < 2:
        return
    cols = len(rows[0])
    table = doc.add_table(rows=len(rows)-1, cols=cols)
    table.style = 'Table Grid'
    for ri, row in enumerate(rows[1:]):
        for ci, cell_text in enumerate(row):
            if ci < cols:
                table.cell(ri, ci).text = cell_text.strip()
    doc.add_paragraph()

def convert(md_path, docx_path):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.font.size = Pt(11)

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    in_table = False
    table_rows = []

    for line in lines:
        line = line.rstrip()
        if not line:
            if in_table and table_rows:
                add_table(doc, table_rows)
                table_rows = []
                in_table = False
            else:
                doc.add_paragraph()
            continue

        if line.startswith('|') and line.endswith('|'):
            if re.match(r'^\|[\s\-:|]+\$', line):
                continue
            cells = [c.strip() for c in line.split('|')[1:-1]]
            table_rows.append(cells)
            in_table = True
            continue

        if in_table and table_rows:
            add_table(doc, table_rows)
            table_rows = []
            in_table = False

        if line.startswith('### '):
            doc.add_heading(line[4:], level=3)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('> '):
            p = doc.add_paragraph(line[2:])
            p.paragraph_format.left_indent = Inches(0.5)
        elif line.startswith('- [ ] '):
            doc.add_paragraph(line[6:], style='List Bullet')
        elif line.startswith('- '):
            doc.add_paragraph(line[2:], style='List Bullet')
        elif re.match(r'^\d+\. ', line):
            doc.add_paragraph(re.sub(r'^\d+\. ', '', line), style='List Number')
        elif line.startswith('```'):
            continue
        else:
            p = doc.add_paragraph()
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)

    if in_table and table_rows:
        add_table(doc, table_rows)

    doc.save(docx_path)
    print(f'OK: {docx_path} saved')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('用法: python3 md_to_docx.py <input.md> <output.docx>')
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
