# Benchmarks

In this directory we write benchmarks for Mentat's performance on different tasks.

## Running Exercism Benchmarks

```
./benchmarks/exercism_practice.py
```

Flags that control the performance of the benchmarks are defined [here](arg_parser.py) and set conservatively so benchmarks without flags will run relatively quickly and cheaply. To run the exercism benchmark with multiple workers on all the tests with one retry for the clojure language run the following:
```
./benchmarks/exercism_practice.py  --max_benchmarks 134 --max_iterations 2 --max_workers 2 --language clojure
```

Warning: If you increase `max_workers` much higher you'll start to get rate limited.

## Running Real World Benchmarks

```
./benchmarks/benchmark_runner.py
```

## Making Real World Benchmarks

Real world benchmarks can either be [samples](benchmarks/mentat/sample_15223222005645d08b81f093e51d52fe.json) or [python files](benchmarks/mentat/).
