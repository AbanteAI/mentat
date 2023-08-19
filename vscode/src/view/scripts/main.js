// @ts-ignore 

// This script will be run within the webview itself
// It cannot access the main VS Code APIs directly.
(function () {
  const vscode = acquireVsCodeApi();
  
  // Handle messages sent from the extension to the webview
  let _streamToElement = null;
  window.addEventListener("message", (event) => {
    const message = event.data;

    // Create a new message or append to streaming message
    let _messageElement = _streamToElement;
    if (!_messageElement) {
      // Create a new element for message
      _messageElement = document.createElement("div");
      _messageElement.classList.add('message');
      if (['user', 'assistant', 'system'].includes(message.type)) {
        _messageElement.classList.add(message.type);
      }
      // Append the message to the container
      const conversationContainer = document.getElementById("conversation-container");
      conversationContainer.appendChild(_messageElement);
    }
    
    if (message.value.includes('@@startstream')) {
      message.value = message.value.replace('@@startstream', '');
      _streamToElement = _messageElement;
    }
    if (message.value.includes('@@endstream')) {
      message.value = message.value.replace('@@endstream', '');
      _streamToElement = null;
    }
    
    _messageElement.innerHTML += message.value;
  });

  // Handle vscode extension commands
  const handleGetResponse = () => {
    const input = document.getElementById('prompt').value;
    if (input) {      
      vscode.postMessage({ command: 'getResponse', data: input });
      document.getElementById('prompt').value = '';
    }
  };

  const handleInterrupt = () => {
    vscode.postMessage({ command: 'interrupt' });
  };

  const handleRestart = () => {
    vscode.postMessage({ command: 'restart' });
  };


  // Add listeners to page elements
  document.getElementById('prompt').addEventListener('keyup', function (e) {
    // If the key that was pressed was the Enter key
    if (e.keyCode === 13) {
      handleGetResponse();
    }
  });
  document.getElementById('get-response').addEventListener('click', handleGetResponse);
  document.getElementById('interrupt').addEventListener('click', handleInterrupt);
  document.getElementById('restart').addEventListener('click', handleRestart);

})();