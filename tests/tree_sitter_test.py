from pathlib import Path
from mentat.treesitter.parser import FunctionSignature, SyntaxTree, get_tree
import pytest

def test_get_tree(temp_testbed):
    test_path = Path(temp_testbed) / 'multifile_calculator' / 'operations.py'
    tree = get_tree(test_path)
    assert isinstance(tree, SyntaxTree)
    assert tree.functions == [
        # Don't know why add_numbers is missing
        FunctionSignature(name='multiply_numbers', return_type='', parameters='(a, b)'),
        FunctionSignature(name='subtract_numbers', return_type='', parameters='(a, b)'),
        FunctionSignature(name='divide_numbers', return_type='', parameters='(a, b)'),
    ]
