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

### Filepath Include and Exclude list
Optional lists of regex patterns that determin which files or directories will be included 
or excluded from context. Either or both lists can be provided. If the file path matches 
both an inclusion rule and an exclusion rule, the exclusion rule always wins (including 
for example filetype exclusion wins over filepath inclusion).
```
{
    "filepath-include-only-these-regex-patterns": [".*/include_this"],
    "filepath-exclude-these-regex-patterns": [".*/exclude_this"]
}
```

### Disable .gitignore processing
There is currently an issue where large projects can overwhelm the test for .gitignore exclusion. This option
disables .gitignore testing to support working with those larger projects. Default is false, which
allows mentat to make use of git ignore testing.
```
{
    "do-not-check-git-ignored": true,
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

