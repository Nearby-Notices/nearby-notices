# Leak test: unsupported sentences against the gate

Run 2026-10-22T19-52-20 on `azure/gpt-4.1-mini`, 44.6 s. Design filed first: `PREREGISTRATION.md`.

- **Tested:** 329 sentences the notice does not support (1 removed on review as construction errors).
- **Let through:** 2.
- **Leak rate:** 0.6% (95% Wilson interval 0.2% to 2.2%; exact one-sided upper bound 1.9%).

| Kind of change | Base sentence | Tested | Let through |
|---|---|---|---|
| date | copied | 87 | 0 |
| date | hand-written | 11 | 0 |
| name | copied | 79 | 0 |
| name | hand-written | 33 | 0 |
| number | copied | 111 | 2 |
| number | hand-written | 8 | 0 |

## Every sentence let through

- 4477626 (number, 22 m -> 29 m): "junction with Priory Street to a point 29m south east of the junction with Priory Street" quotes: ['a point 10m south-east of the junction of Priory Street to a point 22m south-east of the junction of Priory Street', 'a point 5m south-east of Tower Street to a point 29m south east of Tower Street']
- 4477626 (number, 68 m -> 75 m): "75m south east of the juction with Ednam Road" quotes: ['from a point 35m south east of the junction of Ednam Road to a point 68m south east of the juction with Ednam Road']

## Later runs on the same set (not independent: any change made after the first run was shaped on it)

- 2026-10-22T20-00-13: 1 of 329 let through: 4477626 (22 m -> 29 m)
