from mentat.parsers.block_parser import BlockParser
from mentat.parsers.parser import Parser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.parsers.split_diff_parser import SplitDiffParser
from mentat.parsers.unified_diff_parser import UnifiedDiffParser

parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
    "unified-diff": UnifiedDiffParser(),
}
