import * as esbuild from "esbuild";

const args = process.argv.slice(2);

const esbuildProblemMatcherPlugin = {
  name: "esbuild-problem-matcher",
  setup(build) {
    build.onStart(() => {
      console.log("[watch] build started");
    });
    build.onEnd((result) => {
      result.errors.forEach(({ text, file, line, column }) => {
        console.error(`✘ [ERROR] ${text}`);
        console.error(`    ${location.file}:${location.line}:${location.column}`);
      });
      console.log("[watch] build finished");
    });
  },
};

const webviewOptions = {
  entryPoints: ["src/webview/index.tsx"],
  bundle: true,
  outfile: "build/webview/index.js",
  sourcemap: args.includes("--sourcemap") ? "inline" : false,
  minify: args.includes("--minify"),
  plugins: [esbuildProblemMatcherPlugin],
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
  plugins: [esbuildProblemMatcherPlugin],
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
