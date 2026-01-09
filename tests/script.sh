#!/usr/bin/env bash
set -u -o pipefail

# ---------------------------------------------------------------------------
# Usage:
#   tests/script.sh --type <processing|training> --template <name|all> \
#                   [--organization ORG] [--env ENV] [--token TOKEN] \
#                   [--config-dir DIR] [--bump <patch|minor|major|rc|final>] \
#                   [--phase <init|test|smoke|deploy|all>] \
#                   [--report]
# ---------------------------------------------------------------------------

command -v pxl-pipeline >/dev/null || { echo "❌ 'pxl-pipeline' not found in PATH"; exit 1; }

# ----------------------
# Default configuration
# ----------------------
TYPE="processing"                # processing | training
TEMPLATE="all"                   # all | <template_dir_name>
ORGANIZATION="${ORGANIZATION:-test-account}"
ENVIRONMENT="${ENVIRONMENT:-STAGING}"
TOKEN="${PXL_API_TOKEN:-}"       # can also be provided via --token
CONFIG_DIR="${PICSELLIA_CONFIG_DIR:-}"  # can also be provided via --config-dir
BUMP="${PIPELINE_BUMP:-final}"   # patch | minor | major | rc | final
PHASE="all"                      # init | test | smoke | deploy | all
WRITE_REPORT=false

# --------------
# Parse options
# --------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)         TYPE="${2:?--type requires a value}"; shift 2 ;;
    --template)     TEMPLATE="${2:?--template requires a value}"; shift 2 ;;
    --organization) ORGANIZATION="${2:?--organization requires a value}"; shift 2 ;;
    --env)          ENVIRONMENT="${2:?--env requires a value}"; shift 2 ;;
    --token)        TOKEN="${2:?--token requires a value}"; shift 2 ;;
    --config-dir)   CONFIG_DIR="${2:?--config-dir requires a value}"; shift 2 ;;
    --bump)         BUMP="${2:?--bump requires a value}"; shift 2 ;;
    --phase)        PHASE="${2:?--phase requires a value}"; shift 2 ;;
    --report)       WRITE_REPORT=true; shift ;;
    *) echo "Unknown argument: $1"; exit 2 ;;
  esac
done

# Optional: tiny validation on BUMP
case "$BUMP" in
  patch|minor|major|rc|final) ;;
  *) echo "❌ Invalid bump value: '$BUMP' (must be patch|minor|major|rc|final)"; exit 2 ;;
esac

# Validate PHASE
case "$PHASE" in
  init|test|smoke|deploy|all) ;;
  *)
    echo "❌ Invalid phase: '$PHASE' (must be init|test|smoke|deploy|all)"
    exit 2
    ;;
esac

# -----------------------------
# Optional config sandbox (CI)
# -----------------------------
if [[ -n "$CONFIG_DIR" ]]; then
  export PICSELLIA_CONFIG_DIR="$CONFIG_DIR"
  mkdir -p "$PICSELLIA_CONFIG_DIR/picsellia"
fi

# ----------------
# Path resolution
# ----------------
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES_ROOT="$REPO_ROOT/tests/$TYPE"          # tests/<type>/<template>
PIPELINES_DIR="$REPO_ROOT/pipelines"             # workspace for 'pxl-pipeline init'
REPORT_FILE="$REPO_ROOT/ci_cli_commands_report.txt"

mkdir -p "$PIPELINES_DIR"
$WRITE_REPORT && : > "$REPORT_FILE"

# ----------------
# Logging helpers
# ----------------
log_header() {
  echo "🔧 Type:          $TYPE"
  echo "🧪 Tests dir:     $REPO_ROOT/tests"
  echo "📂 Templates dir: $TEMPLATES_ROOT"
  echo "📦 Pipelines dir: $PIPELINES_DIR"
  echo "🎯 Selection:     $TEMPLATE"
  echo "🏢 Organization:  $ORGANIZATION"
  echo "🌍 Environment:   $ENVIRONMENT"
  echo "📌 Version bump:  $BUMP"
  echo "📑 Phase:         $PHASE"
  [[ -n "$CONFIG_DIR" ]] && echo "📁 Config dir:    $PICSELLIA_CONFIG_DIR"
  $WRITE_REPORT && echo "📝 Report file:   $REPORT_FILE"
}

logr() {
  if $WRITE_REPORT; then
    echo -e "$*" | tee -a "$REPORT_FILE"
  else
    echo -e "$*"
  fi
}

log_header

# --------------------
# Non-interactive login
# --------------------
if [[ -n "$TOKEN" ]]; then
  echo "🔐 Performing non-interactive login..."
  if ! pxl-pipeline login --organization "$ORGANIZATION" --env "$ENVIRONMENT" --token "$TOKEN"; then
    echo "❌ Login failed (organization / env / token invalid?)."
    exit 1
  fi
else
  echo "ℹ️  No token provided (neither --token nor PXL_API_TOKEN)."
  echo "    The script assumes a valid token is already configured in:"
  echo "      - ~/.config/picsellia/.env, or"
  echo "      - \$PICSELLIA_CONFIG_DIR/.env (if using --config-dir)."
fi

# --------------------
# Test runner helpers
# --------------------
declare -a RESULTS
ANY_FAILURE=false

run_one_template() {
  local template_name="$1"
  local display="$TYPE/$template_name"
  local template_path="$TEMPLATES_ROOT/$template_name"
  local run_config="$template_path/run_config.toml"
  local ci_config="$template_path/config.toml"   # test-specific config (with docker filled)
  local workdir="$PIPELINES_DIR"

  if [[ ! -d "$template_path" ]]; then
    logr "⚠️  Template not found: $template_path (skip)"
    RESULTS+=("❌ $display (missing template)")
    ANY_FAILURE=true
    return
  fi
  if [[ ! -f "$run_config" ]]; then
    logr "⚠️  run_config.toml not found: $run_config (skip)"
    RESULTS+=("❌ $display (missing run_config.toml)")
    ANY_FAILURE=true
    return
  fi

  logr ""
  logr "─────────────────────────────────────────────"
  logr "Template: $display"
  logr "Folder:   $template_path"
  logr "Config:   $run_config"
  logr "Phase:    $PHASE"
  logr "─────────────────────────────────────────────"
  logr ""

  pushd "$workdir" >/dev/null || {
    logr "❌ Failed to cd into $workdir"
    ANY_FAILURE=true
    RESULTS+=("❌ $display (cd failed)")
    return
  }

  # Helper: ensure that the pipeline workspace exists for non-init phases
  ensure_workspace() {
    if [[ ! -d "$template_name" ]]; then
      logr "❌ Workspace '$workdir/$template_name' not found."
      logr "   Did you run --phase init for this template before running '$PHASE'?"
      RESULTS+=("❌ $display (missing workspace for phase $PHASE)")
      ANY_FAILURE=true
      popd >/dev/null
      return 1
    fi
    return 0
  }

  # ---- Phase: init (or part of 'all') ----
  if [[ "$PHASE" == "init" || "$PHASE" == "all" ]]; then
    # clean workspace for this template
    rm -rf "$template_name"

  # Build init command (training: pass run_config to avoid prompts)
  init_cmd=(pxl-pipeline init "$template_name" --type "$TYPE" --template "$template_name")

  if [[ "$TYPE" == "training" ]]; then
    init_cmd+=(--run-config-file "$run_config")
  fi

  logr "▶️  ${init_cmd[*]}"
  if ! "${init_cmd[@]}"; then
    logr "❌ init failed for $display"
    RESULTS+=("❌ $display (init)")
    ANY_FAILURE=true
    popd >/dev/null
    return
  fi

    # Override config.toml with CI config if present
    if [[ -f "$ci_config" ]]; then
      logr "📄 Overriding config.toml from CI config: $ci_config"
      if ! cp "$ci_config" "$template_name/config.toml"; then
        logr "❌ Failed to copy CI config.toml for $display"
        RESULTS+=("❌ $display (config override)")
        ANY_FAILURE=true
        popd >/dev/null
        return
      fi
    fi

    if [[ "$PHASE" == "init" ]]; then
      logr "✅ $display (init) OK"
      RESULTS+=("✅ $display (init)")
      popd >/dev/null
      return
    fi
  fi

  # For phases other than init/all, ensure workspace exists
  if [[ "$PHASE" != "init" ]]; then
    if ! ensure_workspace; then
      return
    fi
    # On phases test/smoke/all, we can (re)apply CI config just to be safe
    if [[ -f "$ci_config" ]]; then
      logr "📄 Ensuring CI config.toml is applied: $ci_config"
      cp "$ci_config" "$template_name/config.toml" || {
        logr "❌ Failed to copy CI config.toml for $display"
        RESULTS+=("❌ $display (config override)")
        ANY_FAILURE=true
        popd >/dev/null
        return
      }
    fi
  fi

  local phase_label="($PHASE)"

  # ---- Phase: test (or part of 'all') ----
  if [[ "$PHASE" == "test" || "$PHASE" == "all" ]]; then
    logr "▶️  pxl-pipeline test $template_name --run-config-file $run_config"
    if ! pxl-pipeline test "$template_name" --run-config-file "$run_config"; then
      logr "❌ test failed for $display"
      RESULTS+=("❌ $display (test)")
      ANY_FAILURE=true
      popd >/dev/null
      return
    fi
    if [[ "$PHASE" == "test" ]]; then
      logr "✅ $display (test) OK"
      RESULTS+=("✅ $display (test)")
      popd >/dev/null
      return
    fi
  fi

  # ---- Phase: smoke-test (or part of 'all') ----
  if [[ "$PHASE" == "smoke" || "$PHASE" == "all" ]]; then
    logr "▶️  pxl-pipeline smoke-test $template_name --run-config-file $run_config"
    if ! pxl-pipeline smoke-test "$template_name" --run-config-file "$run_config"; then
      logr "❌ smoke-test failed for $display"
      RESULTS+=("❌ $display (smoke-test)")
      ANY_FAILURE=true
      popd >/dev/null
      return
    fi
    if [[ "$PHASE" == "smoke" ]]; then
      logr "✅ $display (smoke) OK"
      RESULTS+=("✅ $display (smoke)")
      popd >/dev/null
      return
    fi
  fi

  # ---- Phase: deploy (or part of 'all') ----
  if [[ "$PHASE" == "deploy" || "$PHASE" == "all" ]]; then
    logr "▶️  pxl-pipeline deploy $template_name --organization $ORGANIZATION --env $ENVIRONMENT --bump $BUMP"
    if ! pxl-pipeline deploy "$template_name" --organization "$ORGANIZATION" --env "$ENVIRONMENT" --bump "$BUMP"; then
      logr "❌ deploy failed for $display"
      RESULTS+=("❌ $display (deploy)")
      ANY_FAILURE=true
      popd >/dev/null
      return
    fi
    if [[ "$PHASE" == "deploy" ]]; then
      logr "✅ $display (deploy) OK"
      RESULTS+=("✅ $display (deploy)")
      popd >/dev/null
      return
    fi
  fi

  # If we reached here, PHASE == all and everything passed
  if [[ "$PHASE" == "all" ]]; then
    logr "✅ $display OK"
    RESULTS+=("✅ $display")
  fi

  popd >/dev/null
}

# ------------------------
# Template selection
# ------------------------
declare -a SELECTED

if [[ "$TEMPLATE" == "all" ]]; then
  if [[ ! -d "$TEMPLATES_ROOT" ]]; then
    echo "❌ Templates directory '$TEMPLATES_ROOT' not found"
    exit 1
  fi
  while IFS= read -r -d '' d; do
    SELECTED+=("$(basename "$d")")
  done < <(find "$TEMPLATES_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
else
  SELECTED+=("$TEMPLATE")
fi

if ((${#SELECTED[@]} == 0)); then
  echo "⚠️  No templates to run."
  exit 0
fi

# ------------------------
# Execution
# ------------------------
for t in "${SELECTED[@]}"; do
  run_one_template "$t"
done

# ------------------------
# Final summary
# ------------------------
logr "\n📊 Final summary:"
if ((${#RESULTS[@]})); then
  for r in "${RESULTS[@]}"; do
    logr "$r"
  done
else
  logr "— no results (empty set) —"
fi

if $ANY_FAILURE; then
  logr "\n❌ At least one template failed."
  exit 1
else
  logr "\n✅ All templates succeeded."
  exit 0
fi
