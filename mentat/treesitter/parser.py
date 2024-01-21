from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Node, Parser

file_extension_map = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
}


@dataclass
class FunctionSignature:
    name: str
    return_type: str
    parameters: str


class TreesitterParsingError(Exception):
    """
    Raised when an error is encountered parsing a file with treesitter, typically ignored
    """


def parse_node(node: Node, source_code: str) -> FunctionSignature | None:
    """Extracts function signature data from a given node."""
    if node.type == "function_definition":

        def _clean_text(node: Node) -> str:
            return " ".join(node.text.decode("utf-8").split())

        _name = node.child_by_field_name("name")
        _return_type = node.child_by_field_name("return_type")
        _parameters = node.child_by_field_name("parameters")
        return FunctionSignature(
            _clean_text(_name) if _name else "",
            _clean_text(_return_type) if _return_type else "",
            _clean_text(_parameters) if _parameters else "",
        )
    else:
        return None


def parse_file(path: Path) -> list[FunctionSignature]:
    # Load parser
    filetype = path.suffix
    if filetype not in file_extension_map:
        raise TreesitterParsingError(f"Filetype {filetype} not supported")
    language_name = file_extension_map[filetype]
    language = Language(str(Path(__file__).parent / "ts-lang.so"), language_name)
    parser = Parser()
    parser.set_language(language)
    # Create syntax tree
    source_code = path.read_text()
    tree = parser.parse(bytes(source_code, "utf8"))
    functions = list[FunctionSignature]()
    cursor = tree.walk()
    cursor.goto_first_child()
    while True:
        function_data = parse_node(cursor.node, source_code)
        if function_data:
            functions.append(function_data)
        if not cursor.goto_next_sibling():
            break

    return functions


def parse_dir(
    path: Path, cwd: Path | str | None = None
) -> dict[str, list[FunctionSignature]]:
    dir_functions = dict[str, list[FunctionSignature]]()
    for file in path.iterdir():
        relative_path = file.relative_to(cwd) if cwd else file
        try:
            if file.is_file():
                file_functions = parse_file(file)
                dir_functions[relative_path.as_posix()] = file_functions
        except TreesitterParsingError:
            print(f"Skipping {file} due to parsing error")
            continue
    return dir_functions
