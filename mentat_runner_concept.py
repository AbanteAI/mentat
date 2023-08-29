import asyncio

# --------------------------
# UI Interface (e.g. terminal, vscode)
# --------------------------
class MentatInterface:
    def __init__(self):
        pass

    def register_runner(self, runner):
        self.runner = runner

class TerminalMentatInterface(MentatInterface):
    """Used to communicate with the terminal"""
    _is_streaming = False
    def print(self, content, color=None, stream=False):
        """Render output to the UI"""
        if stream:
            kwargs = {'end': '', 'flush': True}
            self._is_streaming = True
        else:
            kwargs = {}
            if self._is_streaming:
                self._is_streaming = False
                self.print('')
        print(content, **kwargs)

    # This is the 'infinite loop' used to get user input from terminal.
    # VSCode won't need a loop; it will proactively call get_response via 
    # a LanguageServer command.
    async def start(self):
        while True:
            user_input = await asyncio.get_event_loop().run_in_executor(None, input)
            await self.runner.get_response(user_input)

class VSCodeInterface(MentatInterface):
    def __init__(self, print_handler):
        self.print_handler = print_handler

    def print(self, content, *args, **kwargs):
        self.print_handler(content, *args, **kwargs)
        

# --------------------------
# Mentat Instance
# --------------------------
DEFAULT_SLEEP_TIME = 0.1
class MentatRunner:
    def __init__(self, interface):
        self.interface = interface
        self.interface.register_runner(self)
        self.print('Welcome to Mentat!\nWhat can I do for you?')
    
    # --------------------
    # Handle User Input
    # --------------------
    _conversation = []  # Stand-in for Conversation
    _prompt_options = None
    _user_prompt_option = None
    async def get_response(self, prompt):
        if self._prompt_options is not None:
            _prompt = prompt.lower()
            if _prompt not in self._prompt_options:
                echo = self._conversation[-1]
                self.print('Invalid response')
                self.print(echo)
            else:
                self._conversation.append(_prompt)
                self._user_prompt_option = _prompt
        else:
            # Run async commands in the background
            self._conversation.append(prompt)
            asyncio.create_task(get_llm_response(self, prompt))

    _is_streaming = False
    _interrupt_callback = None
    def interrupt(self):
        self.print('Interrupting')
        if self._interrupt_callback is not None:
            self._interrupt_callback()
        self._is_streaming = False  # Intercepted by stream_manager
            
    # --------------------
    # Methods to be used by Mentat funcs
    # --------------------
    _was_streaming = False
    def print(self, content, *args, **kwargs):
        if self._was_streaming and self._is_streaming:
            self._conversation[-1] += content
        else:
            self._conversation.append(content)
            self._was_streaming = self._is_streaming == True
        self.interface.print(content, *args, **kwargs)

    async def ask_yes_no(self, content, *args, **kwargs):
        self.print(f'{content} (y/n)', *args, **kwargs)
        self._prompt_options = {'y', 'n'}
        async def response_watcher():
            while True:
                if self._user_prompt_option is not None:
                    response = self._user_prompt_option
                    self._prompt_options = None
                    self._user_prompt_option = None
                    return response == 'y'
                await asyncio.sleep(DEFAULT_SLEEP_TIME)
        return await asyncio.create_task(response_watcher())
    
    async def initialize_stream(self, interrupt_callback=False):
        self._is_streaming = True
        self._stream_buffer = ''
        self._interrupt_callback = interrupt_callback
        
        # Loop to transfer stream buffer to interface
        async def stream_manager():
            while self._is_streaming:
                if (self._stream_buffer):
                    self.print(self._stream_buffer, stream=True)
                self._stream_buffer = ''
                await asyncio.sleep(DEFAULT_SLEEP_TIME)
            self._stream_buffer = ''
            self._interrupt_callback = None
        asyncio.create_task(stream_manager())
        
        # Send a stream_handler and done callback to the task
        async def stream_handler(content): 
            self._stream_buffer += content
        async def done(): 
            self._is_streaming = False
        return stream_handler, done
    
# --------------------------
# External Methods (e.g.)
# --------------------------
async def get_llm_response(
        runner: MentatRunner, 
        prompt: str,
):
    
    # Stream a response:
    def interrupt_callback():
        runner.print('Terminating Async Process')  # e.g. The openai stream
    stream_handler, done = await runner.initialize_stream(interrupt_callback)
    message = f'Ok, I\'ll {prompt}.'
    for char in message:
        await stream_handler(char)
        await asyncio.sleep(0.05)
    await done()

    # Get yes/no confirmation
    if await runner.ask_yes_no('Apply these changes?'):
        runner.print('Applying changes')
    else:
        runner.print('Not applying changes')
    runner.print('What else can I do for you?')

# --------------------------
# Run the TerminalInterface Loop
# --------------------------
interface = TerminalMentatInterface()
MR = MentatRunner(interface)
asyncio.run(MR.interface.start())