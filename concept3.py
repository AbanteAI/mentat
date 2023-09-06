import sys
from prompt_toolkit import PromptSession
import signal
import asyncio


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
        self.session = PromptSession()

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

            user_input =  await self.session.prompt_async()

            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")


async def run_mentat(interface):
    for i in range(5):
        print(i)
        await asyncio.sleep(1)

    try:
        interface.display("Welcome to Mentat!\nWhat can I do for you?")
        while True:
            prompt = await interface.get_user_input()
            await get_llm_response(interface, prompt)
    except MentatInterrupt:
        print('Closing Mentat')

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
    print("### SIGINT ###")
    global sigint
    sigint = True

class AsyncController:

    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.loop.add_signal_handler(signal.SIGINT, signal_handler)

    def start_mentat_with_interface(self, interface):
        print("starting!")
        self.loop.run_until_complete(run_mentat(interface))
        print("done!")


if __name__ == "__main__":
    ac = AsyncController()

    interface = TerminalMentatInterface()
    ac.start_mentat_with_interface(interface)



