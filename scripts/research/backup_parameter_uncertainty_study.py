"""Exclusive synthetic parameter-family study. No native or hardware episodes."""
import argparse
from copy import deepcopy
from fractions import Fraction as Q
import hashlib
import json
import os
import re
from pathlib import Path
import platform
import subprocess

from aegis.development.uncertain_backup_certificate_1d import certificate
from aegis.development.durable_feedback_session import canonical, sha
from scripts.research import recovery_supervisor_study_1d as previous
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

ROOT = Path(__file__).resolve().parents[2]
STUDY = 'V9-M5 assumed parameter-family common-metric certificate development v1'
FILES = previous.FILES + ('src/aegis/development/uncertain_backup_certificate_1d.py',
    'scripts/research/backup_parameter_uncertainty_study.py',
    'tests/test_uncertain_backup_certificate_1d.py', 'tests/test_backup_parameter_uncertainty_study.py')


def hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}


def family(width):
    return {key: [str(Q(value)*(1-Q(width))), str(Q(value)*(1+Q(width)))]
            for key, value in (('mass', '1'), ('spring', '4'), ('damping', '3'))}


def plan():
    rows = [dict(id='symmetric_width_'+w, nominal=previous.backup_model(), parameter_bounds=family(w))
            for w in ('0', '.005', '.01', '.02', '.05', '.1', '.15', '.2', '.25', '.4')]
    for name in ('large_disturbance', 'insufficient_cap', 'narrow_region', 'nominal_outside_family',
                 'missing_parameter', 'nonpositive_mass', 'floating_bound', 'unstable_member',
                 'one_sided_family', 'exponent_bound'):
        n = previous.backup_model(); bounds = family('.1')
        if name == 'large_disturbance': n['disturbance'] = '.5'
        if name == 'insufficient_cap': n['force_cap'] = '1'
        if name == 'narrow_region': n['safe_position'] = ['-.05', '.05']
        if name == 'nominal_outside_family': bounds['mass'] = ['2', '3']
        if name == 'missing_parameter': bounds.pop('damping')
        if name == 'nonpositive_mass': bounds['mass'][0] = '0'
        if name == 'floating_bound': bounds['mass'][0] = .9
        if name == 'unstable_member': bounds['mass'] = ['.01', '1']
        if name == 'one_sided_family': bounds = dict(mass=['1', '1.1'], spring=['4', '4.4'], damping=['3', '3.3'])
        if name == 'exponent_bound': bounds['mass'][0] = '9e-1'
        rows.append(dict(id=name, nominal=n, parameter_bounds=bounds))
    return rows


def run(directory):
    directory = Path(directory); directory.mkdir(exist_ok=False)
    pins = hashes()
    metadata = dict(source_sha256=pins, python=platform.python_version(),
                    parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    gate_b='GATE_B_NOT_AUTHORIZED', physics_steps=0)
    assignments = [dict(a, metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl', study=STUDY, assignments=assignments) as log:
        for a in assignments:
            log.start(a['id'])
            try:
                result = certificate(a['nominal'], a['parameter_bounds']); raw = canonical(result)
                with (directory/(a['id']+'.json')).open('xb') as f:
                    f.write(raw+b'\n'); f.flush(); os.fsync(f.fileno())
                fd = os.open(directory, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
                if hashes() != pins: raise ValueError('study source changed')
                log.complete(a['id'], status='COMPLETED', details=dict(result_sha256=sha(result), sources_after=pins))
            except (LedgerError, LedgerWriteError): raise
            except Exception as exc:
                log.complete(a['id'], status='ERROR', details=dict(error_type=type(exc).__name__, error=str(exc)))
                raise
        log.finalize()
    return audit(directory)


def audit(directory):
    directory = Path(directory); ledger = inspect(directory/'assignments.jsonl'); header = ledger['records'][0]
    assignments = header['assignments']; meta = assignments[0]['metadata']
    if (set(meta) != {'source_sha256','python','parent_commit','gate_b','physics_steps'}
            or meta['gate_b'] != 'GATE_B_NOT_AUTHORIZED'
            or type(meta['physics_steps']) is not int or meta['physics_steps'] != 0
            or not isinstance(meta['parent_commit'],str) or not re.fullmatch('[0-9a-f]{40}',meta['parent_commit'])):
        raise ValueError('development provenance/physics contract mismatch')
    if header['study'] != STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments] != plan():
        raise ValueError('plan mismatch')
    if any(a['metadata']!=meta for a in assignments) or meta['source_sha256']!=hashes() or meta['python']!=platform.python_version():
        raise ValueError('source/runtime mismatch')
    completed = {}
    for row in ledger['records']:
        if row['kind']=='TERMINAL' and row['status']=='COMPLETED':
            a = next(a for a in assignments if a['id']==row['id'])
            rebuilt = certificate(a['nominal'], a['parameter_bounds'])
            if (directory/(a['id']+'.json')).read_bytes() != canonical(rebuilt)+b'\n':
                raise ValueError('saved certificate mismatch')
            if row['details'] != dict(result_sha256=sha(rebuilt), sources_after=meta['source_sha256']):
                raise ValueError('terminal/source evidence mismatch')
            completed[a['id']] = rebuilt
    categories = {}
    for result in completed.values(): categories[result['status']] = categories.get(result['status'],0)+1
    return dict(study=STUDY, metadata=meta, counts=ledger['counts'], ledger_state=ledger['state'],
                categories=categories, assignments=[dict(id=a['id'], state=ledger['assignments'][a['id']], result=completed.get(a['id'])) for a in assignments],
                physics_steps=0, independent_hardware_validation=False, operational_authorization=False, gate_b='GATE_B_NOT_AUTHORIZED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    result=run(a.directory) if a.mode=='run' else audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(result)+b'\n')
    print(json.dumps(dict(counts=result['counts'],categories=result['categories'],physics_steps=0,gate_b=result['gate_b'])))


if __name__=='__main__': main()
