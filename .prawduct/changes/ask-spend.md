---
schema: 1
type: fix
scope: ask-spend
closes: [brookstalley/arrt#337]
date: 2026-11-09
title: What Ask's replies cost is written to the spend ledger
---

Ask showed each reply's cost but never recorded it, so `spend_in_month` and
`art_discovery(action='spend')` under-reported against the provider's bill by
whatever Ask had spent. The owner ruled on 2026-10-09 that Ask's spend counts.

Each reply billed anything now writes one `SpendRecord` in a new category,
`ask_tokens`, holding the sum of its model calls' costs as Decimal, the model
the provider says answered (none when its calls named more than one), and token
counts where the provider reported them.
It is written however the reply ended: answered, stopped at the step limit,
refused, failed or abandoned by its client. A write that fails, in the
service's words or the database driver's, is logged and the reply still ends. `Ask` takes the writer as a required `record_cost`, so
an application that builds one cannot leave it unwired.

## Consumer note

The month's spend that Arrt reports now includes what its assistant, Ask, spent.
Nothing is backfilled: replies before this release are not in the ledger.

**Rolling back past this release needs one statement.** A release from before
it refuses to read a spend row in a category it does not know, so the month's
spend fails once Ask has written one. Before starting the previous image, run
`DELETE FROM spend_records WHERE category = 'ask_tokens';` on the catalogue.
That forgets what Ask spent since the upgrade, which the release being rolled
back to never counted anyway. `deploy/README.md` § Ask's spend in the ledger.
