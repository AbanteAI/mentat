<script>
  import Message from './Message.svelte';
  import InputField from './InputField.svelte';
  import Buttons from './Buttons.svelte';
  import { onDestroy, onMount } from 'svelte';
  
  export let vscode;
  export let restartMentat = () => {};

  let messages = [
    { type: 'assistant', value: 'Welcome to Mentat Chat!' }
  ];

  // Mentat input
  let prompt = '';
  const handleGetResponse = () => {
    if (!prompt) {
      return;
    }
    vscode.postMessage({ command: 'getResponse', data: prompt });
    // TODO: Move echo here
    prompt = '';
  }
  const handleInterrupt = () => {
    vscode.postMessage({ command: 'interrupt' });
  }
  
  // Mentat output
  let _isStreaming = false;
  const handleReceiveChunk = (event) => {
    const chunk = event.data;
    // Identify the target message
    const newMessages = [...messages];
    if (!_isStreaming) {
      newMessages.push({ type: chunk.type, value: '' });
    }
    // Update the value
    let newValue = newMessages[newMessages.length - 1].value;
    newValue += chunk.value;
    // Check for and remove control flags
    if (newValue.includes('@@startstream')) {
      _isStreaming = true;
      newValue = newValue.replace('@@startstream', '');
    }
    if (newValue.includes('@@endstream')) {
      _isStreaming = false;
      newValue = newValue.replace('@@endstream', '');
    }
    // Update the message
    if (newValue) {        
      newMessages[newMessages.length - 1].value = newValue;
    }
    messages = newMessages;
  }
  onMount(() => window.addEventListener('message', handleReceiveChunk));
  onDestroy(() => window.removeEventListener('message', handleReceiveChunk));

</script>

<div class="conversation">
  {#each messages as message}
    <Message {...message} />
  {/each}
</div>
<InputField bind:prompt handleGetResponse={handleGetResponse} />
<Buttons 
  handleGetResponse={handleGetResponse}
  handleInterrupt={handleInterrupt}
  handleRestart={restartMentat}
/>

<style>  
  .conversation {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    align-items: flex-start;
    flex-grow: 1;
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
</style>
