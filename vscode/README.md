# Mentat Visual Studio Code Extension

## Install

1. Install Javascript dependencies with `npm`:
    ```
    npm install
    ```
2. Install and activate a virtual environment:
    ```
    # Unix/macOS
    python3 -m venv venv
    source venv/bin/activate

    # Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3. Install `nox` in the activated environment: 
    ```
    python -m pip install nox
    ```    
4. Install Python dependencies:
    ```
    nox -s setup
    ```
5. Run in debugger by pressing `F5` or `Run > Start Debugging` from the VSCode menu



## Build and Deploy

1. Build `mentat.vsix`:
    ```
    nox -s build_package
    ```
    **Note**: This file can be shared and installed manually via `Extensions Panel > Views > Install from VSIX..`

## Notes

This directory was cloned from the [Template for VSCode python tools extensions](https://github.com/microsoft/vscode-python-tools-extension-template) provided by Microsoft.