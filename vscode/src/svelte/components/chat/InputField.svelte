<script lang="ts">
  export let handleGetResponse: () => void;
  export let prompt: string;
</script>

<input 
  bind:value={prompt} 
  type="text" 
  placeholder="Enter a prompt" 
  on:keyup={(e) => {
    if (e.keyCode === 13) {
      handleGetResponse();
    }
  }}
/>

<style>
  input {
    flex-grow: 1;
  }
</style>
