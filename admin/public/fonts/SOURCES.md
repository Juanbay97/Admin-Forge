# Bundled fonts

Only the six typefaces of the vetted white-label list are shipped; each is a latin-subset variable
`wght` woff2 taken unmodified from the official npm registry, with the package's SIL Open Font
License 1.1 text next to it. Nothing is fetched at runtime (`font-src 'self'`).

| Font id | Source package | SHA-256 of the woff2 |
|---------|----------------|----------------------|
| inter | @fontsource-variable/inter | 3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62 |
| montserrat | @fontsource-variable/montserrat | 06b16db7a969135d48d38c49183be7fb88d4452e2a3011957c7851941f4e4879 |
| source-sans-3 | @fontsource-variable/source-sans-3@5.3.1 | 19143dca075972bc84e3fd9eab7416dd40cc565dccb2435a044bdfabe060c7d5 |
| ibm-plex-sans | @fontsource-variable/ibm-plex-sans@5.3.0 | e2291e842cf5af167122a22881a740c7f2dda7716f1e8cd76680264f4a859470 |
| nunito-sans | @fontsource-variable/nunito-sans@5.3.0 | 29e3890496844a9ea81975c52771c587c872b4eb317026422d1995b88d21b57d |
| roboto | @fontsource-variable/roboto@5.3.0 | 1404ca348bd75ef836f4dd8b6f2cc719458642d1237c368296b2fc652dca47dc |

The four newest files were fetched with `npm pack` (registry integrity verified by npm) and copied
from `files/<id>-latin-wght-normal.woff2`; no package is a dependency of the admin. The font ids and
family names must match `src/brand/palette.ts`, `src/forge/branding.py` and the client list
(`tests/unit/fonts.spec.ts` checks the files, licences and `@font-face` rules).
