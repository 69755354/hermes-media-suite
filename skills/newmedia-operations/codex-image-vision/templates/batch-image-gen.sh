#!/bin/bash
# Batch parallel codex image generation template
# Usage: Edit prompts below, then bash batch-image-gen.sh
# Spawns N codex exec processes in parallel (&), waits for all, then lists outputs.
# 6 images typically complete in ~6 min (vs ~25 min sequential)

set -u
OUTDIR="<your_output_dir>"
mkdir -p "$OUTDIR"

# --- Image 1 ---
echo "<prompt_1>
- Save to: ${OUTDIR}/image1.png
- On success output: OUTPUT: ${OUTDIR}/image1.png
- On failure output: BLOCKED: <reason>" \
  | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
    -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow 2>&1 | tail -5 &

# --- Image 2 ---
echo "<prompt_2>
- Save to: ${OUTDIR}/image2.png
- On success output: OUTPUT: ${OUTDIR}/image2.png
- On failure output: BLOCKED: <reason>" \
  | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
    -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow 2>&1 | tail -5 &

# Add more images as needed (copy block, change prompt + output path)...

# --- Wait for all ---
echo "=== All jobs launched, waiting... ==="
wait
echo "=== All jobs done ==="

# --- Verify outputs ---
ls -lh "$OUTDIR"/*.png 2>&1

# --- Batch vision inspection (optional) ---
# Feed all images to codex in one call for structured per-image QC:
# echo "For EACH image, answer: 1) gender correct? 2) layout correct? 3) photorealistic? 4) deformities?" \
#   | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
#     -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow \
#     -i "$OUTDIR/image1.png" -i "$OUTDIR/image2.png" 2>&1 | tail -80
