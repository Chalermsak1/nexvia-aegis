from __future__ import annotations

import numpy as np
import mujoco
import gymnasium as gym
from gymnasium import spaces


class AegisMuJoCoEnv(gym.Env):
    """
    Nexvia Aegis v2.0 - physics-based research environment.

    Phase 1:
    - A 2D point-mass robot simulated in MuJoCo.
    - Robot moves in the XY plane using force control.
    - Target location is hidden from the agent.
    - Observation contains noisy target-relative measurements,
      robot velocity, and a noisy confidence estimate.
    - Ground-truth state is exposed only through info for evaluation.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        observation_noise: float = 0.05,
        control_force: float = 1.0,
        dt: float = 0.02,
        success_radius: float = 0.20,
        max_steps: int = 500,
        render_mode: str | None = None,
    ):
        super().__init__()

        self.observation_noise = observation_noise
        self.control_force = control_force
        self.dt = dt
        self.success_radius = success_radius
        self.max_steps = max_steps
        self.render_mode = render_mode

        self.model = self._build_model()
        self.data = mujoco.MjData(self.model)

        self.robot_joint = 0
        self.step_count = 0

        # Action = force in X/Y.
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(2,),
            dtype=np.float32,
        )

        # Observation:
        # [robot_x, robot_y,
        #  robot_vx, robot_vy,
        #  noisy_target_dx, noisy_target_dy,
        #  confidence]
        self.observation_space = spaces.Box(
            low=np.array(
                [-10.0, -10.0, -10.0, -10.0, -20.0, -20.0, 0.0],
                dtype=np.float32,
            ),
            high=np.array(
                [10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 1.0],
                dtype=np.float32,
            ),
            dtype=np.float32,
        )

        self.robot_pos = np.zeros(2, dtype=np.float64)
        self.target_pos = np.zeros(2, dtype=np.float64)

    def _build_model(self) -> mujoco.MjModel:
        xml = """
        <mujoco model="nexvia_aegis_v2">
          <option timestep="0.02" gravity="0 0 -9.81"/>

          <worldbody>

            <geom
              name="floor"
              type="plane"
              size="10 10 0.1"
              pos="0 0 0"
              rgba="0.15 0.15 0.18 1"
            />

            <body name="robot" pos="0 0 0.25">
              <freejoint/>

              <geom
                name="robot_geom"
                type="sphere"
                size="0.20"
                mass="1"
                rgba="0.2 0.6 1 1"
              />

              <site
                name="robot_site"
                pos="0 0 0"
                size="0.05"
              />
            </body>

            <site
              name="target"
              pos="2 2 0.05"
              size="0.20"
              rgba="1 0.2 0.2 1"
            />

          </worldbody>
        </mujoco>
        """

        return mujoco.MjModel.from_xml_string(xml)

    def _get_robot_state(self):
        robot_body_id = self.model.body("robot").id

        pos = self.data.xpos[robot_body_id][:2].copy()

        # Free joint translational velocity is contained in qvel[:3].
        vel = self.data.qvel[:2].copy()

        return pos, vel

    def _get_observation(self):
        robot_pos, robot_vel = self._get_robot_state()

        true_delta = self.target_pos - robot_pos

        noise = self.np_random.normal(
            0.0,
            self.observation_noise,
            size=2,
        )

        noisy_delta = true_delta + noise

        distance = float(np.linalg.norm(true_delta))

        confidence = float(
            np.exp(
                -distance * 0.15
                - self.observation_noise * 2.0
            )
        )

        observation = np.array(
            [
                robot_pos[0],
                robot_pos[1],
                robot_vel[0],
                robot_vel[1],
                noisy_delta[0],
                noisy_delta[1],
                confidence,
            ],
            dtype=np.float32,
        )

        return observation

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.step_count = 0

        mujoco.mj_resetData(self.model, self.data)

        self.robot_pos = np.array(
            [-2.0, -2.0],
            dtype=np.float64,
        )

        self.target_pos = self.np_random.uniform(
            low=-3.0,
            high=3.0,
            size=2,
        )

        self.target_pos[0] = float(
            np.clip(self.target_pos[0], -3.0, 3.0)
        )
        self.target_pos[1] = float(
            np.clip(self.target_pos[1], -3.0, 3.0)
        )

        # Position of free body is:
        # x, y, z, qw, qx, qy, qz
        self.data.qpos[:3] = [
            self.robot_pos[0],
            self.robot_pos[1],
            0.25,
        ]

        self.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]

        mujoco.mj_forward(self.model, self.data)

        obs = self._get_observation()

        info = {
            "target_pos": self.target_pos.copy(),
            "robot_pos": self.robot_pos.copy(),
            "ground_truth_distance": float(
                np.linalg.norm(self.target_pos - self.robot_pos)
            ),
        }

        return obs, info

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)

        action = np.clip(
            action,
            self.action_space.low,
            self.action_space.high,
        )

        robot_body_id = self.model.body("robot").id

        # Apply force in XY.
        self.data.xfrc_applied[robot_body_id, :2] = (
            action * self.control_force
        )

        mujoco.mj_step(self.model, self.data)

        self.step_count += 1

        robot_pos, robot_vel = self._get_robot_state()

        distance = float(
            np.linalg.norm(self.target_pos - robot_pos)
        )

        terminated = distance <= self.success_radius
        truncated = self.step_count >= self.max_steps

        # Small movement cost.
        reward = -0.01 * float(np.linalg.norm(action))

        if terminated:
            reward += 1.0

        obs = self._get_observation()

        info = {
            "target_pos": self.target_pos.copy(),
            "robot_pos": robot_pos.copy(),
            "ground_truth_distance": distance,
            "step_count": self.step_count,
        }

        # Stop force after each step.
        self.data.xfrc_applied[robot_body_id, :2] = 0.0

        return (
            obs,
            reward,
            terminated,
            truncated,
            info,
        )

    def render(self):
        # Rendering will be added in the next phase.
        return None

    def close(self):
        pass
