import sys
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
    def ask_yes_no(self, prompt=None):
        return self.get_user_input(prompt, options=["y", "n"]).lower() == "y"


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

    def get_user_input(self, prompt=None, options=None):
        while True:
            if prompt is not None:
                self.display(f"{prompt} ({'/'.join(options)})")
            user_input = input()
            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")


class VSCodeInterface(MentatInterface):
    # used for all output, streaming or not
    def display(self, content, color=None, end="\n"):
        print(content, end=end, flush=True)

    def get_user_input(self, prompt=None, options=None):
        while True:
            if prompt is not None:
                self.display(f"{prompt} ({'/'.join(options)})")
            self.display('@@user_input')
            user_input = input()
            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")


# --------------------------
# Mentat Run Function
# --------------------------
def run_mentat(interface):
    interface.display("Welcome to Mentat!\nWhat can I do for you?")
    while True:
        # User control: interrupt means quit
        try:
            prompt = interface.get_user_input()
        except KeyboardInterrupt: 
            print('Closing Mentat')
            break
        # Mentat control: interrupt means stop and go back to user input
        try:
            asyncio.run(get_llm_response(interface, prompt))
            # When get_llm_response calls ask_yes_no, it happens inside of this loop,
            # so even though control flow is back to the user, Ctrl-c is caught below.
        except KeyboardInterrupt:
            interface.display("")
            interface.display("Interrupted! Let's try again. What can I do for you?")


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
    if interface.ask_yes_no("Apply these changes?"):
        interface.display("Applying changes")
    else:
        interface.display("Not applying changes")
    interface.display("What else can I do for you?")


# --------------------------
# Set up interface, start Mentat
# --------------------------
if __name__ == "__main__":
    interface_type = "terminal"
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg in ["--interface", "-i"] and i + 1 < len(args):
            if args[i + 1] == "vscode":
                interface_type = "vscode"

    if interface_type == "vscode":
        interface = VSCodeInterface()
    else:
        interface = TerminalMentatInterface()
    run_mentat(interface)
