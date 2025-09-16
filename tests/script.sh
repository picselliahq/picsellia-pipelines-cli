#!/usr/bin/env bash
set -euo pipefail

ORGANIZATION="test-account"
ENVIRONMENT="STAGING"

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINES_DIR="$BASE_DIR/pipelines"

mkdir -p "$PIPELINES_DIR"

run_tests_for_type() {
  local TYPE=$1
  local TEMPLATE_FILTER=$2
  local DIR="$BASE_DIR/$TYPE"

  echo "Looking for templates in $DIR"
  for TEMPLATE_PATH in "$DIR"/*; do
    if [ -d "$TEMPLATE_PATH" ]; then
      TEMPLATE=$(basename "$TEMPLATE_PATH")

      if [[ -n "$TEMPLATE_FILTER" && "$TEMPLATE" != "$TEMPLATE_FILTER" ]]; then
        continue
      fi

      RUN_CONFIG="$TEMPLATE_PATH/run_config.toml"

      echo "Testing $TYPE/$TEMPLATE"
      cd "$PIPELINES_DIR"

      # ---- Init ----
      echo "▶️  pxl-pipeline init $TEMPLATE --type $TYPE --template $TEMPLATE"
      pxl-pipeline init "$TEMPLATE" --type "$TYPE" --template "$TEMPLATE"

      # ---- Test ----
      echo "▶️  pxl-pipeline test $TEMPLATE --run-config-file $RUN_CONFIG"
      pxl-pipeline test "$TEMPLATE" --run-config-file "$RUN_CONFIG"

      # ---- Smoke test ----
      echo "▶️  pxl-pipeline smoke-test $TEMPLATE --run-config-file $RUN_CONFIG"
      pxl-pipeline smoke-test "$TEMPLATE" --run-config-file "$RUN_CONFIG"

      # ---- Deploy ----
      echo "▶️  pxl-pipeline deploy $TEMPLATE --organization $ORGANIZATION --env $ENVIRONMENT"
      pxl-pipeline deploy "$TEMPLATE" --organization "$ORGANIZATION" --env "$ENVIRONMENT"

      echo "✅ $TYPE/$TEMPLATE OK"
      echo "──────────────────────────────"
      cd "$BASE_DIR"
    fi
  done
}

# ---- Arguments ----
# $1 = type (processing / training)
# $2 = template optionnel (ex: data_auto_tagging)
TYPE=${1:-"processing"}
TEMPLATE=${2:-""}

run_tests_for_type "$TYPE" "$TEMPLATE"
