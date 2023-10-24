# Benchmarks

In this directory we write benchmarks for Mentat's performance on different tasks.

## Running Benchmarks

Benchmarks are run with pytest e.g.
```
pytest -s tests/benchmarks/exercism_practice.py --benchmark
```
Note you need the `-s` to see the printed results and `--benchmark` is necessary for tests that actually call gpt.

They should not start with `test_` or end with `_test.py` so they will not be automatically collected and ran by pytest.

Flags that control the performance of the benchmarks are defined in [conftest](/conftest.py) and set conservatively so benchmarks without flags will run relatively quickly and cheaply. To run the exercism benchmark with multiple workers on all the tests with one retry for the clojure language run the following:
```
pytest -s tests/benchmarks/exercism_practice.py --benchmark --max_benchmarks 134 --max_iterations 2 --max_workers 2 --language clojure --benchmark
```

Warning: If you increase max_workers much higher you'll start to get rate limited.
