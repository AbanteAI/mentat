import os
from pathlib import Path

from git import Repo

CLONE_TO_DIR = Path(__file__).parent / "repos"


def clone_repo(
    url: str, local_dir_name: str, refresh: bool = False, depth: int = 0
) -> None:
    local_dir = CLONE_TO_DIR / local_dir_name
    if os.path.exists(local_dir):
        if refresh:
            repo = Repo(local_dir)
            repo.git.reset("--hard")
            repo.git.clean("-fd")
            repo.remotes.origin.pull()
    else:
        if depth > 0:
            repo = Repo.clone_from(url, local_dir, depth=depth)
        else:
            repo = Repo.clone_from(url, local_dir)
    return local_dir
