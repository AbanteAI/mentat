def pytest_addoption(parser):
    # The following flags are used by benchmark tests
    parser.addoption(
        "--num_exercises",
        action="store",
        default="1",
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
