#!/usr/bin/env bash
# scripts/run_test_survey.sh
#
# Package-by-package test survey for ai_tools.
# Runs each package's tests in isolation, captures results, summarizes pass/fail.
#
# Usage:
#   bash scripts/run_test_survey.sh
#
# Output: ./test_survey_results/<package>.log + summary at end
# Exit:   0 if all pass, 1 if any package has failures

set -uo pipefail

# Ensure consistent test environment
export PYTHONDONTWRITEBYTECODE=1

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_DIR="${REPO_ROOT}/test_survey_results"
mkdir -p "${RESULTS_DIR}"

# Order: foundational packages first, dependents later
PACKAGES=(
  "llm_harness_core"
  "llm_engines"
  "engram_lite"
  "rag_lib"
  "llm_inspector"
  "engram"
  "agent_lib"
  "llm_inspector_ui"
  "language_tutor"
)

declare -A RESULTS
declare -A DURATIONS
declare -A COUNTS

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
green()  { color "32" "$1"; }
red()    { color "31" "$1"; }
yellow() { color "33" "$1"; }
blue()   { color "34" "$1"; }

echo "======================================================================"
echo "ai_tools test survey"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Results: ${RESULTS_DIR}/"
echo "======================================================================"
echo

for pkg in "${PACKAGES[@]}"; do
  pkg_dir="${REPO_ROOT}/${pkg}"
  if [ ! -d "${pkg_dir}/tests" ]; then
    echo "$(yellow "SKIP") ${pkg} — no tests/ directory"
    RESULTS[${pkg}]="SKIP"
    continue
  fi

  log="${RESULTS_DIR}/${pkg}.log"
  echo "$(blue "RUN ") ${pkg}"
  start=$(date +%s)

  # Run pytest from inside the package — keeps each test environment isolated
  # -n auto parallelises across all CPU cores (requires pytest-xdist)
  # --tb=short keeps failure output compact
  # -ra prints a summary of skipped/errored at the end
  # --no-cov disables coverage instrumentation overhead
  (
    cd "${pkg_dir}" && \
    python -m pytest tests -n auto -q --tb=short -ra --no-cov 2>&1
  ) > "${log}"
  rc=$?
  end=$(date +%s)
  DURATIONS[${pkg}]=$((end - start))

  # Extract pass/fail/skip counts from pytest's summary line
  summary=$(grep -E "^=+ .* (passed|failed|error|skipped)" "${log}" | tail -1)
  COUNTS[${pkg}]="${summary:-no summary}"

  if [ ${rc} -eq 0 ]; then
    RESULTS[${pkg}]="PASS"
    echo "  $(green "PASS") (${DURATIONS[${pkg}]}s) ${COUNTS[${pkg}]}"
  elif [ ${rc} -eq 5 ]; then
    # exit 5 = no tests collected (common for empty test dirs)
    RESULTS[${pkg}]="EMPTY"
    echo "  $(yellow "EMPTY") no tests collected"
  else
    RESULTS[${pkg}]="FAIL"
    echo "  $(red "FAIL") (${DURATIONS[${pkg}]}s) ${COUNTS[${pkg}]}"
    # Tail the log so failures are visible inline
    echo "  --- last 10 lines of ${pkg}.log ---"
    tail -10 "${log}" | sed 's/^/  | /'
    echo "  ---"
  fi
done

echo
echo "======================================================================"
echo "SUMMARY"
echo "======================================================================"
total_pass=0
total_fail=0
total_skip=0
total_empty=0
for pkg in "${PACKAGES[@]}"; do
  result="${RESULTS[${pkg}]:-UNKNOWN}"
  count="${COUNTS[${pkg}]:-}"
  dur="${DURATIONS[${pkg}]:-0}s"
  case "${result}" in
    PASS)  printf "  %s  %-22s %s  %s\n" "$(green ' PASS')" "${pkg}" "${dur}" "${count}"; ((total_pass++)) ;;
    FAIL)  printf "  %s  %-22s %s  %s\n" "$(red   ' FAIL')" "${pkg}" "${dur}" "${count}"; ((total_fail++)) ;;
    SKIP)  printf "  %s  %-22s\n"           "$(yellow ' SKIP')" "${pkg}"; ((total_skip++)) ;;
    EMPTY) printf "  %s  %-22s\n"           "$(yellow 'EMPTY')" "${pkg}"; ((total_empty++)) ;;
    *)     printf "  %s  %-22s\n"           "?????" "${pkg}" ;;
  esac
done
echo
echo "Totals: ${total_pass} passed, ${total_fail} failed, ${total_empty} empty, ${total_skip} skipped"
echo "Logs:   ${RESULTS_DIR}/"
echo

if [ ${total_fail} -eq 0 ]; then
  echo "$(green "All packages passed.")"
  exit 0
else
  echo "$(red "${total_fail} package(s) had failures — see logs above.")"
  exit 1
fi
