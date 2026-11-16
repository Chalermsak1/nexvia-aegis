import math
from fractions import Fraction as F
import pytest
from development_eprocess import DevelopmentEProcess,upper_only_score


def test_exact_lower_clipping_counterexample():
    probs=[F(3,4),F(1,4)]
    assert sum(p*(1+F(1,4)*s) for p,s in zip(probs,[F(-9,10),F(3)]))==F(163,160)>1
    assert sum(p*(1+F(1,4)*s) for p,s in zip(probs,[F(-1),F(3)]))==1
    assert upper_only_score(0,.35,3)==-1
    assert upper_only_score(1.4,.35,3)==pytest.approx(3)


def test_exact_floor_counterexample_and_no_replenishment():
    floor=F(1,100)
    assert sum(max(floor,floor*(1+F(1,4)*s)) for s in [F(-1,2),F(1,2)])/2==F(17,1600)>floor
    m=DevelopmentEProcess(bet=.25,cap=3,alpha=.05)
    for i in range(1,101):m.update(z=0,tau=1,sequence=i)
    assert m.log_wealth==pytest.approx(100*math.log(.75))
    assert m.log_wealth<math.log(.01)


@pytest.mark.parametrize('zs,ps',[([F(0),F(4)],[F(3,4),F(1,4)]),([F(0),F(1,2)],[F(1,2)]*2),([F(1,2),F(3,2)],[F(1,2)]*2)])
def test_discrete_null_expected_factor_at_most_one(zs,ps):
    assert sum(z*p for z,p in zip(zs,ps))<=1
    for b in [F(0),F(1,4),F(9,10)]:
        assert sum(p*(1+b*min(z-1,F(3))) for z,p in zip(zs,ps))<=1
        assert sum(float(p)*(1+float(b)*upper_only_score(float(z),1,3)) for z,p in zip(zs,ps))<=1+1e-14


def test_log_product_and_threshold():
    m=DevelopmentEProcess(bet=.25,cap=3,alpha=.05);product=1
    for i,z in enumerate([0,.5,1,2]+[4]*8,1):
        product*=1+.25*min(z-1,3);r=m.update(z=z,tau=1,sequence=i)
        assert r['log_wealth']==pytest.approx(math.log(product))
        assert r['threshold_crossed']==(product>=20)


def test_huge_ratio_and_zero_bet():
    assert upper_only_score(1e308,5e-324,3)==3
    assert DevelopmentEProcess(bet=0,cap=3,alpha=.05).update(z=1e308,tau=5e-324,sequence=1)['log_wealth']==0


@pytest.mark.parametrize('field,value',[('z',True),('z',-1),('z',float('nan')),('z',float('inf')),('tau',0),('tau',-1),('tau',None),('tau',float('nan'))])
def test_invalid_observation_preserves_state(field,value):
    m=DevelopmentEProcess(bet=.25,cap=3,alpha=.05);kw=dict(z=1,tau=1,sequence=1);kw[field]=value
    with pytest.raises(ValueError):m.update(**kw)
    assert m.log_wealth==0 and m.sequence==0


@pytest.mark.parametrize('field,value',[('bet',True),('bet',1),('bet',-1),('cap',-1),('alpha',0),('alpha',1)])
def test_invalid_configuration(field,value):
    kw=dict(bet=.25,cap=3,alpha=.05);kw[field]=value
    with pytest.raises(ValueError):DevelopmentEProcess(**kw)


@pytest.mark.parametrize('sequence',[True,0,2,1.5])
def test_order_rejection(sequence):
    m=DevelopmentEProcess(bet=.25,cap=3,alpha=.05)
    with pytest.raises(ValueError):m.update(z=1,tau=1,sequence=sequence)
    assert m.sequence==0


def test_public_configuration_is_read_only():
    m=DevelopmentEProcess(bet=.25,cap=3,alpha=.05)
    for name,value in [('bet',.5),('cap',4),('alpha',.1)]:
        with pytest.raises(AttributeError):setattr(m,name,value)
