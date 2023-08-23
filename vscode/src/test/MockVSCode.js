// This class replaces `acquireVsCodeApi()` for testing or when running in a browser.

export default class MockVSCode {
  _streaming = false;
  _interrupt = false;
  _chunkLength = 2;

  postMessage(message) {
    // Send a message OUT to vscode.extension
    console.log('Message OUT', message);
    switch (message.command) {
      case 'getPaths':
        this.respond('paths', ['main.js', 'main.css', 'index.html']);
        break;
      case 'getResponse':
        this.respond('user', message.data);
        this.stream(`Responding to ${message.data}`);
        break;
      case 'interrupt':
        if (!this._streaming) {
          this._interrupt = true;
        };
        break;
      default:
        message;
        break;
    }
  }

  respond(type, value) {
    // Send a message IN to the browser
    console.log('Message IN', { type, value });
    window.postMessage({ type, value });
  }

  async stream(value) {
    // Stream a message to the browser
    this._streaming = true;
    const endStream = () => {
      this._interrupt = false;
      this._streaming = false;
      this.respond('assistant', '@@endstream');
    };
    this.respond('assistant', '@@startstream');
    let remaining = value;
    while (true) {
      if (this._interrupt) {
        endStream();
        break;
      }
      const chunk = remaining.slice(0, this._chunkLength);
      remaining = remaining.slice(this._chunkLength);
      this.respond('assistant', chunk);
      if (!remaining) {
        endStream();
        break;
      }
      // Sleep 100 ms
      await new Promise(resolve => setTimeout(resolve, 100));
    };
  }
}
