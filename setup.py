import os
from pathlib import Path

import pkg_resources
from setuptools import find_packages, setup

from mentat import __version__

readme_path = os.path.join(Path(__file__).parent, "README.md")
with open(readme_path, "r", encoding="utf-8") as f:
    long_description = f.read()


setup(
    name="mentat",
    version=__version__,
    python_requires=">=3.10",
    packages=find_packages(
        include=["mentat", "mentat.*", "benchmarks", "benchmarks.*"]
    ),
    install_requires=[
        str(r)
        for r in pkg_resources.parse_requirements(
            open(os.path.join(os.path.dirname(__file__), "requirements.txt"))
        )
    ],
    entry_points={
        "console_scripts": [
            "mentat=mentat.terminal.client:run_cli",
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
        ]
    },
)
