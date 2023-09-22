import asyncio
from collections import deque

from ipdb import set_trace
from termcolor import colored

# class StreamingPrinter:
#     def __init__(self):
#         self.strings_to_print = deque([])
#         self.chars_remaining = 0
#         self.shutdown = False
#
#     def add_string(self, string, end="\n", color=None):
#         if len(string) == 0:
#             return
#         string += end
#
#         colored_string = string
#
#         index = colored_string.index(string)
#         characters = list(string)
#         characters[0] = colored_string[:index] + characters[0]
#         characters[-1] = characters[-1] + colored_string[index + len(string) :]
#
#         self.strings_to_print.extend(characters)
#         self.chars_remaining += len(characters)
#
#     def sleep_time(self):
#         max_finish_time = 1.0
#         required_sleep_time = max_finish_time / (self.chars_remaining + 1)
#         max_sleep = 0.002 if self.shutdown else 0.006
#         min_sleep = 0.002
#         return max(min(max_sleep, required_sleep_time), min_sleep)
#
#     async def print_lines(self):
#         session_conversation = get_session_conversation()
#
#         try:
#             while True:
#                 if self.strings_to_print:
#                     next_string = self.strings_to_print.popleft()
#                     if next_string is None:
#                         continue
#                     await session_conversation.send_message(
#                         source="server", data=dict(content=next_string, end="")
#                     )
#                     self.chars_remaining -= 1
#                 elif self.shutdown:
#                     break
#                 await asyncio.sleep(self.sleep_time())
#         except Exception as e:
#             set_trace()
#             raise e
#
#     def wrap_it_up(self):
#         self.shutdown = True




class StreamingPrinter:
    def __init__(self):
        self.strings_to_print = deque[str]([])
        self.chars_remaining = 0
        self.shutdown = False

    def add_string(self, string: str, end: str = "\n", color: str | None = None):
        if len(string) == 0:
            return
        string += end

        colored_string = colored(string, color) if color is not None else string

        index = colored_string.index(string)
        characters = list(string)
        characters[0] = colored_string[:index] + characters[0]
        characters[-1] = characters[-1] + colored_string[index + len(string) :]

        self.strings_to_print.extend(characters)
        self.chars_remaining += len(characters)

    def sleep_time(self) -> float:
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (self.chars_remaining + 1)
        max_sleep = 0.002 if self.shutdown else 0.006
        min_sleep = 0.002
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        while True:
            if self.strings_to_print:
                next_string = self.strings_to_print.popleft()
                print(next_string, end="", flush=True)
                self.chars_remaining -= 1
            elif self.shutdown:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.shutdown = True
