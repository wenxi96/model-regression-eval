# Token Budget Estimate

- Tasks: 100
- Repeats: 3
- Requests: 300
- Estimated prompt tokens / single pass: 18715
- Estimated prompt tokens including repeats: 56145
- Average prompt tokens / task: 187.2
- Max prompt tokens / task: 259

> This is a tokenizer-free planning estimate. Treat Codex JSONL `turn.completed.usage` as the source of truth after a real run.

## By domain

| domain | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| code | 18 | 3433 | 190.7 | 210 |
| instruction | 12 | 2060 | 171.7 | 185 |
| logic | 20 | 3973 | 198.7 | 236 |
| math | 28 | 5068 | 181.0 | 259 |
| metacognition | 3 | 562 | 187.3 | 200 |
| reading | 15 | 2915 | 194.3 | 232 |
| robustness | 4 | 704 | 176.0 | 205 |

## By skill

| skill | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| algebra | 2 | 330 | 165.0 | 166 |
| ambiguity_detection | 1 | 177 | 177.0 | 177 |
| boolean_logic | 4 | 725 | 181.2 | 192 |
| boolean_precedence | 3 | 527 | 175.7 | 180 |
| boundary_condition | 1 | 164 | 164.0 | 164 |
| bug_reasoning | 1 | 205 | 205.0 | 205 |
| calculation | 5 | 813 | 162.6 | 164 |
| conflict_resolution | 1 | 232 | 232.0 | 232 |
| constraint_following | 1 | 185 | 185.0 | 185 |
| constraint_reasoning | 1 | 236 | 236.0 | 236 |
| constraint_satisfaction | 1 | 220 | 220.0 | 220 |
| counterexample | 1 | 209 | 209.0 | 209 |
| deduction | 4 | 860 | 215.0 | 222 |
| exclusive_or | 1 | 210 | 210.0 | 210 |
| execution_trace | 9 | 1726 | 191.8 | 199 |
| format_following | 7 | 1198 | 171.1 | 177 |
| inclusion_exclusion | 3 | 578 | 192.7 | 196 |
| indexing | 1 | 187 | 187.0 | 187 |
| insufficient_information | 2 | 385 | 192.5 | 200 |
| mutable_default_argument | 1 | 210 | 210.0 | 210 |
| necessary_sufficient | 1 | 215 | 215.0 | 215 |
| negation_handling | 3 | 584 | 194.7 | 206 |
| negation_trap | 1 | 205 | 205.0 | 205 |
| ordered_output | 1 | 175 | 175.0 | 175 |
| ordering | 5 | 906 | 181.2 | 192 |
| pattern_reasoning | 4 | 680 | 170.0 | 170 |
| pigeonhole | 3 | 594 | 198.0 | 203 |
| rate_reasoning | 2 | 368 | 184.0 | 192 |
| recursion_trace | 1 | 198 | 198.0 | 198 |
| scope_reasoning | 1 | 188 | 188.0 | 188 |
| short_context | 8 | 1499 | 187.4 | 199 |
| state_tracking | 7 | 1350 | 192.9 | 213 |
| statistics | 2 | 370 | 185.0 | 185 |
| structured_answer | 2 | 336 | 168.0 | 170 |
| unit_conversion | 2 | 324 | 162.0 | 162 |
| unit_trap | 2 | 335 | 167.5 | 172 |
| weighted_average | 2 | 375 | 187.5 | 189 |
| word_problem | 2 | 377 | 188.5 | 191 |
| worst_case_reasoning | 1 | 259 | 259.0 | 259 |
