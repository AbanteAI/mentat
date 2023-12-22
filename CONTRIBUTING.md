# Welcome #

We're so glad you're thinking about contributing to Mentat!  If you're unsure of anything feel free to ask us or submit an issue.  We appreciate any all contributions, and are excited to see what you add to Mentat!

Before contributing, we encourage you to read our CONTRIBUTING policy (you are here), our [LICENSE](LICENSE), and our [README](README.md).

## Issues ##

If you want to report a bug or request a new feature, the most direct method is to [create an issue](https://github.com/AbanteAI/mentat/issues/new) in this repository.  We recommend that you first search through existing issues (both open and closed) to check if your particular issue has already been reported.  If it has then you might want to add a comment to the existing issue.  If it hasn't then feel free to create a new one.

## Pull requests ##

If you choose to [submit a pull request](https://github.com/AbanteAI/mentat/pulls), you will notice that our continuous integration (CI) system runs a fairly extensive set of linters and syntax checkers.  Your pull request may fail these checks, and that's OK.  If you want you can stop there and wait for us to make the necessary corrections to ensure your code passes the CI checks.

If you want to make the changes yourself, or if you want to become a regular contributor, then you may find it helpful to set up [pre-commit](https://pre-commit.com/) on your local machine.  pre-commit will run the CI checks  locally before you even write your commit message, which can speed up the development cycle considerably.

## Getting Started

### Contribution Process

Mentat follows the usual open source contribution process on Github. In order to contribute, you must fork the repository, create a branch based on the main branch, make your changes there and then create a pull request. Github has excellent documentation (and contributed documentation and videos) on how to do this. See [Contributing to a project](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project), [first contributions](https://github.com/firstcontributions/first-contributions) for more details.

The project, like most projects, does have some customizations specific to Mentat such as code formatting, quality checks which are enforced on each pull request using Github actions. Pull Requests (PRs - described later) are not accepted unless all the checks are passed.

### Setup the Environment

Mentat requires Python (version 3.10 or later) for development. The source code comes with two sets of requirements. The first in requirements.txt are needed to run Mentat. The second additional requirements in dev-requirements.txt are needed to do development work. As a contributor you will need to install both sets of requirements. In addition, you may need some tools outside of the python environment. 

#### Python Virtual Environment setup

We recommend using a python virtual environment dedicated to Mentat development to avoid any conflicts with other projects. One tutorial on setting up python virtual environments can be found here: [Python Virtual Environments](https://www.arch.jhu.edu/python-virtual-environments/). 

##### Conda (anaconda) Specific Notes

Since not all the requirements are available in the conda repositories, it will be necessary to use pip to install the requirements. In order to avoid conflicts between installation using conda and pip you should add the following to your `.condarc` file (the location of the file varies based on the OS - but typically is in the users home directory):

```
pip_interop_enabled: true
```

## Code review and Merge approval ##

In order to maintain standardization of practices, ensure security standards are being met, and to incorporate third party code as seamlessly as possible, all submitted code will go through a code review and merge approval process.

Code contributors are able to coordinate with the Mentat team at any point during the contribution process. We recommend initiating the discussions as early as possible, to decrease the likelihood of issues around merging or using the contributed code occurring late in the process. 

## Attribution ##

This file is based on the CONTRIBUTING.md document from the public domain [development-guide](https://github.com/cisagov/development-guide) project.

