declare module "*.svelte" {
  import { SvelteComponentTyped } from "svelte";
  export default class extends SvelteComponentTyped<{}, {}, {}> {}
}

declare module '@fortawesome/pro-solid-svg-icons/index.es' {
  export * from '@fortawesome/pro-solid-svg-icons';
}