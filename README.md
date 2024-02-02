[![Twitter Follow](https://img.shields.io/twitter/follow/AbanteAi?style=social)](https://twitter.com/AbanteAi)
[![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)
[![Documentation Status](https://readthedocs.org/projects/mentat-ai/badge/?version=latest)](https://docs.mentat.ai/en/latest/?badge=latest)
[![Stable Version](https://img.shields.io/pypi/v/mentat?color=blue)](https://pypi.org/project/mentat/)
[![License](https://img.shields.io/pypi/l/mentat.svg)](https://github.com/AbanteAI/mentat/blob/main/LICENSE)

# 🧙‍♂️ Mentat ⚡

> _It is by will alone I set my mind in motion_
> 
> The Mentat Mantra

The Mentats of Dune combine human creativity with computer-like processing - and now you can too.

---

Mentat is the AI tool that assists you with any coding task, right from your command line.

Unlike Copilot, Mentat coordinates edits across multiple locations and files. And unlike ChatGPT, Mentat already has the context of your project - no copy and pasting required!

Want help understanding a new codebase? Need to add a new feature? Refactor existing code? Mentat can do it!

# 🍿 Example Videos (🔊 on!)

https://github.com/AbanteAI/mentat/assets/128252497/35b027a9-d639-452c-a53c-ef019a645719

See more videos on [Twitter](https://twitter.com/bio_bootloader/status/1683906735248125955) or YouTube:
- [Intro (2 min - same video as above)](https://www.youtube.com/watch?v=lODjaWclwpY)
- [Explaining and editing Llama2.c (3 min)](https://www.youtube.com/watch?v=qSyTWMFOjPs)
- [More Mentat features (4 min)](https://www.youtube.com/watch?v=YJLDIqq8k2A)

# ⚙️ Setup

[Installation and Setup Demonstration Video](https://www.youtube.com/watch?v=bVJP8hY8uRM)

## Install

It is recommended you install this package in a virtualenv:

```
# Python 3.10 or higher is required
python3 -m venv .venv
source .venv/bin/activate
```

Note that you'll have to have activated the virtual environment to run mentat if you install it there.

There are then 3 install methods. The first two will just let you run it:
- PyPI: `python -m pip install mentat`
- Github: `python -m pip install git+https://github.com/AbanteAI/mentat.git`

The third option is useful if you'd also like to modify Mentat's code, as well as run it:

```
git clone https://github.com/AbanteAI/mentat.git
cd mentat

# install with pip in editable mode:
pip install -e .
```

### Add your OpenAI API Key

There are a few options to provide Mentat with your OpenAI API key:

1. Create a `.env` file with the line `OPENAI_API_KEY=<your-api-key>` in the directory you plan to run mentat in or in `~/.mentat/.env`
2. Run `export OPENAI_API_KEY=<your key here>` prior to running Mentat
3. Place the previous command in your `.bashrc` or `.zshrc` to export your key on every terminal startup

If you want to use a models through Azure, Ollama or other service see [this doc](https://docs.mentat.ai/en/latest/user/alternative_models.html) for details.

# 🚀 Usage

Run Mentat from within your project directory. Mentat uses git, so if your project doesn't already have git set up, run `git init`. Then you can run Mentat with:

`mentat <paths to files or directories>`

List the files you would like Mentat to read and edit as arguments. Mentat will add each of them to context, so be careful not to exceed the GPT-4 token context limit. To add multiple files at once, you can also provide directories as arguments. When a directory is provided, Mentat will add all the contained files, except for ones ignored in your `.gitignore`. In addition to files and directories, you can use [glob patterns](https://docs.python.org/3/library/glob.html) to add multiple files at once.

For more information on commands, configuration or using other models see [the documentation](https://docs.mentat.ai/en/latest/user/guides.html).

# 👩‍💻 Roadmap and Contributing

We welcome contributions! To coordinate, make sure to join the Discord server: [![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)

The goal for Mentat is to become the best way to write code. Some big improvements coming up are:
- improved user interface and options (VSCode and other editor integrations, etc)
- use with LLMs other than GPT-4
- seamlessly work with codebases much larger than LLM context limits, without requiring users to filter files manually
- improved edit quality

If this is something you'd like to work on, jump right in! And if you want to join the team to work on this full time, message [@bio_bootloader](https://twitter.com/bio_bootloader) on twitter.

To find something specific to work on, take a look at [open issues](https://github.com/AbanteAI/mentat/issues).
