# Programmatic Image Analysis Script

A complete, runnable Python script for inspecting rendered slide/images when vision APIs aren't available.

## The Script

Save as `inspect_images.py` and run with:
```bash
pip install Pillow numpy   # one-time setup
python inspect_images.py
```

```python
#!/usr/bin/env python3
"""Programmatic visual inspection of rendered images.

Usage:
    python inspect_images.py                    # auto-detect slide-*.jpg
    python inspect_images.py --path output/     # custom directory
    python inspect_images.py image1.jpg image2.jpg  # specific files
"""

import sys, os, glob, re
import numpy as np
from PIL import Image
from collections import Counter


def rgb_to_luminance(r, g, b):
    """Relative luminance per WCAG 2.1."""
    def linearize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(l1, l2):
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def analyze_image(fpath):
    """Run all checks on a single image file."""
    img = Image.open(fpath).convert("RGB")
    arr = np.array(img)
    w, h = arr.shape[1], arr.shape[0]
    name = os.path.basename(fpath)
    print(f"\n=== {name} ({w}x{h}) ===")

    # 1. Edge uniformity
    margin = 15
    edge_std = {
        k: float(np.std(
            arr[:margin] if k == 'top'
            else arr[-margin:] if k == 'bottom'
            else arr[:, :margin] if k == 'left'
            else arr[:, -margin:]
        )) for k in ['top', 'bottom', 'left', 'right']
    }
    high = {k: v for k, v in edge_std.items() if v > 25}
    if high:
        print(f"  ⚠️  High edge variance: {high}")

    # 2. Edge overflow (5px border zone)
    bg_ref = np.mean(arr[:30, :30, :], axis=(0, 1))
    edge_zone = np.concatenate([
        arr[:5].reshape(-1, 3),
        arr[-5:].reshape(-1, 3),
        arr[:, :5].reshape(-1, 3),
        arr[:, -5:].reshape(-1, 3),
    ])
    edge_diff = np.mean(np.abs(edge_zone.astype(float) - bg_ref.astype(float)), axis=1)
    overflow = float(np.mean(edge_diff > 30) * 100)
    if overflow > 10:
        print(f"  ℹ️  Edge-zone divergence: {overflow:.0f}% (check if intentional header/design)")

    # 3. Overall contrast
    L = np.apply_along_axis(lambda p: rgb_to_luminance(*p), 2, arr)
    overall_cr = contrast_ratio(float(np.max(L)), float(np.maximum(np.min(L), 1e-6)))
    status = "✅" if overall_cr >= 7 else ("⚠️" if overall_cr >= 4.5 else "❌")
    print(f"  {status} Overall contrast ratio: {overall_cr:.1f}:1")

    # 4. Low-contrast blocks (100px grid)
    bs = 100
    low = []
    for y in range(0, h - bs + 1, bs):
        for x in range(0, w - bs + 1, bs):
            block = L[y:y + bs, x:x + bs]
            bcr = contrast_ratio(float(np.max(block)),
                                 float(np.maximum(np.min(block), 1e-6)))
            if bcr < 3.0 and float(np.max(block) - np.min(block)) > 0.02:
                low.append((x, y, round(bcr, 2)))
    if low:
        low.sort(key=lambda t: t[2])
        print(f"  ℹ️  Low-contrast blocks: {len(low)} (worst 3: {low[:3]})")
        # Classify: clustered near edges => decorative; scattered => possible text issue
        edge_count = sum(1 for x, y, _ in low if x < 200 or x > w - 200 or y < 200 or y > h - 200)
        if edge_count > len(low) * 0.7:
            print(f"       ~{edge_count}/{len(low)} near edges — likely decorative elements, not text")
    else:
        print(f"  ✅ No low-contrast blocks detected")

    # 5. Edge density + overlap risk
    gray = np.mean(arr, axis=2).astype(float)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    gx = np.pad(gx, ((0, 0), (0, 1)), mode='edge')
    gy = np.pad(gy, ((0, 1), (0, 0)), mode='edge')
    grad = gx + gy
    edge_density = float(np.mean(grad > 40) * 100)
    print(f"  Edge density: {edge_density:.1f}%")
    overlap = float(np.mean(grad > 120) * 100)
    check = "✅" if overlap < 5 else ("⚠️" if overlap < 15 else "❌")
    print(f"  {check} Overlap risk: {overlap:.1f}%")

    # 6. Empty horizontal bands (alignment check)
    hp = np.mean(grad > 40, axis=0)
    runs = []
    s = None
    for i in range(w):
        if hp[i] < 0.02:
            if s is None:
                s = i
        else:
            if s is not None and i - s > w * 0.12:
                runs.append((s, i))
            s = None
    if s is not None and w - s > w * 0.12:
        runs.append((s, w))
    if runs:
        print(f"  ℹ️  Empty horizontal bands: {runs}")

    # 7. Symmetry
    half = w // 2
    left, right = arr[:, :half], np.fliplr(arr[:, half:])
    mw = min(left.shape[1], right.shape[1])
    sym = float(np.mean(np.abs(left[:, :mw].astype(float) - right[:, :mw].astype(float))))
    print(f"  Symmetry diff: {sym:.1f} {'✅' if sym < 25 else ('⚠️' if sym < 40 else '❌')}")

    # 8. Dominant colors
    small = img.resize((64, 36))
    quant = [(r // 32 * 32, g // 32 * 32, b // 32 * 32) for r, g, b in small.getdata()]
    top = Counter(quant).most_common(3)
    print(f"  Top colors: {top}")

    return {
        "name": name,
        "dims": (w, h),
        "contrast_ratio": round(overall_cr, 2),
        "edge_density": round(edge_density, 1),
        "overlap_risk": round(overlap, 1),
        "symmetry": round(sym, 1),
        "low_contrast_blocks": len(low),
    }


def main():
    # Determine files to analyze
    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        base = sys.argv[2]
        files = sorted(glob.glob(os.path.join(base, "slide-*.jpg")))
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        files = [f for f in sys.argv[1:] if os.path.isfile(f)]
    else:
        files = sorted(glob.glob("slide-*.jpg"))

    if not files:
        print("No image files found. Usage:")
        print("  python inspect_images.py                    # auto-detect slide-*.jpg")
        print("  python inspect_images.py --path output/     # custom dir")
        print("  python inspect_images.py img1.jpg img2.jpg  # explicit paths")
        sys.exit(1)

    results = []
    for f in files:
        results.append(analyze_image(f))

    # Summary table
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'File':<30} {'CR':<6} {'Edge%':<7} {'Overlap%':<9} {'Sym':<5} {'LowC':<5}")
    print(f"{'-' * 30} {'-' * 6} {'-' * 7} {'-' * 9} {'-' * 5} {'-' * 5}")
    for r in results:
        print(f"{r['name'][:28]:<30} {r['contrast_ratio']:<6} {r['edge_density']:<7} {r['overlap_risk']:<9} {r['symmetry']:<5} {r['low_contrast_blocks']:<5}")

    # Flagged issues
    print(f"\n  Issues by file:")
    for r in results:
        flags = []
        if r['contrast_ratio'] < 4.5:
            flags.append(f"LOW CONTRAST ({r['contrast_ratio']}:1)")
        if r['overlap_risk'] > 15:
            flags.append(f"OVERLAP ({r['overlap_risk']}%)")
        if r['symmetry'] > 40:
            flags.append(f"ASYMMETRIC ({r['symmetry']})")
        if r['low_contrast_blocks'] > 30 and r['contrast_ratio'] < 4.5:
            flags.append("READABILITY CONCERN")
        if not flags:
            flags.append("✅ OK")
        print(f"    {r['name']}: {', '.join(flags)}")


if __name__ == "__main__":
    main()
```

## Common Issues and Their Signatures

| Issue | Signal | Likely False Positive? |
|-------|--------|------------------------|
| Content overflow | Edge overflow > 50% + high uniformity across all 4 edges | Yes, if top corners differ from bottom corners → decorative header |
| Low text contrast | CR < 4.5 + low-contrast blocks mid-slide, not near edges | No — edges are where margins/decorations live; mid-slide blocks near text areas are real |
| Element overlap | Overlap > 15% | Rare — usually real |
| Poor spacing | Empty horizontal bands > 15% of width on a content slide | Maybe — wide margins are valid design. Check if bands are unevenly distributed |
| Excess asymmetry | Symmetry > 35 on a non-content slide | Cover slides should be under 25 |

## OCR-Enhanced Analysis

For text-specific checks (overlap, vertical alignment, per-character contrast), see the companion reference `references/ocr-enhanced-analysis.md`. This is layered on top of the pixel-level script above — run the pixel script first, then the OCR script for deeper text inspection.
