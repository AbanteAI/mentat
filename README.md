[![Twitter Follow](https://img.shields.io/twitter/follow/bio_bootloader?style=social)](https://twitter.com/bio_bootloader)
[![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)
# 🧙‍♂️ Mentat ⚡

> _It is by will alone I set my mind in motion_
> 
> The Mentat Mantra

The Mentats of Dune combine human creativity with computer-like processing - and now you can too.

---

Mentat is the AI tool that assists you with any coding task, right from your command line.

Unlike Copilot, Mentat coordinates edits across multiple locations and files. And unlike ChatGPT, Mentat already has the context of your project - no copy and pasting required!

Want help understanding a new codebase? Need to add a new feature? Refactor existing code? Mentat can do it!

# 🍿 Example Videos

Coming soon!

# ⚙️ Setup

## Install

If you just want to use Mentat, use one of these methods to install it:
- PyPI: coming soon!
- Github: `python -m pip install git+https://github.com/biobootloader/mentat.git`

If you are more adventurous and would like to use and edit Mentat, try this:
```
# Clone the repo
git clone https://github.com/biobootloader/mentat.git
cd mentat

# optionally, set up a virtual environment to install it in
# if you do this, you'll only be able to run mentat while it's activated
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# install with pip in editable mode:
pip install -e .
```

## Add your OpenAI API Key

You'll need to have API access to GPT-4 to run Mentat. There are a few options to provide Mentat with your OpenAI API key:

1. Create a `.env` file with the line `OPENAI_API_KEY=<your-api-key>` in the directory you plan to run mentat in or in `~/.mentat/.env`
2. Run `export OPENAI_API_KEY=<your key here>` prior to running Mentat
3. Place the previous command in your `.bashrc` or `.zshrc` to export your key on every terminal startup

## Configuration

For custom configuration options see [here](docs/configuration.md)


# 🚀 Usage
Run Mentat with:

`mentat <paths to files or directories>`

If you provide a directory, Mentat will add all non-hidden text files in that directory to it's context. If this exceeds the GPT-4 token context limit, try running Mentat with just the files you need it to see.
