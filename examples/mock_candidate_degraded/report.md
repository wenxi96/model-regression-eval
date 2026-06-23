# Model Capability Regression Run

- Cases: 300
- Unique tasks: 300
- Max repeats per task: 1
- Accuracy: 96.0%
- Weighted accuracy: 96.0%
- Majority accuracy by task: 96.0%
- Any-correct rate by task: 96.0%
- All-correct rate by task: 96.0%
- Consistency rate by task: 100.0%
- Tie rate by task: 0.0%
- Unstable tasks: 0
- Stable failure tasks: 12
- Format error rate: 0.0%
- Tool violation rate: 0.0%
- Median input tokens: -
- Median output tokens: -
- Median reasoning tokens: -
- Median latency: 1.15e-05 s
- Total input tokens: -
- Total output tokens: -
- Total reasoning tokens: -
- Observed input+output tokens: -

## By domain

| domain | cases | tasks | accuracy | majority | consistency | weighted | format errors | tool violations | total in | total out | total reasoning | median reasoning | median latency s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code | 55 | 55 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | - | - | - | - | 1.18e-05 |
| instruction | 38 | 38 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | - | - | - | - | 1.17e-05 |
| logic | 60 | 60 | 93.3% | 93.3% | 100.0% | 93.3% | 0.0% | 0.0% | - | - | - | - | 1.1e-05 |
| math | 85 | 85 | 91.8% | 91.8% | 100.0% | 91.8% | 0.0% | 0.0% | - | - | - | - | 1.1e-05 |
| metacognition | 5 | 5 | 80.0% | 80.0% | 100.0% | 80.0% | 0.0% | 0.0% | - | - | - | - | 1.24e-05 |
| reading | 45 | 45 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | - | - | - | - | 1.15e-05 |
| robustness | 12 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | - | - | - | - | 1.66e-05 |

## Failures

| task | repeat | domain | skill | failure mode | answer | expected | detail |
|---|---:|---|---|---|---|---|---|
| candy_shape_select_001 | 1 | math | worst_case_reasoning | synthetic_regression | __synthetic_wrong__ | 21 | Synthetic degraded example. |
| candy_blind_draw_001 | 1 | math | worst_case_reasoning | synthetic_regression | __synthetic_wrong__ | 29 | Synthetic degraded example. |
| candy_ambiguity_001 | 1 | metacognition | ambiguity_detection | synthetic_regression | __synthetic_wrong__ | ['歧义', '21', '29'] | Synthetic degraded example. |
| pigeonhole_colors_001 | 1 | math | pigeonhole | synthetic_regression | __synthetic_wrong__ | 15 | Synthetic degraded example. |
| socks_pair_001 | 1 | math | pigeonhole | synthetic_regression | __synthetic_wrong__ | 5 | Synthetic degraded example. |
| sequence_001 | 1 | math | pattern_reasoning | synthetic_regression | __synthetic_wrong__ | 42 | Synthetic degraded example. |
| arithmetic_order_001 | 1 | math | calculation | synthetic_regression | __synthetic_wrong__ | 19 | Synthetic degraded example. |
| rate_work_001 | 1 | math | word_problem | synthetic_regression | __synthetic_wrong__ | 2.4 | Synthetic degraded example. |
| knights_knaves_001 | 1 | logic | truthfulness_reasoning | synthetic_regression | __synthetic_wrong__ | D | Synthetic degraded example. |
| box_labels_001 | 1 | logic | constraint_reasoning | synthetic_regression | __synthetic_wrong__ | C | Synthetic degraded example. |
| conditional_001 | 1 | logic | deduction | synthetic_regression | __synthetic_wrong__ | B | Synthetic degraded example. |
| logic_ordering_001 | 1 | logic | ordering | synthetic_regression | __synthetic_wrong__ | 丁 | Synthetic degraded example. |
