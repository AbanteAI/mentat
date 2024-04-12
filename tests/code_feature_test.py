from mentat.code_feature import CodeFeature, get_consolidated_feature_refs
from mentat.interval import Interval


def test_ref_method(temp_testbed):
    test_file = temp_testbed / "test_file.py"
    test_file.write_text("\n".join([""] * 10))
    code_feature = CodeFeature(test_file, Interval(2, 4))
    assert (code_feature.interval.start, code_feature.interval.end) == (2, 4)
    expected = temp_testbed / "test_file.py:2-4"
    assert str(code_feature) == str(expected)


def test_consolidated_refs(temp_testbed):
    scripts_dir = temp_testbed / "scripts"
    features = [
        CodeFeature(scripts_dir / "calculator.py", Interval(1, 10)),
        CodeFeature(scripts_dir / "calculator.py", Interval(10, 20)),
        CodeFeature(scripts_dir / "calculator.py", Interval(30, 40)),
        CodeFeature(scripts_dir / "echo.py"),
        CodeFeature(scripts_dir / "echo.py", Interval(10, 20)),
    ]
    consolidated = get_consolidated_feature_refs(features)
    assert len(consolidated) == 2
    assert consolidated[0] == f"{scripts_dir / 'calculator.py'}:1-10,10-20,30-40"
    assert consolidated[1] == str(scripts_dir / "echo.py")
