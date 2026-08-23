# privacytracker website

Marketing site for [privacytracker](https://github.com/privacykey/privacytracker)
— the app that watches iOS App Store privacy labels and tells you when one
quietly changes.

Static HTML. No framework, no build step. Deploy by pointing any static host at
the repository root.

Production is a Cloudflare Worker serving the repository root as static
assets ([`wrangler.jsonc`](wrangler.jsonc)). Cloudflare Workers Builds is
connected to this repository and deploys every push to `main` with
`npx wrangler deploy`; `just deploy` does the same by hand.

**Hostname:** `privacytracker.privacykey.org` *(DNS not configured yet)*

## Layout

```
.
├── index.html              Hero, features, the five-minute setup walkthrough, install paths
├── about.html              What privacykey is
├── privacy.html            Data posture — what's collected (nothing), every outbound
│                           endpoint, the opt-in surfaces, how to go fully offline
├── legal.html              Apache-2.0 plus bundled third-party libraries by SPDX licence
├── llms.txt                Preferred entry point for cooperating AI agents
├── robots.txt              Search engines welcome; training crawlers blocked
├── security.txt            RFC 9116, mirrored under /.well-known/
├── sitemap.xml
├── site.webmanifest
├── assets/                 CSS, fonts, icons, social images
└── scripts/
    └── update-versions.py  Syncs the dependency version pills in legal.html
```

## Keeping it honest

Two automations guard the pages that make factual claims:

- **`.github/workflows/check-privacy-drift.yml`** watches privacytracker's own
  privacy-policy source. When it changes, the workflow opens an issue so
  `privacy.html` gets reviewed rather than silently drifting. Baseline hashes
  live in `.github/upstream-hashes/`.
- **`.github/workflows/bump-oss-versions.yml`** keeps the third-party version
  pills in `legal.html` current, via `scripts/update-versions.py`.

If you change `privacy.html` in response to an upstream change, record the new
baseline hash in the same commit.

## Conventions

- **privacytracker** and **privacykey** are one word, all lowercase, everywhere
  — including at the start of a sentence.
- Feature claims must match the shipped product. When in doubt, check
  privacytracker's README or the docs site rather than the last version of this
  page.
- `llms.txt` is a factual summary for agents, not marketing copy. Keep its
  feature list in step with the product.

## Related

- [privacytracker](https://github.com/privacykey/privacytracker) — the app
- [docs-privacytracker](https://github.com/privacykey/docs-privacytracker) — the documentation site
- [website-privacykey](https://github.com/privacykey/website-privacykey) — the organisation site
