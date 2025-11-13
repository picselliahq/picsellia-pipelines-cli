#!/usr/bin/env bash
set -u -o pipefail

# Usage:
#   tests/script.sh --type <processing|training> --template <name|all> [--organization ORG] [--env ENV] [--report]
# Ex:
#   tests/script.sh --type processing --template all --organization test-account --env STAGING --report
#   tests/script.sh --type processing --template pre_annotation

command -v pxl-pipeline >/dev/null || { echo "❌ pxl-pipeline introuvable dans le PATH"; exit 1; }

# Defaults
TYPE="processing"                # processing | training
TEMPLATE="all"                   # all | <template_dir_name>
ORGANIZATION="${ORGANIZATION:-test-account}"
ENVIRONMENT="${ENVIRONMENT:-STAGING}"
WRITE_REPORT=false

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)         TYPE="${2:?--type requiert une valeur}"; shift 2;;
    --template)     TEMPLATE="${2:?--template requiert une valeur}"; shift 2;;
    --organization) ORGANIZATION="${2:?--organization requiert une valeur}"; shift 2;;
    --env)          ENVIRONMENT="${2:?--env requiert une valeur}"; shift 2;;
    --report)       WRITE_REPORT=true; shift;;
    *) echo "Arg inconnu: $1"; exit 2;;
  esac
done

# Repo root (tests/..)
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# 🔧 IMPORTANT: les templates + run_config.toml sont sous tests/<type>/<template>
TEMPLATES_ROOT="$BASE_DIR/tests/$TYPE"          # ex: <repo>/tests/processing
PIPELINES_DIR="$BASE_DIR/pipelines"             # workspace où on 'init' les pipelines
REPORT_FILE="$BASE_DIR/ci_cli_commands_report.txt"

mkdir -p "$PIPELINES_DIR"
$WRITE_REPORT && : > "$REPORT_FILE"

echo "🔧 Type:          $TYPE"
echo "🧪 Tests dir:     $BASE_DIR/tests"
echo "📂 Templates dir: $TEMPLATES_ROOT"
echo "📦 Pipelines dir: $PIPELINES_DIR"
echo "🎯 Sélection:     $TEMPLATE"
echo "🏢 Organization:  $ORGANIZATION"
echo "🌍 Environnement: $ENVIRONMENT"
$WRITE_REPORT && echo "📝 Rapport:       $REPORT_FILE"

declare -a RESULTS
ANY_FAILURE=false

logr() {
  if $WRITE_REPORT; then
    echo -e "$*" | tee -a "$REPORT_FILE"
  else
    echo -e "$*"
  fi
}

run_one_template() {
  local template_name="$1"
  local display="$TYPE/$template_name"
  local template_path="$TEMPLATES_ROOT/$template_name"
  local run_config="$template_path/run_config.toml"
  local workdir="$PIPELINES_DIR"

  if [[ ! -d "$template_path" ]]; then
    logr "⚠️  Template introuvable: $template_path (skip)"
    RESULTS+=("❌ $display (missing template)")
    ANY_FAILURE=true
    return
  fi
  if [[ ! -f "$run_config" ]]; then
    logr "⚠️  Fichier run_config.toml introuvable: $run_config (skip)"
    RESULTS+=("❌ $display (missing run_config.toml)")
    ANY_FAILURE=true
    return
  fi

  logr ""
  logr "─────────────────────────────────────────────"
  logr "Template: $display"
  logr "Folder:   $template_path"
  logr "Config:   $run_config"
  logr "─────────────────────────────────────────────"
  logr ""

  pushd "$workdir" >/dev/null || { logr "❌ cd $workdir impossible"; ANY_FAILURE=true; RESULTS+=("❌ $display (cd failed)"); return; }

  rm -rf "$template_name"

  # ---- Init ----
  logr "▶️  pxl-pipeline init $template_name --type $TYPE --template $template_name"
  if ! pxl-pipeline init "$template_name" --type "$TYPE" --template "$template_name"; then
    logr "❌ init failed for $display"
    RESULTS+=("❌ $display (init)")
    ANY_FAILURE=true
    popd >/dev/null
    return
  fi

  # ---- Test ----
  logr "▶️  pxl-pipeline test $template_name --run-config-file $run_config"
  if ! pxl-pipeline test "$template_name" --run-config-file "$run_config"; then
    logr "❌ test failed for $display"
    RESULTS+=("❌ $display (test)")
    ANY_FAILURE=true
    popd >/dev/null
    return
  fi

  # ---- Smoke test ----
  logr "▶️  pxl-pipeline smoke-test $template_name --run-config-file $run_config"
  if ! pxl-pipeline smoke-test "$template_name" --run-config-file "$run_config"; then
    logr "❌ smoke-test failed for $display"
    RESULTS+=("❌ $display (smoke-test)")
    ANY_FAILURE=true
    popd >/dev/null
    return
  fi

  # ---- Deploy ----
  logr "▶️  pxl-pipeline deploy $template_name --organization $ORGANIZATION --env $ENVIRONMENT"
  if ! pxl-pipeline deploy "$template_name" --organization "$ORGANIZATION" --env "$ENVIRONMENT"; then
    logr "❌ deploy failed for $display"
    RESULTS+=("❌ $display (deploy)")
    ANY_FAILURE=true
    popd >/dev/null
    return
  fi

  logr "✅ $display OK"
  RESULTS+=("✅ $display")
  popd >/dev/null
}

# Sélection des templates
declare -a SELECTED
if [[ "$TEMPLATE" == "all" ]]; then
  if [[ ! -d "$TEMPLATES_ROOT" ]]; then
    echo "❌ Répertoire templates '$TEMPLATES_ROOT' introuvable"
    exit 1
  fi
  while IFS= read -r -d '' d; do
    SELECTED+=("$(basename "$d")")
  done < <(find "$TEMPLATES_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
else
  SELECTED+=("$TEMPLATE")
fi

if ((${#SELECTED[@]}==0)); then
  echo "⚠️  Aucun template à exécuter."
  exit 0
fi

# Exécution
for t in "${SELECTED[@]}"; do
  run_one_template "$t"
done

# Résumé
logr "\n📊 Final summary:"
if ((${#RESULTS[@]})); then
  for r in "${RESULTS[@]}"; do logr "$r"; done
else
  logr "— aucun résultat (tableau vide) —"
fi

if $ANY_FAILURE; then
  logr "\n❌ Au moins un template a échoué."
  exit 1
else
  logr "\n✅ Tous les templates ont réussi."
  exit 0
fi
