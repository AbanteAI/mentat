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
        self.token_limit = 32768 if self.allow_32k else 8192
        if tokens > self.token_limit:
            raise KeyboardInterrupt(
                f"Included files already exceed token limit ({tokens} /"
                f" {self.token_limit}). Please try running again with a reduced number"
                " of files."
            )
        elif tokens + 1000 > self.token_limit:
            cprint(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {self.token_limit}), you may not be able to have a long"
                " conversation.",
                "red",
            )
        else:
            cprint(
                f"File and prompt token count: {tokens} / {self.token_limit}", "cyan"
            )

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
            system_message_token_count = count_tokens(system_message)
            messages_token_count = 0
            for message in messages:
                messages_token_count += count_tokens(message["content"])
            token_buffer = 1000
            token_count = (
                system_message_token_count + messages_token_count + token_buffer
            )
            max_tokens_for_code_map = self.token_limit - token_count

            if self.code_map.token_limit:
                code_map_message_token_limit = min(
                    self.code_map.token_limit, max_tokens_for_code_map
                )
            else:
                code_map_message_token_limit = max_tokens_for_code_map

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
                    case _:
                        raise Exception(
                            f"Unknown CodeMapMessage level '{code_map_message.level}'"
                        )
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
