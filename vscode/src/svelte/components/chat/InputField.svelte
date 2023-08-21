<script>
  export let handleGetResponse = () => {};
  export let prompt = '';
</script>

<input 
  bind:value={prompt} 
  class="input" 
  type="text" 
  placeholder="Enter a prompt" 
  on:keyup={(e) => {
    if (e.keyCode === 13) {
      handleGetResponse();
    }
  }}
/>

<style>
  .input {
    height: 2em;
    width: 100%;
    background-color: var(----vscode-input-background);
    color: var(--vscode-input-foreground);
    padding: 0.5em;
    border: 1px solid var(--vscode-input-border);
  }
</style>
