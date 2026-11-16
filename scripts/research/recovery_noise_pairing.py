"""Noise-coupling diagnostic for complete, finite development trace observations.

Only zero-latency, no-dropout, unit-velocity-scale trace configurations are
supported. This checks coupling, not policy performance or scientific acceptance.
"""
import math


def _vector(value):
    if not isinstance(value, list) or len(value) != 3 or any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise ValueError('finite three-vector required')
    return value


def innovations(trace, *, vector_bias, anchor_bias, range_bias):
    _vector(vector_bias); _vector(anchor_bias)
    if type(range_bias) not in (float, int) or not math.isfinite(range_bias):
        raise ValueError('finite range bias required')
    if not isinstance(trace, list): raise ValueError('trace list required')
    rows = []; anchors = []
    for i, r in enumerate(trace):
        if type(r['step']) is not int or r['step'] != i: raise ValueError('trace step order mismatch')
        p, t, v = [_vector(r[k]) for k in ('position', 'target', 'velocity')]
        delta = [y - x for x, y in zip(p, t)]
        distance = r['true_distance']
        if type(distance) not in (float, int) or not math.isfinite(distance) or not math.isclose(distance, math.dist(p, t), rel_tol=0, abs_tol=1e-10):
            raise ValueError('trace distance mismatch')
        if r['vector_fault_injected'] is not False or r['range_raw_transport_valid'] is not True or r['range_fresh'] is not True:
            raise ValueError('faulted/delayed trace is outside diagnostic scope')
        raw = r['range_raw_sample']
        if type(raw) not in (float, int) or not math.isfinite(raw): raise ValueError('invalid raw range')
        row = {}
        for name in ('sensor_a', 'sensor_b'):
            row[name] = [x-y-b for x, y, b in zip(_vector(r[name]), delta, vector_bias)]
        row['range'] = [raw-distance-range_bias]
        row['velocity'] = [x-y for x,y in zip(_vector(r['velocity_observation']),v)]
        if type(r['anchor_requested']) is not bool: raise ValueError('invalid anchor request')
        if r['anchor_requested']:
            if r['anchor_valid'] is not True: raise ValueError('invalid anchor outside scope')
            anchors.append({'step': i, 'innovation': [x-y-b for x,y,b in zip(_vector(r['anchor']),delta,anchor_bias)]})
        elif r['anchor'] is not None or r['anchor_valid'] is not None:
            raise ValueError('anchor observation without request')
        rows.append(row)
    return rows, anchors


def compare(left, right, *, vector_bias, anchor_bias, range_bias, numerical_tolerance):
    if type(numerical_tolerance) not in (float, int) or not math.isfinite(numerical_tolerance) or numerical_tolerance < 0:
        raise ValueError('explicit finite nonnegative numerical tolerance required')
    kwargs = dict(vector_bias=vector_bias, anchor_bias=anchor_bias, range_bias=range_bias)
    a, aq = innovations(left, **kwargs); b, bq = innovations(right, **kwargs)
    common = min(len(a), len(b)); queries = min(len(aq),len(bq))
    def agreement(pairs):
        pairs = list(pairs)
        return all(abs(x-y) <= numerical_tolerance for x,y in pairs) if pairs else None
    comparisons = {name: agreement((x,y) for ra,rb in zip(a,b) for x,y in zip(ra[name],rb[name]))
                   for name in ('sensor_a','sensor_b','range','velocity')}
    return {'classification':'EXPLORATORY_NOISE_COUPLING_DIAGNOSTIC',
            'common_decision_steps': common, 'unmatched_decision_steps': [len(a)-common,len(b)-common],
            'innovation_agreement': comparisons, 'common_anchor_queries': queries,
            'unmatched_anchor_queries':[len(aq)-queries,len(bq)-queries],
            'anchor_query_ordinal_agreement':agreement((x,y) for ra,rb in zip(aq,bq) for x,y in zip(ra['innovation'],rb['innovation'])),
            'anchor_request_steps':[[r['step'] for r in aq],[r['step'] for r in bq]],
            'common_query_steps_equal':all(ra['step']==rb['step'] for ra,rb in zip(aq,bq)) if queries else None,
            'numerical_tolerance':numerical_tolerance,
            'limitations':['Complete supported observations required; malformed/missing readings reject, never imply agreement.',
                           'Agreement covers common prefix/query ordinals only; no physical-time alignment, authentication or efficacy claim.',
                           'Caller must independently verify zero latency/dropout/replay, unit velocity scale and declared biases.'],
            'governance':'GATE_B_NOT_AUTHORIZED'}
