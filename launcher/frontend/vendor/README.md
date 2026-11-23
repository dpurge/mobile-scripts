# Vendored Lit

`lit.js` is Lit 3.3.3 (BSD-3-Clause, see `LICENSE`) bundled into one ESM file with esbuild 0.28.2.
No Lit 3 release ships a standalone browser file, so it is generated once with npm in a scratch
directory. Nothing npm-related lives in the project.

Regenerate (run outside the repo):

```sh
mkdir lit-vendor && cd lit-vendor
npm init -y
npm install lit@3.3.3 esbuild@0.28.2
echo "export * from 'lit';" > entry.js
./node_modules/.bin/esbuild entry.js --bundle --minify --format=esm --outfile=<repo>/launcher/frontend/vendor/lit.js
cp node_modules/lit/LICENSE <repo>/launcher/frontend/vendor/LICENSE
```
