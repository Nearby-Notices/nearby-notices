# Pre-registered test: does the gate let through a sentence the notice does not support?

**Created:** 22/10/2026-19:46 (BST)  *(2026-10-22T18:46Z)*
**Last updated:** 22/10/2026-19:49 (BST)  *(2026-10-22T18:49Z)*

Filed before the test set is built and before any run. Nothing here changes once the run starts.

## Why

The labelled set has 42 false sentences and the gate let none through, so the true leak rate is below 6.9% at 95% confidence. Showing it is below 1% needs about 299 unsupported sentences with none let through (`stats.needed_for_bound(0.01) == 299`). This test reaches that size.

## How the unsupported sentences are made

Each one is a true sentence with exactly one fact changed to a value that appears nowhere in the notice, so it is unsupported by construction and needs no hand label.

- **Base sentences (true by construction):** the 42 hand-written true sentences in `evals/gold.jsonl`, and sentences copied word for word from the 21 notices in `evals/notices` (8 to 45 words, no web or email addresses).
- **One change per sentence, of one of three kinds:**
  - a number with its unit (days, weeks, months, years, metres, kilometres, miles, hectares, megawatts, kilovolts, turbines, houses, homes, dwellings, storeys, tonnes, per cent): the first of n+7, 2n, n+3, n+1 whose digits, and whose number word for 1 to 60, appear nowhere in the notice; for days, also not if the same number of weeks is written;
  - a date written as day, month, year: the day moved by 7, and the new date, and the new day and month, appear nowhere in the notice;
  - a place or organisation from the notice's own labels (`places_include`, `authority`): swapped for one of the same kind from another notice that appears nowhere in this notice.
- **The near-copy case is deliberate.** A sentence copied from the notice with one fact changed is the hardest case for a quote-checking gate, because quotes of the rest of the sentence are really in the notice. Only the model's judgement half can catch it.
- **Size:** 330 sentences, drawn with seed 2026 and spread as evenly as the pool allows across the three kinds of change and the two kinds of base sentence. 330 leaves a margin over 299 in case review removes construction errors.

## Run

The live configuration: Azure OpenAI gpt-4.1-mini, the live gate prompt, `extract.gate` (the model must say "supported" and every quote must be in the notice). One call per sentence, no cache.

## What counts, and what is reported

- **Removed:** the gate returns not supported. **Let through:** the gate keeps it.
- Every sentence let through is read against its notice by hand. If the notice does in fact support it (a construction error, for example the same fact written another way), it is removed from the count and listed. Otherwise it is a leak.
- Reported whatever the result: the number tested, the number let through, every leak with its notice, the exact one-sided 95% upper bound on the leak rate, and the rate by kind of change and by kind of base sentence.
- **Decision rule.** If none get through, the published claim becomes "below 1%" (if at least 299 remain after review). If any get through, the published claim is the bound the result supports, and each leak is filed as an incident with its cause.

## Amendment, 22/10/2026-19:49 (BST)  *(2026-10-22T18:49Z)*, before any run

The 21 notices gave only 177 valid sentences, short of 330. Rather than make several variants of the same sentence (which would not be independent), 45 new public notices were fetched on 22/10/2026 from searches around 15 council offices and city halls across the four nations (`leak_test.py fetch`; notices published from 1 July 2026; 120 to 2,700 words; any naming a private individual with Mr, Mrs, Ms, Miss or Dr left out; none from the main or held-out sets). They were never used to build or tune the service. They have no hand labels, so only number and date changes are made from their copied sentences. Everything else stands: 330 sentences, seed 2026, the same rules for what counts and what is reported.

## Second amendment, 22/10/2026-19:51 (BST)  *(2026-10-22T18:51Z)*, before any run

Final set: 90 new public notices were fetched (from searches around 47 council offices and city halls), after removing copied sentences that were Gazette header lines or carried a signatory's name, and one notice that named a place this project never publishes. The 330 sentences come from 86 notices (21 from the main set, 65 new): 87 date changes and 112 number changes from copied sentences, 79 place or organisation swaps in copied sentences, and 52 changes to the hand-written true sentences (11 date, 8 number, 33 name). The pool held 341 valid sentences; 330 were drawn with seed 2026.
