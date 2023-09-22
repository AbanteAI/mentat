import logging

from mentat.session_stream import get_session_stream

from .code_change import CodeChange, CodeChangeAction
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .config_manager import ConfigManager
from .errors import MentatError
from .llm_api import CostTracker, check_model_availability, choose_model, count_tokens
from .parsing import run_stream_and_parse_llm_response
from .prompts import system_prompt

logger = logging.getLogger()


class LLMConversation:
    def __init__(
        self,
        allow_32k: bool,
        cost_tracker: CostTracker,
        code_file_manager: CodeFileManager,
        code_map: CodeMap | None = None,
    ):
        self.allow_32k = allow_32k
        self.cost_tracker = cost_tracker
        self.code_file_manager = code_file_manager
        self.code_map = code_map

        self.token_limit = 32768 if self.allow_32k else 8192
        self.messages = []
        self.add_system_message(system_prompt)

    @classmethod
    async def create(
        cls,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_file_manager: CodeFileManager,
        code_map: CodeMap | None = None,
    ):
        stream = get_session_stream()

        allow_32k = await check_model_availability(config.allow_32k())

        conv = cls(
            allow_32k,
            cost_tracker,
            code_file_manager,
            code_map,
        )

        tokens = count_tokens(conv.code_file_manager.get_code_message()) + count_tokens(
            system_prompt
        )
        conv.token_limit = 32768 if conv.allow_32k else 8192
        if tokens > conv.token_limit:
            raise MentatError(
                f"Included files already exceed token limit ({tokens} /"
                f" {conv.token_limit}). Please try running again with a reduced number"
                " of files."
            )
        elif tokens + 1000 > conv.token_limit:
            await stream.send(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {conv.token_limit}), you may not be able to have a long"
                " conversation.",
                color="red",
            )
        else:
            await stream.send(
                f"File and prompt token count: {tokens} / {conv.token_limit}",
                color="cyan",
            )

        return conv

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    async def get_model_response(self) -> (str, list[CodeChange]):
        stream = get_session_stream()

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

            code_map_message = await self.code_map.get_message(
                token_limit=code_map_message_token_limit
            )
            if code_map_message:
                match (code_map_message.level):
                    case "signatures":
                        cmap_message_level = "full syntax tree"
                    case "no_signatures":
                        cmap_message_level = "partial syntax tree"
                    case "filenames":
                        cmap_message_level = "filepaths only"
                    case _:
                        raise Exception(
                            f"Unknown CodeMapMessage level '{code_map_message.level}'"
                        )
                await stream.send(
                    f"Including CodeMap ({cmap_message_level})",
                    color="green",
                )
                system_message += f"\n{code_map_message}"
            else:
                await stream.send(
                    "Excluding CodeMap from system message. Reason:",
                    color="yellow",
                )
                await stream.send(
                    "Not enough tokens available in model context.",
                    color="yellow",
                )

        messages.append({"role": "system", "content": system_message})

        model, num_prompt_tokens = await choose_model(messages, self.allow_32k)

        state = await run_stream_and_parse_llm_response(
            messages, model, self.code_file_manager
        )

        await self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(state.message),
            model,
            state.time_elapsed,
        )

        self.add_assistant_message(state.message)
        return state.explanation, state.code_changes
