#!/usr/bin/env bash

poetry run pytest -s tests/benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 1 \
    --max_benchmarks 4 \
    --language javascript \
    --benchmark

# Upload results to S3
TIMESTAMP=$(date +%Y%m%d%H%M%S)
aws s3 cp benchmark_repos/exercism-javascript/results.html s3://abante-benchmark-results/exercism-javascript-results-${TIMESTAMP}.html

# Send slack notification
RESULTS_URL="https://abante-benchmark-results.s3.amazonaws.com/exercism-javascript-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${RESULTS_URL}\"}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK


