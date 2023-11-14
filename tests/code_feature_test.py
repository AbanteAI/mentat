from pathlib import Path
from textwrap import dedent

from mentat.code_feature import CodeFeature, CodeMessageLevel, split_file_into_intervals


def test_split_file_into_intervals(temp_testbed, mock_session_context):
    with open("file_1.py", "w") as f:
        f.write(dedent("""\
            def func_1(x, y):
                return x + y
            
            def func_2():
                return 3
            """))
    code_feature = CodeFeature(
        mock_session_context.cwd / "file_1.py", CodeMessageLevel.CODE
    )
    interval_features = split_file_into_intervals(code_feature, 1)

    assert len(interval_features) == 2

    interval_1 = interval_features[0].interval
    interval_2 = interval_features[1].interval
    assert (interval_1.start, interval_1.end) == (1, 4)
    assert (interval_2.start, interval_2.end) == (4, 6)


def test_ref_method(temp_testbed):
    test_file = Path(temp_testbed) / "test_file.py"
    test_file.write_text("\n".join([""] * 10))
    expected = temp_testbed / "test_file.py:2-4"
    code_feature = CodeFeature(expected, CodeMessageLevel.INTERVAL)
    assert (code_feature.interval.start, code_feature.interval.end) == (2, 4)
    ref_result = code_feature.ref()
    assert ref_result == str(expected)
