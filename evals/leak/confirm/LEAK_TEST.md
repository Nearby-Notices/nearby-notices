# Leak test: unsupported sentences against the gate

Run 2026-10-22T20-07-06 on `azure/gpt-4.1-mini`, 49.4 s. Design filed first: `PREREGISTRATION.md`.

- **Tested:** 330 sentences the notice does not support (0 removed on review as construction errors).
- **Let through:** 0.
- **Leak rate:** below 0.9% at 95% confidence (exact one-sided bound, 0 of 330).

| Kind of change | Base sentence | Tested | Let through |
|---|---|---|---|
| date | copied | 159 | 0 |
| number | copied | 171 | 0 |
