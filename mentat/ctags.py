import platform
import subprocess


def is_ctags_installed() -> bool:
    try:
        subprocess.run(
            ["ctags", "--help"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except subprocess.CalledProcessError:
        return False


# TODO: cache
# TODO: display through stream
# TODO: test
def install_ctags_if_missing():
    if is_ctags_installed():
        return

    print("ctags is not installed. Attempting to install...")

    # Get the current operating system
    os_name = platform.system()
    install_command = ""

    if os_name == "Linux":
        install_command = "sudo apt update && sudo apt install universal-ctags"
    elif os_name == "Darwin":  # macOS
        install_command = "brew update && brew install universal-ctags"
    elif os_name == "Windows":
        install_command = "choco install universal-ctags"
    else:
        raise MentatError(
            f"Can't automatically install universal-ctags for os {os_name}. See"
            " README.md for setup instructions."
        )

    # Confirm with the user before installing
    confirm = (
        input(
            f"Run the following command to install ctags?\n\t{install_command}\n[Y/n]: "
        )
        .strip()
        .lower()
    )
    if confirm in ["y", ""]:
        result = subprocess.run(
            install_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print("Installation output:", result.stdout.decode())
        print("Installation errors:", result.stderr.decode())
    else:
        raise MentatError(
            "Not automatically installing ctags, see README.md for how to install."
            " yourself."
        )

    if not is_ctags_installed():
        raise MentatError(
            "Automatic installation of ctags failed. See README.md for how to install."
        )


def run_ctags():
    install_ctags_if_missing()


if __name__ == "__main__":
    run_ctags()
