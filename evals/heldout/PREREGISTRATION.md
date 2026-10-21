# Pre-registered experiment: does the stronger model improve the gate?

**Created:** 21/10/2026-12:26 (BST)  *(2026-10-21T11:26Z)*
**Last updated:** 21/10/2026-12:26 (BST)  *(2026-10-21T11:26Z)*

Filed before the held-out labels are finalised and before any run on them. This file is committed first; the run comes after. Nothing here changes once the run starts.

## Hypothesis

H0: on the held-out set, the gate's decisions under the current configuration (Azure OpenAI gpt-4.1-mini, the live prompt) and under the comparison configuration (gpt-4.1, same prompt) are equally accurate.
H1: the comparison configuration is more accurate.

## Design

- Items: the 92 hand-checked true and false sentences across 23 held-out notices, never used to build or tune the service.
- Both configurations score every sentence; each decision is marked right or wrong against the checked label.
- Test: exact McNemar on the discordant pairs, two-sided, alpha 0.05.
- Minimum detectable effect, fixed in advance: with 92 paired items, a difference is significant only if at least 6 items flip in one direction with none in the other (p = 0.031), that is about 6.5% of items. Smaller differences will be reported as not detectable, not as "no difference".

## Decision rule

- If H0 is rejected in favour of the comparison model and its cost per notice is within twice the current cost, switch the live service to it.
- Otherwise keep the current model and record the result.

## What is recorded

The run stamp, both result files, the discordant counts, the p-value, the costs, and the decision, appended to `../STATISTICS.md`.
