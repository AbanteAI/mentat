# 🔧 Configuration

To change Mentat's configuration, create `.mentat_config.json` in the git root of the project you are running Mentat for. Alternatively, creating `~/.mentat/.mentat_config.json` will create a default user config that Mentat will use if no config exists in your current git project.

## Options

### Allow 32k
Allow Mentat to use OpenAI's gpt-4 32k context window model. Your API key must already have access to the model.
```
{
    "allow-32k": true
}
```

### File Exclude Glob list
List of [glob patterns](https://docs.python.org/3/library/glob.html) to exclude files from being read/edited by Mentat. These take effect whenever you provide Mentat with a directory as an argument. Mentat will add all files in the directory that are not in your `.gitignore` and do not match these glob patterns. Glob patterns are interpreted from the git root location. If you wanted to exclude all files ending in `.py`, the pattern to use would be `**/*.py` rather than `*.py`. Here is an example that would exclude all hidden directories and files:
```
{
    "file-exclude-glob-list": ["**/.*, **/.*/**"]
}
```

### Input Style
A list of key-value pairs defining a custom [Pygment Style](https://pygments.org/docs/styledevelopment/) to style the Mentat prompt.
```
{
    "input-style": [
        [
            "",
            "#9835bd"
        ],
        [
            "prompt",
            "#ffffff bold"
        ],
        [
            "continuation",
            "#ffffff bold"
        ]
    ]
}
```

