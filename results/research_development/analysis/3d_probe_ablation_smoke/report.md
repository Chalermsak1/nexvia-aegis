# Exploratory 3D benchmark summary

Development simulation only. These are descriptive observations, not a safety certificate or confirmatory test.
Input SHA-256: `ebeaf8b6df40a1d865e8da2bc00d3004f901a469e15a6424c93abbbd7fb7e624`
Declared range fault: `{"bias_m": 0.0, "dropout_probability": 0.0, "latency_steps": 0}`

| Controller | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted | Abstain | Timeout | Collision | CBF infeasible episodes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | 15 | 3 | 9 | 12 | 80.0% | 75.0% | 0 | 3 | 1 | 0 |
| CBF_ONLY | 15 | 3 | 7 | 10 | 66.7% | 70.0% | 0 | 5 | 0 | 0 |
| AEGIS_V9_CBF | 15 | 1 | 2 | 3 | 20.0% | 66.7% | 3 | 9 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_GUARD | 15 | 1 | 0 | 1 | 6.7% | 0.0% | 5 | 9 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_WINDOW | 15 | 1 | 0 | 1 | 6.7% | 0.0% | 5 | 9 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_3D_VETO | 15 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) | 6 | 9 | 0 | 0 |
| AEGIS_3D_AWARE_CBF | 15 | 6 | 2 | 8 | 53.3% | 25.0% | 2 | 5 | 0 | 0 |
| AEGIS_3D_NO_ACTIVE_PROBE | 15 | 3 | 0 | 3 | 20.0% | 0.0% | 11 | 1 | 0 | 0 |

## Results by vector-bias scenario

| Controller | Bias (x, y, z) | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted |
|---|---|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | [0.0, 0.0, 0.0] | 5 | 3 | 1 | 4 | 80.0% | 25.0% |
| UNSHIELDED | [0.5, -0.4, 0.2] | 5 | 0 | 5 | 5 | 100.0% | 100.0% |
| UNSHIELDED | [0.8, 0.8, -0.3] | 5 | 0 | 3 | 3 | 60.0% | 100.0% |
| CBF_ONLY | [0.0, 0.0, 0.0] | 5 | 3 | 1 | 4 | 80.0% | 25.0% |
| CBF_ONLY | [0.5, -0.4, 0.2] | 5 | 0 | 4 | 4 | 80.0% | 100.0% |
| CBF_ONLY | [0.8, 0.8, -0.3] | 5 | 0 | 2 | 2 | 40.0% | 100.0% |
| AEGIS_V9_CBF | [0.0, 0.0, 0.0] | 5 | 0 | 1 | 1 | 20.0% | 100.0% |
| AEGIS_V9_CBF | [0.5, -0.4, 0.2] | 5 | 1 | 0 | 1 | 20.0% | 0.0% |
| AEGIS_V9_CBF | [0.8, 0.8, -0.3] | 5 | 0 | 1 | 1 | 20.0% | 100.0% |
| AEGIS_V9_CBF_RANGE_GUARD | [0.0, 0.0, 0.0] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_GUARD | [0.5, -0.4, 0.2] | 5 | 1 | 0 | 1 | 20.0% | 0.0% |
| AEGIS_V9_CBF_RANGE_GUARD | [0.8, 0.8, -0.3] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.0, 0.0, 0.0] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.5, -0.4, 0.2] | 5 | 1 | 0 | 1 | 20.0% | 0.0% |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.8, 0.8, -0.3] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.0, 0.0, 0.0] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.5, -0.4, 0.2] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.8, 0.8, -0.3] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_3D_AWARE_CBF | [0.0, 0.0, 0.0] | 5 | 3 | 0 | 3 | 60.0% | 0.0% |
| AEGIS_3D_AWARE_CBF | [0.5, -0.4, 0.2] | 5 | 2 | 0 | 2 | 40.0% | 0.0% |
| AEGIS_3D_AWARE_CBF | [0.8, 0.8, -0.3] | 5 | 1 | 2 | 3 | 60.0% | 66.7% |
| AEGIS_3D_NO_ACTIVE_PROBE | [0.0, 0.0, 0.0] | 5 | 3 | 0 | 3 | 60.0% | 0.0% |
| AEGIS_3D_NO_ACTIVE_PROBE | [0.5, -0.4, 0.2] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_3D_NO_ACTIVE_PROBE | [0.8, 0.8, -0.3] | 5 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |

Collision and CBF infeasibility can overlap terminal outcomes. Seeds are reused across arms and bias scenarios; do not treat these rows as independent confirmatory observations. Completeness is checked against the input's declared design, not an independent assignment manifest. Required scientific baselines and model provenance need separate review.
