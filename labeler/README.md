# Serenity Labeler

A standalone Next.js dev tool for building out `evals/dataset.json`
by labeling tweets from the tracked X account.

This folder is intentionally separate from the Python bot: its own
`package.json`, its own dependencies, no shared code. The only
points of contact are read-only access to `../.env` (for
`X_BEARER_TOKEN` and `TRACKED_X_ACCOUNT`) and atomic appends to
`../evals/dataset.json`.

## Run

```sh
cd labeler
npm install
npm run dev
```

Open http://localhost:3344.

## What it does

1. On load, fetches up to 100 recent tweets from `TRACKED_X_ACCOUNT`
   via X's v2 timeline endpoint (retweets and replies excluded).
2. Filters out tweet IDs in `data/seen.json` so you don't re-label
   the same tweet.
3. Shows one tweet at a time. You enter ticker / order_type /
   confidence and click Save (appends to `../evals/dataset.json`)
   or Skip (marks the ID seen but adds nothing).
4. When the unlabeled queue is empty, click "refetch" to pull
   again (subject to X's free-tier rate limit, which is tight —
   usually 1 timeline call per 15 min).

## Invariants enforced

To match what `Oracle.analyze` is allowed to return:

- `order_type == "N/A"` forces `ticker == "N/A"` and
  `confidence == { eq: 0 }`.
- Empty ticker is rejected.

## State

- `data/seen.json` — set of tweet IDs already labeled or skipped.
  Delete it to re-show everything. Gitignored.
- Output goes straight to `../evals/dataset.json`. Review with
  `git diff` before committing.
