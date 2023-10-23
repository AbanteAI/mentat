from pathlib import Path
from textwrap import dedent

import pytest

from mentat.code_feature import CodeFeature, CodeMessageLevel, split_file_into_intervals
from mentat.interval import Interval


def test_split_file_into_intervals(temp_testbed, mock_session_context):
    with open("file_1.py", "w") as f:
        f.write(dedent("""\
            def func_1(x, y):
                return x + y
            
            def func_2():
                return 3
            """))
    code_feature = CodeFeature(Path("file_1.py"), CodeMessageLevel.CODE)
    interval_features = split_file_into_intervals(temp_testbed, code_feature, 1)
    assert len(interval_features) == 2

    interval_1 = interval_features[0].intervals[0]
    interval_2 = interval_features[1].intervals[0]
    assert (interval_1.start, interval_1.end) == (0, 3)
    assert (interval_2.start, interval_2.end) == (4, 6)


def test_ref_method(temp_testbed):
    test_file = Path(temp_testbed) / "test_file.py"
    test_file.write_text("\n".join([""] * 10))
    expected = "test_file.py:2-4,6-8"
    code_feature = CodeFeature(expected, CodeMessageLevel.INTERVAL)
    assert (code_feature.intervals[0].start, code_feature.intervals[0].end) == (2, 4)
    assert (code_feature.intervals[1].start, code_feature.intervals[1].end) == (6, 8)
    ref_result = code_feature.ref()
    assert ref_result == expected
