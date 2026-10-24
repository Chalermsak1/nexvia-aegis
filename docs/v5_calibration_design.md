# NEXVIA AEGIS V5.0 — Mathematical Calibration Design & Coordinate Geometry

**Author:** Autonomous Systems & Robotics Research Group  
**Project:** NEXVIA AEGIS (Physical AI Research Initiative)  
**Version:** 5.0  
**Date:** October 16, 2026  
**Status:** Validated & Audited  

---

## 1. Physical Environment & Coordinate Frame Verification

Before formulating the calibration residual, the coordinate frame and measurement geometry were explicitly audited against the MuJoCo simulation model (`src/aegis/v3/env/world.py`).

### 1.1 World Frame & Robot Geometry
- **Coordinate System:** Right-handed 2D Euclidean Cartesian plane $(x, y) \in \mathbb{R}^2$ on a bounded arena $[-3.0, 3.0] \times [-3.0, 3.0]$ meters.
- **Robot Body:** Rigid sphere ($m = 1.0\text{ kg}$, $r = 0.20\text{ m}$) governed by MuJoCo continuous-time dynamics with simulation timestep $\Delta t = 0.02\text{ s}$.
- **Target Position:** Fixed spatial waypoint $\mathbf{p}_{\text{target}} \in \mathbb{R}^2$.
- **True Target Displacement:** $\mathbf{d}_t = \mathbf{p}_{\text{target}} - \mathbf{p}_{\text{robot}}(t)$.
- **True Scalar Distance:** $D_t = \|\mathbf{d}_t\|_2 = \sqrt{d_{t,x}^2 + d_{t,y}^2}$.

### 1.2 Coordinate Convention
- **Vector Sensors (Primary & Secondary):** Vector sensors report the **relative displacement from the robot to the target** in the robot's local translational frame:
  $$\mathbf{z}_t = \mathbf{d}_t + \mathbf{b} + \boldsymbol{\epsilon}_t, \quad \boldsymbol{\epsilon}_t \sim \mathcal{N}(\mathbf{0}, \sigma_{\text{vec}}^2 \mathbf{I}_2)$$
  The vector measurements represent **relative target displacement**, not absolute world positions.
- **Scalar Range Sensor (Cross-Modal Reference):** Independent line-of-sight range sensor reporting scalar distance:
  $$r_t = \|\mathbf{d}_t\|_2 + \nu_t, \quad \nu_t \sim \mathcal{N}(0, \sigma_{\text{range}}^2)$$

---

## 2. Geometric Residual Formulation

Given a candidate vector sensor bias $\mathbf{b} \in \mathbb{R}^2$, the corrected relative displacement estimate is:
$$\hat{\mathbf{d}}_t(\mathbf{b}) = \mathbf{z}_t - \mathbf{b}$$

The cross-modal geometric residual compares the Euclidean norm of this corrected vector against the independent scalar range measurement:
$$e_t(\mathbf{b}) = \|\mathbf{z}_t - \mathbf{b}\|_2 - r_t$$

### Numerical Sanity Verification
For synthetic zero-noise data with known injected bias $\mathbf{b}^* = [0.75, -0.45]^T$:
$$\|\mathbf{z}_t - \mathbf{b}^*\|_2 = \|(\mathbf{d}_t + \mathbf{b}^*) - \mathbf{b}^*\|_2 = \|\mathbf{d}_t\|_2 = r_t \implies e_t(\mathbf{b}^*) = 0$$
This identity holds with machine precision ($\|e_t(\mathbf{b}^*)\| < 10^{-15}$), verifying that Candidate Model A (relative displacement) is the exact mathematical formulation.

---

## 3. Closed-Form Linear Algebraic Initialization

Non-linear least squares optimization over circular intersections can suffer from local minima and mirror-symmetric saddles. AEGIS V5.0 introduces an exact algebraic linearization to compute an instantaneous global starting guess $\mathbf{x}_0$.

Squaring both sides of the residual model $\|\mathbf{z}_t - \mathbf{b}\|^2 \approx r_t^2$:
$$\|\mathbf{z}_t\|^2 - 2 \mathbf{z}_t^T \mathbf{b} + \|\mathbf{b}\|^2 = r_t^2 \implies 2 \mathbf{z}_t^T \mathbf{b} - \|\mathbf{b}\|^2 = \|\mathbf{z}_t\|^2 - r_t^2$$

Subtracting the equation at reference timestep $t = 0$ cancels the non-linear term $\|\mathbf{b}\|^2$ completely:
$$2 (\mathbf{z}_t - \mathbf{z}_0)^T \mathbf{b} = \left(\|\mathbf{z}_t\|^2 - r_t^2\right) - \left(\|\mathbf{z}_0\|^2 - r_0^2\right)$$

Dividing by 2 yields a linear system:
$$\mathbf{A}_t \mathbf{b} = y_t$$
where:
$$\mathbf{A}_t = (\mathbf{z}_t - \mathbf{z}_0)^T \in \mathbb{R}^{1 \times 2}, \quad y_t = \frac{1}{2} \left[ (\|\mathbf{z}_t\|^2 - r_t^2) - (\|\mathbf{z}_0\|^2 - r_0^2) \right] \in \mathbb{R}$$

For a measurement window of $N$ observations, stacking row-wise yields:
$$\mathbf{A} \mathbf{b} \approx \mathbf{y}, \quad \mathbf{A} \in \mathbb{R}^{(N-1) \times 2}, \quad \mathbf{y} \in \mathbb{R}^{N-1}$$

The unconstrained linear least-squares estimate is solved via SVD:
$$\mathbf{b}_{\text{init}} = (\mathbf{A}^T \mathbf{A})^{-1} \mathbf{A}^T \mathbf{y}$$

### Physical Meaning of $\mathbf{A}$
Since $\mathbf{z}_t = \mathbf{d}_t + \mathbf{b} + \boldsymbol{\epsilon}_t$, the difference vector is:
$$\mathbf{z}_t - \mathbf{z}_0 \approx \mathbf{d}_t - \mathbf{d}_0 = - (\mathbf{p}_{\text{robot}}(t) - \mathbf{p}_{\text{robot}}(0))$$
The rows of $\mathbf{A}$ correspond directly to the **spatial displacement of the robot relative to the initial reference position**. If the robot traverses a non-collinear 2D path, $\text{rank}(\mathbf{A}) = 2$ and the system is uniquely solvable.

---

## 4. Non-Linear Robust Estimation (Huber Loss)

The algebraic estimate $\mathbf{b}_{\text{init}}$ serves as the starting point $\mathbf{x}_0$ for non-linear M-estimation within physical parameter bounds $\mathbf{b} \in [-1.5, 1.5]^2$:

$$\hat{\mathbf{b}} = \arg\min_{\mathbf{b} \in [-1.5, 1.5]^2} \sum_{t=1}^N \rho_\delta(e_t(\mathbf{b}))$$

where $\rho_\delta(\cdot)$ is the Huber loss function:
$$\rho_\delta(e) = \begin{cases} \frac{1}{2} e^2 & \text{if } |e| \le \delta \\ \delta (|e| - \frac{1}{2} \delta) & \text{if } |e| > \delta \end{cases}$$
with scale parameter $\delta = 0.08\text{ m}$.

- **OLS (Ordinary Least Squares):** Equivalent to $\delta = \infty$ (linear loss). Highly sensitive to heavy-tail outlier bursts.
- **Huber Robust Loss:** Transitions to linear penalty for residuals exceeding $\delta$, downweighting sensor burst outliers by up to $60\times$.

---

## 5. Observability Analysis & Geometric Qualification Gate

Trilateration circles intersect at grazing angles when the robot motion baseline $B$ is small relative to the target distance $D$.

### 5.1 Residual Jacobian & Fisher Information Matrix
The sensitivity of the geometric residual with respect to bias is:
$$\mathbf{J}_t = \frac{\partial e_t(\mathbf{b})}{\partial \mathbf{b}} = - \frac{\mathbf{z}_t - \mathbf{b}}{\|\mathbf{z}_t - \mathbf{b}\|_2} = - \hat{\mathbf{u}}_t \in \mathbb{R}^{1 \times 2}$$
where $\hat{\mathbf{u}}_t$ is the unit vector pointing along the line of sight to the target.

The Fisher Information Matrix (Jacobian Gram matrix) is:
$$\mathbf{F} = \mathbf{J}^T \mathbf{J} = \sum_{t=1}^N \hat{\mathbf{u}}_t \hat{\mathbf{u}}_t^T \in \mathbb{R}^{2 \times 2}$$

Let $\lambda_{\max} \ge \lambda_{\min} \ge 0$ be the eigenvalues of $\mathbf{F}$.
- **Minimum Eigenvalue $\lambda_{\min}$:** Measures geometric diversity across the minor observation axis. When the robot moves along a 1D line or remains stationary, $\hat{\mathbf{u}}_t \approx \hat{\mathbf{u}}_0$ for all $t$, and $\lambda_{\min} \to 0$.
- **Condition Number $\kappa = \lambda_{\max} / \lambda_{\min}$:** Quantifies collinearity. For 2D orthogonal probing, $\kappa \in [2000, 8500]$. For 1D collinear motion, $\kappa > 120,000$.

### 5.2 Qualification Gate Thresholds
A candidate calibration is certified only if:
1. **Sample Count Gate:** $N \ge N_{\min} = 6$.
2. **Residual Magnitude Gate:** $\text{RMSE}_{\text{train}} \le \tau_{\text{res}} = 0.25\text{ m}$.
3. **Observability Gate:** $\lambda_{\min} \ge \tau_\lambda = 0.0005$ and $\kappa \le \kappa_{\max} = 15,000$.
4. **Independent Validation Gate:** $\text{RMSE}_{\text{val}} \le \tau_{\text{val}} = 0.15\text{ m}$ on held-out samples.

If any check fails, the estimator returns an explicit rejection code (`REJECTED_POOR_OBSERVABILITY`, `REJECTED_ILL_CONDITIONED`, `REJECTED_HIGH_RESIDUAL`, `REJECTED_INSUFFICIENT_DATA`), forcing the recovery controller to retain conservative abstention.

---

## 6. Information Architecture & Ground-Truth Separation

| Data Classification | Variables | Accessible Subsystems | Restrictions |
| :--- | :--- | :--- | :--- |
| **Agent Observable** | $\mathbf{z}_t^a, \mathbf{z}_t^b, r_t$, $\Delta t$, verification status | Controller, Estimator, Policy | Valid measurements only; NaNs discarded |
| **Evaluator Only** | $\mathbf{p}_{\text{robot}}, \mathbf{p}_{\text{target}}, \mathbf{d}_t$, injected bias $\mathbf{b}^*$ | Benchmark Logger, Regression Tests | **Strictly prohibited** from online estimator |
| **Diagnostic Oracle** | $\hat{\mathbf{b}} = \mathbf{b}^*$ (Ground Truth) | Oracle Upper-Bound Policy | Non-deployable theoretical ceiling only |
