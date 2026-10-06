from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np


@dataclass(frozen=True)
class WorldConfig:
    timestep: float = 0.02
    arena_size: float = 6.0

    robot_mass: float = 1.0
    robot_radius: float = 0.20

    control_force: float = 1.0
    actuator_noise: float = 0.0

    target_radius: float = 0.20
    success_radius: float = 0.25

    max_steps: int = 300

    moving_target: bool = False
    target_velocity: tuple[float, float] = (0.0, 0.0)

    external_force_probability: float = 0.0
    external_force_scale: float = 0.0


class AegisPhysicalWorld:
    """
    Nexvia Aegis 3.0 physical simulation world.

    Responsibilities:
    - MuJoCo physics
    - robot dynamics
    - target state
    - moving target
    - actuator noise
    - external disturbances

    This class exposes ground truth for evaluation.
    The agent must not use ground truth directly.
    """

    def __init__(
        self,
        config: WorldConfig | None = None,
    ):
        self.config = config or WorldConfig()

        self.model = self._build_model()
        self.data = mujoco.MjData(self.model)

        self.robot_body_id = self.model.body(
            "robot"
        ).id

        self.step_count = 0

        self.robot_pos = np.zeros(
            2,
            dtype=np.float64,
        )

        self.robot_velocity = np.zeros(
            2,
            dtype=np.float64,
        )

        self.target_pos = np.zeros(
            2,
            dtype=np.float64,
        )

    def _build_model(self) -> mujoco.MjModel:
        c = self.config

        xml = f"""
        <mujoco model="nexvia_aegis_v3">

          <option
            timestep="{c.timestep}"
            gravity="0 0 -9.81"
          />

          <worldbody>

            <geom
              name="floor"
              type="plane"
              size="{c.arena_size} {c.arena_size} 0.1"
              pos="0 0 0"
            />

            <body
              name="robot"
              pos="-2 -2 0.25"
            >
              <freejoint/>

              <geom
                name="robot_geom"
                type="sphere"
                size="{c.robot_radius}"
                mass="{c.robot_mass}"
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
              size="{c.target_radius}"
            />

          </worldbody>

        </mujoco>
        """

        return mujoco.MjModel.from_xml_string(xml)

    def reset(
        self,
        rng: np.random.Generator,
    ) -> dict:
        mujoco.mj_resetData(
            self.model,
            self.data,
        )

        self.step_count = 0

        self.robot_pos = np.array(
            [-2.0, -2.0],
            dtype=np.float64,
        )

        self.robot_velocity = np.zeros(
            2,
            dtype=np.float64,
        )

        self.target_pos = rng.uniform(
            low=-3.0,
            high=3.0,
            size=2,
        )

        self.data.qpos[:3] = [
            self.robot_pos[0],
            self.robot_pos[1],
            0.25,
        ]

        self.data.qpos[3:7] = [
            1.0,
            0.0,
            0.0,
            0.0,
        ]

        self.data.qvel[:] = 0.0

        mujoco.mj_forward(
            self.model,
            self.data,
        )

        return self.state()

    def state(self) -> dict:
        robot_pos = self.data.xpos[
            self.robot_body_id
        ][:2].copy()

        robot_velocity = self.data.qvel[
            :2
        ].copy()

        self.robot_pos = robot_pos
        self.robot_velocity = robot_velocity

        distance = float(
            np.linalg.norm(
                self.target_pos - robot_pos
            )
        )

        return {
            "robot_pos": robot_pos,
            "robot_velocity": robot_velocity,
            "target_pos": self.target_pos.copy(),
            "distance": distance,
            "step": self.step_count,
        }

    def _move_target(self):
        if not self.config.moving_target:
            return

        velocity = np.asarray(
            self.config.target_velocity,
            dtype=np.float64,
        )

        self.target_pos += (
            velocity * self.config.timestep
        )

        limit = self.config.arena_size - 0.5

        for axis in range(2):
            if self.target_pos[axis] < -limit:
                self.target_pos[axis] = -limit

            if self.target_pos[axis] > limit:
                self.target_pos[axis] = limit

    def step(
        self,
        action: np.ndarray,
        rng: np.random.Generator,
    ) -> dict:
        action = np.asarray(
            action,
            dtype=np.float64,
        )

        action = np.clip(
            action,
            -1.0,
            1.0,
        )

        # Actuator noise.
        if self.config.actuator_noise > 0.0:
            action = (
                action
                + rng.normal(
                    0.0,
                    self.config.actuator_noise,
                    size=2,
                )
            )

            action = np.clip(
                action,
                -1.0,
                1.0,
            )

        applied_force = (
            action
            * self.config.control_force
        )

        # External disturbance.
        if (
            self.config.external_force_probability
            > 0.0
            and rng.random()
            < self.config.external_force_probability
        ):
            disturbance = rng.normal(
                0.0,
                self.config.external_force_scale,
                size=2,
            )

            applied_force += disturbance

        self.data.xfrc_applied[
            self.robot_body_id,
            :2,
        ] = applied_force

        mujoco.mj_step(
            self.model,
            self.data,
        )

        self.data.xfrc_applied[
            self.robot_body_id,
            :2,
        ] = 0.0

        self._move_target()

        self.step_count += 1

        current = self.state()

        current["terminated"] = (
            current["distance"]
            <= self.config.success_radius
        )

        current["truncated"] = (
            self.step_count
            >= self.config.max_steps
        )

        return current

    def close(self):
        self.data = None
        self.model = None
