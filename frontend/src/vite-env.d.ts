/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare namespace YT {
  class Player {
    constructor(elementId: string, options: Record<string, unknown>);
  }
}
