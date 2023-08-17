// @ts-ignore 

// This script will be run within the webview itself
// It cannot access the main VS Code APIs directly.
(function () {
  const vscode = acquireVsCodeApi();

  // Handle messages sent from the extension to the webview
  window.addEventListener("message", (event) => {
    // Get the message from the event
    const message = event.data;

    // Create a new element for message
    const _messageElement = document.createElement("div");
    _messageElement.classList.add('message');
    if (['user', 'assistant', 'system'].includes(message.type)) {
      _messageElement.classList.add(message.type);
    }
    _messageElement.innerHTML = message.value;

    // Append the message to the container
    const conversationContainer = document.getElementById("conversation-container");
    conversationContainer.appendChild(_messageElement);
  });

  // Listen for keyup events on the prompt input element
  document.getElementById('prompt').addEventListener('keyup', function (e) {
    // If the key that was pressed was the Enter key
    if (e.keyCode === 13) {
      vscode.postMessage({
        type: 'message',
        data: { type: 'user', value: this.value }
      });
      this.value = '';
    }
  });

  // Listen for clicks
  const buttons = ['get-response', 'interrupt', 'restart'];
  buttons.forEach(button => {
    document.getElementById(button).addEventListener('click', function () {
      vscode.postMessage({
        type: 'action',
        data: { value: button }
      });
    });
  });
})();