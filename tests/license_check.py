import json
import subprocess

import fire

library_exceptions = [
    "mentat-ai",
    # pip-licenses shows tiktoken's full license text, but it is MIT
    "tiktoken",
]
accepted_licenses = [
    "BSD License",
    "Apache Software License",
    "MIT License",
    "Mozilla Public License 2.0 (MPL 2.0)",
]


def main():
    licenses = json.loads(subprocess.check_output(["pip-licenses", "--format=json"]))
    for package in licenses:
        if "Name" not in package:
            raise ValueError(f"No name found for package {package}")
        elif "License" not in package:
            raise ValueError(f"License not found for package {package['Name']}")
        elif package["Name"] not in library_exceptions:
            package_licenses = package["License"].split(";")
            for package_license in package_licenses:
                if package_license.strip() not in accepted_licenses:
                    raise Exception(
                        f"Package {package['Name']} has license {package['License']};"
                        " if this license is valid, add it to the accepted licenses"
                        " list"
                    )
    print("It's an older license, sir, but it checks out")


if __name__ == "__main__":
    fire.Fire(main)
