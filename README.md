# ⚠️ ARCHIVED PROJECT ⚠️

This repository contains an archived version of Mentat, which was an AI-powered command line tool for coding assistance. This project is no longer maintained or supported.

## Important Note About the Current Mentat

The name "Mentat" is now used by a different project - a GitHub bot that helps with code reviews and issue resolution. If you're looking for the current Mentat GitHub bot, this is not the correct repository. The Mentat bot is a proprietary service by AbanteAI and is not open source.

---

# Historical Information: Mentat CLI Tool

This was a command-line tool that assisted with coding tasks using AI. Below is the historical documentation kept for reference:

> _It is by will alone I set my mind in motion_
>
> The Mentat Mantra

Unlike Copilot, Mentat coordinates edits across multiple locations and files. And unlike ChatGPT, Mentat already has the context of your project - no copy and pasting required!

Want help understanding a new codebase? Need to add a new feature? Refactor existing code? Mentat can do it!

# 🍿 Example Videos (🔊 on!)

https://github.com/AbanteAI/mentat/assets/128252497/35b027a9-d639-452c-a53c-ef019a645719

See more videos on [Twitter](https://twitter.com/bio_bootloader/status/1683906735248125955) or YouTube:

-   [Intro (2 min - same video as above)](https://www.youtube.com/watch?v=lODjaWclwpY)
-   [Explaining and editing Llama2.c (3 min)](https://www.youtube.com/watch?v=qSyTWMFOjPs)
-   [More Mentat features (4 min)](https://www.youtube.com/watch?v=YJLDIqq8k2A)

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

-   PyPI: `python -m pip install mentat`
-   Github: `python -m pip install git+https://github.com/AbanteAI/mentat.git`

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

If you want to use a models through Azure, Ollama or other services see [this doc](https://docs.mentat.ai/en/latest/user/alternative_models.html) for details.

# 🚀 Usage

Run Mentat from within your project directory. Mentat uses git, so if your project doesn't already have git set up, run `git init`. Then you can run Mentat with:

`mentat <paths to files or directories>`

List the files you would like Mentat to read and edit as arguments. Mentat will add each of them to context, so be careful not to exceed the GPT-4 token context limit. To add multiple files at once, you can also provide directories as arguments. When a directory is provided, Mentat will add all the contained files, except for ones ignored in your `.gitignore`. In addition to files and directories, you can use [glob patterns](https://docs.python.org/3/library/glob.html) to add multiple files at once.

For more information on commands, configuration or using other models see [the documentation](https://docs.mentat.ai/en/latest/user/guides.html).

## MacOS Visual Artifacts

Mentat uses [Textual](https://textual.textualize.io/). On MacOS, Textual may not render the TUI correctly; if you run into this problem, use the fix [here](https://textual.textualize.io/FAQ/#why-doesnt-textual-look-good-on-macos).

# ℹ️ Project Status

This project has been archived and is no longer maintained. The development team has moved on to other projects, including the current Mentat GitHub bot. We recommend looking for alternative active projects if you need a command-line AI coding assistant.

If you're interested in AbanteAI's current work, you can follow them on Twitter: [@AbanteAI](https://twitter.com/AbanteAi).
