import * as esbuild from "esbuild";

const args = process.argv.slice(2);

// Webview

const webviewOnEndPlugin = {
  name: "onEnd",
  setup(build) {
    build.onEnd((result) => {
      console.log(`webview build ended with ${result.errors.length} errors`);
    });
  },
};

const webviewOptions = {
  entryPoints: ["src/webview/index.tsx"],
  bundle: true,
  outfile: "build/webview/index.js",
  sourcemap: args.includes("--sourcemap"),
  minify: args.includes("--minify"),
  plugins: [webviewOnEndPlugin],
};

// Extension

const extensionOnEndPlugin = {
  name: "onEnd",
  setup(build) {
    build.onEnd((result) => {
      console.log(`extension build ended with ${result.errors.length} errors`);
    });
  },
};

const extensionOptions = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "build/extension.js",
  external: ["vscode"],
  format: "cjs",
  platform: "node",
  sourcemap: args.includes("--sourcemap"),
  minify: args.includes("--minify"),
  plugins: [extensionOnEndPlugin],
};

if (args.includes("--watch")) {
  const webviewContext = await esbuild.context(webviewOptions);
  const extensionContext = await esbuild.context(extensionOptions);

  await webviewContext.watch();
  await extensionContext.watch();
} else {
  await esbuild.build(webviewOptions);
  await esbuild.build(extensionOptions);
}
