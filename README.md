[![Twitter Follow](https://img.shields.io/twitter/follow/bio_bootloader?style=social)](https://twitter.com/bio_bootloader)
[![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)
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

## Selecting which LLM Model to use

We highly recommend using the default model, `gpt-4-1106-preview`, as it performs vastly better than any other model benchmarked so far. However, if you wish to use a different model, jump [here](#alternative-models).

### Add your OpenAI API Key

You'll need to have API access to GPT-4 to run Mentat. There are a few options to provide Mentat with your OpenAI API key:

1. Create a `.env` file with the line `OPENAI_API_KEY=<your-api-key>` in the directory you plan to run mentat in or in `~/.mentat/.env`
2. Run `export OPENAI_API_KEY=<your key here>` prior to running Mentat
3. Place the previous command in your `.bashrc` or `.zshrc` to export your key on every terminal startup

### Azure OpenAI

Mentat also works with the Azure OpenAI API. To use the Azure API, provide the `AZURE_OPENAI_ENDPOINT` (`https://<your-instance-name>.openai.azure.com/`) and `AZURE_OPENAI_KEY` environment variables instead of `OPENAI_API_KEY`.

In addition, Mentat uses the `gpt-4-1106-preview` model by default. When using Azure, you will have to set the model as described in [configuration.md](docs/configuration.md) to the name you gave your Azure model.

> [!IMPORTANT]
> Due to changes in the OpenAI Python SDK, you can no longer use `OPENAI_API_BASE` to access the Azure API with Mentat.

### Alternative Models

Mentat uses the OpenAI SDK to retrieve chat completions. This means that setting the `OPENAI_API_BASE` environment variable is enough to use any model that has the same response schema as OpenAI. To use models with different response schemas, we recommend setting up a litellm proxy as described [here](https://docs.litellm.ai/docs/proxy/quick_start) and pointing `OPENAI_API_BASE` to the proxy. ollama example:
```
# Ensure model is downloaded and ollama is being served
ollama pull llama2
ollama serve

- Listening on 127.0.0.1:11434

# In another terminal
pip install 'litellm[proxy]'
litellm --model ollama/llama2 --api_base http://localhost:11434 --drop_params

- Uvicorn running on http://0.0.0.0:8000

# In .env
OPENAI_API_BASE=http://localhost:8000
```
> [!NOTE]
> When using a litellm proxy, the model set in Mentat's config will not effect the model being run. To change the model, rerun the litellm proxy with a different model.

> [!IMPORTANT]
> Be sure to include the --drop_params argument when running the litellm proxy! Mentat uses some arguments (such as response_format) that may not be available in alternative models.

## Configuration

For custom configuration options see [configuration.md](docs/configuration.md)

## Install universal-ctags (required to use auto-context)

Installing [universal ctags](https://github.com/universal-ctags/ctags) is helpful if you want to use the auto-context system to have Mentat find relevant parts of files for you.

See the [official instructions](https://github.com/universal-ctags/ctags#the-latest-build-and-package) for installing univeresal ctags for your specific operating system, however you may be able to install a compatible version with one of the following commands:

**OSX**
```shell
brew update && brew install universal-ctags
```

**Ubuntu**
```shell
sudo apt update && sudo apt install universal-ctags
```

**Windows**
```shell
choco install universal-ctags
```


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

### Auto Context

The `Auto Context` feature in Mentat uses retrieval-augmented-generation (RAG) to select relevant snippets from your codebase to include with the user query. To enable `Auto Context`, use the `--auto-context` or `-a` flag when running Mentat:

```
mentat --auto-context
```

Auto-context will add code snippets in order of relevance up to the maximum (8000 tokens by default). Adjust the maximum number of tokens added by auto-context by using the `--auto-tokens` flag:

```
mentat -a --auto-tokens 8000
```

# 👩‍💻 Roadmap and Contributing

We welcome contributions! To coordinate, make sure to join the Discord server: [![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)

The goal for Mentat is to become the best way to write code. Some big improvements coming up are:
- improved user interface and options (VSCode and other editor integrations, etc)
- use with LLMs other than GPT-4
- seamlessly work with codebases much larger than LLM context limits, without requiring users to filter files manually
- improved edit quality

If this is something you'd like to work on, jump right in! And if you want to join the team to work on this full time, message [@bio_bootloader](https://twitter.com/bio_bootloader) on twitter.

To find something specific to work on, take a look at [open issues](https://github.com/AbanteAI/mentat/issues) and/or check this Github Project: [Mentat Development](https://github.com/users/biobootloader/projects/2)
