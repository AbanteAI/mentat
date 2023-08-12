import math
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont
from .code_change import CodeChangeAction

FONT_SIZE = 16
FONT_PATH = Path(__file__).parent / "../fonts/RobotoMono-Regular.ttf"
font = ImageFont.truetype(str(FONT_PATH), size=FONT_SIZE)
change_delimiter = 60 * "="


def _prefixed_lines(code_change, lines, prefix):
    return "\n".join(
        [
            prefix
            + " " * (code_change.line_number_buffer - len(prefix))
            + line.strip("\n")
            for line in lines
        ]
    )


def _generate_code_change_lines(code_change):
    lines_to_draw = [
        str(code_change.file),
        change_delimiter,
        _prefixed_lines(
            code_change,
            code_change.file_lines[
                max(0, math.ceil(code_change.first_changed_line) - 3) : min(
                    math.ceil(code_change.first_changed_line) - 1,
                    len(code_change.file_lines),
                )
            ],
            "",
        ),
        _prefixed_lines(
            code_change,
            code_change.file_lines[
                code_change.first_changed_line - 1 : code_change.last_changed_line
            ],
            "-",
        ),
        _prefixed_lines(code_change, code_change.code_lines, "+"),
        _prefixed_lines(
            code_change,
            code_change.file_lines[
                max(0, int(code_change.last_changed_line)) : min(
                    int(code_change.last_changed_line) + 2, len(code_change.file_lines)
                )
            ],
            "",
        ),
        change_delimiter,
    ]
    return lines_to_draw


def _generate_code_change_image(code_change):
    lines_to_draw = _generate_code_change_lines(code_change)
    _, descent = font.getmetrics()
    text_height = descent + font.getmask("hi").getbbox()[3]
    image_height = 30 + text_height * len(lines_to_draw)
    max_width = max(font.getmask(line).getbbox()[2] for line in lines_to_draw) + 20
    image = Image.new("RGB", (max_width, image_height), color="black")
    draw = ImageDraw.Draw(image)
    for line_num, text in enumerate(lines_to_draw):
        color = 'green' if text.startswith('+') else 'red' if text.startswith('-') else 'white'
        draw.text((10, 10 + text_height * line_num), text, fill=color, font=font)
    return image


def generate_code_change_image(code_change):
    image = _generate_code_change_image(code_change)
    image_name = f"code-change-{uuid4()}.png"
    image_path = Path(__file__).parent / "static" / "output_images" / image_name
    image.save(image_path)
    return f"http://localhost:3333/output_images/{image_name}"
