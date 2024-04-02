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

-   [Intro (2 min - same video as above)](https://www.youtube.com/watch?v=lODjaWclwpY)
-   [Explaining and editing Llama2.c (3 min)](https://www.youtube.com/watch?v=qSyTWMFOjPs)
-   [More Mentat features (4 min)](https://www.youtube.com/watch?v=YJLDIqq8k2A)

### Add your OpenAI API Key

Create a `.env` file with the line `OPENAI_API_KEY=<your-api-key>` in your workspace or in `~/.mentat/.env`.
If you want to use a models through Azure, Ollama or other service see [this doc](https://docs.mentat.ai/en/latest/user/alternative_models.html) for details.

# 🚀 Usage

Right click the files you would like Mentat to read and edit and click 'Mentat: Include File'. Mentat will add them to context, so be careful not to exceed the GPT-4 token context limit. To add multiple files at once, you can also add directories. When a directory is provided, Mentat will add all the contained files, except for ones ignored in your `.gitignore`.

For more information on commands, configuration or using other models see [the documentation](https://docs.mentat.ai/en/latest/user/guides.html).

# 👩‍💻 Roadmap and Contributing

We welcome contributions! To coordinate, make sure to join the Discord server: [![Discord Follow](https://dcbadge.vercel.app/api/server/XbPdxAMJte?style=flat)](https://discord.gg/zbvd9qx9Pb)

The goal for Mentat is to become the best way to write code. Some big improvements coming up are:

-   seamlessly work with codebases much larger than LLM context limits, without requiring users to filter files manually
-   improved edit quality

If this is something you'd like to work on, jump right in! And if you want to join the team to work on this full time, message [@bio_bootloader](https://twitter.com/bio_bootloader) on twitter.

To find something specific to work on, take a look at [open issues](https://github.com/AbanteAI/mentat/issues).
