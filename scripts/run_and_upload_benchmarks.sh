#!/usr/bin/env bash

TIMESTAMP=$(date +%Y%m%d%H%M%S)

#####################
# JAVASCRIPT EXERCISM
#####################
pytest -s tests/benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 1 \
    --max_benchmarks 200 \
    --language javascript \
    --benchmark

SUMMARY=$(jq '.summary_string' benchmark_repos/exercism-javascript/results.json)

# Upload results to S3
aws s3 cp benchmark_repos/exercism-javascript/results.html s3://abante-benchmark-results/exercism-javascript-results-${TIMESTAMP}.html
aws s3 cp benchmark_repos/exercism-javascript/results.json s3://abante-benchmark-results-json/exercism-javascript-results-${TIMESTAMP}.json

# Send slack notification
JAVASCRIPT_RESULTS_URL="https://abante-benchmark-results.s3.amazonaws.com/exercism-javascript-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${JAVASCRIPT_RESULTS_URL}\", \"summary\": \"${SUMMARY}\"}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK


#################
# PYTHON EXERCISM
#################
pytest -s tests/benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 1 \
    --max_benchmarks 200 \
    --language python \
    --benchmark

SUMMARY=$(jq '.summary_string' benchmark_repos/exercism-python/results.json)

# Upload results to S3
aws s3 cp benchmark_repos/exercism-python/results.html s3://abante-benchmark-results/exercism-python-results-${TIMESTAMP}.html
aws s3 cp benchmark_repos/exercism-python/results.json s3://abante-benchmark-results-json/exercism-python-results-${TIMESTAMP}.json

# Send slack notification
PYTHON_RESULTS_URL="https://abante-benchmark-results.s3.amazonaws.com/exercism-python-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${PYTHON_RESULTS_URL}\", \"summary\": \"${SUMMARY}\"}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK


#######################
# REAL WORLD BENCHMARKS
#######################
pytest tests/benchmarks/benchmark_runner.py --benchmark -s --retries 2
SUMMARY=$(jq '.summary_string' results.json)

# Upload results to S3
aws s3 cp results.html s3://abante-benchmark-results/real-world-benchmark-results-${TIMESTAMP}.html
aws s3 cp results.json s3://abante-benchmark-results-json/real-world-benchmark-results-${TIMESTAMP}.json

# Send slack notification
REAL_WORLD_RESULTS_URL="https://abante-benchmark-results.s3.amazonaws.com/real-world-benchmark-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${REAL_WORLD_RESULTS_URL}\", \"summary\": \"${SUMMARY}\"}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK
