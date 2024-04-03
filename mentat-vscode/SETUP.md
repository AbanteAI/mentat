# Mentat VSCode Extension

## Local development setup

These instructions will run through the workflow of running the project locally and
(optionally) using the VSCode debugger for the extension and the webviews.

### Prerequisites

-   VSCode
-   Node v18.16.0

### Steps

1. Install the project

```shell
npm install
```

2. Build the project (if you are getting the error `Cannot find module extension.js...` you probably need to run this!)

```shell
npm run build
```

3. If you want to test changes to Mentat on a branch, you need to egg install (`pip install -e path/to/repo`)
   your branch of mentat into a venv at `~/.mentat/.venv`; otherwise, the extension will automatically pip install mentat for you.

**Without the VSCode Debugger**

If you want to just open VSCode with the extension running (without the VSCode
Debugger), use:

```shell
npm run vscode
```

At this point the extension is running and you should see the Mentat logo attached to
the sidebar. You don't have to follow the rest of the setup instructions. Congrats!

**With the VSCode Debugger**

If you want to open VSCode with the javascript debugger active and debug the running
extension, use:

```shell
code .
```

3. Start the "Run Extension" launch configuration.

Press "f5" or navigate to the "Run and Debug" menu on the sidebar click the green arrow
at the top of the menu. The "Run Extension" launch configuration should be selected.

If everything runs correctly you should see:

-   a second VSCode window opened with the Mentat extension logo in the sidebar
-   the VSCode debugger active and attached in the original VSCode window
-   two "[watch] build finished" log messages in the terminal (one for the extension and
    one for the webview)

4. Click on the Mentat extension menu on the sidebar

The extension will be built correctly if the sidebar is populated with the extension UI.

At this point in the **second** VSCode window (the one with the extension running) you
can load the webview debug tools. Open the command shortcut menu ("\<cmd\> + \<shift\> +
P" for macos) and type "Developer: Open Webview Developer Tools".

With the Webview Developer Tools panel active, Typescript files used in the webview can
be opened with the file browser menu ("\<cmd\> + P" for macos) and breakpoints can be
set as if you were setting breakpoints in a browser.

The extension and webviews will be rebuilt automatically on save, however to see your
changes you need to refresh the VSCode window running the extension manually ("\<cmd\> +
R" for macos).

## Code structure

We use prettier as our linter. The extension code is broken up into 2 main sections:

-   The extension. This is all the code need to mount/unstop the extension, interact with
    VSCode resources, and run any background processes managed by VSCode.
-   The webview. This is all all the React code thats rendered and injected into VSCode
    "webviews".

## Publishing

TODO
