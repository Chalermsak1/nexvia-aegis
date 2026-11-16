"""Configuration preconditions for exploratory recovery noise coupling.

Declared configuration is not authenticated or automatically bound to a trace.
No scientific acceptance rule is implemented here.
"""
from scripts.research.recovery_noise_pairing import compare, _vector

ZERO_FIELDS = ('range_dropout_probability','range_latency_steps','anchor_dropout_probability',
               'velocity_dropout_probability','velocity_latency_steps','velocity_replay_probability',
               'secondary_velocity_dropout_probability')
UNIT_FIELDS = ('velocity_scale','secondary_velocity_scale')
PAIRED_FIELDS = ('seed','controller_type','sensor_bias','range_bias_m','anchor_bias_xyz',
                 'navigation_force_method','max_steps','recovery_steps','post_stop_steps','post_abstain_steps')


def validate(config):
    if not isinstance(config, dict): raise ValueError('explicit configuration required')
    required = set(ZERO_FIELDS + UNIT_FIELDS + PAIRED_FIELDS + ('velocity_bias_xyz','fail_vectors_after_stop_proposal'))
    if not required <= set(config): raise ValueError('missing explicit configuration fields')
    for name in ZERO_FIELDS:
        if type(config[name]) not in (int,float) or config[name] != 0:
            raise ValueError('unsupported fault configuration: ' + name)
    for name in UNIT_FIELDS:
        if type(config[name]) not in (int,float) or config[name] != 1:
            raise ValueError('unsupported velocity scale: ' + name)
    if config['fail_vectors_after_stop_proposal'] is not False:
        raise ValueError('adaptive vector loss outside scope')
    for name in ('sensor_bias','anchor_bias_xyz','velocity_bias_xyz'):
        _vector(config[name])
    if config['velocity_bias_xyz'] != [0,0,0]: raise ValueError('velocity bias outside scope')
    if type(config['seed']) is not int or config['seed'] < 0: raise ValueError('invalid development seed')
    if config['controller_type'] not in ('AEGIS_3D_ANCHOR_RECOVERY','AEGIS_3D_RECOVERY_MONITOR'):
        raise ValueError('unsupported controller')
    for name in ('max_steps','recovery_steps','post_stop_steps','post_abstain_steps'):
        if type(config[name]) is not int or config[name] < (1 if name in ('max_steps','recovery_steps') else 0):
            raise ValueError('invalid execution count')
    if config['navigation_force_method'] not in ('AXIS_CLIP','DIRECTION_PRESERVING_PEAK'):
        raise ValueError('unknown navigation method')


def compare_configured(left, right, *, left_config, right_config, numerical_tolerance):
    validate(left_config); validate(right_config)
    if any(left_config[k] != right_config[k] for k in PAIRED_FIELDS):
        raise ValueError('unmatched pair configuration')
    result = compare(left, right, vector_bias=left_config['sensor_bias'],
                     anchor_bias=left_config['anchor_bias_xyz'], range_bias=left_config['range_bias_m'],
                     numerical_tolerance=numerical_tolerance)
    result['configuration_preconditions'] = 'SUPPORTED_DECLARED_PAIR'
    result['limitations'].append('Configuration is caller-declared, not independently bound or authenticated to these traces.')
    return result
