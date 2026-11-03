---
name: "excel-recalc-verify"
description: "重算 Excel 公式、或需要检查表格排版是否被切掉时使用。绕开会挂死的官方 recalc 脚本，用持久 profile 的 LibreOffice 一秒完成；并给出行高截断问题的唯一可靠查法（静态字体度量），含三条已被实验证伪的旧做法。"
---

# Excel 重算与排版校验

用 openpyxl 写入的公式**不带缓存值**，直接交付的话用户在 Excel 里可能看到空白或 0。任何写了公式的 xlsx 在交付前都必须重算一次，并且核对排版。

## 第一步：不要用官方 recalc 脚本

**不要调用 xlsx skill 自带的 `scripts/recalc.py`。** 实测在这个沙箱里连续三次超时（149s / 164s / 139s）：它每次新建临时 LibreOffice profile，bootstrap 就要 140 秒以上，而且走 Basic 宏那条路径即使 profile 已预热也会挂死。

改用下面这个辅助脚本，复用固定 profile 目录（`~/.lo_profile_persist`）、走 convert-to 过滤器原地覆盖，约 1–3 秒完成。已验证批注、图片、合并单元格、数字格式全部无损（69 条批注 / 9 张图 / 33 个合并区）。

把它写成 `lorecalc.py` 再开工：

```python
import os, shutil, subprocess, sys
from pathlib import Path
from openpyxl import load_workbook

PROFILE = f"file://{os.environ['HOME']}/.lo_profile_persist"

def recalc(path, timeout=180):
    p = Path(path)
    outdir = p.parent / "_recalc_tmp"
    outdir.mkdir(exist_ok=True)
    r = subprocess.run(
        ["soffice", f"-env:UserInstallation={PROFILE}", "--headless",
         "--norestore", "--nolockcheck", "--convert-to", "xlsx",
         "--outdir", str(outdir), str(p)],
        env=dict(os.environ, SAL_USE_VCLPLUGIN="svp"),
        capture_output=True, text=True, timeout=timeout)
    if not (outdir / p.name).exists():
        raise RuntimeError(f"convert failed: {r.stdout} {r.stderr}")
    shutil.copyfile(outdir / p.name, p)      # 原地覆盖

def audit(path):
    wb = load_workbook(path, data_only=True)
    bad = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("#"):
                    bad.append((ws.title, c.coordinate, v))
    return bad

if __name__ == "__main__":
    for f in sys.argv[1:]:
        recalc(f)
        for s, coord, v in audit(f):
            print(f"ERROR {s}!{coord} = {v}")
        print(f"ok: {f}")
```

重算后必须扫一遍结果：`#` 开头的错误值（`#REF!` / `#DIV/0!` / `#NAME?`）和意外的 None 都要查清再交付。跨表引用改过表名、或公式里用了 LibreOffice 不认的函数时，最容易在这里暴露。

## ⭐ 三条被实验证伪的旧做法（都做过阳性对照，别再用）

**① `pdftotext` 永远查不出「行高不够、文字被切掉」—— 一个都查不出。**
原因：LibreOffice **不裁剪**超出行高的文字，而是让它压到下一行上继续画，字仍然完整留在 PDF 文本层里。阳性对照：故意把三行文字塞进 13pt 行高，渲染出来目视明显重叠，`pdftotext` 一个字不缺。

⛔ **因此「在段末放一句固定哨兵文字、再 grep 它在不在」这个思路是错的，已删除。** 它物理上不可能报警，只会给你虚假的安全感。

**② `pdftotext -layout` 会把相邻列交错输出。**
一段文字的换行处会插进旁边列的内容。靠「找不见的尾巴」当判据，在一个已知无误的中文模板上报了 **24 个假阳性**。`-layout` 只能拿来 grep `###`（列宽不足会真的渲染成井号），**不能拿来判文本完整性**。

**③ 「LibreOffice 不能把合并单元格跨页断开、页尾的多行合并说明块会被直接切掉一半」是错的，没能复现。**
造一个 4 行的合并块，在 6 个不同的分页错位处（起始行 46~56）逐一扫过，每次结束标记词都在，一个字都没丢。**跨页不是缺陷来源。**

保留的做法（理由换了）：把长说明写成**一行一句、每行单独 merge**仍然值得做 —— 它让分页落在行与行之间、行高也更好控；大块（敏感度表、校验块）前插 `Break` 强制分页也保留，那是为了版面整齐，不是为了防切字。

**④ 顺带：「按字符数估行数」精度不够。** 在真实模板上给了 2 个假阳性：145 字符在 113 宽的合并区里一行放得下，103 字符在 40 宽的列里要 3 行，两者都落在每单位列宽约 1.28 个字符 —— **没有任何单一"装填效率系数"能同时说对**。别再写 `rowh(text, per_line=74)` 这种函数。

## 行高截断的唯一可靠查法：静态字体度量

不需要 LibreOffice、不需要渲染，纯 Python + 字体文件就能算，所以内存小的本机也跑得动。四步：

1. **列宽换算成磅**：Excel 列宽单位 → 磅 = `(单位 × 7 + 5) × 0.75`，再**减约 4pt 内边距**当可用宽。合并区的可用宽是所跨各列相加。
2. **行高**：单行 = 字号 × 1.20；多行乘行数。
3. **量真实字宽**：用 PIL/freetype 按字号量每个字符的像素宽（拉丁用 Liberation Sans，中日韩用 Noto CJK），再贪心折行。**拉丁按空格断行、中日韩逐字断行** —— 这一点搞错，中文会被当成一个超长单词永不换行。
4. **算出的所需高度 > 该行行高，就报 FAIL。**

### ⚠️ 只有两种单元格会真的被切

- **显式设过行高的行**（`ws.row_dimensions[r].height = ...`）
- **合并区**（合并区**不参与自动行高**，Excel/LibreOffice 都不会为它撑高）

**没设过行高的普通行，渲染时会自己撑开，不算缺陷。** 不区分这一点，扫描器会在完全正常的文件上刷出一屏假阳性，然后人就再也不看报告了。

把这套写成一个 `fitscan.py` 复用，并让生成脚本**直接调它算行高**（表头行、合并区、以及任何要显式设高的行），而不是事后再扫 —— 这样"装不下"这类缺陷从源头就不会产生。

## 转图看图仍然要做，但它是眼睛不是判据

```bash
soffice -env:UserInstallation="file://$HOME/.lo_profile_persist" --headless \
        --norestore --convert-to pdf --outdir /tmp/_pv1 "报价表.xlsx"
pdftoppm -r 110 -png /tmp/_pv1/报价表.pdf /tmp/_pv1/page
pdftotext -layout /tmp/_pv1/报价表.pdf - | grep -nE '#{3,}'   # 这条有效：列宽不足
```

然后用 Read 工具逐页看那些 png。重点看：表头有没有被切、金额列有没有变成 `####`、产品图有没有压住文字或跑到打印区域外、整体版面有没有明显错乱。另外**把 PDF 页数纳入基准**（页数突变说明版面被改坏了），这是一条便宜又有效的机器判据。

**每次渲染换一个新目录名**（`_pv1` / `_pv2` / `_pv3`…）。这个沙箱的 `rm` 不可靠，旧 PDF 删不掉，会让你看着上一版的图以为改动生效了。

## ⭐ 方法论：一个没有阳性对照验证过的判据等于没有判据

写完一条检查，**必须造一个"本来就该被它抓住"的坏样本，确认它真的报警**。只跑真实文件看到"0 问题"什么都不能证明 —— 可能是文件好，也可能是判据永远返回通过（上面的哨兵句就是这么废掉的）。

据此**放弃**过一条判据：查 PDF 页边缘 3 像素带里有没有黑点（切边）。30 页真实文件基线干净（0 触墨），但**造不出阳性对照样本**，无法证明它能查出任何东西，所以宁可不上线。

## 这个沙箱的两个硬坑

`nohup` / `setsid` 起的后台任务在下一次 bash 调用里就消失了（每次调用是独立 PID namespace，`--unshare-pid`），日志文件永远是空的。**所有耗时命令必须在同一次 bash 调用里前台跑完**，别指望轮询日志。

`rm` 经常返回 "Operation not permitted"，会让 `&&` 链在中间断掉，后面的 heredoc 根本不执行。**别在命令链里放 `rm`**；要覆盖文件就用 Write 工具，要清临时目录就换个新目录名。

## 在本机（Mac）跑而不是在沙箱跑

如果是通过本机桥（`newme-mac`）执行，注意**内存闸门会拒绝任何含 "libreoffice" / "soffice" 字样的命令**（那台机器只有 8 GB）。探测路径时改写成 `ls -d /Applications/Lib*.app` 之类绕开关键词；真要在本机重算就加 `#FORCE`，但先确认没有别的重活在跑。

所以**默认在沙箱里重算，本机只负责存放成品**。本机侧的检查脚本要写成纯静态、不依赖 LibreOffice：结构检查（表齐不齐、公式数对不对、该是公式的格子有没有被写死）+ 上面那套**静态字体度量**的行高检查 —— 这两类都不需要渲染，同事双击就能跑。给验收流水线加一个 `--fast` 开关跳过所有要 LibreOffice 的关，就是为这个场景准备的。

