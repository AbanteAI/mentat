import os
from timeit import default_timer as timer

import fire
import openai
import tiktoken
from dotenv import load_dotenv


def get_tokens_from_message(message: str) -> int:
    return len(tiktoken.encoding_for_model("gpt-4").encode(message))


# Set up the OpenAI API
load_dotenv("mentat/.env")
openai.api_key = os.getenv("OPENAI_API_KEY")


def run(prompt, model: str = "gpt-4-0314") -> str:
    messages = [
        {"role": "system", "content": "be a helpful assistant"},
        {"role": "user", "content": prompt},
    ]

    start = timer()
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.5,
        stream=True,
    )

    started = False
    message = []
    for chunk in response:
        if not started:
            time_to_first_token = timer() - start
            started = True
        delta = chunk.choices[0].delta
        content = delta.get("content", None)
        if content is not None:
            message.append(content)
            print(content, end="", flush=True)
    time_to_last_token = timer() - start
    message = "".join(message)
    token_count = get_tokens_from_message(message)

    print("\n")
    print(f"Token count: {token_count}")
    print(f"Time to first token: {time_to_first_token}")
    print(f"Tokens/second: {token_count / time_to_last_token}")
    print(f"Time to last token: {time_to_last_token}")


if __name__ == "__main__":
    fire.Fire(run)
