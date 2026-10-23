# inspect-quote-check

An [Inspect](https://inspect.aisi.org.uk/) scorer, registered as an Inspect extension, for evaluating claims that a model must ground in a source with its own quotes.

A claim is kept only if the model says it is supported, it offers at least one quote, every span of every quote is really in the source (whole words; case and punctuation ignored; "a ... b" counts as two spans), and every number in the claim also appears in the quotes. The number rule catches a common grounded-looking error: a true quote giving "68m" offered as support for "75m".

```python
from inspect_quote_check import verbatim_quotes
Task(dataset=..., solver=generate(), scorer=verbatim_quotes(source_field="text", claim_field="claim"))
```

Installed, it also resolves by registry name: `inspect_quote_check/verbatim_quotes`. The pure check, `decide(source, reply, claim)`, has no Inspect dependency and returns the decision with its reason.

Built for, and tested on, the safety check of Nearby Notices (pre-registered leak tests: `../../evals/leak/`).
