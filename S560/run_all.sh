#!/usr/bin/env bash
# Master script to run both projects' tests and aggregate results
set -e
ROOT_DIR=$(cd "$(dirname "$0")"; pwd -P)
PROJECT_A="$ROOT_DIR/Project_A_PreChange"
PROJECT_B="$ROOT_DIR/Project_B_PostChange"
OUT_DIR="$ROOT_DIR/results"
mkdir -p "$OUT_DIR"

echo "Running Project A tests (PreChange)"
pushd "$PROJECT_A" >/dev/null
./run_tests.sh || { echo "Project A tests failed"; exit 1; }
cp results/results_pre.json "$OUT_DIR/"
cp logs/log_pre.txt "$OUT_DIR/"
popd >/dev/null

echo "Running Project B tests (PostChange)"
pushd "$PROJECT_B" >/dev/null
./run_tests.sh || { echo "Project B tests failed"; exit 1; }
cp results/results_post.json "$OUT_DIR/"
cp logs/log_post.txt "$OUT_DIR/"
popd >/dev/null

python3 "$ROOT_DIR/shared/compare_results.py" "$OUT_DIR/results_pre.json" "$OUT_DIR/results_post.json" "$OUT_DIR/compare_report.md"

echo "All done. Aggregated results are in $OUT_DIR"
