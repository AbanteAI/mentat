import os
from pathlib import Path

from setuptools import find_packages, setup


def read_requirements(file):
    with open(file, "r") as f:
        return f.read().splitlines()


readme_path = os.path.join(Path(__file__).parent, "README.md")
with open(readme_path, "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="mentat-ai",
    version="0.1.9",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=read_requirements("requirements.txt"),
    package_data={
        "mentat": ["default_config.json"],
    },
    entry_points={
        "console_scripts": [
            "mentat=mentat.app:run_cli",
        ],
    },
    description="AI coding assistant on your command line",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="Apache-2.0",
)
