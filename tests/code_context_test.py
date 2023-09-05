import os
from unittest import TestCase

import pytest

from mentat.app import expand_paths
from mentat.code_context import CodeContext
from mentat.config_manager import ConfigManager
from mentat.errors import UserError


def test_path_gitignoring(temp_testbed, mock_config):
    gitignore_path = ".gitignore"
    testing_dir_path = "git_testing_dir"
    os.makedirs(testing_dir_path)

    # create 3 files, 2 ignored in gitignore, 1 not
    ignored_file_path_1 = os.path.join(testing_dir_path, "ignored_file_1.txt")
    ignored_file_path_2 = os.path.join(testing_dir_path, "ignored_file_2.txt")
    non_ignored_file_path = os.path.join(testing_dir_path, "non_ignored_file.txt")

    with open(gitignore_path, "w") as gitignore_file:
        gitignore_file.write("ignored_file_1.txt\nignored_file_2.txt")

    for file_path in [ignored_file_path_1, ignored_file_path_2, non_ignored_file_path]:
        with open(file_path, "w") as file:
            file.write("I am a file")

    # Run CodeFileManager on the git_testing_dir, and also explicitly pass in ignored_file_2.txt
    paths = [testing_dir_path, ignored_file_path_2]
    code_context = CodeContext(config=mock_config, paths=paths, exclude_paths=[])

    expected_file_paths = [
        os.path.join(temp_testbed, ignored_file_path_2),
        os.path.join(temp_testbed, non_ignored_file_path),
    ]

    case = TestCase()
    file_paths = [str(file_path.resolve()) for file_path in code_context.files]
    case.assertListEqual(sorted(expected_file_paths), sorted(file_paths))


def test_config_glob_exclude(mocker, temp_testbed, mock_config):
    # Makes sure glob exclude config works
    mock_glob_exclude = mocker.MagicMock()
    mocker.patch.object(ConfigManager, "file_exclude_glob_list", new=mock_glob_exclude)
    mock_glob_exclude.side_effect = [[os.path.join("glob_test", "**", "*.py")]]

    glob_exclude_path = os.path.join("glob_test", "bagel", "apple", "exclude_me.py")
    glob_include_path = os.path.join("glob_test", "bagel", "apple", "include_me.ts")
    directly_added_glob_excluded_path = os.path.join(
        "glob_test", "bagel", "apple", "directly_added_glob_excluded.py"
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
        config=mock_config,
        paths=[".", directly_added_glob_excluded_path],
        exclude_paths=[],
    )
    file_paths = [str(file_path.resolve()) for file_path in code_context.files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, directly_added_glob_excluded_path) in file_paths


def test_glob_include(temp_testbed, mock_config):
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

    file_paths = expand_paths(["**/*.py"])
    code_context = CodeContext(
        config=mock_config,
        paths=file_paths,
        exclude_paths=[],
    )
    file_paths = [str(file_path.resolve()) for file_path in code_context.files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, glob_include_path2) in file_paths


def test_cli_glob_exclude(temp_testbed, mock_config):
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

    file_paths = expand_paths(["**/*.py"])
    exclude_paths = expand_paths(["**/*.py", "**/*.ts"])
    code_context = CodeContext(
        config=mock_config,
        paths=file_paths,
        exclude_paths=exclude_paths,
    )

    file_paths = [file_path for file_path in code_context.files]
    assert os.path.join(temp_testbed, glob_include_then_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths


def test_text_encoding_checking(temp_testbed, mock_config):
    # Makes sure we don't include non text encoded files, and we quit if user gives us one
    nontext_path = "iamnottext.py"
    with open(nontext_path, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))

    paths = ["./"]
    code_context = CodeContext(
        config=mock_config,
        paths=paths,
        exclude_paths=[],
    )
    file_paths = [file_path for file_path in code_context.files]
    assert os.path.join(temp_testbed, nontext_path) not in file_paths

    with pytest.raises(UserError) as e_info:
        nontext_path_requested = "iamalsonottext.py"
        with open(nontext_path_requested, "wb") as f:
            # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
            f.write(bytearray([0x81]))

        paths = [nontext_path_requested]
        _ = CodeContext(
            config=mock_config,
            paths=paths,
            exclude_paths=[],
        )
    assert e_info.type == UserError
