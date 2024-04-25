import os
from pathlib import Path
from textwrap import dedent
from unittest import TestCase

import pytest

from mentat.code_context import CodeContext
from mentat.config import Config
from mentat.git_handler import get_non_gitignored_files
from mentat.include_files import is_file_text_encoded
from mentat.interval import Interval
from tests.conftest import run_git_command


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_path_gitignoring(temp_testbed, mock_code_context):
    gitignore_path = ".gitignore"
    testing_dir_path = "git_testing_dir"
    os.makedirs(testing_dir_path)

    # create 3 files, 2 ignored in gitignore, 1 not
    ignored_file_path_1 = Path(os.path.join(testing_dir_path, "ignored_file_1.txt"))
    ignored_file_path_2 = Path(os.path.join(testing_dir_path, "ignored_file_2.txt"))
    non_ignored_file_path = Path(os.path.join(testing_dir_path, "non_ignored_file.txt"))

    with open(gitignore_path, "w") as gitignore_file:
        gitignore_file.write("ignored_file_1.txt\nignored_file_2.txt")

    for file_path in [ignored_file_path_1, ignored_file_path_2, non_ignored_file_path]:
        with open(file_path, "w") as file:
            file.write("I am a file")

    # Run CodeFileManager on the git_testing_dir, and also explicitly pass in ignored_file_2.txt
    mock_code_context.include(testing_dir_path)
    mock_code_context.include(ignored_file_path_2)

    expected_file_paths = [
        os.path.join(temp_testbed, ignored_file_path_2),
        os.path.join(temp_testbed, non_ignored_file_path),
    ]

    case = TestCase()
    file_paths = [str(file_path.resolve()) for file_path in mock_code_context.include_files]
    case.assertListEqual(sorted(expected_file_paths), sorted(file_paths))


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_bracket_file(temp_testbed, mock_code_context):
    file_path_1 = Path("[file].tsx")
    file_path_2 = Path("test:[file].tsx")

    with file_path_1.open("w") as file_1:
        file_1.write("Testing")
    with file_path_2.open("w") as file_2:
        file_2.write("Testing")

    mock_code_context.include(file_path_1)
    mock_code_context.include(file_path_2)
    expected_file_paths = [
        temp_testbed / file_path_1,
        temp_testbed / file_path_2,
    ]

    case = TestCase()
    file_paths = list(mock_code_context.include_files.keys())
    case.assertListEqual(sorted(expected_file_paths), sorted(file_paths))


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_config_glob_exclude(mocker, temp_testbed, mock_code_context):
    # Makes sure glob exclude config works
    mocker.patch.object(Config, "file_exclude_glob_list", new=[os.path.join("glob_test", "**", "*.py")])

    glob_exclude_path = os.path.join("glob_test", "bagel", "apple", "exclude_me.py")
    glob_include_path = os.path.join("glob_test", "bagel", "apple", "include_me.ts")
    directly_added_glob_excluded_path = Path(
        os.path.join("glob_test", "bagel", "apple", "directly_added_glob_excluded.py")
    )
    os.makedirs(os.path.dirname(glob_exclude_path), exist_ok=True)
    with open(glob_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am excluded")
    with open(glob_include_path, "w") as glob_include_file:
        glob_include_file.write("I am included")
    with open(directly_added_glob_excluded_path, "w") as directly_added_glob_excluded_file:
        directly_added_glob_excluded_file.write("Config excludes me but I'm included if added directly")

    mock_code_context.include(".")
    mock_code_context.include(directly_added_glob_excluded_path)

    assert Path(temp_testbed / glob_exclude_path) not in mock_code_context.include_files
    assert Path(temp_testbed / glob_include_path) in mock_code_context.include_files
    assert Path(temp_testbed / directly_added_glob_excluded_path) in mock_code_context.include_files


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_glob_include(temp_testbed, mock_code_context):
    # Make sure glob include works
    glob_include_path = os.path.join("glob_test", "bagel", "apple", "include_me.py")
    glob_include_path2 = os.path.join("glob_test", "bagel", "apple", "include_me2.py")
    glob_exclude_path = os.path.join("glob_test", "bagel", "apple", "exclude_me.ts")

    os.makedirs(os.path.dirname(glob_include_path), exist_ok=True)
    with open(glob_include_path, "w") as glob_include_file:
        glob_include_file.write("I am included")
    os.makedirs(os.path.dirname(glob_include_path2), exist_ok=True)
    with open(glob_include_path2, "w") as glob_include_file:
        glob_include_file.write("I am also included")
    os.makedirs(os.path.dirname(glob_exclude_path), exist_ok=True)
    with open(glob_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am not included")

    mock_code_context.include("**/*.py")

    file_paths = [str(file_path.resolve()) for file_path in mock_code_context.include_files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, glob_include_path2) in file_paths


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_cli_glob_exclude(temp_testbed, mock_code_context):
    # Make sure cli glob exclude works and overrides regular include
    glob_include_then_exclude_path = os.path.join("glob_test", "bagel", "apple", "include_then_exclude_me.py")
    glob_exclude_path = os.path.join("glob_test", "bagel", "apple", "exclude_me.ts")

    os.makedirs(os.path.dirname(glob_include_then_exclude_path), exist_ok=True)
    with open(glob_include_then_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am included then excluded")
    os.makedirs(os.path.dirname(glob_exclude_path), exist_ok=True)
    with open(glob_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am excluded")

    mock_code_context.include("**/*.py", exclude_patterns=["**/*.py", "**/*.ts"])

    file_paths = [file_path for file_path in mock_code_context.include_files]
    assert os.path.join(temp_testbed, glob_include_then_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_text_encoding_checking(temp_testbed, mock_session_context):
    # Makes sure we don't include non text encoded files, and we quit if user gives us one
    nontext_path = "iamnottext.py"
    with open(nontext_path, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))

    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.cwd,
    )
    code_context.include("./")
    file_paths = [file_path for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, nontext_path) not in file_paths

    nontext_path_requested = "iamalsonottext.py"
    with open(nontext_path_requested, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.cwd,
    )
    code_context.include(nontext_path_requested)
    assert not code_context.include_files


@pytest.mark.ragdaemon
@pytest.mark.asyncio
@pytest.mark.clear_testbed
async def test_max_auto_tokens(mocker, temp_testbed, mock_session_context):
    with open("file_1.py", "w") as f:
        f.write(
            dedent(
                """\
            def func_1(x, y):
                return x + y
            
            def func_2():
                return 3
            """
            )
        )

    with open("file_2.py", "w") as f:
        f.write(
            dedent(
                """\
            def func_3(a, b, c):
                return a * b ** c
            
            def func_4(string):
                print(string)
            """
            )
        )
    run_git_command(temp_testbed, "add", ".")
    run_git_command(temp_testbed, "commit", "-m", "initial commit")

    code_context = CodeContext(
        mock_session_context.stream,
        temp_testbed,
    )
    await code_context.refresh_daemon()
    code_context.include("file_1.py")
    mock_session_context.config.auto_context_tokens = 8000

    code_message = await code_context.get_code_message(0, prompt="prompt")
    assert mock_session_context.llm_api_handler.spice.count_tokens(code_message, "gpt-4", is_message=True) == 85  # Code
    assert (
        code_message
        == """\
Code Files:

file_1.py
1:def func_1(x, y):
2:    return x + y
3:
4:def func_2():
5:    return 3

file_2.py
1:def func_3(a, b, c):
2:    return a * b ** c
3:
4:def func_4(string):
5:    print(string)
"""
    )


@pytest.mark.ragdaemon
@pytest.mark.asyncio
@pytest.mark.clear_testbed
async def test_get_all_features(temp_testbed, mock_session_context):
    # Create a sample file
    path1 = Path(temp_testbed) / "sample_path1.py"
    path2 = Path(temp_testbed) / "sample_path2.py"
    with open(path1, "w") as file1:
        file1.write("def sample_function():\n    pass\n")
    with open(path2, "w") as file2:
        file2.write("def sample_function():\n    pass\n")

    mock_code_context = CodeContext(
        mock_session_context.stream,
        temp_testbed,
    )
    await mock_code_context.refresh_daemon()

    # Test without include_files
    features = mock_code_context.get_all_features()
    assert len(features) == 2
    feature1 = next(f for f in features if f.path == path1)
    feature2 = next(f for f in features if f.path == path2)
    for _f, _p in zip((feature1, feature2), (path1, path2)):
        feature = next(f for f in features if f.path == _p)
        assert feature.path == _p

    # Test with include_files argument matching one file
    mock_code_context.include(path1)
    features = mock_code_context.get_all_features(split_intervals=False)
    assert len(features) == 2
    feature1b = next(f for f in features if f.path == path1)
    feature2b = next(f for f in features if f.path == path2)
    assert feature1b.interval.whole_file()
    assert feature2b.interval.whole_file()


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_get_code_message_ignore(mocker, temp_testbed, mock_session_context):
    mock_session_context.config.auto_context_tokens = 8000
    mocker.patch.object(Config, "maximum_context", new=7000)
    code_context = CodeContext(
        mock_session_context.stream,
        temp_testbed,
        ignore_patterns=["scripts", "**/*.txt"],
    )
    code_message = await code_context.get_code_message(0, prompt="prompt")

    # Iterate through all files in temp_testbed; if they're not in the ignore
    # list, they should be in the code message.
    for file in get_non_gitignored_files(temp_testbed):
        if str(file).startswith(".ragdaemon"):
            continue
        abs_path = temp_testbed / file
        rel_path = abs_path.relative_to(temp_testbed).as_posix()
        if not is_file_text_encoded(abs_path) or "scripts" in rel_path or rel_path.endswith(".txt"):
            assert rel_path not in code_message
        else:
            assert rel_path in code_message


@pytest.mark.no_git_testbed
def test_include_single_file_interval(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:10-12")

    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert multifile_calculator_path in mock_code_context.include_files
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 1
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(10, 12)


@pytest.mark.no_git_testbed
def test_include_multiple_file_intervals(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:10-12")
    mock_code_context.include("multifile_calculator/calculator.py:14-20")

    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 2
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(10, 12)
    assert mock_code_context.include_files[multifile_calculator_path][1].interval == Interval(14, 20)


@pytest.mark.no_git_testbed
def test_include_missing_file_interval(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:9000-9001")
    assert len(mock_code_context.include_files) == 0


@pytest.mark.no_git_testbed
def test_include_overlapping_file_intervals(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:1-5")
    mock_code_context.include("multifile_calculator/calculator.py:1-6")
    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 2
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(1, 5)
    assert mock_code_context.include_files[multifile_calculator_path][1].interval == Interval(1, 6)


@pytest.mark.no_git_testbed
def test_include_duplicate_file_interval(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:1-5")
    mock_code_context.include("multifile_calculator/calculator.py:1-5")
    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 1
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(1, 5)


@pytest.mark.no_git_testbed
def test_exclude_single_file_interval(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:10-12")
    mock_code_context.exclude("multifile_calculator/calculator.py:10-12")
    assert len(mock_code_context.include_files) == 0


@pytest.mark.no_git_testbed
def test_exclude_multiple_file_intervals(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:1-5")
    mock_code_context.include("multifile_calculator/calculator.py:6-10")
    mock_code_context.exclude("multifile_calculator/calculator.py:1-5")
    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 1
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(6, 10)


@pytest.mark.no_git_testbed
def test_exclude_missing_file_interval(mock_code_context):
    mock_code_context.include("multifile_calculator/calculator.py:1-5")
    mock_code_context.exclude("multifile_calculator/calculator.py:3-10")
    assert len(mock_code_context.include_files) == 1
    multifile_calculator_path = Path("multifile_calculator/calculator.py").resolve()
    assert len(mock_code_context.include_files[multifile_calculator_path]) == 1
    assert mock_code_context.include_files[multifile_calculator_path][0].interval == Interval(1, 5)


@pytest.mark.no_git_testbed
def test_include_single_directory(mock_code_context):
    mock_code_context.include("multifile_calculator", exclude_patterns=["**/__pycache__"])
    assert len(mock_code_context.include_files) == 3
    assert Path("multifile_calculator/__init__.py").resolve() in mock_code_context.include_files
    assert Path("multifile_calculator/calculator.py").resolve() in mock_code_context.include_files
    assert Path("multifile_calculator/operations.py").resolve() in mock_code_context.include_files


@pytest.mark.no_git_testbed
def test_include_duplicate_directory(mock_code_context):
    mock_code_context.include("multifile_calculator", exclude_patterns=["**/__pycache__"])
    mock_code_context.include("multifile_calculator", exclude_patterns=["**/__pycache__"])
    assert len(mock_code_context.include_files) == 3


@pytest.mark.no_git_testbed
def test_include_missing_directory(mock_code_context):
    mock_code_context.include("multifile_calculator", exclude_patterns=["**/__pycache__"])
    mock_code_context.include("this_directory_does_not_exist")
    assert len(mock_code_context.include_files) == 3


@pytest.mark.no_git_testbed
def test_exclude_single_directory(mock_code_context):
    mock_code_context.include("multifile_calculator", exclude_patterns=["**/__pycache__"])
    mock_code_context.exclude("multifile_calculator")
    assert len(mock_code_context.include_files) == 0


@pytest.mark.no_git_testbed
def test_exclude_missing_directory(mock_code_context):
    mock_code_context.exclude("this_directory_does_not_exist")
    assert len(mock_code_context.include_files) == 0
