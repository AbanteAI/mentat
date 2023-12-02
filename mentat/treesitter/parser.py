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

def get_tree(path: Path) -> SyntaxTree:
    # Load parser
    filetype = path.suffix
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
