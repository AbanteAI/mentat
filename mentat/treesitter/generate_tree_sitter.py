import subprocess
from pathlib import Path

from tree_sitter import Language


# Base directory to clone the grammars into. 
TEMP_DIR = Path(__file__).parent / "grammars"

LANGUAGES = {
    "go": "https://github.com/tree-sitter/tree-sitter-go",
    "javascript": "https://github.com/tree-sitter/tree-sitter-javascript",
    "python": "https://github.com/tree-sitter/tree-sitter-python",
}

def clone_or_update_repo(lang: str, repo_url: str):
    lang_dir = TEMP_DIR / lang
    
    if not lang_dir.exists():
        # Clone the repository.
        print(f"Cloning {repo_url} into {lang_dir}...")
        subprocess.run(["git", "clone", repo_url, lang_dir], check=True)
    else:
        # Update the existing repository.
        print(f"Updating {lang_dir}...")
        subprocess.run(["git", "-C", lang_dir, "pull"], check=True)

def bytes_to_human_readable(num: float, i_unit: int=0) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    if num < 1024.0:
        return f"{num:.2f} {units[i_unit]}"
    return bytes_to_human_readable(num / 1024.0, i_unit + 1)

def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    for lang, repo_url in LANGUAGES.items():
        clone_or_update_repo(lang, repo_url)
    Language.build_library(
        (Path(__file__).parent / "ts-lang.so").as_posix(),
        [str(TEMP_DIR / lang) for lang in LANGUAGES],
    )
    # ask to delete temporary files
    tslang_size = Path(__file__).parent.joinpath("ts-lang.so").stat().st_size
    tslang_size = bytes_to_human_readable(tslang_size)
    print(f"Generated parser ts-lang.so ({tslang_size})")
    tempdir_size = sum(f.stat().st_size for f in TEMP_DIR.glob("**/*") if f.is_file())
    tempdir_size = bytes_to_human_readable(tempdir_size)
    print(f"Remove {tempdir_size} temporary files? (y/n)")
    if input() == "y":
        print("Deleting...")
        subprocess.run(["rm", "-rf", TEMP_DIR], check=True)

if __name__ == "__main__":
    main()
