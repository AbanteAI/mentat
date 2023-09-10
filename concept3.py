import asyncio
import signal
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


class MentatInterrupt(Exception):
    pass


class MentatInterface:
    # should be implemented by subclasses
    def display(self, content, color=None, end="\n"):
        pass

    # should be implemented by subclasses
    async def get_user_input(self, prompt=None, options=None):
        pass

    # convenience function
    async def ask_yes_no(self, prompt=None):
        return (await self.get_user_input(prompt, options=["y", "n"])).lower() == "y"


class TerminalMentatInterface(MentatInterface):
    """Used to communicate with the terminal"""

    def __init__(self):
        self.loop = None
        self.bindings = KeyBindings()
        self.session = PromptSession(key_bindings=self.bindings)

        @self.bindings.add("c-c")
        def _(event):
            print("### control-c caught by binding ###")
            signal_handler()

    def set_loop(self, loop):
        self.loop = loop

    def display(self, content, color=None, end="\n"):
        print(content, end=end, flush=True)
        global sigint
        if sigint:
            sigint = False
            raise MentatInterrupt()

    async def get_user_input(self, prompt=None, options=None):
        while True:
            if prompt is not None:
                self.display(f"{prompt} ({'/'.join(options)})")

            # user_input = await self.session.prompt_async(handle_sigint=False)

            async def check_sigint():
                # run until sigint is set
                while not sigint:
                    await asyncio.sleep(0.1)

            # make into tasks, run both until one returns
            sigint_task = asyncio.create_task(check_sigint())
            user_input_task = asyncio.create_task(self.session.prompt_async())
            done, pending = await asyncio.wait(
                [sigint_task, user_input_task], return_when=asyncio.FIRST_COMPLETED
            )

            # cancel the other task
            for task in pending:
                task.cancel()

            # reset sigint handler
            self.loop.add_signal_handler(signal.SIGINT, signal_handler)

            if user_input_task not in done:
                raise MentatInterrupt()

            user_input = user_input_task.result()

            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")


async def run_mentat(interface):
    try:
        interface.display("Welcome to Mentat!\nWhat can I do for you?")
        while True:
            prompt = await interface.get_user_input()
            await get_llm_response(interface, prompt)
    except MentatInterrupt:
        print("Closing Mentat")


async def get_llm_response(interface, prompt: str):
    message = f"Ok, I'll {prompt}.\n"
    try:
        for char in message:
            interface.display(char, end="")
            await asyncio.sleep(0.05)
    except MentatInterrupt:
        print("\nUser interrupted stream\n")

    # Get yes/no confirmation
    if await interface.ask_yes_no("Apply these changes?"):
        interface.display("Applying changes")
    else:
        interface.display("Not applying changes")
    interface.display("What else can I do for you?")


sigint = False


def signal_handler():
    print("### signal-handler ###")
    global sigint
    sigint = True


class AsyncController:
    def __init__(self, interface):
        self.loop = asyncio.get_event_loop()
        self.loop.add_signal_handler(signal.SIGINT, signal_handler)
        self.interface = interface
        self.interface.set_loop(self.loop)

    def start_mentat(self):
        print("starting!")
        self.loop.run_until_complete(run_mentat(self.interface))
        print("done!")


if __name__ == "__main__":
    interface = TerminalMentatInterface()
    ac = AsyncController(interface)
    ac.start_mentat()
