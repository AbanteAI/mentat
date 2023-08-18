import json
import subprocess
from collections import defaultdict

from ipdb import set_trace

from .code_file_manager import CodeFileManager


class CodeMap:
    def __init__(self, code_file_manager: CodeFileManager):
        self.code_file_manager = code_file_manager
        self.ctags = defaultdict(set)

    def build(self):
        for file_path in self.code_file_manager.file_paths:
            ctags_cmd = [
                "ctags",
                "--fields=+S",
                "--extras=-F",
                "--input-encoding=utf-8",
                "--output-format=json",
                "--output-encoding=utf-8",
                file_path,
            ]
            output = subprocess.check_output(ctags_cmd, stderr=subprocess.PIPE).decode(
                "utf-8"
            )
            output_lines = output.splitlines()

            for output_line in output_lines:
                try:
                    tag = json.loads(output_line)
                except json.decoder.JSONDecodeError as err:
                    print(f"Error parsing ctags output: {err}")
                    print(repr(output_line))
                    continue

                scope = tag.get("scope")
                kind = tag.get("kind")
                name = tag.get("name")
                signature = tag.get("signature")

                last = name
                if signature:
                    last += " " + signature

                # TODO: get relative filepath
                rel_fname = file_path

                res = [rel_fname]
                if scope:
                    res.append(scope)
                res += [kind, last]

                self.ctags[file_path].add(tuple(res))

    def get_message(self):
        self.build()  # TODO: cache this?

        file_messages = []
        for file, ctags in self.ctags.items():
            sorted_tags = sorted(ctags)

            output = ""
            last = [None] * len(sorted_tags[0])
            tab = "\t"
            for tag in sorted_tags:
                tag = list(tag)

                for i in range(len(last) + 1):
                    if i == len(last):
                        break
                    if last[i] != tag[i]:
                        break

                num_common = i

                indent = tab * num_common
                rest = tag[num_common:]

                for j, item in enumerate(rest):
                    output += indent + item + "\n"
                    indent += tab
                last = tag

            file_messages.append(output)

        message = "\n".join(file_messages)

        return message
