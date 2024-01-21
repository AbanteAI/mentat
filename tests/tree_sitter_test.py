from pathlib import Path
from mentat.treesitter.parser import FunctionSignature, SyntaxTree, parse_file, parse_dir
import pytest

def test_parse_file(temp_testbed):
    test_path = temp_testbed / 'multifile_calculator' / 'operations.py'
    tree = parse_file(test_path)
    assert isinstance(tree, SyntaxTree)
    assert tree.functions == [
        # Don't know why add_numbers is missing
        FunctionSignature(name='multiply_numbers', return_type='', parameters='(a, b)'),
        FunctionSignature(name='subtract_numbers', return_type='', parameters='(a, b)'),
        FunctionSignature(name='divide_numbers', return_type='', parameters='(a, b)'),
    ]

def test_parse_dir(temp_testbed):
    test_path = temp_testbed / 'multifile_calculator'
    tree = parse_dir(test_path)
    
    expected_functions = [
        'add_numbers', 'multiply_numbers', 'subtract_numbers', 'divide_numbers', 'calculate'
    ]
    assert [f.name for f in tree.functions] == expected_functions
