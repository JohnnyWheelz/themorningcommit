# themorningcommit

Public static site for [themorningcommit.com](https://themorningcommit.com).

The repository contains public website artifacts only. Private source bundles, email metadata, batch state, processing receipts, local paths, and credentials are prohibited.

## Build a release

```bash
python scripts/build-site.py --report D:/Agentic/artifacts/rpallibrary-digests/latest.html
npm run validate
```

## Publication

The guarded Hermes morning workflow builds and validates a dated edition, commits it as `JohnnyWheelz`, pushes `main`, waits for Cloudflare Pages, verifies the live page, and only then finalizes the private Gmail batch.
