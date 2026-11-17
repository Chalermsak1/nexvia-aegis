import json,tempfile
from pathlib import Path
import pytest
from aegis.development.restart_process_experiment import Records,read_records,Endpoint


def test_pending_bytes_are_preserved_without_promoting_uncommitted_evidence(tmp_path):
    r=Records(tmp_path/'role',dict(role='controller'));r.append('COMMAND_INTENT',command=dict(command_id='A:1'))
    (tmp_path/'role'/'pending_00000002.json').write_bytes(b'partial')
    result=read_records(tmp_path/'role')
    assert len(result['records'])==2 and result['pending'][0]['bytes']==7
    assert (tmp_path/'role'/'pending_00000002.json').read_bytes()==b'partial'


def test_committed_record_corruption_or_missing_index_is_rejected(tmp_path):
    r=Records(tmp_path/'role',dict(role='controller'));r.append('ACK',command_id='A:1')
    p=tmp_path/'role'/'00000001.json';p.write_text('{}')
    with pytest.raises((ValueError,KeyError)):read_records(tmp_path/'role')


def test_local_datagrams_do_not_depend_on_recipient_process_progress():
    with tempfile.TemporaryDirectory(prefix='nxproto-',dir='/private/tmp') as d:
        p=Path(d);a=Endpoint(p/'a');b=Endpoint(p/'b')
        try:
            assert a.send(p/'b',dict(kind='COMMAND',command_id='A:1'))
            assert b.drain()==[dict(kind='COMMAND',command_id='A:1')]
            assert not a.send(p/'missing',dict(kind='COMMAND'))
            with pytest.raises(ValueError):a.send(p/'b',dict(body='x'*1900))
        finally:a.close();b.close()


def test_pending_alias_of_committed_record_is_identified_without_repair(tmp_path):
    import os
    r=Records(tmp_path/'role',dict(role='controller'));r.append('ACK')
    os.link(tmp_path/'role'/'00000001.json',tmp_path/'role'/'pending_00000001.json')
    assert read_records(tmp_path/'role')['pending'][0]['committed_alias'] is True
