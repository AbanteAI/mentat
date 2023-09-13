def pytest_addoption(parser):
    # To be used by benchmarks for easy testing on subsets.
    parser.addoption(
        "--num_exercises",
        action="store",
        default="200",
        help="Number of exercises to run",
    )
    parser.addoption(
        "--max_iterations",
        action="store",
        default="1",
        help="Number of times to rerun mentat with error messages",
    )
    parser.addoption(
        "--max_workers",
        action="store",
        default="1",
        help="Number of workers to use for multiprocessing",
    )
