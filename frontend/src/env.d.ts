/// <reference types="@ngx-env/builder/env" />

interface ImportMetaEnv {
  readonly NG_APP_BACKEND: string;
  readonly NG_APP_MARKET_WS?: string;
  readonly NG_APP_BRANDFETCH_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
