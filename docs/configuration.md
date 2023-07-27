# 🔧 Configuration

To change Mentat's default configuration, create `~/.mentat/config.json` and add the fields you want to change.

## Options

### Allow 32k
___
Allow Mentat to use OpenAI's gpt-4 32k context window model. Your API key must already have access to the model.
```
{
    "allow-32k": true
}
```

### Filetype Include and Exclude list
Determines which file types inside of a directory will be automatically included or excluded from context when Mentat is given a directory. This will not affect hidden files, ignored files, or files specified by their direct path.
```
{
    "filetype-include-list": [".include_this"],
    "filetype-exclude-list": [".exclude_this"]
}
```

### File Exclude Glob list
List of [glob patterns](https://docs.python.org/3/library/glob.html) that will exclude all files from context that it matches starting from the given directory.
```
{
    "file-exclude-glob-list": ["**/exclude_this.*"]
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

