<script>
  import { onDestroy, onMount } from 'svelte';
  import Fa from 'svelte-fa'
  import { faPaperPlane, faStop, faArrowLeft } from '@fortawesome/free-solid-svg-icons'
  
  import Message from './Message.svelte';
  import InputField from './InputField.svelte';
  
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

<button class='back-button' on:click={restartMentat}>
  <Fa icon={faArrowLeft} />
  <div class='spacer' />
  Start Over
</button>
<div class="conversation">
  {#each messages as message}
    <Message {...message} />
  {/each}
</div>
<div class="control">
  <InputField bind:prompt handleGetResponse={handleGetResponse} />
  <div class='spacer' />
  {#if _isStreaming}
    <button on:click={handleInterrupt}>
      <Fa icon={faStop} />
    </button>
    {/if}
    {#if !_isStreaming }
    <button on:click={handleGetResponse}>
      <Fa icon={faPaperPlane} />
    </button>
  {/if}
</div>

<style>  
  .back-button {
    display: flex;
    flex-direction: row;
    justify-content: start;
    align-items: center;
    background-color: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    padding: 0.8em;
  }
  .back-button:hover {
    cursor: pointer;
    background-color: var(--vscode-button-hoverBackground);
  }
  .spacer {
    padding: 0.25em;
  }
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
  .control {
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    padding: 0.5em;
  } 
  .spacer {
    padding: 0.25em;
  }
</style>
