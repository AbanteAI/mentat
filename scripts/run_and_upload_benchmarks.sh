#!/usr/bin/env bash

TIMESTAMP=$(date +%Y%m%d%H%M%S)

#######################
# REAL WORLD BENCHMARKS
#######################
./benchmarks/benchmark_runner.py --retries 2
SUMMARY=$(jq '.summary_string' results.json)

# Upload results to S3
aws s3 cp results.html s3://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.html
aws s3 cp results.json s3://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.json

# Send slack notification
REAL_WORLD_RESULTS_URL="http://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${REAL_WORLD_RESULTS_URL}\", \"summary\": ${SUMMARY}}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK
