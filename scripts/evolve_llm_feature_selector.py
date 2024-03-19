# ruff: noqa: E501
import argparse
import asyncio
import json
import logging
from pathlib import Path
from textwrap import dedent
from typing import Any

from openai import AsyncOpenAI

from benchmarks.context_benchmark import test_code_context_performance
from mentat.errors import ModelError
from mentat.prompts.prompts import read_prompt

prompts_dir = Path(__file__).parent.parent / "mentat/resources/prompts"


async def evaluate_prompt(prompt: str) -> dict[str, dict[str, float]]:
    """Evaluate feature_selection performance with the given prompt"""
    print("\n" + "-" * 80)
    print(f"Evaluating prompt: {prompt}")
    print("-" * 80 + "\n")
    with open(prompts_dir / "feature_selection_prompt.txt", "w") as f:
        f.write(prompt)
    return await test_code_context_performance([])


# Fitness Function
def recall_weighted_mean(scores: dict[str, dict[str, Any]], weight: int = 3) -> float:
    """Calculate score of prompt based on scores of all features"""
    precision_scores = [s["precision"] for s in scores.values() if s["precision"] is not None]
    recall_scores = [s["recall"] for s in scores.values() if s["recall"] is not None]

    recall_score = sum(recall_scores) / len(recall_scores)  # mean
    precision_mean = sum(precision_scores) / len(precision_scores)
    precision_target = 0.8  # "Add an additional 25% of related context"
    precision_score = 1 - abs(precision_mean - precision_target)
    return (weight * recall_score + precision_score) / (weight + 1)


async def generate_variations(scores: dict[str, dict[str, float]], population: int) -> list[dict[str, str]]:
    """Generate variations of the prompt based on the highest-scoring prompts"""
    system_prompt = dedent(
        """\
        You are part of an automated coding system, specifically the part of that system that selects code which is related to the user's query. \
        The heart of this selection system is a large language model (LLM), like yourself. \
        The system will use statistical methods to generate a select a large sample of code for a given user query; \
        that code, along with the query, is then sent to the LLM, and the LLM should return the lines/files which are relevant to that query. \
        Your job is to help write variations on instructions for the code-selection LLM to maximize its accuracy. \
        Below you will see a list of prompts and scores which have already been evaluated. \
        Use what you see, together with your creativity, to write {population} new prompts that you think will be even better. \
        Feel free to make significant changes to the prompt in your variations - take risks and be creative.
        The goals of the task, as hopefully reflected by the scores below, are: \
          1. To identify areas of code which would be edited, deleted, or added to in response to a user query. \
          2. If an 'Expected Edits' list is provided to the code-selection LLM, it *must* include the lines which are expected to be edited. This is reflected in the scores below as 'Recall'. \
          3. To also identify relevant context to the query, such as the type-definitions of variables which will be edited, or functions which would be directly affected by the edits. \
          4. To NOT select irrelevant files or lines of code. \
          5. It's critical respond to this with a JSON-parsable list of strings (one for each prompt). \
    """
    ).format(population=population)
    scores = [(prompt, recall_weighted_mean(scores[prompt])) for prompt in scores]
    top_scores = sorted(scores, key=lambda x: x[1], reverse=True)[:population]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Scores: {top_scores}"},
    ]
    async_client = AsyncOpenAI()
    response = await async_client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.5,
    )
    response = response.choices[0].message.content
    try:
        prompts = json.loads(response)
        assert isinstance(prompts, list)
        assert all(isinstance(p, str) for p in prompts)
        return prompts[:population]
    except (json.JSONDecodeError, AssertionError):
        logging.error(f"LLM response is not JSON-parsable: {response}")
        raise ModelError(f"LLM response is not JSON-parsable: {response}")


async def evolve_prompt(population: int = 5) -> None:
    """Evolve prompt by a single generation"""

    scores = {}
    scores_path = prompts_dir / "feature_selection_prompt_scores.json"
    if scores_path.exists():
        with open(scores_path, "r") as f:
            scores = json.load(f)

    prompts_to_evaluate = []
    active_prompt = read_prompt(Path("feature_selection_prompt.txt"))
    if active_prompt not in scores:  # First time
        prompts_to_evaluate.append(active_prompt)
    else:
        prompts_to_evaluate = await generate_variations(scores, population)

    for prompt in prompts_to_evaluate:
        score = await evaluate_prompt(prompt)
        scores[prompt] = score
        with open(scores_path, "w") as f:
            json.dump(scores, f)

    best_prompt = max(scores, key=lambda k: recall_weighted_mean(scores[k]))
    with open(prompts_dir / "feature_selection_prompt.txt", "w") as f:
        f.write(str(best_prompt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evolve feature selection prompt based on current benchmarks")
    parser.add_argument(
        "--generations",
        default=10,
        help="The number of generations to evolve",
    )
    parser.add_argument(
        "--population",
        default=5,
        help="The number of prompts to evaluate per generation",
    )
    args = parser.parse_args()
    for i in range(args.generations):
        print(f"Evolving Generation {i}")
        asyncio.run(evolve_prompt(args.population))
