from termcolor import cprint

from .code_change import CodeChange
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .config_manager import ConfigManager
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
        code_map: CodeMap | None = None,
    ):
        self.messages = list[dict[str, str]]()
        self.add_system_message(system_prompt)
        self.cost_tracker = cost_tracker
        self.code_file_manager = code_file_manager
        self.code_map = code_map
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

        tokens = count_tokens(
            code_file_manager.get_code_message(), self.model
        ) + count_tokens(system_prompt, self.model)

        self.context_size = model_context_size(self.model)
        maximum_context = config.maximum_context()
        if maximum_context:
            if self.context_size:
                self.context_size = min(self.context_size, maximum_context)
            else:
                self.context_size = maximum_context
        if self.context_size:
            if self.context_size and tokens > self.context_size:
                raise KeyboardInterrupt(
                    f"Included files already exceed token limit ({tokens} /"
                    f" {self.context_size}). Please try running again with a reduced"
                    " number of files."
                )
            elif tokens + 1000 > self.context_size:
                cprint(
                    f"Warning: Included files are close to token limit ({tokens} /"
                    f" {self.context_size}), you may not be able to have a long"
                    " conversation.",
                    "red",
                )
            else:
                cprint(
                    f"File and prompt token count: {tokens} / {self.context_size}",
                    "cyan",
                )

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    def get_model_response(self, config: ConfigManager) -> tuple[str, list[CodeChange]]:
        messages = self.messages.copy()

        code_message = self.code_file_manager.get_code_message()
        system_message = code_message

        if self.code_map:
            system_message_token_count = count_tokens(system_message, self.model)
            messages_token_count = 0
            for message in messages:
                messages_token_count += count_tokens(message["content"], self.model)
            token_buffer = 1000
            token_count = (
                system_message_token_count + messages_token_count + token_buffer
            )

            if self.context_size:
                max_tokens_for_code_map = self.context_size - token_count
                if self.code_map.token_limit:
                    code_map_message_token_limit = min(
                        self.code_map.token_limit, max_tokens_for_code_map
                    )
                else:
                    code_map_message_token_limit = max_tokens_for_code_map
            else:
                code_map_message_token_limit = self.code_map.token_limit

            code_map_message = self.code_map.get_message(
                token_limit=code_map_message_token_limit
            )
            if code_map_message:
                match (code_map_message.level):
                    case "signatures":
                        cprint_message_level = "full syntax tree"
                    case "no_signatures":
                        cprint_message_level = "partial syntax tree"
                    case "filenames":
                        cprint_message_level = "filepaths only"

                cprint_message = f"\nIncluding CodeMap ({cprint_message_level})"
                cprint(cprint_message, color="green")
                system_message += f"\n{code_map_message}"
            else:
                cprint_message = [
                    "\nExcluding CodeMap from system message.",
                    "Reason: not enough tokens available in model context.",
                ]
                cprint_message = "\n".join(cprint_message)
                cprint(cprint_message, color="yellow")

        messages.append({"role": "system", "content": system_message})

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
