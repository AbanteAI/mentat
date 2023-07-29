from setuptools import find_packages, setup


def read_requirements(file):
    with open(file, "r") as f:
        return f.read().splitlines()


setup(
    name="mentat-ai",
    version="0.1.5",
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
    description="AI Coding Assistant",
    license="Apache-2.0",
)
