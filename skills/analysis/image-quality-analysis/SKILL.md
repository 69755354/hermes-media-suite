---
name: image-quality-analysis
description: "Programmatic visual inspection of rendered images (slides, screenshots, UI mockups, diagrams) using Pillow + NumPy when vision APIs are unavailable. Covers contrast, margins, overlap, symmetry, edge density, empty space, and color analysis."
license: Proprietary. LICENSE.txt has complete terms
---

# Image Quality Analysis

Programmatic fallback for visual inspection when `vision_analyze` or the model's native vision capability is unavailable.

## When to Use

- `vision_analyze` returned an error (model doesn't support images, API refused)
- You have rendered JPEG/PNG images of slides, UI screenshots, diagrams, or mockups
- You need objective pixel-level measurements (contrast ratios, margin widths, overlap detection)
- The model is text-only and cannot process images directly

## Dependencies

```bash
pip install Pillow numpy    # or use --system-site-packages venv
```

## What It Checks

| Check | What It Detects | Pitfall |
|-------|----------------|---------|
| **Edge uniformity** | Non-uniform margins (content too close to edge) | Decorative headers cause false positives — check corner colors |
| **Edge overflow** | Content bleeding into the 5px outer zone | Headers/borders that intentionally extend to edges |
| **Contrast ratio** | WCAG contrast (SSR) per block and overall | Low-contrast decorative elements (not text) will still flag |
| **Low-contrast blocks** | Areas where contrast drops below 3:1 | Often decorative gradients on dark/colored backgrounds |
| **Edge density** | % of pixels with high gradient (text/element presence) | Measure of how content-dense the slide is |
| **Overlap risk** | % of very-high-gradient pixels (potential element stacking) | Truly overlapping elements produce very high local gradient |
| **Empty horizontal bands** | Large spans of empty columns (>12% width) | Can indicate alignment or spacing issues |
| **Symmetry** | Left-right pixel difference | Cover slides should be symmetric; content slides naturally asymmetric |
| **Dominant colors** | Top 3 quantized colors | Quick check of whether palette matches expectations |
| **OCR text overlap** | pytesseract bounding-box overlap detection | CJK characters naturally overlap in segmentations — filter with area > 100px² threshold |
| **OCR vertical alignment** | y-position range within text rows (target ≤ 5px) | OCR may mis-group multi-line entries; verify row assignment |
| **Margin content bleed** | Bright/dark pixels near slide border differing from background | Only flag if bleed percentage > 10% and not a deliberate design element |
| **Precise WCAG contrast** | Per-character text-to-background contrast using WCAG 2.1 relative luminance formula | OCR sampling on anti-aliased text borders can undercount; use mid-character region for accurate foreground reading |

## Workflow

### 1. Render images to analyze

For PPT slides:
```bash
python scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 150 output.pdf slide
```

### 2. Run the analysis script

Save the script from `references/programmatic-analysis.md` and run:
```bash
python inspect_slides.py
```

### 3. Interpret results

Reference table:

| Metric | Good | Investigate | Bad |
|--------|------|-------------|-----|
| Contrast ratio | ≥ 7:1 (AAA) | 4.5–7:1 (AA) | < 4.5:1 |
| Edge overflow | < 15% | 15–50% (may be decorative header) | > 50% |
| Overlap risk | < 5% | 5–15% | > 15% |
| Symmetry (content) | < 20 | 20–35 | > 35 |
| Symmetry (cover) | < 25 | 25–40 | > 40 |
| Low-contrast blocks | < 10 | 10–30 (likely decoration) | > 30 |

### 4. Fix and re-verify

Make changes to the source (PPTX, HTML, etc.), re-render images, and re-run the script until critical metrics pass.

## Common False Positive Patterns

1. **Decorative headers** — Top edge variance > 30 but bottom/left/right are clean. Check if top-corner color differs from bottom-corner color. If yes → intentional design.
2. **Gradient backgrounds** — Low-contrast blocks clustered in transition zones of a gradient. Check coordinates — blocks that form a line across the slide are gradient artifacts.
3. **Dark cover slides** — Will always produce many low-contrast blocks (dark-on-dark decorative elements). Check overall CR instead — if it's ≥ 7:1, body text is readable.
4. **Symmetry on content slides** — Two-column layouts, icon grids, and text-heavy slides are naturally asymmetric. Compare symmetry scores across similar slide types only.

## Slide Layout Analysis (Deep Inspection)

For **slide-specific layout analysis** — content balance (top-heavy, left-heavy), inter-element spacing consistency, bottom-edge text proximity, zone color differentiation, and margin uniformity — use `references/slide-layout-analysis.md`.

Run the basic pixel-level script from `references/programmatic-analysis.md` first (covers contrast, edge overflow, symmetry, overlap). If the basic pass is inconclusive, or the user specifically asked about spacing/balance/overflow, run the deeper slide-layout techniques from the new reference.

## Fallback Chain for Image Inspection

When a user asks for slide/image visual QA, follow this priority order:

1. **vision_analyze** (fastest) — works when the active model supports image inputs
2. **browser_navigate + browser_vision** — works when vision_analyze fails but the browser backend is available. Serve images via a local HTTP server (`python3 -m http.server <port>`), then navigate to `http://localhost:<port>/image.jpg` and use `browser_vision()`. **Caveat:** Browser may block localhost addresses; test with curl first.
3. **Programmatic Pillow + pytesseract** (this skill) — works everywhere regardless of model or browser access. See `references/programmatic-analysis.md` for the core pixel-level script and `references/ocr-enhanced-analysis.md` for the full OCR-based overlap/misalignment/contrast pipeline.

## OCR-Enhanced Analysis (pytesseract)

When pixel-level analysis gives ambiguous results, layer on OCR for text-specific checks:

```python
import pytesseract
data = pytesseract.image_to_data(img, lang='chi_sim+eng', output_type=pytesseract.Output.DICT)
```

### Text Overlap Detection

Compare bounding boxes of all detected text blocks. Overlap area = width_of_overlap × height_of_overlap. Flag when area > 100 px².

**Critical pitfall for CJK text:** pytesseract segments Chinese text character-by-character. Adjacent characters in the same word naturally have overlapping bounding boxes (typically 1–15 px²). Use an area threshold of **100 px²** to filter these out from real overlaps.

### Vertical Alignment Check

Group text blocks by y-position (30px bands). Within each band, check the y-range (min y to max y). Flag if > 10px — indicates characters in the same logical line are vertically misaligned.

### Per-Character Contrast Verification

Extract the text block's pixel region and its immediate background (5px border around the block). Compute WCAG contrast ratio between foreground and background. Flag if ratio < 2.0 (unreadable). Note that anti-aliased text at block borders can produce misleadingly low contrast — sample from the character's interior, not its edge.

### Content Bleed (Margin Check)

Sample pixels along each 30px margin. For dark-background slides, bright pixels in the margin signal content bleed. For light-background slides, dark pixels signal bleed. Cross-reference which edge(s) are affected to distinguish intentional header/footer from genuine overflow.

## When to Use This vs. Visual Inspection

| Situation | Use |
|-----------|-----|
| Vision API available + model supports images | `vision_analyze` or subagent |
| Model is text-only | Programmatic script |
| Need precise pixel measurements | Programmatic script |
| Need subjective design judgment | Visual inspection |
| Text overlap/overflow suspected | Programmatic + OCR layer |
