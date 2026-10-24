from __future__ import annotations

import numpy as np
import pytest

from aegis.env.inspection import (
    ABSTAIN,
    INSPECT,
    MOVE,
    STOP,
    VERIFY,
    AegisInspectionEnv,
)
from aegis.policies import (
    AegisPolicy,
    AgentContext,
    AlwaysActPolicy,
    InspectOncePolicy,
)


def test_inspection_env_initialization():
    env = AegisInspectionEnv(scenario="normal")
    obs, info = env.reset(seed=42)
    assert obs.shape == (12,)
    assert "inspection_count" in info
    assert "verification_count" in info
    assert "step_count" in info
    env.close()


def test_always_act_policy():
    env = AegisInspectionEnv(scenario="normal")
    policy = AlwaysActPolicy()
    obs, info = env.reset(seed=42)

    context = AgentContext(
        inspection_count=info["inspection_count"],
        max_inspections=env.max_inspections,
        verification_count=info["verification_count"],
        max_verifications=env.max_verifications,
        step_count=info["step_count"],
    )

    action = policy.act(obs, context)
    assert action in (MOVE, STOP)
    env.close()


def test_inspect_once_policy():
    env = AegisInspectionEnv(scenario="normal")
    policy = InspectOncePolicy()
    obs, info = env.reset(seed=42)

    context = AgentContext(
        inspection_count=0,
        max_inspections=env.max_inspections,
        verification_count=0,
        max_verifications=env.max_verifications,
        step_count=0,
    )
    assert policy.act(obs, context) == INSPECT

    context.inspection_count = 1
    assert policy.act(obs, context) in (MOVE, STOP)
    env.close()


def test_aegis_policy_execution():
    env = AegisInspectionEnv(scenario="normal")
    policy = AegisPolicy()
    obs, info = env.reset(seed=42)
    policy.reset(seed=42)

    context = AgentContext(
        inspection_count=info["inspection_count"],
        max_inspections=env.max_inspections,
        verification_count=info["verification_count"],
        max_verifications=env.max_verifications,
        step_count=info["step_count"],
    )

    action = policy.act(obs, context)
    assert action in (MOVE, INSPECT, STOP, ABSTAIN, VERIFY)
    assert "distance" in policy.last_diagnostics
    assert "probability" in policy.last_diagnostics
    env.close()
