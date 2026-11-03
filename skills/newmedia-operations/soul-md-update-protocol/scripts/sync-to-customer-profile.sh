#!/bin/bash
# Sync updated skills from main directory to customer profile
# Usage: ./sync-to-customer-profile.sh [skill_name1] [skill_name2] ...
# Without args, syncs all known skills

PROFILE_DIR="/home/ubuntu/.hermes/profiles/customer/skills"
MAIN_DIR="/home/ubuntu/.hermes/skills"

KNOWN_SKILLS=(
  "newmedia-operations/shuziren"
  "newmedia-operations/huoshan"
  "newmedia-operations/soul-md-update-protocol"
  "newmedia-operations/semantic-digital-human-workflow"
)

if [ $# -gt 0 ]; then
  for skill in "$@"; do
    found=false
    for known in "${KNOWN_SKILLS[@]}"; do
      if [[ "$known" == *"$skill"* ]]; then
        cp "$MAIN_DIR/$known/SKILL.md" "$PROFILE_DIR/$known/SKILL.md" 2>/dev/null \
          && echo "✅ $known" || echo "❌ $known"
        found=true
      fi
    done
    if [ "$found" = false ]; then
      cp "$MAIN_DIR/$skill/SKILL.md" "$PROFILE_DIR/$skill/SKILL.md" 2>/dev/null \
        && echo "✅ $skill" || echo "❌ $skill (not found in main dir)"
    fi
  done
else
  for skill in "${KNOWN_SKILLS[@]}"; do
    mkdir -p "$PROFILE_DIR/$(dirname $skill)"
    cp "$MAIN_DIR/$skill/SKILL.md" "$PROFILE_DIR/$skill/SKILL.md" 2>/dev/null \
      && echo "✅ $skill" || echo "❌ $skill"
  done
fi

echo "=== Done ==="
echo "Note: Run DB clear + gateway restart after sync"
