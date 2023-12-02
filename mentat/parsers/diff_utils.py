def matching_index(orig_lines: list[str], new_lines: list[str]) -> int:
    orig_lines = orig_lines.copy()
    new_lines = new_lines.copy()
    index = _exact_match(orig_lines, new_lines)
    if index == -1:
        orig_lines = [s.lower() for s in orig_lines]
        new_lines = [s.lower() for s in new_lines]
        index = _exact_match(orig_lines, new_lines)
        if index == -1:
            orig_lines = [s.strip() for s in orig_lines]
            new_lines = [s.strip() for s in new_lines]
            index = _exact_match(orig_lines, new_lines)
            if index == -1:
                new_orig_lines = [s for s in orig_lines if s]
                new_new_lines = [s for s in new_lines if s]
                index = _exact_match(new_orig_lines, new_new_lines)
                if new_orig_lines and index != -1:
                    index = orig_lines.index(new_orig_lines[index])
    return index


def _exact_match(orig_lines: list[str], new_lines: list[str]) -> int:
    if "".join(new_lines).strip() == "" and "".join(orig_lines).strip() == "":
        return 0
    for i in range(len(orig_lines) - (len(new_lines) - 1)):
        if orig_lines[i : i + len(new_lines)] == new_lines:
            return i
    return -1
