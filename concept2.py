import asyncio


# --------------------------
# UI Interface (e.g. terminal, vscode)
# --------------------------
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

    # --------------------
    # Methods called by VSCode
    # --------------------

    pass

    # --------------------
    # Methods called by Mentat
    # --------------------

    # used for all output, streaming or not
    def display(self, content, color=None, end="\n"):
        print(content, end=end, flush=True)

    async def get_user_input(self, prompt=None, options=None):
        while True:
            if prompt is not None:
                self.display(f"{prompt} ({'/'.join(options)})")
            user_input = await asyncio.get_event_loop().run_in_executor(None, input)
            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")


class VSCodeInterface(MentatInterface):
    pass


# --------------------------
# Mentat Run Function
# --------------------------
async def run_mentat(interface):
    interface.display("Welcome to Mentat!\nWhat can I do for you?")
    while True:
        prompt = await interface.get_user_input()
        await get_llm_response(interface, prompt)


# --------------------------
# External Methods (e.g.)
# --------------------------
async def get_llm_response(interface, prompt: str):
    # Stream a response:
    # def interrupt_callback():
    #     runner.print("Terminating Async Process")  # e.g. The openai stream

    # stream_handler, done = await runner.initialize_stream(interrupt_callback)
    message = f"Ok, I'll {prompt}.\n"
    for char in message:
        interface.display(char, end="")
        await asyncio.sleep(0.05)
    # await done()

    # Get yes/no confirmation
    if await interface.ask_yes_no("Apply these changes?"):
        interface.display("Applying changes")
    else:
        interface.display("Not applying changes")
    interface.display("What else can I do for you?")


# --------------------------
# Set up interface, start Mentat
# --------------------------
interface = TerminalMentatInterface()
asyncio.run(run_mentat(interface))
