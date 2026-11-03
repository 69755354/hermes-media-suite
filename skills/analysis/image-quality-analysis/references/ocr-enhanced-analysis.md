# OCR-Enhanced Image Analysis (pytesseract)

Adds text-specific checks on top of the pixel-level script in `programmatic-analysis.md`. Detects text overlap, vertical misalignment, per-character contrast failures, and content bleed near margins.

## Dependencies

```bash
# pytesseract requires tesseract-ocr installed system-wide
apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng  # Linux
pip install pytesseract Pillow
```

## Script

```python
#!/usr/bin/env python3
"""OCR-enhanced slide inspection: overlap, vertical alignment, per-character contrast, margin bleed."""

import os, sys, glob
import re
from collections import defaultdict
from PIL import Image, ImageStat
import pytesseract


def relative_luminance(rgb):
    """WCAG 2.1 relative luminance."""
    def linearize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(c1, c2):
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def analyze_slide(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    pixels = img.load()
    issues = []

    # ── Margin content bleed ──
    margin_size = 30
    is_dark_bg = ImageStat.Stat(img.convert("L")).mean[0] < 80
    is_light_bg = not is_dark_bg

    for margin_name in ["top", "bottom", "left", "right"]:
        if margin_name == "top":
            region = [pixels[x, y] for x in range(0, w, 5) for y in range(0, margin_size)]
        elif margin_name == "bottom":
            region = [pixels[x, y] for x in range(0, w, 5) for y in range(h - margin_size, h)]
        elif margin_name == "left":
            region = [pixels[x, y] for x in range(0, margin_size) for y in range(0, h, 5)]
        else:
            region = [pixels[x, y] for x in range(w - margin_size, w) for y in range(0, h, 5)]

        if not region:
            continue
        avg_lum = sum(sum(c) / 3 for c in region) / len(region)

        if is_dark_bg and avg_lum > 120:
            issues.append(f"Content bleed near {margin_name} edge (margin lum={avg_lum:.0f})")
        elif is_light_bg and avg_lum < 120:
            issues.append(f"Content bleed near {margin_name} edge (margin lum={avg_lum:.0f})")

    # ── OCR analysis ──
    try:
        ocr_data = pytesseract.image_to_data(img, lang='chi_sim+eng', output_type=pytesseract.Output.DICT)
        blocks = []
        for i, text in enumerate(ocr_data['text']):
            if text.strip() and int(ocr_data['conf'][i]) > 20:
                x, y, tw, th = (ocr_data['left'][i], ocr_data['top'][i],
                                 ocr_data['width'][i], ocr_data['height'][i])
                blocks.append({
                    'text': text, 'x': x, 'y': y, 'w': tw, 'h': th,
                    'right_edge': x + tw, 'bottom_edge': y + th,
                })

        # 1) Text near edges (potential overflow)
        for b in blocks:
            if b['right_edge'] > w - 20:
                issues.append(f"Text near right edge: '{b['text']}' at x={b['right_edge']} (w={w})")
            if b['bottom_edge'] > h - 20:
                issues.append(f"Text near bottom edge: '{b['text']}' at y={b['bottom_edge']} (h={h})")

        # 2) Vertical alignment within text rows
        y_groups = defaultdict(list)
        for b in blocks:
            y_key = round(b['y'] / 30) * 30
            y_groups[y_key].append(b)

        for y_key, group in sorted(y_groups.items()):
            if len(group) >= 2:
                y_positions = [b['y'] for b in group]
                y_range = max(y_positions) - min(y_positions)
                if y_range > 10:
                    texts = [b['text'] for b in group]
                    issues.append(f"Vertical misalignment at y~{y_key}: y-range={y_range}px texts={texts[:4]}")

        # 3) Text overlap (> 100 px² threshold = real overlap, not CJK adjacency)
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b_ = blocks[i], blocks[j]
                ol_x = max(0, min(a['right_edge'], b_['right_edge']) - max(a['x'], b_['x']))
                ol_y = max(0, min(a['bottom_edge'], b_['bottom_edge']) - max(a['y'], b_['y']))
                area = ol_x * ol_y
                if area > 100:
                    issues.append(f"Overlap: '{a['text']}' x '{b_['text']}' = {ol_x}x{ol_y}px (area={area})")

        # 4) Per-character contrast (WCAG check)
        for b in blocks[:15]:  # sample first 15 blocks
            try:
                # Text region
                txt_rgn = img.crop((b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']))
                fg_lum = relative_luminance(tuple(int(v) for v in ImageStat.Stat(txt_rgn).mean))

                # Background region (just outside the block)
                bx, by = max(0, b['x'] - 4), max(0, b['y'] - 4)
                bx2 = min(w, b['x'] + b['w'] + 4)
                by2 = min(h, b['y'] + b['h'] + 4)
                bg_rgn = img.crop((bx, by, bx2, by2))
                bg_lum = relative_luminance(tuple(int(v) for v in ImageStat.Stat(bg_rgn).mean))

                cr = (max(fg_lum, bg_lum) + 0.05) / (min(fg_lum, bg_lum) + 0.05)
                if cr < 2.0:
                    issues.append(f"Low contrast '{b['text']}': ratio={cr:.2f} (WCAG fail)")

            except Exception:
                pass

    except Exception as e:
        issues.append(f"OCR error: {e}")

    return issues


def main():
    files = sorted(sys.argv[1:]) if len(sys.argv) > 1 else sorted(glob.glob("slide-*.jpg"))
    if not files:
        print("Usage: python ocr_analysis.py slide-*.jpg")
        sys.exit(1)

    all_issues = {}
    total = 0
    for f in files:
        issues = analyze_slide(f)
        all_issues[f] = issues
        total += len(issues)
        print(f"\n=== {f} ===")
        if issues:
            for iss in issues:
                print(f"  ❌ {iss}")
        else:
            print("  ✅ No issues found")

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total} issues across {len(files)} files")


if __name__ == "__main__":
    main()
```

## Interpreting OCR Findings

### Overlap: Real vs. CJK Adjacency

| Overlap area | Likely cause | Action |
|-------------|--------------|--------|
| 1–15 px² | Adjacent CJK characters | Ignore (OCR artifact) |
| 16–100 px² | Tight character spacing or OCR drift | Check visually; low priority |
| > 100 px² | Genuine overlapping elements | Flag — two text elements crossing into each other's space |

### Contrast Thresholds

| Sampled ratio | Verdict |
|---------------|---------|
| < 2.0 | Unreadable — text nearly same color as background |
| 2.0–2.99 | Marginal — OK for large headings, fails for body |
| 3.0–4.49 | WCAG AA for large text only |
| ≥ 4.5 | WCAG AA for body text |

### Common False Positive Patterns

1. **Anti-aliased character edges** — OCR samples at block borders where text blends with background. Fix: sample from the character's interior pixels rather than the full OCR bounding box.
2. **Gradient background near text** — Creates artificially low contrast in the surrounding region. Fix: sample bg from a neutral area (e.g., known theme bg color) rather than immediately adjacent to the text block.
3. **Dark cover slides** — Will always flag many low-contrast blocks. The critical question is whether *body text* is readable, not decorative elements.
