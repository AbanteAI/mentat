import os
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont

from .code_change import CodeChangeAction
from .code_change_display import get_code_change_text

FONT_SIZE = 16
FONT_PATH = Path(__file__).parent / "../fonts/RobotoMono-Regular.ttf"
font = ImageFont.truetype(str(FONT_PATH), size=FONT_SIZE)
change_delimiter = 60 * "="


def _build_path_tree(file_paths, git_root):
    tree = {}
    for path in file_paths:
        path = os.path.relpath(path, git_root)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def _get_max_width(tree, prefix=""):
    max_width = 0
    for key in tree.keys():
        max_width = max(max_width, font.getmask(f"{prefix}{key}").getbbox()[2])
        if tree[key]:
            max_width = max(max_width, _get_max_width(tree[key], prefix + "    "))
    return max_width + 20


def _build_tree_lines_to_draw(
    tree, changed_files, list_to_draw, cur_path="", prefix=""
):
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        new_prefix = prefix + ("│   " if i < len(keys) - 1 else "    ")
        cur = os.path.join(cur_path, key)
        star = "* " if cur in changed_files else ""
        color = "yellow" if star else "white"
        list_to_draw.append((f"{prefix}{star}{key}", color))
        if tree[key]:
            _build_tree_lines_to_draw(
                tree[key], changed_files, list_to_draw, cur, new_prefix
            )


def generate_path_tree_image(file_paths, git_root):
    tree = _build_path_tree(file_paths, git_root)
    max_width = _get_max_width(tree)
    list_to_draw = []
    _build_tree_lines_to_draw(tree, [], list_to_draw)

    _, descent = font.getmetrics()
    text_height = descent + font.getmask("hi").getbbox()[3]
    image_height = 30 + text_height * len(list_to_draw)

    image = Image.new("RGB", (max_width, image_height), color="black")
    draw = ImageDraw.Draw(image)

    for line_num, (text, color) in enumerate(list_to_draw):
        draw.text((10, 10 + text_height * line_num), text, fill=color, font=font)

    image_name = f"path-{uuid4()}.png"
    image_path = Path(__file__).parent / "static" / "output_images" / image_name
    image.save(image_path)

    return f"http://localhost:3333/output_images/{image_name}"


def _generate_code_change_image_and_lines(code_changes):
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
    return image, lines_to_draw


def generate_code_change_image_and_lines(code_changes):
    image, change_lines = _generate_code_change_image_and_lines(code_changes)
    image_name = f"code-change-{uuid4()}.png"
    image_path = Path(__file__).parent / "static" / "output_images" / image_name
    image.save(image_path)
    return f"http://localhost:3333/output_images/{image_name}", [
        code_change_line[1].replace(change_delimiter, "==")
        for code_change_line in change_lines
    ]