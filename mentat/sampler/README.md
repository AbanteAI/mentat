# Mentat Sampler API
The Sampler API is an open-source standard to captures interactions between a developer and an LLM-based AI Assistant. It's intended to facilitate sharing of benchmarks and fine-tuning data throughout the open-source community and industry.

| Field            | Type          | Description |
|------------------|---------------|-------------|
| title            | `str`         | plaintext by creator |
| description      | `str`         | plaintext by creator |
| repo             | `str`         | a url to download the code |
| merge_base       | `str`         | the latest permanent commit |
| diff_merge_base  | `str`         | between merge_base and latest commit |
| diff_active      | `str`         | between latest commit and active (pre-edit) code |
| hexsha_active    | `str`         | sha256 of the complete repo pre-edit |
| messages         | `list[dict]`  | user and assistant messages. |
| args             | `list[str]`   | list of `<relative_path>[:<start_line>,<end_line>]` |
| diff_edit        | `str`         | between starting (diff_head) and ending code. |
| hexsha_edit      | `str`         | sha256 of the complete repo post-edit |
| test_command     | `str`         | discrete pass/fail, e.g. ‘pytest -k diff_active’ |
| version          | `str`         | current Sample API version |

### Notes on Mentat Implementation
- All diffs and code changes follow standard git-diff format (`diff --git a/new_filename...`)
- Samples should link to a permanent commit. Mentat has a config variable `sample_merge_base_target` (e.g. 'master'). If this value is None (default), merge_base is set to the latest commit on HEAD, otherwise it's set to the merge-base of HEAD and `..target`. 
- `git_handler.get_hexsha_active` takes a sha256 of all unignored files in your current git repo (including unstaged changes and new files). We call it once before the edit and once after. We'll use the second one (hexsha_edit) as the sample's primary id. If two samples are created one-after-the-next, the hexsha_edit of a parent is the same as the hexsha_active of its child. This lets you string samples together to fine-tune agents.
- Messages can be a single user message or a whole prior conversation. If any assistant messages include edits, they should be converted to git-diff format. Prior messages can include messages with mistakes, where the sample task is to find and/or correct it.
