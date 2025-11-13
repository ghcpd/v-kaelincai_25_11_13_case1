#!/usr/bin/env bash
set -e
ROOT=$(pwd)
START_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Run Project A tests
cd Project_A_PreChange
./run_tests.sh
cd $ROOT
# Run Project B tests
cd Project_B_PostChange
./run_tests.sh
cd $ROOT
# Aggregate results
mkdir -p results
cp Project_A_PreChange/results/results_pre.json results/results_pre.json || true
cp Project_B_PostChange/results/results_post.json results/results_post.json || true
# Generate compare report
python scripts/compare_results.py
END_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# compute duration in seconds
START_EPOCH=$(date -d "$START_TS" +%s)
END_EPOCH=$(date -d "$END_TS" +%s)
DURATION=$((END_EPOCH-START_EPOCH))
cat > results/execution_metadata.json <<EOF
{
  "start": "${START_TS}",
  "end": "${END_TS}",
  "duration_seconds": ${DURATION}
}
EOF
