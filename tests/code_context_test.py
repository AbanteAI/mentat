import os
from pathlib import Path
from textwrap import dedent
from unittest import TestCase

import pytest

from mentat.code_context import CodeContext
from mentat.code_feature import CodeMessageLevel
from mentat.config import Config
from mentat.git_handler import get_non_gitignored_files
from mentat.include_files import is_file_text_encoded
from mentat.llm_api import count_tokens
from tests.conftest import run_git_command


@pytest.mark.asyncio
async def test_path_gitignoring(temp_testbed, mock_session_context):
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
    paths = [Path(testing_dir_path), Path(ignored_file_path_2)]
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(paths, [])

    expected_file_paths = [
        os.path.join(temp_testbed, ignored_file_path_2),
        os.path.join(temp_testbed, non_ignored_file_path),
    ]

    case = TestCase()
    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    case.assertListEqual(sorted(expected_file_paths), sorted(file_paths))


@pytest.mark.asyncio
async def test_config_glob_exclude(mocker, temp_testbed, mock_session_context):
    # Makes sure glob exclude config works
    mocker.patch.object(
        Config, "file_exclude_glob_list", new=[os.path.join("glob_test", "**", "*.py")]
    )

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
    with open(
        directly_added_glob_excluded_path, "w"
    ) as directly_added_glob_excluded_file:
        directly_added_glob_excluded_file.write(
            "Config excludes me but I'm included if added directly"
        )

    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths([Path("."), directly_added_glob_excluded_path], [])

    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, directly_added_glob_excluded_path) in file_paths


@pytest.mark.asyncio
async def test_glob_include(temp_testbed, mock_session_context):
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

    file_paths = ["**/*.py"]
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(file_paths, [])

    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, glob_include_path2) in file_paths


@pytest.mark.asyncio
async def test_cli_glob_exclude(temp_testbed, mock_session_context):
    # Make sure cli glob exclude works and overrides regular include
    glob_include_then_exclude_path = os.path.join(
        "glob_test", "bagel", "apple", "include_then_exclude_me.py"
    )
    glob_exclude_path = os.path.join("glob_test", "bagel", "apple", "exclude_me.ts")

    os.makedirs(os.path.dirname(glob_include_then_exclude_path), exist_ok=True)
    with open(glob_include_then_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am included then excluded")
    os.makedirs(os.path.dirname(glob_exclude_path), exist_ok=True)
    with open(glob_exclude_path, "w") as glob_exclude_file:
        glob_exclude_file.write("I am excluded")

    file_paths = ["**/*.py"]
    exclude_paths = ["**/*.py", "**/*.ts"]
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(file_paths, exclude_paths)

    file_paths = [file_path for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_include_then_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths


@pytest.mark.asyncio
async def test_text_encoding_checking(temp_testbed, mock_session_context):
    # Makes sure we don't include non text encoded files, and we quit if user gives us one
    nontext_path = "iamnottext.py"
    with open(nontext_path, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))

    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(["./"], [])
    file_paths = [file_path for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, nontext_path) not in file_paths

    nontext_path_requested = "iamalsonottext.py"
    with open(nontext_path_requested, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths([Path(nontext_path_requested)], [])
    assert not code_context.include_files


@pytest.fixture
def features(mocker):
    features_meta = [
        ("somefile.txt", CodeMessageLevel.CODE, "some diff"),
        ("somefile.txt", CodeMessageLevel.CMAP_FULL, "some diff"),
        ("somefile.txt", CodeMessageLevel.CMAP_FULL, None),
        ("somefile.txt", CodeMessageLevel.CMAP, None),
        ("differentfile.txt", CodeMessageLevel.CODE, "some diff"),
    ]
    features = []
    for file, level, diff in features_meta:
        feature = mocker.MagicMock()
        feature.path = Path(file)
        feature.level = level
        feature.diff = diff
        features.append(feature)
    return features


@pytest.mark.asyncio
async def test_get_code_message_cache(mocker, temp_testbed, mock_session_context):
    mocker.patch.object(Config, "maximum_context", new=10)
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(
        ["multifile_calculator"], ["multifile_calculator/calculator.py"]
    )

    file = Path("multifile_calculator/operations.py")
    feature = mocker.MagicMock()
    feature.path = file
    code_context.features = [feature]

    # Return cached value if no changes to file or settings
    mock_get_code_message = mocker.patch(
        "mentat.code_context.CodeContext._get_code_message"
    )
    mock_get_code_message.return_value = "test1"
    value1 = await code_context.get_code_message(prompt="", max_tokens=1e6)
    mock_get_code_message.return_value = "test2"
    value2 = await code_context.get_code_message(prompt="", max_tokens=1e6)
    assert value1 == value2

    # Regenerate if settings change
    value3 = await code_context.get_code_message(prompt="", max_tokens=1e5)
    assert value1 != value3

    # Regenerate if feature files change
    mock_get_code_message.return_value = "test3"
    lines = file.read_text().splitlines()
    lines[0] = "something different"
    file.write_text("\n".join(lines))
    value4 = await code_context.get_code_message(prompt="", max_tokens=1e6)
    assert value3 != value4


@pytest.mark.asyncio
async def test_get_code_message_include(mocker, temp_testbed, mock_session_context):
    mocker.patch.object(Config, "maximum_context", new=0)
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(
        ["multifile_calculator"], ["multifile_calculator/calculator.py"]
    )

    # If max tokens is less than include_files, return include_files without
    # raising and Exception (that's handled elsewhere)
    code_message = await code_context.get_code_message(prompt="", max_tokens=1e6)
    expected = [
        "Code Files:",
        "",
        "multifile_calculator/__init__.py",
        "1:",
        "",
        "multifile_calculator/operations.py",
        *[
            f"{i+1}:{line}"
            for i, line in enumerate(
                Path("multifile_calculator/operations.py").read_text().split("\n")
            )
        ],
    ]
    assert code_message.splitlines() == expected


@pytest.mark.asyncio
@pytest.mark.clear_testbed
async def test_max_auto_tokens(mocker, temp_testbed, mock_session_context):
    with open("file_1.py", "w") as f:
        f.write(dedent("""\
            def func_1(x, y):
                return x + y
            
            def func_2():
                return 3
            """))

    with open("file_2.py", "w") as f:
        f.write(dedent("""\
            def func_3(a, b, c):
                return a * b ** c
            
            def func_4(string):
                print(string)
            """))
    run_git_command(temp_testbed, "add", ".")
    run_git_command(temp_testbed, "commit", "-m", "initial commit")

    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.set_paths(["file_1.py"], [])
    code_context.use_llm = False
    mock_session_context.config.auto_context = True

    async def _count_max_tokens_where(limit: int) -> int:
        code_message = await code_context.get_code_message(prompt="", max_tokens=limit)
        return count_tokens(code_message, "gpt-4")

    assert await _count_max_tokens_where(1e6) == 85  # Code
    assert await _count_max_tokens_where(84) == 65  # Cmap w/ signatures
    assert await _count_max_tokens_where(60) == 57  # Cmap
    assert await _count_max_tokens_where(52) == 47  # fnames
    # Always return include_files, regardless of max
    assert await _count_max_tokens_where(0) == 42  # Include_files only


@pytest.mark.clear_testbed
def test_get_all_features(temp_testbed, mock_session_context):
    # Create a sample file
    path1 = Path(temp_testbed) / "sample_path1.py"
    path2 = Path(temp_testbed) / "sample_path2.py"
    with open(path1, "w") as file1:
        file1.write("def sample_function():\n    pass\n")
    with open(path2, "w") as file2:
        file2.write("def sample_function():\n    pass\n")

    # Test without include_files
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    features = code_context._get_all_features(level=CodeMessageLevel.CODE)
    assert len(features) == 2
    feature1 = next(f for f in features if f.path == path1)
    feature2 = next(f for f in features if f.path == path2)
    for _f, _p in zip((feature1, feature2), (path1, path2)):
        feature = next(f for f in features if f.path == _p)
        assert feature.path == _p
        assert feature.level == CodeMessageLevel.CODE
        assert feature.diff is None
        assert feature.user_included is False

    # Test with include_files argument matching one file
    code_context.set_paths([path1], [])
    features = code_context._get_all_features(level=CodeMessageLevel.FILE_NAME)
    assert len(features) == 2
    feature1b = next(f for f in features if f.path == path1)
    feature2b = next(f for f in features if f.path == path2)
    assert feature1b.user_included is True
    assert feature1b.level == CodeMessageLevel.FILE_NAME
    assert feature2b.user_included is False
    assert feature2b.level == CodeMessageLevel.FILE_NAME


@pytest.mark.asyncio
async def test_get_code_message_ignore(mocker, temp_testbed, mock_session_context):
    mock_session_context.config.auto_context = True
    mocker.patch.object(Config, "maximum_context", new=7000)
    code_context = CodeContext(
        mock_session_context.stream,
        mock_session_context.git_root,
    )
    code_context.use_llm = False
    code_context.set_paths([], [], ["scripts", "**/*.txt"])
    code_message = await code_context.get_code_message("", 1e6)

    # Iterate through all files in temp_testbed; if they're not in the ignore
    # list, they should be in the code message.
    for file in get_non_gitignored_files(temp_testbed):
        abs_path = temp_testbed / file
        rel_path = abs_path.relative_to(temp_testbed).as_posix()
        if (
            not is_file_text_encoded(abs_path)
            or "scripts" in rel_path
            or rel_path.endswith(".txt")
        ):
            assert rel_path not in code_message
        else:
            assert rel_path in code_message
