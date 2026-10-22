/// <reference types="@ngx-env/builder/env" />

interface ImportMetaEnv {
  readonly NG_APP_BACKEND: string;
  readonly NG_APP_MARKET_WS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
