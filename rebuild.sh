#!/usr/bin/env bash
# Full rebuild: discover → resolve → extract all domains → schema --reset → sync.
# Usage (from ozro-data root, with venv):
#   ./rebuild.sh
# Or:
#   bash rebuild.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 1
fi

run() {
  echo ""
  echo "=== $* ==="
  "$PYTHON" pipeline.py "$@"
}

echo "ozro-data rebuild starting in $ROOT"

run discover
run resolve

# Pre-E5 + core catalogs (README / extractor_deps order)
run extract level_penalty
run extract maps
run extract mobs
run extract items
run extract npcs
run extract map_connections
run extract map_distances
run extract skills
run extract spawns
run extract mobs   # re-run: resolve mob_role from spawns/slaves

run extract shops
run extract npc_scripts
run extract item_scripts
run extract item_restrictions
run extract drops
run extract quests
run extract quest_groups
run extract instances
run extract boxes
run extract recipes
run extract enchantments
run extract item_relationships
run extract random_options
run extract barters
run extract npc_enchants
run extract acquisition
run extract item_dependencies
run extract npc_script_rewards
run extract closure_sanity

run schema --reset
run sync

echo ""
echo "rebuild OK — ozro_* reloaded from reports/"
