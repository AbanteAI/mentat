<script>
  export let path = ''
  export let index = ''
  export let toggleSelect = () => {}

  function handleToggleSelect() {
      toggleSelect(index)
  }5
</script>

<div style="width: 100%; display: flex;">
  <input type="checkbox" checked={path.selected} on:change={handleToggleSelect} />
  <span style="flex: 1;">{path.name}</span>
</div>

