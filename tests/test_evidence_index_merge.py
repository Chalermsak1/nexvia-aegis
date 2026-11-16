"""PR #9 integrity regression: historical records and original bytes survive merge."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'docs/research/NEXVIA_AEGIS_DEVELOPMENT_EVIDENCE_INDEX_2026-10-31.json'


def test_both_historical_snapshots_and_all_record_fields_are_preserved():
 index=json.loads(INDEX.read_text());merged={r['path']:r for r in index['ledgers']};expected=set()
 assert index['total_ledgers']==len(merged)==21
 assert {s['id']:s['ledger_count'] for s in index['snapshots']}=={'research_hardening':19,'main':21}
 for snapshot in index['snapshots']:
  p=ROOT/snapshot['path'];raw=p.read_bytes()
  assert hashlib.sha256(raw).hexdigest()==snapshot['sha256']
  original=json.loads(raw)
  assert snapshot['original_metadata']=={k:v for k,v in original.items() if k!='ledgers'}
  assert len(original['ledgers'])==snapshot['ledger_count']
  for old in original['ledgers']:
   expected.add(old['path']);new=merged[old['path']]
   assert snapshot['id'] in new['provenance_snapshots']
   assert all(new[k]==v for k,v in old.items())
 assert expected==set(merged)
 assert index['governance']['gate_b']=='GATE_B_NOT_AUTHORIZED'


def test_inventory_references_only_matching_development_ledger_bytes():
 index=json.loads(INDEX.read_text())
 for item in index['ledgers']:
  path=Path(item['path'])
  assert not path.is_absolute() and '..' not in path.parts
  assert path.parts[:3]==('results','research_development','dev') and path.suffix=='.jsonl'
  with (ROOT/path).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
  assert actual==item['sha256']
  assert (ROOT/path).stat().st_size==item['bytes']
  if 'counts' in item and 'assignment_counts' in item:assert item['counts']==item['assignment_counts']
  if 'state' in item and 'visible_state' in item:assert item['state']==item['visible_state']
