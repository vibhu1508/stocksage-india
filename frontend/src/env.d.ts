/// <reference types="@ngx-env/builder/env" />

interface ImportMetaEnv {
  readonly NG_APP_BACKEND: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
