# Mentat Visual Studio Code Extension

## Setup
Setup the extension environment by installing Javascript and Python dependencies:
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
5. Run in debugger by pressing `F5` or `Run > Start Debugging` from the VSCode menu. In order to run this step, your workspace folder must be set to `mentat/vscode`. If you're in the `mentat` repo, that means opening a new window in the sub-folder.

## Build and Deploy
Compile the extension into a `vsix` file. This is used to publish, and can also be shared and installed manually via `Extensions Panel > Views > Install from VSIX..`
1. Build `mentat.vsix`:
    ```
    nox -s build_package
    ```

## Run in Web Browser
The Javascript/Svelte portion of the code can be run separate from the vscode extension. This is useful during development as hot-reload is not supported by vscode extensions.

1. Start the frontend-development server:
    ```
    npm run start
    ```
2. Go to `localhost:3000` in your browser

## Notes

This directory was cloned from the [Template for VSCode python tools extensions](https://github.com/microsoft/vscode-python-tools-extension-template) provided by Microsoft.