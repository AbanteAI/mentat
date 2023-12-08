import importlib.util
import os

import pytest
from git import Repo

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
async def test_benchmark(retries, benchmarks):
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
        title = benchmark.title

        run = True
        if len(benchmarks) > 0:
            run = False
            for b in benchmarks:
                if b.lower() in title.lower():
                    run = True
                    break
        if not run:
            continue

        print("Benchmark:", title)
        results[title] = {}

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
            results[title][prompt] = {
                "Success": 0,
            }
            for i in range(1, retries + 1):
                client = PythonClient(cwd=codebase, config=benchmark.config)
                await client.startup()
                await client.call_mentat_auto_accept(prompt)
                await client.wait_for_edit_completion()
                await client.call_mentat("q")
                await client.shutdown()

                success = benchmark.verify()

                repo.git.reset("--hard")
                repo.git.clean("-fd")
                if success:
                    results[title][prompt]["Success"] += 1
            print(f"  Succeeded: {results[title][prompt]['Success']}/{retries}")

        repo.git.checkout(start_commit)
    print(results)
