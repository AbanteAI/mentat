from pathlib import Path

from mentat.errors import SampleError
from mentat.sampler.utils import apply_diff_to_repo, setup_repo


async def validate_sample(sample, cwd: Path | str | None = None) -> tuple[bool, str]:
    """Validate a sample by applying diffs and checking sample fields."""
    try:
        required_fields = ["id", "repo", "merge_base", "message_prompt"]
        for field in required_fields:
            if not getattr(sample, field):
                return False, f"Missing required field: {field}"
        if not sample.message_edit and not sample.diff_edit:
            return False, "Samples must include either diff_edit or message_edit."

        try:
            repo = setup_repo(
                url=sample.repo,
                cwd=cwd,
                commit=sample.merge_base,
                diff_merge_base=sample.diff_merge_base,
                diff_active=sample.diff_active,
            )
        except SampleError as e:
            return False, str(e)
        # TODO: Validate context (paths)
        if sample.diff_edit:
            errors = apply_diff_to_repo(sample.diff_edit, repo)
            if errors:
                return False, f"Error applying diff_edit: {errors}"

        return True, ""
    except Exception as e:
        return False, f"Error validating sample: {e}"
