import importlib.util
import os

import pytest
from git import Repo

from mentat.config import Config
from mentat.python_client.client import PythonClient
from tests.benchmarks.utils import clone_repo


def dynamic_import(path_to_module, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path_to_module)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.benchmark


@pytest.fixture
def retries(request):
    return int(request.config.getoption("--retries"))


@pytest.mark.asyncio
async def test_benchmark(retries):
    print("Running benchmarks")
    benchmarks_dir = f"{os.path.dirname(__file__)}/benchmarks"

    benchmark_paths = []
    for root, dirs, files in os.walk(benchmarks_dir):
        for file in files:
            if file.endswith(".py"):
                benchmark_paths.append(os.path.join(root, file))

    print("Found benchmarks:", " ".join(benchmark_paths))
    results = {}
    for path in benchmark_paths:
        benchmark = dynamic_import(path, "benchmark")
        print("Benchmark:", benchmark.title)
        results[benchmark.title] = {}

        codebase = clone_repo(
            url=benchmark.repo,
            local_dir_name=benchmark.repo.split("/")[-1],
            refresh=False,
        )

        os.chdir(codebase)
        repo = Repo(".")
        start_commit = repo.commit()
        repo.git.checkout(benchmark.commit)

        for prompt in benchmark.prompts:
            print("  Prompt:", prompt)
            for i in range(1, retries + 1):
                client = PythonClient(
                    config=Config(
                        auto_context=True,
                        maximum_context=8000,
                    )
                )

                await client.startup()
                await client.call_mentat_auto_accept(prompt)
                await client.wait_for_edit_completion()
                await client.call_mentat("q")
                await client.shutdown()

                success = benchmark.verify()

                repo.git.reset("--hard")
                repo.git.clean("-fd")
                if success:
                    print("  Passed")
                    results[benchmark.title][prompt] = {
                        "Passed": True,
                        "Attempts": i,
                    }
                    break
                else:
                    if i == retries:
                        print("  Failed")
                        results[benchmark.title][prompt] = {
                            "Passed": False,
                            "Attempts": i,
                        }
                    else:
                        print(f"  Failed on {i}th attempt")

        repo.git.checkout(start_commit)
    print(results)
