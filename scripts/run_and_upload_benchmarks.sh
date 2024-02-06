#!/usr/bin/env bash

TIMESTAMP=$(date +%Y%m%d%H%M%S)

#####################
# JAVASCRIPT EXERCISM
#####################
./benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 2 \
    --max_benchmarks 200 \
    --language javascript

SUMMARY=$(jq '.summary_string' benchmarks/benchmark_repos/exercism-javascript/results.json)
BUCKET="benchmarks.mentat.ai"

# Upload results to S3
aws s3 cp benchmarks/benchmark_repos/exercism-javascript/results.html s3://${BUCKET}/exercism-javascript-results-${TIMESTAMP}.html
aws s3 cp benchmarks/benchmark_repos/exercism-javascript/results.json s3://${BUCKET}/exercism-javascript-results-${TIMESTAMP}.json
aws s3 cp benchmarks/benchmark_repos/exercism-javascript/summary/results.json s3://${BUCKET}/summary/exercism-javascript-results-${TIMESTAMP}.json

# Send slack notification
JAVASCRIPT_RESULTS_URL="http://${BUCKET}/exercism-javascript-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${JAVASCRIPT_RESULTS_URL}\", \"summary\": ${SUMMARY}}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK


#################
# PYTHON EXERCISM
#################
./benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 2 \
    --max_benchmarks 200 \
    --language python

SUMMARY=$(jq '.summary_string' benchmarks/benchmark_repos/exercism-python/results.json)

# Upload results to S3
aws s3 cp benchmarks/benchmark_repos/exercism-python/results.html s3://${BUCKET}/exercism-python-results-${TIMESTAMP}.html
aws s3 cp benchmarks/benchmark_repos/exercism-python/results.json s3://${BUCKET}/exercism-python-results-${TIMESTAMP}.json
aws s3 cp benchmarks/benchmark_repos/exercism-python/summary/results.json s3://${BUCKET}/summary/exercism-python-results-${TIMESTAMP}.json

# Send slack notification
PYTHON_RESULTS_URL="http://${BUCKET}/exercism-python-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${PYTHON_RESULTS_URL}\", \"summary\": ${SUMMARY}}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK


#######################
# REAL WORLD BENCHMARKS
#######################
./benchmarks/benchmark_runner.py --retries 2
SUMMARY=$(jq '.summary_string' results.json)

# Upload results to S3
aws s3 cp results.html s3://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.html
aws s3 cp results.json s3://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.json
aws s3 cp summary/results.json s3://${BUCKET}/summary/real-world-benchmark-results-${TIMESTAMP}.json

# Send slack notification
REAL_WORLD_RESULTS_URL="http://${BUCKET}/real-world-benchmark-results-${TIMESTAMP}.html"
curl -X POST -H "Content-Type: application/json" -d "{\"benchmark_report\": \"${REAL_WORLD_RESULTS_URL}\", \"summary\": ${SUMMARY}}" $SLACK_BENCHMARK_NOTIFICATION_WEBHOOK

###################
# REBUILD DASHBOARD
###################

rm -rf summary
aws s3 cp s3://${BUCKET}/summary/ summary --recursive
./benchmarks/benchmark_result_list.py summary index.html
aws s3 cp index.html s3://${BUCKET}
