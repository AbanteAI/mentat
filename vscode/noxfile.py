# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""All the action we need during build"""

import json
import os
import shutil
import pathlib
import urllib.request as url_lib
from typing import List

import nox  # pylint: disable=import-error


def _pip_install_requirements(session: nox.Session, requirements_path: str) -> None:
    """Installs pip from a requirements file to bundled/libs.
    
    Includes the "--implementation py" flag to exclude architecture-specific packages.
    """
    session.install(
        "-t",
        "./bundled/libs",
        "--no-cache-dir",
        "--implementation",
        "py",
        "--no-deps",
        "--upgrade",
        "-r",
        requirements_path,
    )


def _install_bundle(session: nox.Session) -> None:
    """Install vscode-python-tools-extension-template requirements."""
    _pip_install_requirements(session, "./requirements.txt")


EXCLUDED_PACKAGES = ['tiktoken']  # is architecture-specific
def _install_mentat_dependencies(session: nox.Session) -> None:
    """Installs mentat's Python dependencies."""
    
    # Read the requirements and filter out the excluded packages
    with open("../requirements.txt", 'r') as f:
        lines = f.readlines()
        filtered_requirements = [line for line in lines if not any(pkg in line for pkg in EXCLUDED_PACKAGES)]
    
    # Install filtered requirements using a temp file
    temp_requirements_path = "./temp_requirements.txt"
    with open(temp_requirements_path, 'w') as f:
        f.writelines(filtered_requirements)
    _pip_install_requirements(session, temp_requirements_path)
    os.remove(temp_requirements_path)

    # For excluded packages, download all available wheels as well as dependencies
    for pkg in EXCLUDED_PACKAGES:
        _install_all_wheels_and_deps(session, pkg)


def _install_all_wheels_and_deps(session: nox.Session, package_name: str='tiktoken') -> None:
    """Download all available wheels for the latest release, as well as dependencies."""
    
    # Get list of wheels for the latest release
    with url_lib.urlopen(f"https://pypi.org/pypi/{package_name}/json") as response:
        data = json.loads(response.read().decode())
    
    # Filter by Python version and release version
    MIN_PY_VERSION = 10
    urls = [
        release['url'] for release in data['releases'][data['info']['version']]
        if release['packagetype'] == 'bdist_wheel'  # Only get wheel files
        and any(f"-cp3{num}-" in release['filename'] for num in range(MIN_PY_VERSION, 15))  # Filter Python versions
    ]

    # Download all to bundled/libs
    output_dir = f"./bundled/libs/{package_name}_wheels"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for url in urls:
        with url_lib.urlopen(url) as response, open(os.path.join(output_dir, os.path.basename(url)), 'wb') as out_file:
            out_file.write(response.read())
            print(f"Downloaded {os.path.basename(url)}")

    # Install package's dependencies
    requirements = data['info'].get('requires_dist', [])
    if requirements:
        requirements_clean = '\n'.join(item.replace(" (", "").replace(")", "") for item in requirements)
        temp_requirements_path = "./temp_requirements.txt"
        with open(temp_requirements_path, 'w') as f:
            f.writelines(requirements_clean)
        _pip_install_requirements(session, temp_requirements_path)
        os.remove(temp_requirements_path)
        

def _copy_mentat_code() -> None:
    """Copies the current mentat code into `./bundled/libs/mentat`."""
    src_dir = pathlib.Path(__file__).parent.parent / 'mentat'
    dst_dir = pathlib.Path(__file__).parent / "bundled/libs/mentat"
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)


def _update_pip_packages(session: nox.Session) -> None:
    session.run("pip-compile", "--generate-hashes", "--resolver=backtracking", "--upgrade", "./requirements.in")
    session.run(
        "pip-compile",
        "--generate-hashes",
        "--resolver=backtracking",
        "--upgrade",
        "./src/test/python_tests/requirements.in",
    )


def _get_package_data(package):
    json_uri = f"https://registry.npmjs.org/{package}"
    with url_lib.urlopen(json_uri) as response:
        return json.loads(response.read())


def _update_npm_packages(session: nox.Session) -> None:
    pinned = {
        "vscode-languageclient",
        "@types/vscode",
        "@types/node",
    }
    package_json_path = pathlib.Path(__file__).parent / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))

    for package in package_json["dependencies"]:
        if package not in pinned:
            data = _get_package_data(package)
            latest = "^" + data["dist-tags"]["latest"]
            package_json["dependencies"][package] = latest

    for package in package_json["devDependencies"]:
        if package not in pinned:
            data = _get_package_data(package)
            latest = "^" + data["dist-tags"]["latest"]
            package_json["devDependencies"][package] = latest

    # Ensure engine matches the package
    if (
        package_json["engines"]["vscode"]
        != package_json["devDependencies"]["@types/vscode"]
    ):
        print(
            "Please check VS Code engine version and @types/vscode version in package.json."
        )

    new_package_json = json.dumps(package_json, indent=4)
    # JSON dumps uses \n for line ending on all platforms by default
    if not new_package_json.endswith("\n"):
        new_package_json += "\n"
    package_json_path.write_text(new_package_json, encoding="utf-8")
    session.run("npm", "install", external=True)


def _setup_template_environment(session: nox.Session) -> None:
    session.install("wheel", "pip-tools")
    session.run("pip-compile", "--generate-hashes", "--resolver=backtracking", "--upgrade", "./requirements.in")
    session.run(
        "pip-compile",
        "--generate-hashes",
        "--resolver=backtracking",
        "--upgrade",
        "./src/test/python_tests/requirements.in",
    )
    _install_bundle(session)
    _install_mentat_dependencies(session)
    _copy_mentat_code()


@nox.session()
def setup(session: nox.Session) -> None:
    """Sets up the template for development."""
    _setup_template_environment(session)


@nox.session()
def tests(session: nox.Session) -> None:
    """Runs all the tests for the extension."""
    session.install("-r", "src/test/python_tests/requirements.txt")
    session.run("pytest", "src/test/python_tests")


@nox.session()
def lint(session: nox.Session) -> None:
    """Runs linter and formatter checks on python files."""
    session.install("-r", "./requirements.txt")
    session.install("-r", "src/test/python_tests/requirements.txt")

    session.install("pylint")
    session.run("pylint", "-d", "W0511", "./bundled/tool")
    session.run(
        "pylint",
        "-d",
        "W0511",
        "--ignore=./src/test/python_tests/test_data",
        "./src/test/python_tests",
    )
    session.run("pylint", "-d", "W0511", "noxfile.py")

    # check formatting using black
    session.install("black")
    session.run("black", "--check", "./bundled/tool")
    session.run("black", "--check", "./src/test/python_tests")
    session.run("black", "--check", "noxfile.py")

    # check import sorting using isort
    session.install("isort")
    session.run("isort", "--check", "./bundled/tool")
    session.run("isort", "--check", "./src/test/python_tests")
    session.run("isort", "--check", "noxfile.py")

    # check typescript code
    session.run("npm", "run", "lint", external=True)


@nox.session()
def build_package(session: nox.Session) -> None:
    """Builds VSIX package for publishing."""
    _setup_template_environment(session)
    session.run("npm", "install", external=True)
    session.run("npm", "run", "vsce-package", external=True)


@nox.session()
def update_packages(session: nox.Session) -> None:
    """Update pip and npm packages."""
    session.install("wheel", "pip-tools")
    _update_pip_packages(session)
    _update_npm_packages(session)
