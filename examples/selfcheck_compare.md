# Model Capability Regression Compare

- Paired cases: 300
- Paired tasks: 300
- Task overlap rate: 100.0%
- Domain mismatches: 0
- Baseline case accuracy: 100.0%
- Candidate case accuracy: 96.0%
- Delta case accuracy: -4.0 pp
- Baseline majority accuracy: 100.0%
- Candidate majority accuracy: 96.0%
- Delta majority accuracy: -4.0 pp
- Case regressions: 12
- Case improvements: 0
- Net case regressions: 12
- Stable task regressions: 12
- Stable task improvements: 0
- Net stable task regressions: 12
- McNemar/sign-test exact p-value, cases: 0.000488
- McNemar/sign-test exact p-value, task majority: 0.000488

## By domain

| domain | n | baseline | candidate | delta | regressions | improvements |
|---|---:|---:|---:|---:|---:|---:|
| code | 55 | 100.0% | 100.0% | +0.0 pp | 0 | 0 |
| instruction | 38 | 100.0% | 100.0% | +0.0 pp | 0 | 0 |
| logic | 60 | 100.0% | 93.3% | -6.7 pp | 4 | 0 |
| math | 85 | 100.0% | 91.8% | -8.2 pp | 7 | 0 |
| metacognition | 5 | 100.0% | 80.0% | -20.0 pp | 1 | 0 |
| reading | 45 | 100.0% | 100.0% | +0.0 pp | 0 | 0 |
| robustness | 12 | 100.0% | 100.0% | +0.0 pp | 0 | 0 |

## Stable task regression cases

| task | domain | skill | baseline correct/repeats | candidate correct/repeats |
|---|---|---|---:|---:|
| arithmetic_order_001 | math | calculation | 1/1 | 0/1 |
| box_labels_001 | logic | constraint_reasoning | 1/1 | 0/1 |
| candy_ambiguity_001 | metacognition | ambiguity_detection | 1/1 | 0/1 |
| candy_blind_draw_001 | math | worst_case_reasoning | 1/1 | 0/1 |
| candy_shape_select_001 | math | worst_case_reasoning | 1/1 | 0/1 |
| conditional_001 | logic | deduction | 1/1 | 0/1 |
| knights_knaves_001 | logic | truthfulness_reasoning | 1/1 | 0/1 |
| logic_ordering_001 | logic | ordering | 1/1 | 0/1 |
| pigeonhole_colors_001 | math | pigeonhole | 1/1 | 0/1 |
| rate_work_001 | math | word_problem | 1/1 | 0/1 |
| sequence_001 | math | pattern_reasoning | 1/1 | 0/1 |
| socks_pair_001 | math | pigeonhole | 1/1 | 0/1 |

## Case-level regression cases

| task | repeat | domain | skill | baseline | candidate | expected | failure mode |
|---|---:|---|---|---|---|---|---|
| arithmetic_order_001 | 1 | math | calculation | 19 | __synthetic_wrong__ | 19 | synthetic_regression |
| box_labels_001 | 1 | logic | constraint_reasoning | C | __synthetic_wrong__ | C | synthetic_regression |
| candy_ambiguity_001 | 1 | metacognition | ambiguity_detection | 歧义,21,29 | __synthetic_wrong__ | ['歧义', '21', '29'] | synthetic_regression |
| candy_blind_draw_001 | 1 | math | worst_case_reasoning | 29 | __synthetic_wrong__ | 29 | synthetic_regression |
| candy_shape_select_001 | 1 | math | worst_case_reasoning | 21 | __synthetic_wrong__ | 21 | synthetic_regression |
| conditional_001 | 1 | logic | deduction | B | __synthetic_wrong__ | B | synthetic_regression |
| knights_knaves_001 | 1 | logic | truthfulness_reasoning | D | __synthetic_wrong__ | D | synthetic_regression |
| logic_ordering_001 | 1 | logic | ordering | 丁 | __synthetic_wrong__ | 丁 | synthetic_regression |
| pigeonhole_colors_001 | 1 | math | pigeonhole | 15 | __synthetic_wrong__ | 15 | synthetic_regression |
| rate_work_001 | 1 | math | word_problem | 2.4 | __synthetic_wrong__ | 2.4 | synthetic_regression |
| sequence_001 | 1 | math | pattern_reasoning | 42 | __synthetic_wrong__ | 42 | synthetic_regression |
| socks_pair_001 | 1 | math | pigeonhole | 5 | __synthetic_wrong__ | 5 | synthetic_regression |
