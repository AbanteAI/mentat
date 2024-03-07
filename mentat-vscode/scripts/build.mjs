import * as esbuild from "esbuild";

const args = process.argv.slice(2);

function getFormattedDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = (now.getMonth() + 1).toString().padStart(2, "0");
  const day = now.getDate().toString().padStart(2, "0");
  const hours = now.getHours().toString().padStart(2, "0");
  const minutes = now.getMinutes().toString().padStart(2, "0");
  const seconds = now.getSeconds().toString().padStart(2, "0");
  const formattedDate = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  return formattedDate;
}

const esbuildProblemMatcherPlugin = {
  name: "esbuild-problem-matcher",
  setup(build) {
    build.onStart(() => {
      console.log(`${getFormattedDateString()} [watch] build started`);
    });
    build.onEnd((result) => {
      result.errors.forEach(({ text, file, line, column }) => {
        console.error(`✘ [ERROR] ${text}`);
        console.error(`    ${location.file}:${location.line}:${location.column}`);
      });
      console.log(`${getFormattedDateString()} [watch] build finished`);
    });
  },
};

const webviewOptions = {
  entryPoints: ["src/webviews/index.tsx"],
  bundle: true,
  outfile: "build/webviews/index.js",
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
  sourcemap: args.includes("--sourcemap") ? "inline" : false,
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
