"""Exact affine two-clock enclosure from asserted causal timestamp exchanges.

local = rate * remote + offset. Nonnegative, possibly asymmetric transport
delays yield half-plane constraints; no RTT/2 assumption, source authentication,
variable drift or clock-reset inference is provided.
"""
from fractions import Fraction as Q
from .recovery_feedback_state_1d import _number
from .durable_feedback_session import canonical,sha


def tick(value):
    if type(value) is not int or not 0<=value<2**63:raise ValueError('nonnegative int64 timestamp required')
    return value


def _clip(poly,a,b,c):
    result=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        fp=a*p[0]+b*p[1]-c;fq=a*q[0]+b*q[1]-c
        if fp<=0:result.append(p)
        if (fp<0 and fq>0) or (fp>0 and fq<0):
            ratio=fp/(fp-fq);result.append((p[0]+ratio*(q[0]-p[0]),p[1]+ratio*(q[1]-p[1])))
    return list(dict.fromkeys(result))


class IndependentClockMap:
    def __init__(self,*,local_epoch,remote_epoch,rate_bounds,max_extrapolation):
        if any(type(x) is not str or not 0<len(x)<=128 for x in (local_epoch,remote_epoch)):raise ValueError('explicit clock epochs required')
        if not isinstance(rate_bounds,list) or len(rate_bounds)!=2:raise ValueError('rate interval required')
        self.lo,self.hi=map(_number,rate_bounds)
        if not 0<self.lo<=self.hi:raise ValueError('positive ordered clock rates required')
        self.local_epoch,self.remote_epoch=local_epoch,remote_epoch
        self.extrapolation=tick(max_extrapolation);self._seen={};self._exchanges=[];self._poly=None;self._fault=False

    def add(self,exchange):
        if self._fault:return dict(status='CONTRADICTORY_CLOCK_EVIDENCE',operational_authorization=False)
        fields={'id','local_epoch','remote_epoch','local_send','remote_receive','remote_send','local_receive'}
        if not isinstance(exchange,dict) or set(exchange)!=fields:raise ValueError('exact exchange fields required')
        if exchange['local_epoch']!=self.local_epoch or exchange['remote_epoch']!=self.remote_epoch:return dict(status='CLOCK_EPOCH_REJECTED',operational_authorization=False)
        name=exchange['id']
        if type(name) is not str or not 0<len(name)<=128:raise ValueError('exchange identity required')
        values=[tick(exchange[k]) for k in ('local_send','remote_receive','remote_send','local_receive')]
        l1,r2,r3,l4=values
        if l4<l1 or r3<r2:raise ValueError('negative local/remote exchange elapsed time')
        digest=sha(exchange)
        if name in self._seen:
            if digest==self._seen[name]:return dict(status='REPLAY_IGNORED',operational_authorization=False)
            self._fault=True;return dict(status='CONTRADICTORY_CLOCK_EVIDENCE',operational_authorization=False)
        if len(self._seen)>=64:raise ValueError('clock evidence resource limit; no silent eviction')
        if self._poly is None:
            low=min(Q(l1)-a*r2 for a in (self.lo,self.hi));high=max(Q(l4)-a*r3 for a in (self.lo,self.hi))
            poly=[(self.lo,low),(self.hi,low),(self.hi,high),(self.lo,high)] if low<=high else []
        else:poly=list(self._poly)
        poly=_clip(poly,-Q(r2),-Q(1),-Q(l1))  # local_send <= rate*remote_receive + offset
        poly=_clip(poly,Q(r3),Q(1),Q(l4))      # rate*remote_send + offset <= local_receive
        if not poly:self._fault=True;return dict(status='CONTRADICTORY_CLOCK_EVIDENCE',operational_authorization=False)
        self._poly=poly;self._seen[name]=digest;self._exchanges.append((r2,r3))
        return dict(status='CONDITIONAL_CLOCK_MAP_UPDATED',vertices=[[str(a),str(b)] for a,b in poly],operational_authorization=False)

    def map_event(self,remote_time,*,local_epoch,remote_epoch):
        tick(remote_time)
        out=dict(status='UNKNOWN_CLOCK_MAPPING',local_interval=None,operational_authorization=False,
                 source_authentication='NOT_ESTABLISHED',local_epoch=self.local_epoch,remote_epoch=self.remote_epoch)
        if self._fault:return dict(out,status='CONTRADICTORY_CLOCK_EVIDENCE')
        if local_epoch!=self.local_epoch or remote_epoch!=self.remote_epoch:return dict(out,status='CLOCK_EPOCH_REJECTED')
        if self._poly is None:return out
        low=min(x[0] for x in self._exchanges);high=max(x[1] for x in self._exchanges)
        if not max(0,low-self.extrapolation)<=remote_time<=high+self.extrapolation:return dict(out,status='EXTRAPOLATION_LIMIT')
        values=[a*remote_time+b for a,b in self._poly]
        return dict(out,status='CONDITIONAL_INTERVAL_MAPPING',local_interval=[str(min(values)),str(max(values))],
                    exact_integer_tick=(min(values)==max(values) and min(values).denominator==1))
