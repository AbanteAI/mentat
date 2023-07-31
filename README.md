[![Twitter Follow](https://img.shields.io/twitter/follow/bio_bootloader?style=social)](https://twitter.com/bio_bootloader)
[![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)
[![Stable Version](https://img.shields.io/pypi/v/mentat-ai?color=blue)](https://pypi.org/project/mentat-ai/)
[![License](https://img.shields.io/pypi/l/mentat-ai.svg)](https://github.com/biobootloader/mentat/blob/main/LICENSE)

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

https://github.com/biobootloader/mentat/assets/128252497/35b027a9-d639-452c-a53c-ef019a645719

See more videos on [Twitter](https://twitter.com/bio_bootloader/status/1683906735248125955) or YouTube:
- [Intro (2 min - same video as above)](https://www.youtube.com/watch?v=lODjaWclwpY)
- [Explaining and editing Llama2.c (3 min)](https://www.youtube.com/watch?v=qSyTWMFOjPs)
- [More Mentat features (4 min)](https://www.youtube.com/watch?v=YJLDIqq8k2A)

# ⚙️ Setup

[Installation and Setup Demonstration Video](https://www.youtube.com/watch?v=bVJP8hY8uRM)

## Install

Before installing, it's suggested that you create a virtual environment to install it in:

```
# Python 3.10 or higher is required
python3 -m venv .venv
source .venv/bin/activate
```

Note that you'll have to have activated the virtual environment to run mentat if you install it there.

There are then 3 install methods. The first two will just let you run it:
- PyPI: `python -m pip install mentat-ai`
- Github: `python -m pip install git+https://github.com/biobootloader/mentat.git`

The third option is useful if you'd also like to modify Mentat's code, as well as run it:

```
git clone https://github.com/biobootloader/mentat.git
cd mentat

# install with pip in editable mode:
pip install -e .
```

## Add your OpenAI API Key

You'll need to have API access to GPT-4 to run Mentat. There are a few options to provide Mentat with your OpenAI API key:

1. Create a `.env` file with the line `OPENAI_API_KEY=<your-api-key>` in the directory you plan to run mentat in or in `~/.mentat/.env`
2. Run `export OPENAI_API_KEY=<your key here>` prior to running Mentat
3. Place the previous command in your `.bashrc` or `.zshrc` to export your key on every terminal startup

## Configuration

For custom configuration options see [configuration.md](docs/configuration.md)


# 🚀 Usage

Run Mentat from within your project directory. Mentat uses git, so if your project doesn't already have git set up, run `git init`. Then you can run Mentat with:

`mentat <paths to files or directories>`

List the files you would like Mentat to read and edit as arguments. Mentat will add each of them to context, so be careful not to exceed the GPT-4 token context limit. To add multiple files at once, you can also provide directories as arguments. When a directory is provided, Mentat will add all the contained files, except for ones ignored in your `.gitignore`. In addition to files and directories, you can use [glob patterns](https://docs.python.org/3/library/glob.html) to add multiple files at once.

## Options

### Exclude Files

Exclude given paths, directories, or [glob patterns](https://docs.python.org/3/library/glob.html) from Mentat's context. Takes precedence over included file paths.
```
mentat path/to/directory --exclude exclude_me.py dir1/dir2 **/*.ts
```
