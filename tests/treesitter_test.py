from mentat.treesitter.parser import FunctionSignature, parse_dir, parse_file


def test_parse_file(temp_testbed):
    test_path = temp_testbed / "multifile_calculator" / "operations.py"
    file_functions = parse_file(test_path)
    assert file_functions == [
        FunctionSignature(name="add_numbers", return_type="", parameters="(a, b)"),
        FunctionSignature(name="multiply_numbers", return_type="", parameters="(a, b)"),
        FunctionSignature(name="subtract_numbers", return_type="", parameters="(a, b)"),
        FunctionSignature(name="divide_numbers", return_type="", parameters="(a, b)"),
    ]


def test_parse_dir(temp_testbed):
    test_path = temp_testbed / "multifile_calculator"
    tree = parse_dir(test_path, cwd=temp_testbed)
    dir_function_keys = [
        "multifile_calculator/__init__.py",
        "multifile_calculator/calculator.py",
        "multifile_calculator/operations.py",
    ]
    assert sorted(list(tree.keys())) == sorted(dir_function_keys)
