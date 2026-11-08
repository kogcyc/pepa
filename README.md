# PEPA

Website for Prince Street Emergency Preparation Association.
Built with Pelican and Tailwind CSS.

## Local development

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run build
python -m http.server 8000 --directory output
```

Open http://localhost:8000. Edit pages in `content/pages/`, templates in
`theme/templates/`, and custom CSS in `src/styles.css`.
Run `npm run build` after changes. Generated files are not committed.

## Cloudflare Pages

Connect the GitHub repository and use:

- Framework preset: None
- Root directory: repository root
- Build command: `python -m pip install -r requirements.txt && npm run build`
- Build output directory: `output`

Cloudflare installs npm dependencies from `package-lock.json`.
Python must be 3.11 or newer; use the current Pages build image.
After the first deployment, add `pepaweb.org` under the project's Custom domains.

Search runs in the browser; Pelican refreshes its index on every build.
The site contains no server-side application or database.
