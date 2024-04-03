import json
import subprocess

import fire

library_exceptions = [
    "mentat",
    # pip-licenses shows tiktoken's full license text, but it is MIT
    "tiktoken",
    # openai as Apache 2.0; for some reason, after updating to 1.0, pip-licenses thinks it's UNKNOWN
    "openai",
    # Is Apache 2.0 but shows up as UNKNOWN
    "chroma-hnswlib",
    # textual-autocomplete is MIT but shows up as UNKNOWN
    "textual-autocomplete",
]
accepted_licenses = [
    "BSD License",
    "Apache Software License",
    "MIT License",
    "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)",
    "Python Software Foundation License",
    "Apache 2.0",
    "Apache-2.0",
    "BSD 3-Clause",
    "3-Clause BSD License",
    "ISC License (ISCL)",
    "Historical Permission Notice and Disclaimer (HPND)",
    "BSD",
    "The Unlicense (Unlicense)",
    "Apache License, Version 2.0",
    "Apache License v2.0",
    "DFSG approved",
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
