import App from './App.svelte';
import MockVSCode from '../test/MockVSCode';
import { VsCodeApi } from '../types/globals';

// Acquire context: vscode or mock
declare function acquireVsCodeApi(): VsCodeApi;
let vscode: VsCodeApi;
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

// Initialize Svelte app with context
const app = new App({
	target: document.body,
	props: { vscode }
});

export default app;