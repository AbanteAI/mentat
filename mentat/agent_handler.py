import shlex
from pathlib import Path
from typing import List

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from mentat.code_feature import CodeMessageLevel
from mentat.llm_api_handler import count_tokens, prompt_tokens
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no, collect_user_input
from mentat.transcripts import ModelMessage

agent_file_selection_prompt_path = Path("agent_file_selection_prompt.txt")
agent_command_prompt_path = Path("agent_command_selection_prompt.txt")


class AgentHandler:
    def __init__(self):
        self._agent_enabled = False

        self.agent_file_message = ""
        self.agent_file_selection_prompt = read_prompt(agent_file_selection_prompt_path)
        self.agent_command_prompt = read_prompt(agent_command_prompt_path)

    # Make this property readonly because we have to set things when we enable agent mode
    @property
    def agent_enabled(self):
        return self._agent_enabled

    def disable_agent_mode(self):
        self._agent_enabled = False

    async def enable_agent_mode(self):
        ctx = SESSION_CONTEXT.get()

        self._agent_enabled = True
        ctx.stream.send(
            "Finding files to determine how to test changes...", color="cyan"
        )
        features = ctx.code_context.get_all_features(CodeMessageLevel.FILE_NAME)
        messages: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system", content=self.agent_file_selection_prompt
            ),
            ChatCompletionSystemMessageParam(
                role="system",
                content="\n".join(
                    str(feature.path.relative_to(ctx.git_root)) for feature in features
                ),
            ),
        ]
        model = ctx.config.model
        response = await ctx.llm_api_handler.call_llm_api(messages, model, False)
        content = response.choices[0].message.content or ""

        paths = [
            Path(path) for path in content.strip().split("\n") if Path(path).exists()
        ]
        self.agent_file_message = ""
        for path in paths:
            file_contents = "\n".join(ctx.code_file_manager.read_file(path))
            self.agent_file_message += f"{path}\n\n\n{file_contents}"

        ctx.stream.send(
            "The model has chosen these files to help it determine how to test its"
            " changes:",
            color="cyan",
        )
        ctx.stream.send("\n".join(str(path) for path in paths))
        ctx.cost_tracker.log_api_call_stats(
            prompt_tokens(messages, model),
            count_tokens(content, model, full_message=False),
            model,
        )

        messages.append(
            ChatCompletionAssistantMessageParam(role="assistant", content=content)
        )
        ctx.conversation.add_transcript_message(
            ModelMessage(message=content, prior_messages=messages, message_type="agent")
        )

    async def _determine_commands(self):
        ctx = SESSION_CONTEXT.get()

        model = ctx.config.model
        messages = ctx.conversation.get_messages() + [
            ChatCompletionSystemMessageParam(
                role="system", content=self.agent_command_prompt
            ),
            ChatCompletionSystemMessageParam(
                role="system", content=self.agent_file_message
            ),
        ]
        max_tokens = None
        if ctx.config.maximum_context:
            max_tokens = (
                ctx.config.maximum_context
                - prompt_tokens(messages, model)
                - ctx.config.token_buffer
            )
        code_message = await ctx.code_context.get_code_message(max_tokens=max_tokens)
        code_message = ChatCompletionSystemMessageParam(
            role="system", content=code_message
        )
        messages = messages[:-1] + [code_message] + messages[-1:]
        # TODO: Should this even be a separate call or should we collect commands in the edit call?
        response = await ctx.llm_api_handler.call_llm_api(messages, model, False)
        content = response.choices[0].message.content or ""
        ctx.cost_tracker.log_api_call_stats(
            prompt_tokens(messages, model),
            count_tokens(content, model, full_message=False),
            model,
        )

        messages.append(
            ChatCompletionAssistantMessageParam(role="assistant", content=content)
        )
        ctx.conversation.add_model_message(content, messages)

        commands = content.strip().split("\n")
        return commands

    async def add_agent_context(self) -> bool:
        """
        Returns whether or not control should be handed back to user
        """
        ctx = SESSION_CONTEXT.get()

        commands = await self._determine_commands()
        if not commands:
            return True
        ctx.stream.send(
            "The model has chosen these commands to test its changes:", color="cyan"
        )
        ctx.stream.send("\n".join(commands for commands in commands))
        ctx.stream.send("Run these commands?", color="cyan")
        run_commands = await ask_yes_no(default_yes=True)
        if not run_commands:
            ctx.stream.send(
                "Enter a new-line separated list of commands to run, or nothing to"
                " return control to the user:",
                color="cyan",
            )
            commands: list[str] = (await collect_user_input()).data.strip().splitlines()
            if not commands:
                return True

        ctx.conversation.add_message(
            ChatCompletionSystemMessageParam(
                role="system",
                content=(
                    "You are currently being run autonomously. The following commands"
                    " are being run to test your previous changes. If the commands show"
                    " any errors with your changes, fix them. In order to return"
                    " control to the user, make no more changes to the files. If you"
                    " don't know how to fix a problem, do not waste time trying to"
                    " solve it! The user would much prefer to regain control if you"
                    " can't solve a problem."
                ),
            )
        )
        for command in commands:
            await ctx.conversation.run_command(shlex.split(command))
        return False
