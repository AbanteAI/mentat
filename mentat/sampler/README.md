# Sampler
The sampler captures interactions between you and Mentat. It generates an instance of `Sample` from your current conversation and codebase and saves it to a `.json` file.

## Generate Samples
In any github-connected repo:
1. Run `mentat`. If you're not working directly from a permanent commit, use e.g. `--sample_merge_base_target upstream/main`.
2. Give mentat a command, and accept its edits.
3. Leaving the mentat conversation open, **edit Mentat's edits** directly in your code editor.
4. Update Mentat's `include_files` using the `/include`/`/exclude` commands to reflect **context relevant to edits**
5. Call `/sample` to generate `~/.mentat/samples/sample_<id>.json`. You will be prompted to fill-in missing and optional fields.

## `Sample` API
A `Sample` captures interactions between a developer and any LLM Coding Assistant. It consists of a starting codebase, a user command, and the expected LLM response - text, a git diff, or both. It can also include a list of paths/line-numbers to be included with the prompt, diffs to setup the git environment, and more:

| Field                     | Req | Type                   | Description |
|---------------------------|-----|------------------------|-------------|
| title                     |     | `str`                  | plaintext by creator |
| description               |     | `str`                  | plaintext by creator |
| id                        |     | `uuid`                 |  |
| parent_id                 |     | `uuid`                 | id of sample immediately before this |
| repo                      | *   | `str`                  | a url to download the code |
| environment_setup_commit  |     | `str`                  | commit hash to use for environment setup and installation |
| merge_base                | *   | `str`                  | the latest permanent commit |
| diff_merge_base           |     | `str`                  | between merge_base and latest commit |
| diff_active               |     | `str`                  | between latest commit and active (pre-edit) code |
| context                   |     | `list[str]`            | list of `<relative_path>[:<start_line>-<end_line>]` |
| message_history           |     | `list[dict[str, str]]` | list of prior user and assistant messages |
| message_prompt            | *   | `str`                  | the sample task |
| hint_text                 |     | `str`                  | extra information, e.g. github issue comments
| message_edit              |     | `str`                  | plaintext response returned for sample edit |
| diff_edit                 | *   | `str`                  | between starting (diff_head) and ending code. |
| test_patch                |     | `str`                  | A patch to files used to evaluate the samples
| FAIL_TO_PASS              |     | `str`                  | A json list of test commands resolved by diff_edit |
| PASS_TO_PASS              |     | `str`                  | A json list of test commands that pass before and after |
| version                   |     | `str`                  | current Sample API version |

Notes:
- All diffs and code changes follow standard git-diff format (`diff --git a/new_filename...`)
- Samples should link to a permanent commit. Mentat has a config variable `sample_merge_base_target` (e.g. 'master'). If this value is None (default), merge_base is set to the latest commit on HEAD, otherwise it's set to the merge-base of HEAD and `..target`. 
- `message_history` can include user or assistant messages. If any assistant messages include edits, they should be converted to git-diff format. It can include messages with mistakes, where the sample task is to find and/or correct it. NOTE: git diffs may not correspond to an actual git record, as they are a "hypothetical edit" and may not have SHA-1's. See mentat.parsers.git_parser for more details.

## Evaluate Samples
The evaluation procedure, in abstract, is:
1. Clone the `repo` and checkout `merge_base`. 
   a. If there's a `diff_merge_base`, it's applied using `git apply` and committed (temporarily).
   b. If there's a `diff_active`, it's applied using `git apply`. 
2. Generate the conversation history
   a. Add code from files/lines in `paths` as a System message
   b. Add messages from `message_history` as User or Assistant messages. Convert edits from git-diff format to target edit format.
   c. Add `message_prompt` as a User message
3. Generate an LLM Completion for the conversation.
4. If using a Coding Assistant tool, process the response to apply edits to codebase.
5. Return the text portion of the conversation and the git diff, corresponding to `message_edit` and `diff_edit`

We provide two implementations of this:
- Run `python scripts/sampler [<id>...]` from the command line, in the mentat repo. Prints to terminal.
- Import `Sample` and call `Sample.evalute()` in Python. Returns a dict wtih `response` and `diff_edit`

## Use Cases
1. **Benchmarking Code Assistants**. Compare any LLM coding assitant's output to the sample output, or other assistants. We also support a `sample_<id>.py`, which will be run inside the edited codebase and generate a deterministic evaluation.
2. **Benchmarking RAG Systems**. After Step 1 of evaluation, use the active file system, `messages` and `user_prompt` to select relevant context for the question. Compare this to `paths`.
3. **Fine Tuning Code Assistants**. Use the sample to generate fine-tuning examples for e.g. generating outputs in a specific format.
