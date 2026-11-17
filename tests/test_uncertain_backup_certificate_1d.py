from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
import random
import pytest
from aegis.development.uncertain_backup_certificate_1d import certificate
from aegis.development.passive_backup_supervisor_1d import model, certificate as point_certificate
from scripts.research.backup_parameter_uncertainty_study import family
from scripts.research.recovery_supervisor_study_1d import backup_model


def test_singleton_matches_existing_point_model_without_rewriting_it():
    n=backup_model();r=certificate(n,family('0'));p=point_certificate(n)
    assert r['conditional_sampled_invariance']
    for field in ('P','P_inverse','contraction_upper','minimum_disturbance_level','backup_force_bound_squared','position_bound_squared'):
        assert r[field]==p[field]
    assert Q(r['uniform_decay_lower'])==1


@pytest.mark.parametrize('width',['.005','.01','.02','.05','.1'])
def test_supported_families_have_exact_uniform_decay_and_no_authority(width):
    r=certificate(backup_model(),family(width))
    assert r['status']=='CONDITIONAL_SAMPLED_FAMILY_INVARIANT'
    assert Q(r['uniform_decay_lower'])>0
    assert all(r['checks'].values())
    assert not any(r[k] for k in ('dispatch','operational_authorization','hardware_validation','handoff_or_supervisor_integration'))


def test_interval_residual_encloses_direct_matrices_at_interior_and_boundary_parameters():
    n=backup_model();r=certificate(n,family('.1'));P=[[Q(x) for x in row] for row in r['P']];eta=Q(r['uniform_decay_lower'])
    def linear(i,j,A):return P[i][j]-sum(A[u][i]*P[u][v]*A[v][j] for u,v in product(range(2),repeat=2))
    for m,k,c in product((Q('.9'),Q('1'),Q('1.1')),(Q('3.6'),Q('4'),Q('4.4')),(Q('2.7'),Q('3'),Q('3.3'))):
        h=Q('.02');A=((1-h*h*k/m,h*(1-h*c/m)),(-h*k/m,1-h*c/m))
        S=[[linear(i,j,A) for j in range(2)] for i in range(2)]
        for i,j in product(range(2),repeat=2):
            lo,hi=map(Q,r['residual_enclosure'][i][j]);assert lo<=S[i][j]<=hi
        # Independent exact 2x2 PSD criterion for S-eta*I.
        assert S[0][0]>=eta and S[1][1]>=eta
        assert (S[0][0]-eta)*(S[1][1]-eta)-S[0][1]**2>=0


def test_arbitrarily_switching_parameters_and_disturbance_follow_scalar_physics_inside_set():
    n=backup_model();r=certificate(n,family('.1'));P=[[Q(x) for x in row] for row in r['P']];rng=random.Random(17110904)
    def energy(p,v):return P[0][0]*p*p+2*P[0][1]*p*v+P[1][1]*v*v
    for _ in range(10):
        p=Q(rng.randint(-10,10),100);v=Q(rng.randint(-20,20),100)
        assert energy(p,v)<=5
        for _ in range(60):
            m=rng.choice([Q('.9'),Q('1'),Q('1.1')]);k=rng.choice([Q('3.6'),Q('4'),Q('4.4')]);c=rng.choice([Q('2.7'),Q('3'),Q('3.3')]);w=rng.choice([Q('-.01'),Q(0),Q('.01')])
            force=-k*p-c*v;assert abs(force)<=4
            v+=Q('.02')*(force+w)/m;p+=Q('.02')*v
            assert energy(p,v)<=5 and Q('-.5')<=p<=Q('.32')


def test_input_and_force_bounds_enclose_common_mass_correlation_and_stiffness_damping_corners():
    n=backup_model();r=certificate(n,family('.1'));s=model(n);P=s['P'];inverse=s['inverse'];beta=Q(r['disturbance_input_norm_squared_upper']);force2=Q(r['backup_force_bound_squared'])
    for m,k,c in product((Q('.9'),Q('1'),Q('1.1')),(Q('3.6'),Q('4'),Q('4.4')),(Q('2.7'),Q('3'),Q('3.3'))):
        B=(Q('.0004')/m,Q('.02')/m)
        assert sum(B[i]*P[i][j]*B[j] for i,j in product(range(2),repeat=2))<=beta
        F=(k,c);assert 5*sum(F[i]*inverse[i][j]*F[j] for i,j in product(range(2),repeat=2))<=force2


@pytest.mark.parametrize('field,value,failed',[('force_cap','1','force_cap_sufficient'),('disturbance','.5','disturbance_level_sufficient'),('safe_position',['-.05','.05'],'safe_projection_sufficient')])
def test_each_physical_constraint_is_required(field,value,failed):
    n=backup_model();n[field]=value;r=certificate(n,family('.1'))
    assert r['status']=='FAMILY_INVARIANCE_NOT_ESTABLISHED' and not r['checks'][failed]


def test_wide_family_is_inconclusive_even_when_selected_point_models_have_certificates():
    r=certificate(backup_model(),family('.2'))
    assert r['status']=='FAMILY_INVARIANCE_NOT_ESTABLISHED'
    assert r['contraction_upper'] is None and r['minimum_disturbance_level'] is None
    for mass in ('.8','1','1.2'):
        n=backup_model();n['mass']=mass;assert point_certificate(n)['status']=='CONDITIONAL_SAMPLED_INVARIANT_SET'
    # Point-specific certificates are not a common certificate for switching.


def test_family_can_contain_an_unstable_member_despite_nominal_point_pass():
    bounds=family('.1');bounds['mass']=['.01','1'];r=certificate(backup_model(),bounds)
    assert not r['conditional_sampled_invariance']
    n=backup_model();s=model(n);p=Q(0);v=Q('.5')
    assert s['P'][1][1]*v*v<=5
    v+=Q('.02')/Q('.01')*(-4*p-3*v);p+=Q('.02')*v
    W=s['P'][0][0]*p*p+2*s['P'][0][1]*p*v+s['P'][1][1]*v*v
    assert W>5  # Independent witness, not inferred from the sufficient-test failure.


@pytest.mark.parametrize('bounds',[None,{},dict(mass=['0','1'],spring=['4','4'],damping=['3','3']),dict(mass=['1.1','.9'],spring=['4','4'],damping=['3','3']),dict(mass=[.9,1.1],spring=['4','4'],damping=['3','3']),dict(mass=['9e-1','1.1'],spring=['4','4'],damping=['3','3']),dict(mass=['2','3'],spring=['4','4'],damping=['3','3']),dict(mass=['.9','1.1'],spring=['4','4'],damping=[False,'3'])])
def test_invalid_or_contradictory_family_is_unknown_not_nominal_fallback(bounds):
    r=certificate(backup_model(),bounds)
    assert r['status']=='UNKNOWN_PARAMETER_INPUT' and not r['conditional_sampled_invariance']


def test_nonunit_scales_and_nonzero_anchor_keep_normalized_contract():
    n=backup_model();n.update(position_scale='2',velocity_scale='3',anchor='1',safe_position=['.5','1.5'],level='1')
    r=certificate(n,family('.01'))
    assert r['status']=='CONDITIONAL_SAMPLED_FAMILY_INVARIANT'
    assert r['P']!=certificate(backup_model(),family('.01'))['P']


def test_input_records_are_not_mutated():
    n=backup_model();b=family('.1');saved=deepcopy((n,b));certificate(n,b)
    assert (n,b)==saved
