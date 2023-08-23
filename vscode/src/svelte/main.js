import App from './App.svelte';
import MockVSCode from '../test/MockVSCode';

let vscode;
try {
  // Running inside vscode
  vscode = acquireVsCodeApi();
} catch {
  // Running in a browser
  vscode = new MockVSCode();

  // Inject the vscode-styles.css into the head of the document
  const linkElement = document.createElement("link");
  linkElement.rel = "stylesheet";
  linkElement.href = "vscode-styles.css";
  document.head.appendChild(linkElement);
}

const app = new App({
	target: document.body,
	props: { vscode }
});

export default app;