# PEPA website

Prince Street Emergency Preparation Association.

The site uses Pelican and Tailwind CSS. Templates are in `theme/templates`;
Tailwind scans those templates and `content/` for utility classes.

Install dependencies:

```sh
python -m pip install -r requirements.txt
npm install
```

Build CSS and HTML together:

```sh
npm run build
```

The public site is generated in `output/`. For a local preview:

```sh
.venv/bin/python -m http.server 8000 --directory output
```

Open http://localhost:8000. Edit custom CSS in `src/styles.css`.
`npm run watch:css` rebuilds the CSS as you edit; rerun `npm run build`
to copy it into `output/` and regenerate HTML.

Do not edit generated CSS in `theme/static/styles.css` or files in `output/`.
The homepage and Classes page are Markdown files in `content/pages/`.
The shared template provides a centered 80% container, header navigation,
and footer. Add class information to `content/pages/classes.md`.

The Search page searches published page and article titles and full text in
the browser. `plugins/search_index.py` rebuilds `output/search-index.js`
automatically with Pelican. Drafts and hidden content are excluded.
Search requires JavaScript but no backend service.
