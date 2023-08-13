from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont

from .code_change import CodeChangeAction
from .code_change_display import get_code_change_text

FONT_SIZE = 16
FONT_PATH = Path(__file__).parent / "../fonts/RobotoMono-Regular.ttf"
font = ImageFont.truetype(str(FONT_PATH), size=FONT_SIZE)
change_delimiter = 60 * "="


def _generate_code_change_image(code_changes):
    lines_to_draw = []

    for code_change in code_changes:
        for line_num, line in enumerate(
            get_code_change_text(code_change, cli_formatted=False)
        ):
            if line_num == 0 and code_change.action == CodeChangeAction.CreateFile:
                for split_line in line.split("\n"):
                    lines_to_draw.append(("green", split_line))
            elif line_num == 0 and code_change.action == CodeChangeAction.DeleteFile:
                for split_line in line.split("\n"):
                    lines_to_draw.append(("red", split_line))
            else:
                for split_line in line.split("\n"):
                    if split_line.startswith("+"):
                        lines_to_draw.append(("green", split_line))
                    elif split_line.startswith("-"):
                        lines_to_draw.append(("red", split_line))
                    else:
                        lines_to_draw.append(("white", split_line))

    _, descent = font.getmetrics()

    text_height = descent + font.getmask("TEXT").getbbox()[3]
    image_height = 30 + text_height * len(lines_to_draw)
    max_width = (
        max(
            [
                font.getmask(line[1]).getbbox()[2]
                for line in lines_to_draw
                if line[1] != ""
            ]
        )
        + 20
    )

    image = Image.new("RGB", (max_width, image_height), color="black")
    draw = ImageDraw.Draw(image)

    for line_num, text in enumerate(lines_to_draw):
        draw.text(
            (10, 10 + text_height * line_num),
            text=text[1],
            fill=text[0],
            font=font,
        )
    return image


def generate_code_change_image(code_changes):
    image = _generate_code_change_image(code_changes)
    image_name = f"code-change-{uuid4()}.png"
    image_path = Path(__file__).parent / "static" / "output_images" / image_name
    image.save(image_path)
    return f"http://localhost:3333/output_images/{image_name}"
