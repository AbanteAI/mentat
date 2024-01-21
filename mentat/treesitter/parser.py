from pathlib import Path
from typing import List, Union
from dataclasses import dataclass

from tree_sitter import Language, Parser, Node

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

@dataclass
class SyntaxTree:
    functions: List[FunctionSignature]

def clean_text(node: Node) -> str:
    return " ".join(node.text.decode('utf-8').split())

class TreesitterParsingError(Exception):
    """
    Raised when an error is encountered parsing a file with treesitter, typically ignored
    """

def extract_function_data(node: Node, source_code: str) -> Union[FunctionSignature, None]:
    """Extracts function signature data from a given node."""
    if node.type == "function_definition":
        _name = node.child_by_field_name("name")
        _return_type = node.child_by_field_name("return_type")
        _parameters = node.child_by_field_name("parameters")
        return FunctionSignature(
            clean_text(_name) if _name else "",
            clean_text(_return_type) if _return_type else "",
            clean_text(_parameters) if _parameters else "",
        )
    else:
        return None

def parse_file(path: Path) -> SyntaxTree:
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
    while cursor.goto_next_sibling():
        function_data = extract_function_data(cursor.node, source_code)
        if function_data:
            functions.append(function_data)

    return SyntaxTree(functions)

def parse_dir(path: Path) -> SyntaxTree:
    functions = list[FunctionSignature]()
    for file in path.iterdir():
        try:
            if file.is_file():
                parsed_file = parse_file(file)
                functions.extend(parsed_file.functions)
        except TreesitterParsingError as e:
            print(f"Skipping {file} due to parsing error")
            continue
    return SyntaxTree(functions)
