from mentat.git_handler import get_git_diff
            f"/sample {temp_testbed.as_posix()}",
    session = Session(
        cwd=Path.cwd(), paths=[Path("multifile_calculator/calculator.py")]
    )
    sample_path = temp_testbed / "temp_sample.json"
    with open(temp_testbed / "test_file.py", "w") as f:
        f.write("test")
    with open(temp_testbed / "scripts" / "calculator2.py", "w") as f:
        f.write("test")
    with open(temp_testbed / "scripts" / "calculator.py", "r") as f:
        new_lines = f.readlines()
    with open(cwd / "multifile_calculator" / f"calculator{index}.py", "w") as f:
        f.write("test\n")
    diff_edit = get_git_diff("HEAD", cwd)
        [f"I will make the following edits. {llm_response}"]
    await python_client.call_mentat(f"/sample {temp_testbed.as_posix()}")
        [f"I will make the following edits. {llm_response}"]