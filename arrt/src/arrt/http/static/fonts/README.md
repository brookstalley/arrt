# Typefaces

Served by the curation surface itself (`/static/fonts/`) and declared at the
top of `../app.css`. Each family's licence is the `OFL.txt` beside its files.

| Family | Files | Source | Licence |
|---|---|---|---|
| Newsreader (variable: `opsz`, `wght` 200–800) | `newsreader/{latin,latin-ext}-{normal,italic}.woff2` | npm `@fontsource-variable/newsreader@5.3.0`, `files/newsreader-*-standard-*.woff2` | SIL OFL 1.1 |
| Instrument Sans (variable: `wdth` 75–100%, `wght` 400–700) | `instrument-sans/{latin,latin-ext}-{normal,italic}.woff2` | npm `@fontsource-variable/instrument-sans@5.3.0`, `files/instrument-sans-*-standard-*.woff2` | SIL OFL 1.1 |

The `standard` builds carry every axis the family has. To update a family,
replace its four files from a newer release of the same package, keeping the
names, and update the version above. The `unicode-range` values in `app.css`
come from the same package's `standard.css`.
