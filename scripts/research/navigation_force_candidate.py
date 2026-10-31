"""Development force ablation; no safety or arrival decision."""
import numpy as np


def navigation_force(vector, limit=2., *, method='AXIS_CLIP'):
    if isinstance(limit, bool) or not np.isscalar(limit) or not np.isfinite(limit) or limit <= 0:
        raise ValueError('limit must be finite and positive')
    vector = np.asarray(vector, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError('finite 3D vector required')
    if method == 'AXIS_CLIP':
        return np.clip(vector, -limit, limit)
    if method == 'DIRECTION_PRESERVING_PEAK':
        return vector * min(1., limit / max(float(np.max(np.abs(vector))), limit))
    raise ValueError('unknown force method')
