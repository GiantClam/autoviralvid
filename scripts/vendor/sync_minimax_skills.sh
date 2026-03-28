#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor/minimax-skills"
PINNED_SHA="${MINIMAX_SKILLS_REF:-34c6cf05d7a2b68076bafa00e6f360bc9506bba6}"
UPSTREAM_REPO="${MINIMAX_SKILLS_REPO:-https://github.com/MiniMax-AI/skills.git}"
LOCAL_MIRROR="$ROOT_DIR/.tmp_minimax_skills_ref_20260327"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/minimax-skills.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[sync_minimax_skills] pinned commit: $PINNED_SHA"

if [[ -d "$LOCAL_MIRROR/.git" ]]; then
  echo "[sync_minimax_skills] using local mirror: $LOCAL_MIRROR"
  git clone --quiet --no-checkout "$LOCAL_MIRROR" "$TMP_DIR/repo"
else
  echo "[sync_minimax_skills] cloning upstream: $UPSTREAM_REPO"
  git clone --quiet --filter=blob:none --no-checkout "$UPSTREAM_REPO" "$TMP_DIR/repo"
fi

git -C "$TMP_DIR/repo" checkout --quiet "$PINNED_SHA"

rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR/plugins" "$VENDOR_DIR/skills"
cp -R "$TMP_DIR/repo/plugins/pptx-plugin" "$VENDOR_DIR/plugins/"
cp -R "$TMP_DIR/repo/skills/pptx-generator" "$VENDOR_DIR/skills/"
printf "%s\n" "$PINNED_SHA" > "$VENDOR_DIR/PINNED_COMMIT"

cat > "$VENDOR_DIR/README.md" <<EOF
# Vendored MiniMax PPTX Skills

This directory is a pinned vendor snapshot copied from \`$UPSTREAM_REPO\`.

- Commit: \`$PINNED_SHA\`
- Paths:
  - \`plugins/pptx-plugin\`
  - \`skills/pptx-generator\`

Refresh with:

\`\`\`bash
bash scripts/vendor/sync_minimax_skills.sh
\`\`\`
EOF

echo "[sync_minimax_skills] synced into $VENDOR_DIR"
