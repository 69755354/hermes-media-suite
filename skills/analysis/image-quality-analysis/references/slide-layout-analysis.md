# Slide Layout Analysis (Deep Inspection)

## When to Use

After running the basic `programmatic-analysis.md` script, use these deeper techniques when:
- The user specifically asks about **layout** and **spacing** issues (not just contrast/color)
- You need to check **content balance** (top-heavy, left-heavy, bottom-text-overflow)
- You're inspecting **multi-zone slides** (G/Y/R zones, 3-step guides)
- You need **inter-element gap measurement** (spacing consistency between cards/items)
- You're checking **zone color differentiation** (are green/yellow/red zones visually distinct?)
- The basic pass found nothing but the user wants a deeper look

## Dependencies

```bash
pip install Pillow numpy
```

## Technique 1: Content Distribution Grid (4×6)

Maps content density across the slide in a 4-row × 6-column grid using standard deviation per cell. Higher values = more content (text, images, edges).

```python
from PIL import Image, ImageOps
import numpy as np

def content_grid(path):
    gray = np.array(ImageOps.grayscale(Image.open(path)))
    h, w = gray.shape
    cell_h, cell_w = h // 4, w // 6
    grid = np.zeros((4, 6))
    for i in range(4):
        for j in range(6):
            cell = gray[i*cell_h:(i+1)*cell_h, j*cell_w:(j+1)*cell_w]
            grid[i, j] = round(float(cell.std()), 1)
    return grid
```

### Interpretation

| Grid Pattern | What It Means |
|-------------|---------------|
| High values concentrated in top rows (R1-R2) | **Top-heavy** — title + dense content block, possible dead space below |
| High values in top-left (R0-1, C0-2) | **Left-heavy** — content clustered left, empty right side |
| High values uniform across 4-6 columns | **Full-width content** — cards, grids, multi-column layouts |
| Low values in a specific row (< 5) | **Dead space** — possible wasted vertical space |
| Values in R3-C5, R4-C5 near 0 | Bottom-right **empty quadrant** — illustration/text doesn't fill the slide |
| Even distribution across all 24 cells | **Well-balanced layout** |

### Balance Ratios

```python
g = content_grid("slide.jpg")

# Top/Bottom balance (ideal: ~1.0)
top_bot_ratio = float(g[:2].mean()) / max(float(g[2:].mean()), 0.1)
# > 2.5 = top-heavy, < 0.4 = bottom-heavy

# Left/Right balance (ideal: ~1.0)
lr_ratio = float(g[:, :3].mean()) / max(float(g[:, 3:].mean()), 0.1)
# > 2.0 = left-heavy, < 0.5 = right-heavy
```

## Technique 2: Bottom-Edge Text Proximity

Detects content that's too close to the slide bottom edge — a common clipping/overflow issue.

```python
def bottom_proximity(path):
    gray = np.array(ImageOps.grayscale(Image.open(path)))
    h = gray.shape[0]
    
    # Check progressively closer to bottom
    thresholds = [3, 5, 8, 10]  # percent from bottom
    for pct in thresholds:
        strip = gray[int(h*(1-pct/100)):, :]
        if float(strip.std()) > 20:
            return f"Content within {pct}% of bottom (strip std={strip.std():.1f})"
    return "No content within 10% of bottom"
```

**Action thresholds:**
- Within **3%** (~25px on 844px slide) → **HIGH** — text may be cut off in print/projection
- Within **5-8%** → **MEDIUM** — marginal, investigate
- Within **10%** → acceptable

Also check **exact rightmost/leftmost active columns** for precise margin measurement:

```python
col_activity = gray.std(axis=0)
active_cols = np.where(col_activity > 15)[0]
rightmost = active_cols[-1]
leftmost = active_cols[0]
right_margin_pct = (w - rightmost) / w * 100
left_margin_pct = leftmost / w * 100
```

**Action thresholds for margins:**
- Right margin < 2% or left/right margin ratio > 2:1 → **asymmetric margins** — fix
- Left margin 5%, right margin 1.5% → content is crammed against right edge

## Technique 3: Inter-Element Spacing (Gap Measurement)

Measures the gaps between content zones to detect uneven spacing — especially useful for grid layouts, card decks, and multi-item forms.

```python
def measure_gaps(path, std_threshold=12):
    gray = np.array(ImageOps.grayscale(Image.open(path)))
    h = gray.shape[0]
    row_active = gray.std(axis=1) > std_threshold
    
    content_zones = []
    in_content = False
    for y in range(h):
        is_active = row_active[y]
        if is_active and not in_content:
            zone_start = y
            in_content = True
        elif not is_active and in_content:
            content_zones.append((zone_start, y-1, y-zone_start))
            in_content = False
    if in_content:
        content_zones.append((zone_start, h-1, h-zone_start))
    
    gaps = []
    for i in range(len(content_zones) - 1):
        gap = content_zones[i+1][0] - content_zones[i][1] - 1
        gaps.append(gap)
    
    return content_zones, gaps
```

### Interpretation

| Pattern | What It Means |
|---------|---------------|
| 5 items, first gap is 22px, rest are 53-56px | **Inconsistent spacing** — first item too close to second |
| 3 zones, all gaps = 30px | **Perfect spacing** — well-structured |
| Gap sizes vary more than 50% | **Uneven layout** — revise alignment |
| Many tiny gaps (5-13px) between small zones | **Cramped text** — elements are densely packed |

### Zone Height Consistency

For multi-zone slides (e.g., 3 G/Y/R zones), check if all zones are equal height:

```python
heights = [z[2] for z in content_zones[:3]]  # first 3 zones
if max(heights) - min(heights) > h * 0.05:
    print(f"⚠ Uneven zones: {heights} (diff > 5% of slide height)")
```

## Technique 4: Zone Color Differentiation (Multi-Zone Slides)

For slides with colored zone backgrounds (G/Y/R, traffic light), check if the colors are visually distinct enough. Run this on slides like the test interpretation result.

```python
def zone_colors(path, num_zones=3):
    import math
    img = np.array(Image.open(path).convert("RGB"))
    h = img.shape[0]
    zone_h = h // num_zones
    
    for i in range(num_zones):
        zone = img[i*zone_h:(i+1)*zone_h, :, :]
        r, g, b = float(zone[:,:,0].mean()), float(zone[:,:,1].mean()), float(zone[:,:,2].mean())
        
        # Determine dominant channel
        if r > g + 10 and r > b + 10:
            color = "RED"
        elif g > r + 10 and g > b + 10:
            color = "GREEN"
        elif abs(r-g) < 15 and r > 200:
            color = "YELLOW/NEUTRAL"
        else:
            color = "INDISTINCT"
        
        # Compare to expected zone colors
        print(f"  Zone {i+1}: RGB({r:.0f},{g:.0f},{b:.0f}) → {color}")
    
    # Cross-zone differentiation score
    # Compute average RGB distance between adjacent zones
    diffs = []
    for i in range(num_zones - 1):
        z1 = img[i*zone_h:(i+1)*zone_h, :, :].mean(axis=(0,1))
        z2 = img[(i+1)*zone_h:(i+2)*zone_h, :, :].mean(axis=(0,1))
        dist = math.sqrt(sum((a-b)**2 for a,b in zip(z1, z2)))
        diffs.append(dist)
    print(f"  Average zone-to-zone color distance: {np.mean(diffs):.1f}")
    if np.mean(diffs) < 15:
        print(f"  ⚠ Zones are visually very similar — increase saturation/pigment")
```

**Action threshold:** Average inter-zone RGB distance < 15 means zones are nearly indistinguishable. Target > 25 for clear differentiation.

## Technique 5: Margin Uniformity

Checks whether all four slide margins use the same background color — detects decorative header bands, footers, or inconsistent padding.

```python
def margin_check(path):
    img = np.array(Image.open(path).convert("RGB"))
    h, w = img.shape[:2]
    
    margins = {
        "top": tuple(img[0:8, :, :].mean(axis=(0,1)).astype(int).tolist()),
        "bottom": tuple(img[h-8:h, :, :].mean(axis=(0,1)).astype(int).tolist()),
        "left": tuple(img[:, 0:8, :].mean(axis=(0,1)).astype(int).tolist()),
        "right": tuple(img[:, w-8:w, :].mean(axis=(0,1)).astype(int).tolist()),
    }
    
    margin_list = list(margins.values())
    max_diff = max(cd(margin_list[0], m) for m in margin_list)
    return margins, max_diff
```

**Action threshold:** max_diff > 45 means non-uniform margins — typically a decorative header (top differs from white sides/bottom). This is normal for most content slides.

## Technique 6: Content Zone Detection (Boundary Finding)

Precise boundary detection for text blocks, useful when checking whether a title or section has adequate breathing room.

```python
def content_boundaries(path, threshold=12):
    gray = np.array(ImageOps.grayscale(Image.open(path)))
    h, w = gray.shape
    
    # Horizontal row activity
    row_std = gray.std(axis=1)
    active_rows = np.where(row_std > threshold)[0]
    
    # Group into continuous zones
    zones = []
    if len(active_rows) > 0:
        start = active_rows[0]
        for i in range(1, len(active_rows)):
            if active_rows[i] - active_rows[i-1] > 3:  # gap threshold
                zones.append((start, active_rows[i-1]))
                start = active_rows[i]
        zones.append((start, active_rows[-1]))
    
    # Check margins around each zone
    for i, (zs, ze) in enumerate(zones):
        top_gap = zs if i == 0 else zs - zones[i-1][1] - 1
        bot_gap = h - ze - 1 if i == len(zones) - 1 else zones[i+1][0] - ze - 1
        print(f"  Zone {i+1}: y={zs}-{ze} (h={ze-zs+1}px), top_gap={top_gap}px, bot_gap={bot_gap}px")
        if top_gap < 10 or bot_gap < 10:
            print(f"    ⚠ Tight margins ({min(top_gap, bot_gap)}px)")
```

## Combined Inspection Workflow

For a full slide inspection, run these in order:

1. **Content grid** — detect balance issues and dead space
2. **Bottom proximity** — check for overflow at bottom edge
3. **Margin uniformity** — detect header/footer patterns
4. **Content boundaries** — precise zone detection
5. **Inter-element gaps** — spacing consistency
6. **Zone colors** — color differentiation (multi-zone slides only)

## Example: Checking S2-S4 (Opening Sequence)

For a workshop's opening sequence (icebreaker → self-test → interpretation):

```python
for slide_num in [2, 3, 4]:
    path = f"/path/to/slide-{slide_num:02d}.jpg"
    g = content_grid(path)
    print(f"\nSlide {slide_num}:")
    print(f"  Top/bot ratio = {g[:2].mean()/max(g[2:].mean(), 0.1):.1f}")
    print(f"  Left/right ratio = {g[:,:3].mean()/max(g[:,3:].mean(), 0.1):.1f}")
    print(f"  Bottom proximity: {bottom_proximity(path)}")
    zones, gaps = measure_gaps(path)
    if gaps:
        print(f"  Gaps: {gaps}")
        if max(gaps) - min(gaps) > 10:
            print(f"  ⚠ Uneven gaps (range: {min(gaps)}-{max(gaps)}px)")
```

## Common Pitfalls

- **std_threshold tuning**: Different slides need different thresholds. Dark backgrounds with white text need threshold=8-10; light backgrounds with black text need 12-15. Test on one slide first to calibrate.
- **Zone false positives**: Decorative headers, footers, and slide numbers will create small content zones. Filter out zones < 15px height when measuring inter-item spacing.
- **Color differentiation on neutral backgrounds**: When checking zone colors, sample from the zone's colored header/banner area, not the neutral/white text body. For S4-style interpretation zones, the color lives in the top strip of each zone rectangle.
- **Margins with decorative bands**: Top margin often differs from side/bottom margins due to colored header bands. This is normal — compare content slides horizontally, not against the cover slide.
- **Zone detection on complex slides**: Grid layouts with many small elements (card decks, icon grids) will produce many small content zones. Use a higher threshold (15-18) or measure gaps column-by-column instead of row-by-row.
