"""DEVELOPMENT ONLY: caller must establish E[Z_t|past]<=tau_t.

Tau must be positive/predictable; fixed bet/cap are chosen before observations.
No calibration, missingness, restart, multiplicity, authentication, or certified
floating-point proof is supplied. No existing monitor/evaluator is changed.
"""
import math


def finite(x,name):
    if type(x) not in (float,int):raise ValueError(name+' must be finite, not bool')
    try:valid=math.isfinite(x)
    except OverflowError:valid=False
    if not valid:raise ValueError(name+' must be finite')
    return float(x)


def upper_only_score(z,tau,cap):
    z=finite(z,'z');tau=finite(tau,'tau');cap=finite(cap,'cap')
    if z<0 or tau<=0 or cap<0:raise ValueError('require z>=0, tau>0, cap>=0')
    if z==0:return -1.
    log_ratio=math.log(z)-math.log(tau)
    return cap if log_ratio>=math.log1p(cap) else math.expm1(log_ratio)


class DevelopmentEProcess:
    """Single process; no reset/replenishment API. Conditional null is unverified."""
    def __init__(self,*,bet,cap,alpha):
        self._bet=finite(bet,'bet');self._cap=finite(cap,'cap');self._alpha=finite(alpha,'alpha')
        if not 0<=self.bet<1 or self.cap<0 or not 0<self.alpha<1:raise ValueError('invalid configuration')
        self.log_threshold=-math.log(self.alpha);self.log_wealth=0.;self.sequence=0
    @property
    def bet(self):return self._bet
    @property
    def cap(self):return self._cap
    @property
    def alpha(self):return self._alpha
    def update(self,*,z,tau,sequence):
        if type(sequence) is not int or sequence!=self.sequence+1:raise ValueError('strict sequence required')
        score=upper_only_score(z,tau,self.cap)
        log_factor=math.log1p(self.bet*score);candidate=self.log_wealth+log_factor
        if not math.isfinite(candidate):raise ValueError('numeric evidence limit')
        self.log_wealth=candidate;self.sequence=sequence
        return {'sequence':sequence,'score':score,'log_factor':log_factor,'log_wealth':candidate,
                'threshold_crossed':candidate>=self.log_threshold}
