# Notice kinds: results

Trained 23/10/2026 15:46 on 1324 notices; tested on the 440 held out in `split.json` before any training.
Labels are the service's own language model's (gpt-4.1-mini): the kind it gave while writing a summary, or the answer to a kind-only question.
So these numbers measure agreement with those labels: the model reproduces them without a model call.

| | Right on the held-out set | 95% Wilson interval |
|---|---|---|
| This model (word and character n-grams, logistic regression) | 402 of 440 (91.4%) | 88.4% to 93.6% |
| Baseline: the most common kind for each notice code | 309 of 440 (70.2%) | 65.8% to 74.3% |

Exact McNemar test on the paired results: the model alone right on 104, the baseline alone right on 11, p = 3.8e-20.
Macro-averaged F1 across kinds: 0.87.

| Kind | Held out | F1 |
|---|---|---|
| electricity or energy | 22 | 0.93 |
| environmental permit | 6 | 0.91 |
| footpath or bridleway | 3 | 0.60 |
| one way or turning restriction | 11 | 0.84 |
| other | 52 | 0.81 |
| parking or waiting restriction | 236 | 0.97 |
| planning application | 22 | 0.93 |
| planning permission or order | 36 | 0.85 |
| road closure | 24 | 0.68 |
| speed limit | 17 | 0.94 |
| tree or forestry | 1 | 1.00 |
| water or drainage | 10 | 0.95 |

Confusion (rows: label; columns: model, in the order of the table above):

```
electricity or energy         20   0   0   0   2   0   0   0   0   0   0   0
environmental permit           0   5   0   0   0   0   1   0   0   0   0   0
footpath or bridleway          0   0   3   0   0   0   0   0   0   0   0   0
one way or turning restricti   0   0   0   8   2   0   0   1   0   0   0   0
other                          0   0   1   0  43   1   0   2   5   0   0   0
parking or waiting restricti   0   0   0   0   7 226   0   1   1   1   0   0
planning application           1   0   0   0   0   0  21   0   0   0   0   0
planning permission or order   0   0   1   0   0   0   1  33   1   0   0   0
road closure                   0   0   2   0   0   0   0   5  16   0   0   1
speed limit                    0   0   0   0   0   1   0   0   0  16   0   0
tree or forestry               0   0   0   0   0   0   0   0   0   0   1   0
water or drainage              0   0   0   0   0   0   0   0   0   0   0  10
```
