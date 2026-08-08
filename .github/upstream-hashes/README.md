# Upstream hashes

SHA-256 fingerprints of files in the upstream privacytracker app repo
that the website mirrors. The `check-privacy-drift.yml` workflow
compares each fetched upstream file against the matching hash here;
when they diverge, it opens a `privacy-drift` issue for review and
records the new hash.

Files
-----
- `privacy-policy.sha256` — fingerprint of `app/privacy-policy/page.tsx`
  in https://github.com/privacykey/privacytracker. Watched by
  `.github/workflows/check-privacy-drift.yml`.

Editing
-------
These files are managed by the workflow. You shouldn't need to
edit them by hand. If you do (e.g. to force a re-check), make the
file empty or delete the line — the workflow treats that as a
"first run" and records the current hash without raising an issue.
