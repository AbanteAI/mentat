from termcolor import cprint

from .code_change import CodeChange
from .code_file_manager import CodeFileManager
from .code_context import CodeContext
from .config_manager import ConfigManager, user_config_path
from .llm_api import (
    CostTracker,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from .parsing import run_async_stream_and_parse_llm_response
from .prompts import system_prompt


class Conversation:
    def __init__(
        self,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_file_manager: CodeFileManager,
        code_context: CodeContext,
    ):
        self.messages = list[dict[str, str]]()
        self.add_system_message(system_prompt)
        self.cost_tracker = cost_tracker
        self.code_file_manager = code_file_manager

        self.code_context = code_context
        self.model = config.model()
        if not is_model_available(self.model):
            raise KeyboardInterrupt(
                f"Model {self.model} is not available. Please try again with a"
                " different model."
            )
        if "gpt-4" not in self.model:
            cprint(
                "Warning: Mentat has only been tested on GPT-4. You may experience"
                " issues with quality. This model may not be able to respond in"
                " mentat's edit format.",
                color="yellow",
            )
            if "gpt-3.5" not in self.model:
                cprint(
                    "Warning: Mentat does not know how to calculate costs or context"
                    " size for this model.",
                    color="yellow",
                )

        context_size = model_context_size(self.model)
        maximum_context = config.maximum_context()
        if maximum_context:
            if context_size:
                context_size = min(context_size, maximum_context)
            else:
                context_size = maximum_context

        if not context_size:
            raise KeyboardInterrupt(
                f"Context size for {self.model} is not known. Please set"
                f" maximum-context in {user_config_path}."
            )
        system_tokens = count_tokens(system_prompt, self.model)
        code_context.refresh(max_tokens=context_size - system_tokens - 1000)
        tokens = system_tokens + code_context.root.count_tokens(self.model, recursive=True)
        if tokens + 1000 > context_size:
            cprint(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {context_size}), you may not be able to have a long"
                " conversation.",
                "red",
            )
        else:
            cprint(
                f"File and prompt token count: {tokens} / {context_size}",
                "cyan",
            )

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    def get_model_response(self) -> tuple[str, list[CodeChange]]:
        messages = self.messages.copy()
        code_message = self.code_context.get_code_message()

        messages.append({"role": "system", "content": code_message})

        num_prompt_tokens = get_prompt_token_count(messages, self.model)

        state = run_async_stream_and_parse_llm_response(
            messages, self.model, self.code_file_manager
        )

        self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(state.message, self.model),
            self.model,
            state.time_elapsed,
        )

        self.add_assistant_message(state.message)
        return state.explanation, state.code_changes
