"""Bounded, single-writer DEVELOPMENT temporal feedback sessions.

Replay checks are in-memory, conditional on truthful session/clock/source labels.
No durable rollback protection, cryptographic identity, action authorization,
physical execution proof, variable FIFO delay, or source-clock mapping is claimed.
"""
from copy import deepcopy
from fractions import Fraction as Q
import hashlib
import json

from .recovery_envelope_1d import internal, point, spec
from .recovery_feedback_state_1d import (
    EvidenceConflict, _bounds, _fields, _label, _meet, _tick, assess_feedback, prepare_feedback,
)


KINDS = ('STATE', 'FORCE', 'COMMAND_ENQUEUED', 'COMMAND_CONSUMED', 'POWER')
ASSUMPTIONS = ('evidence_status measurement_bounds_asserted actuator_model_asserted '
               'power_bounds_asserted command_records_asserted clock_bounds_asserted')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class TemporalFeedbackSession:
    """Explicit sessions; bounded records; rollback/conflict faults latch.

    Sequence space is per (source_id, kind) within one session. Received ticks
    come from the local caller, separately from immutable packet bodies. A source
    event may arrive out of sequence within the configured replay window; its
    original timestamp never changes. Full records are retained to the explicit
    session budget rather than silently evicting unresolved command evidence.
    """

    def __init__(self, model, *, session_id, clock_id, start_tick, limits, assumptions):
        self._model = deepcopy(model)
        self._s = spec(self._model)
        _fields(limits, 'max_transport_ticks max_state_age_ticks max_reaction_ticks reorder_window max_records max_streams')
        for name in ('max_transport_ticks', 'max_state_age_ticks', 'max_reaction_ticks'):
            if type(limits[name]) is not int or not 0 <= limits[name] <= 64:
                raise ValueError('temporal resource limits must be integer 0..64')
        for name, maximum in (('reorder_window',128), ('max_records',128), ('max_streams',32)):
            if type(limits[name]) is not int or not 1 <= limits[name] <= maximum:
                raise ValueError('invalid temporal resource budget: '+name)
        _fields(assumptions, ASSUMPTIONS)
        if assumptions['evidence_status'] not in ('COMPATIBLE_UNDER_ASSERTED_BOUNDS','UNKNOWN','CONTRADICTORY'):
            raise ValueError('invalid evidence status')
        if any(type(assumptions[key]) is not bool for key in assumptions if key != 'evidence_status'):
            raise ValueError('explicit boolean assumptions required')
        self._limits = deepcopy(limits)
        self._assumptions = deepcopy(assumptions)
        self._used_sessions = set()
        self.begin_session(session_id=session_id, clock_id=clock_id, start_tick=start_tick)

    def begin_session(self, *, session_id, clock_id, start_tick):
        """Explicit resynchronization boundary; never assumes a physical reset.

        No previous observation, power window, force or queue is carried into
        the new session. Fresh state/power inputs are required; missing force
        and queue history remain full-cap uncertainty in the existing adapter.
        IDs cannot be reused during this object's lifetime. Process restart
        requires an external trusted resynchronization procedure, not this API.
        """
        _label(session_id); _label(clock_id); _tick(start_tick)
        if session_id in self._used_sessions or len(self._used_sessions) >= 128:
            raise ValueError('session ID reuse or session resource limit; external resynchronization required')
        self._used_sessions.add(session_id)
        self._session_id, self._clock_id = session_id, clock_id
        self._start_tick = self._clock = start_tick
        self._records, self._streams = [], {}
        self._fault = None
        self._replays = self._too_old = self._rejections = 0
        return self._response('NEW_SESSION_REQUIRES_RESYNCHRONIZATION')

    def _response(self, status, **extra):
        return dict(status=status, session_id=self._session_id, clock_id=self._clock_id,
                    operational_authorization=False, action=None,
                    trust='IN_MEMORY_LABEL_CHECKS_NOT_AUTHENTICATION', **extra)

    def _latch(self, status, reason):
        self._fault = dict(status=status, reason=reason)
        return self._response(status, reason=reason)

    def _packet(self, packet, received_tick):
        _fields(packet, 'session_id clock_id frame source_id kind sequence event_tick payload')
        _label(packet['source_id'])
        if packet['frame']!='WORLD_X_SI':raise ValueError('explicit WORLD_X_SI frame required')
        if packet['kind'] not in KINDS:
            raise ValueError('unsupported event kind')
        _tick(packet['sequence']); _tick(packet['event_tick'])
        if not self._start_tick <= packet['event_tick'] <= received_tick:
            raise ValueError('event before session boundary or after receipt')
        payload = packet['payload']; kind = packet['kind']
        if kind == 'STATE':
            _fields(payload, 'position velocity')
            _bounds(payload['position']); _bounds(payload['velocity'])
        elif kind == 'FORCE':
            _fields(payload, 'force'); _bounds(payload['force'])
        elif kind == 'COMMAND_ENQUEUED':
            _fields(payload, 'command_id effective_target'); _label(payload['command_id'])
            target = _bounds(payload['effective_target'])
            if not target.inside(internal(-self._s['cap'].hi,self._s['cap'].hi)):
                raise ValueError('post-cap command bounds outside model domain')
        elif kind == 'COMMAND_CONSUMED':
            _fields(payload, 'command_id'); _label(payload['command_id'])
        else:
            _fields(payload, 'absolute_cut_ticks')
            value = payload['absolute_cut_ticks']
            if not isinstance(value,list) or len(value)!=2:
                raise ValueError('absolute cutoff interval required')
            _tick(value[0]); _tick(value[1])
            if value[0]>value[1]:raise ValueError('absolute cutoff order')

    def _reconcile(self, records):
        commands, by_tick, consumed, forces = {}, {}, {}, {}
        states = []
        power, power_receipt = None, 0
        for row in records:
            p, t, kind = row['payload'], row['event_tick'], row['kind']
            if kind == 'STATE':
                states.append(row)
            elif kind == 'FORCE':
                cap = internal(-self._s['cap'].hi,self._s['cap'].hi)
                forces[t] = _meet(forces.get(t,cap),_bounds(p['force']),'force packets conflict or exceed cap')
            elif kind == 'POWER':
                value = internal(Q(p['absolute_cut_ticks'][0]),Q(p['absolute_cut_ticks'][1]))
                power = _meet(power,value,'absolute power bounds conflict; no budget renewal or restoration')
                power_receipt = max(power_receipt,row['received_tick'])
            elif kind == 'COMMAND_ENQUEUED':
                name = p['command_id']; target = _bounds(p['effective_target'])
                if name in commands:
                    old = commands[name]
                    if old['enqueue_tick']!=t:raise EvidenceConflict('command ID reused at another enqueue tick')
                    old['target'] = _meet(old['target'],target,'command target acknowledgements conflict')
                else:
                    if t in by_tick and by_tick[t]!=name:
                        raise EvidenceConflict('two command IDs at one tick violate one-target-per-tick contract')
                    by_tick[t] = name
                    commands[name] = dict(enqueue_tick=t,target=target,source_id=row['source_id'],received_tick=row['received_tick'])
            else:
                name = p['command_id']
                if name in consumed and consumed[name]!=t:
                    raise EvidenceConflict('command acknowledged consumed at different endpoints')
                consumed[name] = t
        # Check pairwise necessary physical consistency, not just latest-arrival
        # replacement. Large gaps exceed this bounded transport implementation;
        # old packets are then retained but not asserted as current constraints.
        accel = internal(-(self._s['cap'].hi+self._s['disturbance'])/self._s['mass'].lo,
                          (self._s['cap'].hi+self._s['disturbance'])/self._s['mass'].lo)
        h = self._s['dt']
        for i, a in enumerate(states):
            for b in states[i+1:]:
                old,new = (a,b) if a['event_tick']<=b['event_tick'] else (b,a)
                age = new['event_tick']-old['event_tick']
                if age>self._limits['max_state_age_ticks']:continue
                pos,vel = _bounds(old['payload']['position']),_bounds(old['payload']['velocity'])
                pn = pos+point(age*h)*vel+point(h*h*age*(age+1)/2)*accel
                vn = vel+point(age*h)*accel
                _meet(pn,_bounds(new['payload']['position']),'state position history contradicts declared model')
                _meet(vn,_bounds(new['payload']['velocity']),'state velocity history contradicts declared model')
        if power is not None:
            for tick,value in forces.items():
                if power.hi < tick:
                    _meet(value,point(Q(0)),'force history contradicts certainly elapsed power cutoff')
        delays = set(range(self._s['delay_ticks'][0],self._s['delay_ticks'][1]+1))
        for name,endpoint in consumed.items():
            if power is not None and power.hi<=endpoint-1:
                raise EvidenceConflict('consumption acknowledgement conflicts with unpowered interval/queue flush')
            if name in commands:
                # Endpoint after completed interval, NOT enqueue, send time or
                # proof that the slew-limited force reached its target.
                delay = endpoint-commands[name]['enqueue_tick']-1
                delays.intersection_update({delay})
                if not delays:raise EvidenceConflict('consumption acknowledgements contradict static delay contract')
        return dict(commands=commands,consumed=consumed,delays=sorted(delays),power=power,
                    power_receipt=power_receipt,orphan_consumptions=sorted(set(consumed)-set(commands)))

    def ingest(self, packet, *, received_tick):
        """Ingest one body with its LOCAL receipt epoch; replays never refresh it."""
        if self._fault:return self._response(**self._fault)
        try:
            _tick(received_tick)
            if not isinstance(packet,dict):raise ValueError('packet object required')
            if packet.get('session_id')!=self._session_id or packet.get('clock_id')!=self._clock_id:
                self._rejections+=1
                return self._response('SESSION_OR_CLOCK_REJECTED')
            if received_tick<self._clock:
                return self._latch('SESSION_RESYNC_REQUIRED','local receipt clock regressed')
            self._packet(packet,received_tick)
            self._clock=received_tick
            stream=(packet['source_id'],packet['kind'])
            state=self._streams.get(stream,dict(highest=-1,seen={}))
            sequence=packet['sequence']
            fingerprint=hashlib.sha256(_canonical(packet)).hexdigest()
            if sequence in state['seen']:
                if state['seen'][sequence]!=fingerprint:
                    return self._latch('CONTRADICTORY_EVIDENCE','same stream/sequence reused with a different body')
                self._replays+=1
                return self._response('REPLAY_IGNORED')
            if sequence<=state['highest']-self._limits['reorder_window']:
                self._too_old+=1
                return self._response('STALE_SEQUENCE_REJECTED')
            if received_tick-packet['event_tick']>self._limits['max_transport_ticks']:
                self._rejections+=1
                return self._response('TRANSPORT_LATENCY_REJECTED')
            if len(self._records)>=self._limits['max_records'] or (stream not in self._streams and len(self._streams)>=self._limits['max_streams']):
                return self._latch('SESSION_RESYNC_REQUIRED','bounded record/stream budget exhausted; evidence not evicted')
            row=dict(deepcopy(packet),received_tick=received_tick)
            trial=self._records+[row]
            self._reconcile(trial)
            highest=max(state['highest'],sequence)
            seen={n:digest for n,digest in state['seen'].items() if n>highest-self._limits['reorder_window']}
            seen[sequence]=fingerprint
            self._streams[stream]=dict(highest=highest,seen=seen)
            self._records=trial
            return self._response('ACCEPTED',transport_ticks=received_tick-packet['event_tick'])
        except EvidenceConflict as exc:
            return self._latch('CONTRADICTORY_EVIDENCE',str(exc))
        except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
            self._rejections+=1
            return self._response('UNKNOWN_INPUT',reason=str(exc))

    def assess_at(self, assessment_tick, *, reaction_delay_ticks):
        """Forecast to an explicitly bounded intervention-effect epoch.

        Arbitrary capped actions are enclosed during the pre-enqueue reaction
        interval; the existing measured-P recovery policy starts at effect_tick.
        FIFO actuator delay remains separate. No future packets are used. The
        forecast does not advance the actual receipt clock into the future.
        """
        out=self._response('UNKNOWN_INPUT',assessment=None,preparation=None,
                           future_position_containment='NOT_ESTABLISHED',
                           reaction_prefix_containment=None,combined_finite_horizon_containment=None)
        if self._fault:return dict(out,**self._fault)
        try:
            _tick(assessment_tick)
            if assessment_tick<self._clock:
                self._latch('SESSION_RESYNC_REQUIRED','assessment clock regressed')
                return dict(out,**self._fault)
            self._clock=assessment_tick
            if type(reaction_delay_ticks) is not int or not 0<=reaction_delay_ticks<=self._limits['max_reaction_ticks']:
                raise ValueError('reaction forecast exceeds declared resource budget')
            effect=_tick(assessment_tick+reaction_delay_ticks)
            joint=self._reconcile(self._records)
            out.update(assessment_tick=assessment_tick,effect_tick=effect,reaction_delay_ticks=reaction_delay_ticks,
                       accepted_records=len(self._records),replays_ignored=self._replays,
                       stale_sequences_rejected=self._too_old,packets_rejected=self._rejections,
                       supported_static_delays=joint['delays'],command_tracking={},
                       orphan_consumptions=joint['orphan_consumptions'])
            for name,command in joint['commands'].items():
                endpoints=[command['enqueue_tick']+d+1 for d in joint['delays']]
                if name in joint['consumed']:status='ACKNOWLEDGED_CONSUMED_NOT_PHYSICAL_OUTCOME_PROOF'
                elif max(endpoints)<=assessment_tick:status='EXECUTION_UNCONFIRMED'
                elif min(endpoints)>assessment_tick:status='PENDING_UNDER_ASSERTED_MODEL'
                else:status='POSSIBLY_PENDING_EXECUTION_UNCONFIRMED'
                out['command_tracking'][name]=dict(status=status,possible_completion_endpoints=endpoints,
                    acknowledged_completion_tick=joint['consumed'].get(name))
            if joint['orphan_consumptions']:
                return dict(out,status='UNKNOWN_COMMAND_HISTORY',reason='consumption references lack enqueue evidence')
            latest={}
            ignored=[]
            forces=[]
            for row in self._records:
                if row['kind']=='STATE':
                    source=row['source_id'];tick=row['event_tick']
                    if effect-tick>self._limits['max_state_age_ticks']:
                        ignored.append(dict(source_id=source,event_tick=tick,reason='OUTSIDE_STATE_TRANSPORT_BUDGET'))
                        continue
                    if source not in latest or tick>latest[source]['sample_tick']:
                        latest[source]=dict(sample_tick=tick,received_tick=row['received_tick'],clock_id=self._clock_id,
                                            frame='WORLD_X_SI',source_id=source,**deepcopy(row['payload']))
                    elif tick==latest[source]['sample_tick']:
                        for name in ('position','velocity'):
                            latest[source][name]=_meet(_bounds(latest[source][name]),_bounds(row['payload'][name]),'same-epoch state conflict').wire()
                elif row['kind']=='FORCE':
                    forces.append(dict(sample_tick=row['event_tick'],received_tick=row['received_tick'],
                                       clock_id=self._clock_id,frame='WORLD_X_SI',source_id=row['source_id'],**deepcopy(row['payload'])))
            commands=[dict(enqueue_tick=c['enqueue_tick'],received_tick=c['received_tick'],clock_id=self._clock_id,
                           frame='WORLD_X_SI',source_id=c['source_id'],effective_target=c['target'].wire())
                      for c in joint['commands'].values() if c['enqueue_tick']<effect]
            power=None if joint['power'] is None else dict(
                absolute_cut_ticks=[int(joint['power'].lo),int(joint['power'].hi)],received_tick=joint['power_receipt'],
                clock_id=self._clock_id,source_id='TEMPORAL_POWER_INTERVAL_INTERSECTION')
            evidence=dict(assessment_tick=effect,clock_id=self._clock_id,max_state_age_ticks=self._limits['max_state_age_ticks'],
                          state_observations=list(latest.values()),force_observations=forces,commands=commands,power=power)
            model=deepcopy(self._model);model['delay_ticks']=[min(joint['delays']),max(joint['delays'])]
            current=deepcopy(evidence);current['assessment_tick']=assessment_tick
            current['commands']=[c for c in current['commands'] if c['enqueue_tick']<assessment_tick]
            at_start=prepare_feedback(model,current,**self._assumptions)
            if at_start['status']!='READY_CONDITIONAL_INPUTS':
                if at_start['status']=='CONTRADICTORY_EVIDENCE':
                    self._latch('CONTRADICTORY_EVIDENCE',at_start.get('reason','feedback conflict at reaction start'))
                return dict(out,status=at_start['status'],preparation=at_start,conclusion=at_start['status'])
            p0,v0=_bounds(at_start['model']['position']),_bounds(at_start['model']['velocity'])
            accel=internal(-(self._s['cap'].hi+self._s['disturbance'])/self._s['mass'].lo,
                            (self._s['cap'].hi+self._s['disturbance'])/self._s['mass'].lo)
            prefix=[];h=self._s['dt']
            for n in range(reaction_delay_ticks+1):
                pos=p0+point(n*h)*v0+point(h*h*n*(n+1)/2)*accel
                prefix.append(dict(tick=assessment_tick+n,position=pos.wire()))
            prefix_ok=all(_bounds(row['position']).inside(self._s['safe_position']) for row in prefix)
            result=assess_feedback(model,evidence,**self._assumptions)
            out.update(status=result['preparation']['status'],preparation=result['preparation'],assessment=result['assessment'],
                       conclusion=result['conclusion'],expired_state_records_not_used=ignored,
                       reaction_prefix=prefix,reaction_prefix_containment=prefix_ok)
            if result['assessment'] is not None:
                combined=prefix_ok and result['assessment']['finite_horizon_containment']
                out['combined_finite_horizon_containment']=combined
                if not prefix_ok:out['conclusion']='NOT_ESTABLISHED_REACTION_PREFIX_EXITS_SAFE_SET'
            if out['status']=='CONTRADICTORY_EVIDENCE':
                self._latch('CONTRADICTORY_EVIDENCE',result['preparation'].get('reason','feedback conflict'))
            return out
        except EvidenceConflict as exc:
            self._latch('CONTRADICTORY_EVIDENCE',str(exc))
            return dict(out,**self._fault)
        except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
            return dict(out,status='UNKNOWN_INPUT',reason=str(exc))
