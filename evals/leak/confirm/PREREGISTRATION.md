# Pre-registered confirmation: the gate with the numbers rule, on notices it was never shaped on

**Created:** 22/10/2026-20:00 (BST)  *(2026-10-22T19:00Z)*
**Last updated:** 22/10/2026-20:05 (BST)  *(2026-10-22T19:05Z)*

Filed before these notices are fetched and before any run. Nothing here changes once the run starts.

## Why

The first leak test (`../PREREGISTRATION.md`, `../LEAK_TEST.md`) let through 2 of 329 unsupported sentences, both number changes in one long traffic order. A code rule was then added: every number in a sentence must also be in its quotes. Rerunning the same 330 sentences after designing a rule on them would flatter it, so the rule is measured here on a fresh set.

## Design

- **Notices:** new public notices fetched from searches around council offices and city halls across the four nations, published from 1 July 2026, 120 to 2,700 words, none from the main, held-out or first leak sets, any naming a private individual (Mr, Mrs, Ms, Miss, Dr) left out.
- **Sentences:** copied word for word from those notices, with exactly one number-with-unit or date changed to a value that appears nowhere in the notice (the same rules as the first test, with one correction from its review: a number written with its unit attached, such as "28m", now also counts as appearing). No place swaps, because these notices have no hand labels.
- **Size:** 330, drawn with seed 2027.
- **Run:** the live configuration (Azure OpenAI gpt-4.1-mini, the live gate prompt, `extract.gate` with the numbers rule). One call per sentence.

## What counts, and what is reported

The same as the first test: every sentence let through is read against its notice by hand; a construction error is removed and listed; anything else is a leak. Reported whatever the result: the number tested, the number let through, every leak, and the exact one-sided 95% upper bound (below 1% needs 0 of at least 299).

## Amendment, 22/10/2026-20:05 (BST)  *(2026-10-22T19:05Z)*, before any run

Searches within 10 miles gave too few notices, so the searches were widened to 30 miles, up to five notices per centre, around 60 council offices and city halls. 189 fresh notices were fetched; the 330 sentences (159 date changes, 171 number changes) come from 141 of them. The pool held 425 valid sentences.
- Also before the run: a moved date now takes the right ending ("2nd" moved by 7 is "9th", not "9nd"). Same counts.
