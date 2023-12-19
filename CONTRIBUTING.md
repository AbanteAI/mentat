# Welcome #

We're so glad you're thinking about contributing to the Mentat project!  If you're unsure or afraid of anything, just ask or submit the issue or pull request anyway.  The worst that can happen is that you'll be politely asked to change something.  We appreciate any sort of contribution, and don't want a wall of rules to get in the way of that.

Before contributing, we encourage you to read our CONTRIBUTING policy (you are here), our [LICENSE](LICENSE), and our [README](README.md), all of which should be in this repository.

## Issues ##

If you want to report a bug or request a new feature, the most direct method is to [create an issue](https://github.com/AbanteAI/mentat/issues/new) in this repository.  We recommend that you first search through existing issues (both open and closed) to check if your particular issue has already been reported.  If it has then you might want to add a comment to the existing issue.  If it hasn't then feel free to create a new one.

## Pull requests ##

If you choose to [submit a pull request](https://github.com/AbanteAI/mentat/pulls), you will notice that our continuous integration (CI) system runs a fairly extensive set of linters and syntax checkers.  Your pull request may fail these checks, and that's OK.  If you want you can stop there and wait for us to make the necessary corrections to ensure your code passes the CI checks.

If you want to make the changes yourself, or if you want to become a regular contributor, then you will want to set up [pre-commit](https://pre-commit.com/) on your local machine.  Once you do that, the CI checks will run locally before you even write your commit message.  This speeds up your development cycle considerably.

## Getting Started

### Contribution Process.

Mentat follows the usual open source contribution process on Github. In order to contribute, you must fork the repository, create a branch based on the main branch, make your changes there and then create a pull request. Github has excellent documentation (and contributed documentation and videos) on how to do this. See [Contributing to a project](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project), [first contributions](https://github.com/firstcontributions/first-contributions) for more details.

The project, like most projects, does have some customizations specific to Mentat such as code formatting, quality checks which are enforced on each pull request using Github actions. Pull Requests (PRs - described later) are not accepted unless all the checks are passed.

### Setup the Environment.

Mentat requires Python (version 3.10 or later) for development. The source code comes with two sets of requirements. The first in requirements.txt are needed to run Mentat. The second additional requirements in dev-requirements.txt are needed to do development work. As a contributor you will need to install both sets of requirements to have the full set of tools. In addition you will need some tools outside of the python environment. 

#### Python Virtual Environment setup

For python it is best to setup a virtual environment dedicated to mentat development to avoid any conflicts with other projects. This section is not meant to be comprehensive in setting up python virtual environments. There are good tutorials on how to do that such as [Python Virtual Environments](https://www.arch.jhu.edu/python-virtual-environments/).  the notes below are supplemental to help with Mentat development.

##### Conda (anaconda) Specific Notes

Since not all the requirements are available in the conda repositories, it will be necessary to use pip to install the requirements. In order to avoid conflicts between installation using conda and pip you should add the following to your `.condarc` file (the location of the file varies based on the OS - but typically is in the users home directory):

```
pip_interop_enabled: true
```

## Commit Message Guidelines

The guidelines below are for commit messages. While currently not enforced, eventually we will enforce the guidelines and use them for the [CHANGELOG.md][changelog-uri] generation and we strongly encourage following the guidelines.

```text
<TYPE>(<SCOPE>): imperative subject in present tense less than 80 characters
NOTES:
Add any additional notes in imperative present tense.
BREAKING CHANGE:
Describe the previous behavior in contrast to the new behavior and how it might effect consumers.
```

Allows types are:

* **feat**: represents a new feature
* **fix**: represents a bug fix
* **build**: changes to the gitlab pipeline or build scripts
* **refactor**: refactor code without expecting any behavioral change
* **test**: updates to test code only
* **perf**: updates for performance only (should include a benchmark for verification)
* **docs**: update to documentation only
* **style**: changes to style only (reformatting, whitespace changes, etc)

The `(<SCOPE>)` argument should only be included if the change is isolated to a single module. This should be the name
of the module that was modified.

Only include a BREAKING CHANGE footer if necessary. Only include a NOTES body if it adds appropriate value.

The header line **SHOULD** be in all lowercase characters and exclude any special characters other than the semi-colon
and the parentheses around the scope (if included).

Example commit message:

```text
docs: add documentation on contributing.
* initial creation of the contributing documentation.
NOTES:
Contirbution follows the usual Github open source contribution mechanism. However, there are some customizations specific to Mentat. The general approach, where to find more information and Mentat specific guidelines are documented here.
```

## Code review and Merge approval ##

In order to maintain standardization of practices, ensure security standards are being met, and to incorporate third party code as seamlessly as possible, all submitted code will go through a code review and merge approval process.

Code contributors are able to coordinate with the Mentat team at any point during the contribution process. We recommend initiating the discussions as early as possible, to decrease the likelihood of issues around merging or using the contributed code occurring late in the process. 

The type of contribution being made (e.g. typo corrections vs. a new repository), complexity of code change (e.g. adding a new test vs. adding a new function), and the testability of the code (e.g. well-documented and replicable) will factor into the level of interaction needed with the Mentat team.

**Keep in mind this is an open source project manned by volunteers. This means that there is no guarantee on acceptance of contributions or turn around time for responding to any issues, pull requests.**

## Attribution ##

This file is based on the CONTRIBUTING.md document from the public domain [development-guide](https://github.com/cisagov/development-guide) project.

