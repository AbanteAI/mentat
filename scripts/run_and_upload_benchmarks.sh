#!/usr/bin/env bash

TIMESTAMP=$(date +%Y%m%d%H%M%S)

#####################
# JAVASCRIPT EXERCISM
#####################
pwd
ls
./benchmarks/exercism_practice.py \
    --max_iterations 2 \
    --max_workers 1 \
    --max_benchmarks 1 \
    --language javascript

pwd
ls
tree
