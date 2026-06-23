# Token Budget Estimate

- Tasks: 300
- Repeats: 3
- Requests: 900
- Estimated prompt tokens / single pass: 56439
- Estimated prompt tokens including repeats: 169317
- Average prompt tokens / task: 188.1
- Max prompt tokens / task: 292

> This is a tokenizer-free planning estimate. Treat Codex JSONL `turn.completed.usage` as the source of truth after a real run.

## By domain

| domain | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| code | 55 | 10609 | 192.9 | 218 |
| instruction | 38 | 6550 | 172.4 | 187 |
| logic | 60 | 12103 | 201.7 | 246 |
| math | 85 | 15093 | 177.6 | 292 |
| metacognition | 5 | 1004 | 200.8 | 240 |
| reading | 45 | 8863 | 197.0 | 232 |
| robustness | 12 | 2217 | 184.8 | 220 |

## By skill

| skill | tasks | est prompt tokens | avg/task | max/task |
|---|---:|---:|---:|---:|
| algebra | 14 | 2317 | 165.5 | 168 |
| ambiguity_detection | 2 | 417 | 208.5 | 240 |
| average_trap | 2 | 362 | 181.0 | 181 |
| boolean_logic | 14 | 2510 | 179.3 | 192 |
| boolean_precedence | 5 | 887 | 177.4 | 184 |
| boundary_condition | 1 | 164 | 164.0 | 164 |
| bug_reasoning | 6 | 1234 | 205.7 | 208 |
| calculation | 19 | 3092 | 162.7 | 164 |
| case_sensitive_output | 2 | 355 | 177.5 | 178 |
| conditional_reasoning | 2 | 441 | 220.5 | 240 |
| conflict_resolution | 3 | 674 | 224.7 | 232 |
| constraint_following | 2 | 368 | 184.0 | 185 |
| constraint_reasoning | 1 | 236 | 236.0 | 236 |
| constraint_satisfaction | 1 | 220 | 220.0 | 220 |
| counterexample | 4 | 754 | 188.5 | 209 |
| deduction | 18 | 3841 | 213.4 | 225 |
| exactly_vs_at_least | 2 | 390 | 195.0 | 198 |
| exception_reasoning | 2 | 423 | 211.5 | 216 |
| exclusive_or | 1 | 210 | 210.0 | 210 |
| execution_trace | 20 | 3845 | 192.2 | 199 |
| format_following | 22 | 3776 | 171.6 | 187 |
| inclusion_exclusion | 3 | 578 | 192.7 | 196 |
| indexing | 8 | 1526 | 190.8 | 195 |
| information_extraction | 4 | 798 | 199.5 | 213 |
| insufficient_information | 3 | 587 | 195.7 | 202 |
| mutable_default_argument | 2 | 428 | 214.0 | 218 |
| mutable_state | 2 | 398 | 199.0 | 201 |
| necessary_sufficient | 3 | 678 | 226.0 | 246 |
| negation_handling | 9 | 1858 | 206.4 | 220 |
| negation_trap | 2 | 387 | 193.5 | 205 |
| ordered_output | 3 | 529 | 176.3 | 182 |
| ordering | 12 | 2215 | 184.6 | 214 |
| pattern_reasoning | 9 | 1525 | 169.4 | 170 |
| percentage_trap | 1 | 181 | 181.0 | 181 |
| pigeonhole | 12 | 2341 | 195.1 | 208 |
| policy_priority | 5 | 1076 | 215.2 | 232 |
| rate_reasoning | 3 | 559 | 186.3 | 192 |
| recursion_trace | 2 | 396 | 198.0 | 198 |
| scope_reasoning | 2 | 376 | 188.0 | 188 |
| short_context | 18 | 3415 | 189.7 | 214 |
| state_tracking | 16 | 3066 | 191.6 | 213 |
| statistics | 7 | 1288 | 184.0 | 185 |
| structured_answer | 8 | 1356 | 169.5 | 180 |
| truthfulness | 2 | 400 | 200.0 | 201 |
| truthfulness_reasoning | 1 | 234 | 234.0 | 234 |
| unit_conversion | 7 | 1135 | 162.1 | 163 |
| unit_trap | 2 | 335 | 167.5 | 172 |
| weighted_average | 3 | 565 | 188.3 | 190 |
| word_problem | 6 | 1142 | 190.3 | 192 |
| worst_case_reasoning | 2 | 551 | 275.5 | 292 |
