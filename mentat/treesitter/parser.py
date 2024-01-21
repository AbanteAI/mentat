from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import attrs
from tree_sitter import Language, Node, Parser

from mentat.git_handler import get_non_gitignored_files
from mentat.utils import is_file_text_encoded

file_extension_map = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
}


def _clean_text(node: Node) -> str:
    return " ".join(node.text.decode("utf-8").split())


def _clean_field(node: Node, field: str) -> str:
    _field = node.child_by_field_name(field)
    return _clean_text(_field) if _field else ""


def parse_imports(
    import_line: str, import_namespace: dict[str, str] = {}
) -> list[tuple[str, str]]:
    module = ""
    if import_line.startswith("from"):
        _, module, import_line = import_line.split(" ", 2)
        module = module.strip()
        if module in import_namespace:
            module = import_namespace[module] + "."

    import_line = import_line.replace("import", "").strip()
    source_alias = ""
    as_alias = ""
    if " as " in import_line:
        source_alias, as_alias = import_line.split(" as ", 1)
        source_alias = source_alias.strip()
        source_alias = import_namespace.get(source_alias, source_alias)
        as_alias = as_alias.strip()
        as_alias = import_namespace.get(as_alias, as_alias)
    else:
        as_alias = import_line.strip()
        source_alias = import_namespace.get(as_alias, as_alias)

    output = list[tuple[str, str]]()
    for _source, _as in zip(source_alias.split(","), as_alias.split(",")):
        output.append((f"{module}{_source.strip()}", _as.strip()))
    return output


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
        self.edges: dict[str, set[str]] = defaultdict(set)

    def add_node(self, node: CallGraphNode):
        self.nodes[node.name] = node

    def add_edge(self, _from: str, _to: str):
        self.edges[_from].add(_to)

    def save(self, path: Path):
        with open(path, "w") as f:
            f.write("NODES\n")
            f.write("\n".join(self.nodes.keys()))
            f.write("\nEDGES\n")
            f.write("\n".join([f"{k} -> {v}" for k, v in self.edges.items()]))


def parse_node(
    node: Node,
    call_path: str,
    call_graph: CallGraph | None = None,
    namespace: dict[str, str] = {},
    import_namespace: dict[str, str] = {},
) -> CallGraph:
    """Extracts function signature data from a given node."""
    if call_graph is None:
        call_graph = CallGraph()

    # If it's an import, add it to the namespace
    if node.type in ["import_declaration", "import_statement", "import_from_statement"]:
        imports = parse_imports(_clean_text(node), import_namespace)
        for module, name in imports:
            # Check for match, otherwise add
            namespace[name] = module

    # If it's a function_definition, add a node and add to call_path
    elif node.type == "function_definition":
        call_path = call_path + ":" + _clean_field(node, "name")
        _return_type = _clean_field(node, "return_type")
        _parameters = _clean_field(node, "parameters")
        new_node = CallGraphNode(
            call_path,
            _return_type,
            _parameters,
        )
        call_graph.add_node(new_node)
        namespace[_clean_field(node, "name")] = call_path

    # Else if it's a call, add an edge to call_path
    # If it's an import, add it to the imports list
    elif node.type == "call":
        # TODO: _clean_field is repurposed here, but makes a lot of mistakes.
        _name = _clean_field(node, "function")
        # Check for stem in namespace
        if "." in _name:
            stem = _name.split(".")[0]
            if stem in namespace:
                _name = _name.replace(stem, namespace[stem])
        else:
            _name = namespace.get(_name, _name)
        call_graph.add_edge(call_path, _name)

    # If it has children, parse with call_path
    if node.children:
        for child in node.children:
            # if "calculate" in call_path and int(child.start_point[0]) >= 8:
            #     print('wait')
            parse_node(child, call_path, call_graph)

    return call_graph


def parse_file(
    path: Path,
    cwd: Path,
    cg: CallGraph | None = None,
    import_namespace: dict[str, str] = {},
) -> CallGraph:
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
        parse_node(cursor.node, call_path, cg, import_namespace=import_namespace.copy())
        if not cursor.goto_next_sibling():
            break
    return cg


def load_namespace_for_dir(path: Path, cwd: Path | str | None = None) -> dict[str, str]:
    cwd = path if cwd is None else Path(cwd)
    namespace: dict[str, str] = {}
    for file in path.iterdir():
        relative_path = file.relative_to(cwd.parent)
        _parts = [str(p) for p in relative_path.parts]
        if file.suffix:
            _parts[-1] = _parts[-1].replace(file.suffix, "")
        for part in _parts[::-1]:
            i_part = _parts.index(part)
            namespace_id = ".".join(_parts[i_part:])
            if namespace_id not in namespace:
                namespace[namespace_id] = ".".join(_parts)
    return namespace


def parse_dir(
    path: Path, cwd: Path | str | None = None, recursive: bool = True
) -> CallGraph:
    cwd = path if cwd is None else Path(cwd)
    cg = CallGraph()
    files = path.iterdir() if recursive is False else get_non_gitignored_files(path)
    for file in files:
        abs_path = path / file
        import_namespace = load_namespace_for_dir(abs_path.parent, cwd)
        try:
            if is_file_text_encoded(abs_path):
                parse_file(abs_path, cwd, cg, import_namespace.copy())
        except TreesitterParsingError:
            print(f"Skipping {file} due to parsing error")
            continue
    return cg
