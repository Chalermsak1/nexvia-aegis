# Exploratory 3D benchmark summary

Development simulation only. These are descriptive observations, not a safety certificate or confirmatory test.
Input SHA-256: `ff873f92b23212e366d63bb17f4d54dedff8c9c13526a8e4ec8e439caaf4695c`

| Controller | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted | Abstain | Timeout | Collision | CBF infeasible episodes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | 9 | 2 | 5 | 7 | 77.8% | 71.4% | 0 | 2 | 1 | 0 |
| CBF_ONLY | 9 | 2 | 2 | 4 | 44.4% | 50.0% | 0 | 5 | 0 | 0 |
| AEGIS_V9_CBF | 9 | 1 | 0 | 1 | 11.1% | 0.0% | 0 | 8 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_GUARD | 9 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) | 1 | 8 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_WINDOW | 9 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) | 1 | 8 | 0 | 0 |
| AEGIS_V9_CBF_RANGE_3D_VETO | 9 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) | 1 | 8 | 0 | 0 |
| AEGIS_3D_AWARE_CBF | 9 | 6 | 0 | 6 | 66.7% | 0.0% | 0 | 3 | 0 | 0 |

## Results by vector-bias scenario

| Controller | Bias (x, y, z) | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted |
|---|---|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | [0.0, 0.0, 0.0] | 3 | 2 | 1 | 3 | 100.0% | 33.3% |
| UNSHIELDED | [0.5, -0.4, 0.2] | 3 | 0 | 3 | 3 | 100.0% | 100.0% |
| UNSHIELDED | [0.8, 0.8, -0.3] | 3 | 0 | 1 | 1 | 33.3% | 100.0% |
| CBF_ONLY | [0.0, 0.0, 0.0] | 3 | 2 | 0 | 2 | 66.7% | 0.0% |
| CBF_ONLY | [0.5, -0.4, 0.2] | 3 | 0 | 2 | 2 | 66.7% | 100.0% |
| CBF_ONLY | [0.8, 0.8, -0.3] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF | [0.0, 0.0, 0.0] | 3 | 1 | 0 | 1 | 33.3% | 0.0% |
| AEGIS_V9_CBF | [0.5, -0.4, 0.2] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF | [0.8, 0.8, -0.3] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_GUARD | [0.0, 0.0, 0.0] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_GUARD | [0.5, -0.4, 0.2] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_GUARD | [0.8, 0.8, -0.3] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.0, 0.0, 0.0] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.5, -0.4, 0.2] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_WINDOW | [0.8, 0.8, -0.3] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.0, 0.0, 0.0] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.5, -0.4, 0.2] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_V9_CBF_RANGE_3D_VETO | [0.8, 0.8, -0.3] | 3 | 0 | 0 | 0 | 0.0% | UNDEFINED (0 accepted) |
| AEGIS_3D_AWARE_CBF | [0.0, 0.0, 0.0] | 3 | 2 | 0 | 2 | 66.7% | 0.0% |
| AEGIS_3D_AWARE_CBF | [0.5, -0.4, 0.2] | 3 | 2 | 0 | 2 | 66.7% | 0.0% |
| AEGIS_3D_AWARE_CBF | [0.8, 0.8, -0.3] | 3 | 2 | 0 | 2 | 66.7% | 0.0% |

Collision and CBF infeasibility can overlap terminal outcomes. Seeds are reused across arms and bias scenarios; do not treat these rows as independent confirmatory observations. Completeness is checked against the input's declared design, not an independent assignment manifest.
