#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor/minimax-skills"

test -f "$VENDOR_DIR/plugins/pptx-plugin/README.md"
test -f "$VENDOR_DIR/skills/pptx-generator/SKILL.md"
test -f "$VENDOR_DIR/PINNED_COMMIT"

grep -Eq "^[0-9a-f]{40}$" "$VENDOR_DIR/PINNED_COMMIT"
echo "vendor snapshot is present and pinned"
