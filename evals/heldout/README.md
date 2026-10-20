# Held-out evaluation set

**Created:** 20/10/2026-15:25 (BST)  *(2026-10-20T14:25Z)*
**Last updated:** 20/10/2026-15:25 (BST)  *(2026-10-20T14:25Z)*

These 23 notices, fetched on 20 October 2026, were never used to build or tune the service. The main set in `evals/` was used to find and fix failures. A score on that set therefore says how well the fixes worked on the cases they were made for. A score on this set says how the service does on notices it has never seen.

- **Scope.** 11 Gazette categories, from councils and agencies in Scotland, England and Wales. Notices naming private individuals were left out.
- **How the labels were made.** The draft labels in `gold_draft.jsonl` were written with an AI assistant. They become `gold.jsonl` only after every line has been checked by hand against the notice (`CHECK_SHEET.md`).
- **Running it.** `uv run python evals/run.py --set heldout`. The runner refuses to start until `gold.jsonl` exists.
- **The rule that keeps it honest.** Run it once per change of model or design, and report the result. Never change the service because of a single held-out item. If a held-out failure leads to a fix, move that notice into the main set and replace it here with a new one.
