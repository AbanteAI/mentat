import os

from git import Repo

CLONE_TO_DIR = f"{os.path.dirname(__file__)}/../../../"


def clone_repo(url: str, local_dir_name: str, refresh: bool = False) -> None:
    local_dir = f"{CLONE_TO_DIR}{local_dir_name}"
    if os.path.exists(local_dir):
        if refresh:
            repo = Repo(local_dir)
            repo.git.reset("--hard")
            repo.git.clean("-fd")
            repo.remotes.origin.pull()
    else:
        repo = Repo.clone_from(url, local_dir)
    return local_dir