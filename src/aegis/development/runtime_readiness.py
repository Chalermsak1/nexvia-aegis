"""DEVELOPMENT restart, deadline, calibration and response contracts.

All outputs deny operational authority. Deadlines gate computation results, not
physical actuators, and cannot preempt a blocking callback. Calibration samples
remain synthetic or unreviewed; consistency is not hardware validation.
"""
from copy import deepcopy
import time
from .durable_feedback_session import sha,runtime_identity
from .independent_clock_mapping import tick
from .recovery_feedback_state_1d import _bounds,_number


def restart_check(*,actual_checkpoint,expected_checkpoint,actual_runtime,expected_runtime,
                  boot_id,boot_start_ns,now_ns,freshness_limit_ns,fresh_observations):
    out=dict(status='RESTART_BLOCKED',operational_authorization=False,hardware_validation=False,
             boot_id=boot_id,trust='CALLER_PROVIDED_PINS_AND_FRESHNESS_NOT_HARDWARE_ATTESTATION')
    checkpoint_fields={'store_id','header_sha256','seq','head_sha256'}
    if (not isinstance(actual_checkpoint,dict) or set(actual_checkpoint)!=checkpoint_fields
            or type(actual_checkpoint.get('seq')) is not int or not 0<=actual_checkpoint['seq']<=512
            or actual_checkpoint!=expected_checkpoint or actual_runtime!=expected_runtime or actual_runtime!=runtime_identity()):
        return dict(out,reason='PIN_OR_CHECKPOINT_MISMATCH')
    if type(boot_id) is not str or not boot_id or len(boot_id)>128:raise ValueError('boot identity required')
    tick(boot_start_ns);tick(now_ns);tick(freshness_limit_ns)
    if now_ns<boot_start_ns:return dict(out,reason='BOOT_CLOCK_REGRESSED')
    required={'STATE','ACTUATOR','POWER','CLOCK_MAP'}
    if not isinstance(fresh_observations,dict) or set(fresh_observations)!=required:return dict(out,reason='FRESH_RESYNCHRONIZATION_REQUIRED')
    for row in fresh_observations.values():
        if not isinstance(row,dict) or set(row)!={'boot_id','observed_ns','received_ns','evidence_asserted'}:raise ValueError('exact fresh-observation fields required')
        tick(row['observed_ns']);tick(row['received_ns'])
        if row['boot_id']!=boot_id or row['evidence_asserted'] is not True or not boot_start_ns<=row['observed_ns']<=row['received_ns']<=now_ns or now_ns-row['observed_ns']>freshness_limit_ns:
            return dict(out,reason='STALE_OR_UNASSERTED_RESTART_EVIDENCE')
    return dict(out,status='DEV_RESYNCHRONIZED_NO_OPERATIONAL_AUTHORITY',reason=None)


class DeadlineGuard:
    """One-shot monotonic computation budget. No OS/hardware hard-RT claim."""
    def __init__(self,*,boot_id,clock=time.monotonic_ns):
        if type(boot_id) is not str or not boot_id:raise ValueError('boot identity required')
        self.boot_id=boot_id;self.clock=clock;self._last=None;self._fault=False;self._budgets={};self._counter=0

    def _now(self):
        try:value=tick(self.clock())
        except Exception:self._fault=True;raise
        if self._last is not None and value<self._last:self._fault=True
        self._last=value
        if self._fault:raise ValueError('monotonic clock fault; new boot/resynchronization required')
        return value

    def begin(self,budget_ns):
        tick(budget_ns)
        if budget_ns==0 or self._counter>=1024:raise ValueError('positive budget and bounded lifecycle required')
        start=self._now();deadline=tick(start+budget_ns);self._counter+=1
        key=self._counter;self._budgets[key]=(start,deadline)
        return dict(boot_id=self.boot_id,id=key,start_ns=start,deadline_ns=deadline)

    def evaluate(self,budget,compute):
        out=dict(status='RESULT_WITHHELD',result=None,result_sha256=None,operational_authorization=False,
                 boot_id=self.boot_id,actuation_dispatched=False)
        if not isinstance(budget,dict) or set(budget)!={'boot_id','id','start_ns','deadline_ns'}:
            return dict(out,reason='INVALID_BUDGET')
        key=budget['id']
        if type(key) is not int or type(budget['start_ns']) is not int or type(budget['deadline_ns']) is not int or budget['boot_id']!=self.boot_id or self._budgets.get(key)!=(budget['start_ns'],budget['deadline_ns']):
            return dict(out,reason='UNKNOWN_OR_REUSED_BUDGET')
        self._budgets.pop(key)  # one-shot even after failure; never renew spent time
        try:
            before=self._now()
            if before>=budget['deadline_ns']:return dict(out,reason='DEADLINE_MISSED_BEFORE_COMPUTATION',finished_ns=before)
            result=compute()
            after=self._now()
            if after>=budget['deadline_ns']:return dict(out,reason='DEADLINE_MISSED_AFTER_COMPUTATION',finished_ns=after)
            return dict(out,status='COMPUTED_WITHIN_BUDGET_NOT_DISPATCHED',result=deepcopy(result),
                        result_sha256=sha(result),finished_ns=after,reason=None)
        except Exception as exc:
            return dict(out,reason='COMPUTATION_OR_CLOCK_FAILURE',error_type=type(exc).__name__)


def calibration_check(profile,samples):
    required={'classification','device_id','reference_id','frame','velocity_error_bound','force_error_bound'}
    if not isinstance(profile,dict) or set(profile)!=required:raise ValueError('exact calibration evidence profile required')
    if profile['classification'] not in ('SYNTHETIC_ONLY','HARDWARE_UNREVIEWED'):raise ValueError('unsupported or unauthenticated calibration classification')
    if any(type(profile[k]) is not str or not 0<len(profile[k])<=128 for k in ('device_id','reference_id')):raise ValueError('device and independent reference labels required')
    if profile['frame']!='WORLD_X_SI':raise ValueError('explicit WORLD_X_SI calibration frame required')
    limits={k:_number(profile[k+'_error_bound']) for k in ('velocity','force')}
    if any(value<0 for value in limits.values()):raise ValueError('nonnegative error bounds required')
    out=dict(status='UNKNOWN_CALIBRATION_EVIDENCE',classification=profile['classification'],hardware_validation=False,
             independent_review=False,operational_authorization=False,profile_sha256=sha(profile),samples_sha256=sha(samples))
    if not isinstance(samples,list) or len(samples)>256:raise ValueError('bounded sample list required')
    if not samples:return out
    ids=set();supported=True;witnesses=[]
    for row in samples:
        fields={'id','device_id','reference_id','frame','sample_ns','velocity','force','reference_velocity','reference_force'}
        if not isinstance(row,dict) or set(row)!=fields:raise ValueError('exact paired calibration sample required')
        if type(row['id']) is not str or not 0<len(row['id'])<=128 or row['id'] in ids:raise ValueError('unique calibration sample identities required')
        ids.add(row['id']);tick(row['sample_ns'])
        if any(row[k]!=profile[k] for k in ('device_id','reference_id','frame')):raise ValueError('calibration device/reference/frame mismatch')
        for key in ('velocity','force'):
            measured,reference=_bounds(row[key]),_bounds(row['reference_'+key])
            worst=max(abs(a-b) for a in (measured.lo,measured.hi) for b in (reference.lo,reference.hi))
            if worst>limits[key]:
                supported=False
                if measured.lo==measured.hi and reference.lo==reference.hi:witnesses.append(dict(id=row['id'],quantity=key,error=str(worst)))
    return dict(out,status='WITHIN_DECLARED_ERROR_BOUNDS_NOT_VALIDATION' if supported else 'ERROR_BOUND_NOT_ESTABLISHED',
                sample_count=len(samples),point_violation_witnesses=witnesses)


def select_response(temporal,*,deadline,restart,calibration,boot_id,mode):
    """Return an offline candidate only; UNKNOWN never becomes a zero command."""
    out=dict(status='NO_JUSTIFIED_RESPONSE',candidate=None,dispatch=False,operational_authorization=False,
             hardware_validation=False,mode=mode,reason=None)
    if mode!='DEVELOPMENT_SIMULATION':return dict(out,reason='HARDWARE_OPERATION_NOT_AUTHORIZED_OR_VALIDATED')
    if restart.get('boot_id')!=boot_id or restart.get('status')!='DEV_RESYNCHRONIZED_NO_OPERATIONAL_AUTHORITY':return dict(out,reason='RESTART_RESYNCHRONIZATION_REQUIRED')
    if deadline.get('boot_id')!=boot_id or deadline.get('status')!='COMPUTED_WITHIN_BUDGET_NOT_DISPATCHED' or deadline.get('result_sha256')!=sha(temporal):return dict(out,reason='DEADLINE_OR_RESULT_BINDING_FAILED')
    if calibration.get('classification')!='SYNTHETIC_ONLY' or calibration.get('status')!='WITHIN_DECLARED_ERROR_BOUNDS_NOT_VALIDATION':return dict(out,reason='DEVELOPMENT_CALIBRATION_CONTRACT_UNSUPPORTED')
    if any(x.get('operational_authorization') is not False for x in (temporal,deadline,restart,calibration)):
        return dict(out,reason='FOREIGN_AUTHORITY_CLAIM_REJECTED')
    a=temporal.get('assessment')
    if (temporal.get('status')!='READY_CONDITIONAL_INPUTS' or temporal.get('conclusion')!='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY'
            or temporal.get('reaction_prefix_containment') is not True or temporal.get('combined_finite_horizon_containment') is not True
            or not isinstance(a,dict) or a.get('terminal_sample_condition') is not True):
        return dict(out,reason='RECOVERY_NOT_ESTABLISHED')
    return dict(out,status='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY',candidate='DECLARED_MEASURED_P_RECOVERY',reason=None)
