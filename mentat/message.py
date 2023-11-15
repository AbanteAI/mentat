import base64
import json
from enum import Enum
from pathlib import Path
from typing import Any

import attr


class MessageRole(Enum):
    System = "system"
    User = "user"
    Assistant = "assistant"


@attr.define
class Message:
    role: MessageRole = attr.field()
    text: str = attr.field()
    image_path: Path | None = attr.field(default=None)

    def llm_view(self, use_path: bool = False) -> dict[str, Any]:
        "Returns the message as it should be put into the LLM API"
        if self.image_path:
            if use_path:
                image_data = self.image_path  # For logging
            else:
                with open(self.image_path, "rb") as image_file:
                    decoded = base64.b64encode(image_file.read()).decode("utf-8")
                    image_data = f"data:image/png;base64,{decoded}"
            return {
                "role": self.role.value,
                "content": [
                    {
                        "type": "text",
                        "text": self.text,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data,
                        },
                    },
                ],
            }
        else:
            return {"role": self.role.value, "content": self.text}

    def __str__(self) -> str:
        return json.dumps(
            self.llm_view(use_path=True),
            default=str,
        )
