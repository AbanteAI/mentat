import os
from pathlib import Path

import pkg_resources
from setuptools import find_packages, setup

readme_path = os.path.join(Path(__file__).parent, "README.md")
with open(readme_path, "r", encoding="utf-8") as f:
    long_description = f.read()


version_path = os.path.join(Path(__file__).parent, "mentat/VERSION")
with open(version_path, "r", encoding="utf-8") as f:
    VERSION = f.read().strip()

setup(
    name="mentat",
    version=VERSION,
    python_requires=">=3.10",
    packages=find_packages(include=["mentat", "mentat.*", "benchmarks", "benchmarks.*"]),
    install_requires=[
        str(r)
        for r in pkg_resources.parse_requirements(open(os.path.join(os.path.dirname(__file__), "requirements.txt")))
    ],
    entry_points={
        "console_scripts": [
            "mentat=mentat.terminal.client:run_cli",
            "mentat-server=mentat.server.mentat_server:main",
            "mentat-daemon=mentat.daemon:main",
        ],
    },
    description="AI coding assistant on your command line",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="Apache-2.0",
    include_package_data=True,
    extras_require={
        "dev": [
            str(r)
            for r in pkg_resources.parse_requirements(
                open(os.path.join(os.path.dirname(__file__), "dev-requirements.txt"))
            )
        ],
    },
)
