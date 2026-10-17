# Incidents

Every outage, wrong output or fix, dated.

## 17/10/2026, before launch

- First live search near Dudley: 6 notices, 66 seconds, because each notice needs 3 to 4 model calls on the local 27B model and extraction runs inside the request. Fix before public use: pre-extract in the background and show "reading..." for notices not yet done.
- Two notices lost every summary sentence to the gate (the judge returned quotes that were not verbatim). Honest, but worth a stricter quoting instruction and an evaluation set.
- One "Where" field included a council contact address rather than an affected place. Prompt to say "places affected, not addresses for correspondence".
