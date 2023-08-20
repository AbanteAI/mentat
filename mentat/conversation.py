from termcolor import cprint

from .code_change import CodeChange
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .config_manager import ConfigManager
from .llm_api import CostTracker, check_model_availability, choose_model, count_tokens
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
        self.messages = []
        self.add_system_message(system_prompt)
        self.cost_tracker = cost_tracker
        self.code_file_manager = code_file_manager
        self.code_map = code_map
        self.allow_32k = check_model_availability(config.allow_32k())

        tokens = count_tokens(code_file_manager.get_code_message()) + count_tokens(
            system_prompt
        )
        token_limit = 32768 if self.allow_32k else 8192
        if tokens > token_limit:
            raise KeyboardInterrupt(
                f"Included files already exceed token limit ({tokens} / {token_limit})."
                " Please try running again with a reduced number of files."
            )
        elif tokens + 1000 > token_limit:
            cprint(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {token_limit}), you may not be able to have a long conversation.",
                "red",
            )
        else:
            cprint(f"File and prompt token count: {tokens} / {token_limit}", "cyan")

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    def get_model_response(self, config: ConfigManager) -> (str, list[CodeChange]):
        messages = self.messages.copy()

        code_message = self.code_file_manager.get_code_message()
        system_message = code_message

        if self.code_map:
            code_map_message = self.code_map.get_message()
            if code_map_message is not None:
                code_map_message_token_count = count_tokens(code_map_message)
                prompt_token_count = 0
                prompt_token_count += count_tokens(code_message)
                for message in messages:
                    prompt_token_count += count_tokens(message["content"])
                token_buffer = 1000
                token_limit = 32768 if self.allow_32k else 8192
                token_count = (
                    prompt_token_count + code_map_message_token_count + token_buffer
                )
                if token_count < token_limit:
                    system_message = "\n".join([code_message, code_map_message])

        messages.append({"role": "system", "content": system_message})

        model, num_prompt_tokens = choose_model(messages, self.allow_32k)

        state = run_async_stream_and_parse_llm_response(
            messages, model, self.code_file_manager
        )

        self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(state.message),
            model,
            state.time_elapsed,
        )

        self.add_assistant_message(state.message)
        return state.explanation, state.code_changes
