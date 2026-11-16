"""Development-only capture witness and independently ticked command lease.

A separate capture registry is a MODELED TRUST ASSUMPTION, not an authenticated
sensor, secure clock, signature, production ticket or physical freshness proof.
A compromised registry can vouch for stale values. A lease only limits duration;
it cannot recognize a timely but semantically wrong command.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from .bounded_braking import BoundedStatePacket, scalar, vector


def payload_sha256(packet):
    if not isinstance(packet, BoundedStatePacket): raise ValueError('missing packet')
    body = asdict(packet)
    body.pop('sequence'); body.pop('acquired_seconds')
    # Full measurement payload is bound; delivery sequence/time are checked separately.
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class CaptureWitness:
    """Direct-state-sensor capture registry, separately scheduled in simulation.

    Not an estimator attestation: a real estimator's transformations/dependencies
    need their own provenance contract. No register/renew interface is exposed to
    the command producer in the study. Old records are not reissued as new ones.
    """
    def __init__(self, *, dt_seconds=.02):
        self.dt = scalar(dt_seconds, 'capture tick', positive=True)
        self.records, self.last_capture = {}, {}

    def capture(self, packet, *, tick):
        if type(tick) is not int or tick < 0 or not isinstance(packet, BoundedStatePacket):
            raise ValueError('invalid capture')
        if packet.source not in ('SIM_PRIMARY', 'SIM_SECONDARY'): raise ValueError('unknown source')
        if tick <= self.last_capture.get(packet.source, -1): raise ValueError('capture replay')
        if packet.acquired_seconds != tick * self.dt: raise ValueError('capture time mismatch')
        record = {'id': f'{packet.source}:{tick}', 'source': packet.source, 'capture_tick': tick,
                  'payload_sha256': payload_sha256(packet)}
        self.records[record['id']] = record
        self.last_capture[packet.source] = tick
        return dict(record)


class FreshnessGateway:
    """Compare untrusted delivery to separately supplied capture evidence.

    Registry/witness authenticity and correct clock remain caller assumptions.
    The study does not use signatures or infer trust from this hash comparison.
    Any rejection latches; callers cannot clear it with a later favorable sample.
    """
    def __init__(self, *, dt_seconds=.02, max_age_ticks=4):
        self.dt = scalar(dt_seconds, 'gateway tick', positive=True)
        if type(max_age_ticks) is not int or max_age_ticks < 0: raise ValueError('invalid age')
        self.max_age = max_age_ticks
        self.failure, self.used = None, {}

    def check(self, packet, receipt_id, *, tick, witness):
        if self.failure: return {'accepted': False, 'reason': 'LATCHED:' + self.failure}
        try:
            if type(tick) is not int or tick < 0: raise ValueError('INVALID_GATEWAY_TICK')
            if not isinstance(packet, BoundedStatePacket): raise ValueError('MISSING_PACKET')
            if not isinstance(receipt_id, str) or receipt_id not in witness.records: raise ValueError('MISSING_CAPTURE_RECEIPT')
            receipt = witness.records[receipt_id]
            if receipt['source'] != packet.source: raise ValueError('CAPTURE_SOURCE_MISMATCH')
            acquired = receipt['capture_tick']
            if acquired > tick: raise ValueError('FUTURE_CAPTURE')
            if tick - acquired > self.max_age: raise ValueError('STALE_CAPTURE')
            if acquired <= self.used.get(packet.source, -1): raise ValueError('CAPTURE_REUSED')
            if packet.acquired_seconds != acquired * self.dt: raise ValueError('RELABELLED_ACQUISITION_TIME')
            if payload_sha256(packet) != receipt['payload_sha256']: raise ValueError('CAPTURE_PAYLOAD_MISMATCH')
        except (ValueError, TypeError, OverflowError) as exc:
            self.failure = str(exc) or type(exc).__name__
            return {'accepted': False, 'reason': self.failure}
        self.used[packet.source] = acquired
        return {'accepted': True, 'reason': 'MATCHES_MODELED_CAPTURE_WITNESS'}


@dataclass(frozen=True)
class CommandLease:
    sequence: int
    issued_tick: int
    expires_tick: int
    force_n: object


class LeaseWatchdog:
    """Independent-tick simulation guard; one tick is one physics interval.

    Leases cover [issued_tick, expires_tick). A new heartbeat alone cannot renew
    one. Refusal, freshness failure, missed expiry or bad clock latches zero
    commanded force and requests fallback. This Python class is not an actual
    independently powered/threaded hardware watchdog.
    """
    def __init__(self, *, max_lease_ticks=1, force_norm_limit_n=2.):
        if type(max_lease_ticks) is not int or max_lease_ticks <= 0: raise ValueError('invalid lease limit')
        self.max_lease = max_lease_ticks
        self.limit = scalar(force_norm_limit_n, 'force limit', positive=True)
        self.last_tick, self.last_sequence, self.lease, self.failure = None, -1, None, None

    def advance(self, *, tick, command, refusal=False, freshness_ok=None):
        if type(tick) is not int or tick < 0: raise ValueError('invalid watchdog clock')
        if type(refusal) is not bool or (freshness_ok is not None and type(freshness_ok) is not bool): raise ValueError('invalid watchdog flags')
        if self.failure is None:
            if tick != (0 if self.last_tick is None else self.last_tick + 1): self.failure = 'WATCHDOG_CLOCK_DISCONTINUITY'
            elif freshness_ok is False: self.failure = 'FRESHNESS_REJECTED'
            elif refusal: self.failure = 'CONTROLLER_REFUSED'
            elif command is not None:
                try:
                    if not isinstance(command, CommandLease): raise ValueError('MALFORMED_LEASE')
                    if any(type(v) is not int for v in (command.sequence, command.issued_tick, command.expires_tick)): raise ValueError('NONINTEGER_LEASE')
                    if command.sequence <= self.last_sequence: raise ValueError('LEASE_REPLAY')
                    if command.issued_tick != tick: raise ValueError('LATE_OR_FUTURE_ISSUE')
                    if not 0 < command.expires_tick - command.issued_tick <= self.max_lease: raise ValueError('INVALID_LEASE_DURATION')
                    force = vector(command.force_n)
                    if math.hypot(*force) > self.limit + 1e-12: raise ValueError('EXCESS_FORCE')
                    self.lease = CommandLease(command.sequence, command.issued_tick, command.expires_tick, force)
                    self.last_sequence = command.sequence
                except (ValueError, TypeError, OverflowError) as exc:
                    self.failure = str(exc)
            if self.failure is None and (self.lease is None or tick >= self.lease.expires_tick): self.failure = 'NO_LIVE_COMMAND_LEASE'
        self.last_tick = tick
        return {'state': 'FALLBACK_REQUESTED' if self.failure else 'LIVE_LEASE',
                'reason': self.failure, 'force_n': [0., 0., 0.] if self.failure else list(self.lease.force_n),
                'fallback_requested': bool(self.failure), 'lease_expires_tick': self.lease.expires_tick if self.lease else None}
