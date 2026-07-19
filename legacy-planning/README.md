# GIA Legacy Planning — Infinite Banking Platform

A fully self-contained, single-file web app (`index.html`). No build step, no server,
no dependencies — everything (PDF import, modeling, presentations, PDF export) runs
in the visitor's browser, and their data never leaves their machine.

## Deploy to Netlify (my-legacy-planning.netlify.app)

This replaces the old React app — a new deploy fully supersedes the previous one.

**Drag & drop (fastest):**
1. Log in at https://app.netlify.com and open the `my-legacy-planning` site.
2. Go to the **Deploys** tab.
3. Drag this `legacy-planning` folder (or a zip of it) onto the deploy area.

**Or via Netlify CLI:**
```
netlify deploy --prod --dir=legacy-planning
```

## GitHub Pages

The repo's existing Pages workflow serves this folder at
`/legacy-planning/` once merged to the default branch.
