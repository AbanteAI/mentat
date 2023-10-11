# Mentat VSCode Extension

## Local development setup

Make sure you're running Node v18.16.0

1. Install the project

```
npm install
```

2. Open VSCode

```
vscode .
```

3. Install all of the extensions in `./.vscode/extensions.json`

The VSCode debugger will use these for reading and handling errors from esbuild and
eslint.

4. Start the "Run Extension" launch configuration.

Press "f5" or navigate to the "Run and Debug" click the green arrow at the top of the
menu. The "Run Extension" launch configuration should be selected.

If everything runs correctly you should see:

- a second VSCode window opened with the Mentat extension logo in the sidebar
- the VSCode debugger active and attacked in the original VSCode window
- two "[watch] build finished" log messages in the terminal

5. Click on the Mentat extension

The extension will be built correctly if the sidebar is populated with the extension UI.

At this point in the **second** VSCode window (the one with the extension running) you
can load the webview debug tools. Open the command shortcut menu ("<cmd> + <shift> + P"
for macos) and type "Developer: Open Webview Developer Tools".

With the Webview Developer Tools panel active, Typescript files used in the webview can
be opened with the file browser menu ("<cmd> + P" for macos) and breakpoints can be set
as if you were setting breakpoints in a browser.
