import os
from pathlib import Path

import pkg_resources


def read_requirements(filename):
    """Read requirements from a file and return as a list of strings."""
    with open(os.path.join(os.path.dirname(__file__), filename)) as f:
        return [str(r) for r in pkg_resources.parse_requirements(f)]


def hook(version, build_data):
    """Custom build hook for hatchling to set dynamic dependencies."""
    build_data["dependencies"] = read_requirements("requirements.txt")
    build_data["optional-dependencies"] = {"dev": read_requirements("dev-requirements.txt")}
    return build_data
