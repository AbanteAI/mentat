from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import attrs
from tree_sitter import Language, Node, Parser

file_extension_map = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
}


class TreesitterParsingError(Exception):
    """
    Raised when an error is encountered parsing a file with treesitter, typically ignored
    """


@attrs.define
class CallGraphNode:
    name: str
    return_type: str
    parameters: str


class CallGraph:
    def __init__(self):
        self.nodes = dict[str, CallGraphNode]()
        self.edges: dict[str, list[str]] = defaultdict(list)

    def add_node(self, node: CallGraphNode):
        self.nodes[node.name] = node

    def add_edge(self, _from: str, _to: str):
        self.edges[_from].append(_to)

    def save(self, path: Path):
        with open(path, "w") as f:
            f.write("NODES\n")
            f.write("\n".join(self.nodes.keys()))
            f.write("\nEDGES\n")
            f.write("\n".join([f"{k} -> {v}" for k, v in self.edges.items()]))


def parse_node(
    node: Node, call_path: str, call_graph: CallGraph | None = None
) -> CallGraph:
    """Extracts function signature data from a given node."""
    if call_graph is None:
        call_graph = CallGraph()

    def _clean_text(node: Node) -> str:
        return " ".join(node.text.decode("utf-8").split())

    def _clean_field(node: Node, field: str) -> str:
        _field = node.child_by_field_name(field)
        return _clean_text(_field) if _field else ""

    # If it's a function_definition, add a node and add to call_path
    if node.type == "function_definition":
        call_path = call_path + ":" + _clean_field(node, "name")
        _return_type = _clean_field(node, "return_type")
        _parameters = _clean_field(node, "parameters")
        new_node = CallGraphNode(
            call_path,
            _return_type,
            _parameters,
        )
        call_graph.add_node(new_node)

    # Else if it's a call, add an edge to call_path
    elif node.type == "call":
        _name = _clean_field(node, "function")
        call_graph.add_edge(call_path, _name)

    # If it has children, parse with call_path
    if node.children:
        for child in node.children:
            # if "calculate" in call_path and int(child.start_point[0]) >= 8:
            #     print('wait')
            parse_node(child, call_path, call_graph)

    return call_graph


def parse_file(path: Path, cwd: Path, cg: CallGraph | None = None) -> CallGraph:
    # Load parser
    filetype = path.suffix
    if filetype not in file_extension_map:
        raise TreesitterParsingError(f"Filetype {filetype} not supported")

    if cg is None:
        cg = CallGraph()
    relative_path = path.relative_to(cwd)
    call_path = relative_path.as_posix()

    language_name = file_extension_map[filetype]
    language = Language(str(Path(__file__).parent / "ts-lang.so"), language_name)
    parser = Parser()
    parser.set_language(language)
    source_code = path.read_text()
    tree = parser.parse(bytes(source_code, "utf8"))
    cursor = tree.walk()
    cursor.goto_first_child()
    while True:
        parse_node(cursor.node, call_path, cg)
        if not cursor.goto_next_sibling():
            break
    return cg


def parse_dir(path: Path, cwd: Path | str | None = None) -> CallGraph:
    cwd = path if cwd is None else Path(cwd)
    cg = CallGraph()
    for file in path.iterdir():
        try:
            if file.is_file():
                parse_file(file, cwd, cg)
        except TreesitterParsingError:
            print(f"Skipping {file} due to parsing error")
            continue
    return cg
