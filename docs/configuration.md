# 🔧 Configuration

To change Mentat's configuration, create `.mentat_config.json` in the git root of the project you are running Mentat for. Alternatively, creating `~/.mentat/.mentat_config.json` will create a default user config that Mentat will use if no config exists in your current git project.

## Options

### Use 32k
Allow Mentat to use OpenAI's gpt-4 32k context window model. Your API key must already have access to the model.
```json
{
    "model": "gpt-4-32k-0314"
}
```

### File Exclude Glob list
List of [glob patterns](https://docs.python.org/3/library/glob.html) to exclude files from being read/edited by Mentat. These take effect whenever you provide Mentat with a directory as an argument. Mentat will add all files in the directory that are not in your `.gitignore` and do not match these glob patterns. Glob patterns are interpreted from the git root location. If you wanted to exclude all files ending in `.py`, the pattern to use would be `**/*.py` rather than `*.py`. Here is an example that would exclude all hidden directories and files:
```json
{
    "file-exclude-glob-list": ["**/.*, **/.*/**"]
}
```

### Input Style
A list of key-value pairs defining a custom [Pygment Style](https://pygments.org/docs/styledevelopment/) to style the Mentat prompt.
```json
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

## 🦙 Alternative Models

Mentat uses [litellm](https://github.com/BerriAI/litellm), so you can direct it to use any local or hosted model. See their documentation to assist setting up any required environment variables, and set the model (and possibly llm_provider, if litellm doesn't automatically recognize the model) in `~/.mentat/.mentat_config.json`:
```json
{
    "model": "<model_name>",
    "llm-provider": "<litellm_llm_provider>"
}
```

### Maximum Context

If you use a model unknown to litellm, you can manually set the maximum context of the model like so:
```json
{
    "maximum-context": 16000
}
```
This can also be used to save costs by setting a more conservative limit on models with larger context sizes.

### Alternative Formats

Mentat is able to edit files by parsing a specific format that the model is told to follow. We are always working to improve the format we use, and have multiple formats available. Although we expect the default format to perform the best, you can test out other formats using the configuration.
```json
{
    "format": "block"
}
```
Available formats:
* block
* replacement
* unified-diff
