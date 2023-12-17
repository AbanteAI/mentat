from uuid import uuid4

from git import Repo  # type: ignore

from mentat.errors import SampleError


def get_active_snapshot_commit(repo: Repo) -> str | None:
    """Returns the commit hash of the current active snapshot, or None if there are no active changes."""
    if not repo.is_dirty():
        return None
    try:
        # Stash active changes and record the current position
        repo.git.add("--all")  # So new files are included
        repo.git.stash("push", "-u")
        detached_head = repo.head.is_detached
        if detached_head:
            current_state = repo.head.commit.hexsha
        else:
            current_state = repo.active_branch.name
        # Commit them on a temporary branch
        temp_branch = f"sample_{uuid4().hex}"
        repo.git.checkout("-b", temp_branch)
        repo.git.stash("apply")
        repo.git.commit("-am", temp_branch)
        # Save the commit hash for diffing against later
        new_commit = repo.head.commit.hexsha
        # Reset repo to how it was before
        repo.git.checkout(current_state)
        repo.git.branch("-D", temp_branch)
        repo.git.stash("apply")
        repo.git.stash("drop")
        # Return the hexsha of the new commit
        return new_commit

    except Exception as e:
        raise SampleError(
            "WARNING: Mentat encountered an error while making temporary git changes:"
            f" {e}. If your active changes have disappeared, they can most likely be "
            "recovered using 'git stash pop'."
        )
