# Token Budget Estimate

- Tasks: 40
- Repeats: 1
- Requests: 40
- Estimated prompt tokens / single pass: 7541
- Estimated prompt tokens including repeats: 7541
- Average prompt tokens / task: 188.5
- Max prompt tokens / task: 220

> This is a tokenizer-free planning estimate. Treat Codex JSONL `turn.completed.usage` as the source of truth after a real run.

## By domain

| domain | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| code | 7 | 1347 | 192.4 | 210 |
| instruction | 5 | 858 | 171.6 | 177 |
| logic | 8 | 1606 | 200.8 | 220 |
| math | 11 | 2004 | 182.2 | 193 |
| metacognition | 2 | 362 | 181.0 | 185 |
| reading | 6 | 1159 | 193.2 | 213 |
| robustness | 1 | 205 | 205.0 | 205 |

## By skill

| skill | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| ambiguity_detection | 1 | 177 | 177.0 | 177 |
| boolean_logic | 2 | 355 | 177.5 | 183 |
| boolean_precedence | 1 | 173 | 173.0 | 173 |
| calculation | 2 | 328 | 164.0 | 164 |
| constraint_satisfaction | 1 | 220 | 220.0 | 220 |
| counterexample | 1 | 209 | 209.0 | 209 |
| deduction | 1 | 215 | 215.0 | 215 |
| exclusive_or | 1 | 210 | 210.0 | 210 |
| execution_trace | 4 | 766 | 191.5 | 195 |
| format_following | 4 | 683 | 170.8 | 177 |
| inclusion_exclusion | 1 | 188 | 188.0 | 188 |
| insufficient_information | 1 | 185 | 185.0 | 185 |
| mutable_default_argument | 1 | 210 | 210.0 | 210 |
| negation_handling | 1 | 205 | 205.0 | 205 |
| negation_trap | 1 | 205 | 205.0 | 205 |
| ordered_output | 1 | 175 | 175.0 | 175 |
| ordering | 1 | 192 | 192.0 | 192 |
| pattern_reasoning | 1 | 170 | 170.0 | 170 |
| pigeonhole | 1 | 193 | 193.0 | 193 |
| rate_reasoning | 1 | 192 | 192.0 | 192 |
| recursion_trace | 1 | 198 | 198.0 | 198 |
| short_context | 2 | 376 | 188.0 | 192 |
| state_tracking | 4 | 783 | 195.8 | 213 |
| statistics | 2 | 370 | 185.0 | 185 |
| weighted_average | 1 | 186 | 186.0 | 186 |
| word_problem | 2 | 377 | 188.5 | 191 |
