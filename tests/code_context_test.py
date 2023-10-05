import os
from pathlib import Path
from unittest import TestCase

import pytest

from mentat.code_context import (
    CodeContext,
    _longer_feature_already_included,
    _shorter_features_already_included,
)
from mentat.code_file import CodeMessageLevel
from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.errors import UserError
from mentat.llm_api import count_tokens
from mentat.parsers.block_parser import BlockParser
from mentat.include_files import expand_paths


@pytest.mark.asyncio
async def test_path_gitignoring(mock_stream, temp_testbed, mock_config):
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
    code_context = await CodeContext.create(
        config=mock_config, paths=paths, exclude_paths=[]
    )

    expected_file_paths = [
        os.path.join(temp_testbed, ignored_file_path_2),
        os.path.join(temp_testbed, non_ignored_file_path),
    ]

    case = TestCase()
    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    case.assertListEqual(sorted(expected_file_paths), sorted(file_paths))


@pytest.mark.asyncio
async def test_config_glob_exclude(mock_stream, mocker, temp_testbed, mock_config):
    # Makes sure glob exclude config works
    mock_glob_exclude = mocker.MagicMock()
    mocker.patch.object(ConfigManager, "file_exclude_glob_list", new=mock_glob_exclude)
    mock_glob_exclude.side_effect = [[os.path.join("glob_test", "**", "*.py")]]

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

    code_context = await CodeContext.create(
        config=mock_config,
        paths=[Path("."), directly_added_glob_excluded_path],
        exclude_paths=[],
    )
    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, directly_added_glob_excluded_path) in file_paths


@pytest.mark.asyncio
async def test_glob_include(mock_stream, temp_testbed, mock_config):
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
    code_context = await CodeContext.create(
        config=mock_config,
        paths=file_paths,
        exclude_paths=[],
    )
    file_paths = [str(file_path.resolve()) for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_include_path) in file_paths
    assert os.path.join(temp_testbed, glob_include_path2) in file_paths


@pytest.mark.asyncio
async def test_cli_glob_exclude(mock_stream, temp_testbed, mock_config):
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
    code_context = await CodeContext.create(
        config=mock_config,
        paths=file_paths,
        exclude_paths=exclude_paths,
    )

    file_paths = [file_path for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, glob_include_then_exclude_path) not in file_paths
    assert os.path.join(temp_testbed, glob_exclude_path) not in file_paths


@pytest.mark.asyncio
async def test_text_encoding_checking(mock_stream, temp_testbed, mock_config):
    # Makes sure we don't include non text encoded files, and we quit if user gives us one
    nontext_path = "iamnottext.py"
    with open(nontext_path, "wb") as f:
        # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
        f.write(bytearray([0x81]))

    paths = [Path("./")]
    code_context = await CodeContext.create(
        config=mock_config,
        paths=paths,
        exclude_paths=[],
    )
    file_paths = [file_path for file_path in code_context.include_files]
    assert os.path.join(temp_testbed, nontext_path) not in file_paths

    with pytest.raises(UserError) as e_info:
        nontext_path_requested = "iamalsonottext.py"
        with open(nontext_path_requested, "wb") as f:
            # 0x81 is invalid in UTF-8 (single byte > 127), and undefined in cp1252 and iso-8859-1
            f.write(bytearray([0x81]))

        paths = [Path(nontext_path_requested)]
        _ = await CodeContext.create(
            config=mock_config,
            paths=paths,
            exclude_paths=[],
        )
    assert e_info.type == UserError


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


def test_longer_feature_already_included(features):
    higher_level = _longer_feature_already_included(features[1], [features[0]])
    assert higher_level is True
    lower_diff = _longer_feature_already_included(features[1], [features[2]])
    assert lower_diff is False
    higher_diff = _longer_feature_already_included(features[2], [features[1]])
    assert higher_diff is True


def test_shorter_features_already_included(features):
    lower_level = _shorter_features_already_included(
        features[1], [features[0]] + features[2:]
    )
    assert set(lower_level) == set(features[2:4])


@pytest.mark.asyncio
async def test_get_code_message_cache(mocker, temp_testbed, mock_config, mock_stream):
    code_file_manager = CodeFileManager(mock_config)
    parser = BlockParser()
    code_context = await CodeContext.create(
        config=mock_config,
        paths=["multifile_calculator"],
        exclude_paths=["multifile_calculator/calculator.py"],
        auto_tokens=10,
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
    value1 = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    mock_get_code_message.return_value = "test2"
    value2 = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    assert value1 == value2

    # Regenerate if settings change
    code_context.settings.auto_tokens = 11
    value3 = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    assert value1 != value3

    # Regenerate if feature files change
    mock_get_code_message.return_value = "test3"
    lines = file.read_text().splitlines()
    lines[0] = "something different"
    file.write_text("\n".join(lines))
    value4 = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    assert value3 != value4


@pytest.mark.asyncio
async def test_get_code_message_include(temp_testbed, mock_config):
    code_file_manager = CodeFileManager(mock_config)
    parser = BlockParser()
    code_context = await CodeContext.create(
        config=mock_config,
        paths=["multifile_calculator"],
        exclude_paths=["multifile_calculator/calculator.py"],
    )

    # If max tokens is less than include_files, return include_files without
    # raising and Exception (that's handled elsewhere)
    code_context.settings.auto_tokens = 0
    code_message = await code_context.get_code_message("gpt-4", code_file_manager, parser)
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

    # Fill-in complete files if there's enough room
    code_context.settings.auto_tokens = 1000 * 0.95  # Sometimes it's imprecise
    code_message = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    print(code_message)
    assert 500 <= count_tokens(code_message, "gpt-4") <= 1000
    messages = code_message.split("\n\n")
    assert messages[0] == "Code Files:"
    for message in messages[1:]:
        message_lines = message.splitlines()
        if message_lines:
            assert Path(message_lines[0]).exists()

    # Otherwise, fill-in what fits
    code_context.settings.auto_tokens = 400
    code_message = await code_context.get_code_message("gpt-4", code_file_manager, parser)
    print(code_message)
    assert count_tokens(code_message, "gpt-4") <= 800
