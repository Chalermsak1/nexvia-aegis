"""Offline, exclusive evidence export for DEVELOPMENT research only.

No artifact execution, archive extraction, network requests, Git mutations,
authorization, or cryptographic authenticity claims. Markdown validation supports
the documented conservative subset and rejects unsupported link constructs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
from urllib.parse import unquote, urlsplit


class PackageError(ValueError):
    pass


ALLOWED = ('src/', 'scripts/research/', 'tests/', 'docs/research/', 'results/research_development/')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
SCHEMA = 'nexvia-development-evidence-package/1'


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:raise PackageError('duplicate JSON key: '+key)
        out[key] = value
    return out


def load_json(path):
    if path.stat().st_size > 8*1024*1024:raise PackageError('JSON resource limit')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(PackageError('nonfinite JSON')))


def relative(name):
    if not isinstance(name,str) or not name or '\\' in name or any(ord(c)<32 for c in name):
        raise PackageError('invalid repository-relative path')
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ('.','..') or part.startswith('.') for part in name.split('/')):
        raise PackageError('absolute, hidden or traversing input path rejected')
    if path.as_posix()!=name or not name.startswith(ALLOWED):
        raise PackageError('input outside development export scope: '+name)
    if any(re.search(r'holdout|reserved|seeds?|private.?key|production.?ticket',part,re.I) for part in path.parts):
        raise PackageError('protected input name rejected: '+name)
    return name


def safe_file(root, name):
    name = relative(name)
    if root.is_symlink():raise PackageError('symlinked input root rejected')
    path = root
    for part in PurePosixPath(name).parts:
        path = path/part
        if path.is_symlink():raise PackageError('symlinked input rejected: '+name)
    if not path.is_file():raise PackageError('missing regular input: '+name)
    return path


def fingerprint(path):
    fd = os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):raise PackageError('regular file required')
        if info.st_size>256*1024*1024:raise PackageError('file resource limit exceeded')
        h=hashlib.sha256();size=0
        with os.fdopen(fd,'rb',closefd=False) as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
        if size!=info.st_size:raise PackageError('input changed while hashing')
        return dict(sha256=h.hexdigest(),size_bytes=size)
    finally:os.close(fd)


def git_state(root):
    def git(*args):
        return subprocess.run(['git','--no-optional-locks','-c','core.fsmonitor=false','-C',str(root),*args],
                              check=True,capture_output=True,text=True).stdout.strip()
    top=Path(git('rev-parse','--show-toplevel')).resolve()
    if top!=root:raise PackageError('repository root must be explicit Git top level')
    if git('diff','--no-ext-diff','--name-only','--'):raise PackageError('tracked worktree changes present; preserved, export refused')
    if git('diff','--cached','--no-ext-diff','--name-only','--'):raise PackageError('staged changes present; preserved, export refused')
    branch=git('rev-parse','--abbrev-ref','HEAD')
    return dict(head=git('rev-parse','HEAD'),branch=branch,tracked_worktree_clean=True,index_clean=True)


def _without_inline_code(text):
    return re.sub(r'(`+)(.*?)\1',lambda m:' '*len(m.group()),text)


def _slug(text):
    return re.sub(r'[^\w\- ]','',text.replace('`','').lower()).replace(' ','-')


def markdown(root, name):
    """Strict ATX/fence/table/inline-reference-local-link subset; no HTML."""
    path=safe_file(root,name)
    if path.stat().st_size>2*1024*1024:raise PackageError('Markdown resource limit')
    raw=path.read_bytes();text=raw.decode('utf-8')
    if not raw.endswith(b'\n') or b'\r' in raw or b'\x00' in raw:raise PackageError('Markdown newline/encoding structure: '+name)
    lines=text.splitlines();visible=[];headings=[];anchors=set();duplicates={};fence=None;level=0
    for index,line in enumerate(lines):
        if line!=line.rstrip() or '\t' in line:raise PackageError(f'Markdown whitespace at {name}:{index+1}')
        token=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line)
        if fence:
            if token and token[1][0]==fence[0] and len(token[1])>=fence[1] and not token[2].strip():fence=None
            visible.append('');continue
        if token:
            fence=(token[1][0],len(token[1]));visible.append('');continue
        visible.append(_without_inline_code(line))
        heading=re.match(r'^(#{1,6}) (.+?)\s*#*$',line)
        if heading:
            new=len(heading[1])
            if new>level+1:raise PackageError('skipped Markdown heading level: '+name)
            if index and lines[index-1].strip():raise PackageError('blank line required before heading: '+name)
            if index+1<len(lines) and lines[index+1].strip():raise PackageError('blank line required after heading: '+name)
            level=new;slug=_slug(heading[2]);n=duplicates.get(slug,0);duplicates[slug]=n+1
            anchors.add(slug if not n else slug+'-'+str(n));headings.append(dict(level=new,text=heading[2]))
    if fence:raise PackageError('unclosed Markdown fence: '+name)
    if not headings or headings[0]['level']!=1 or sum(h['level']==1 for h in headings)!=1:
        raise PackageError('exactly one initial H1 required: '+name)
    if next((line for line in lines if line.strip()),'')!='# '+headings[0]['text']:
        raise PackageError('document must start with its H1: '+name)
    table_count=0;index=0
    while index<len(visible):
        if not visible[index].lstrip().startswith('|'):index+=1;continue
        rows=[]
        while index<len(visible) and visible[index].lstrip().startswith('|'):
            line=visible[index].strip()
            if not line.endswith('|'):raise PackageError('table row lacks closing pipe: '+name)
            rows.append([cell.strip() for cell in re.split(r'(?<!\\)\|',line[1:-1])]);index+=1
        if len(rows)<2 or any(not re.fullmatch(r':?-{3,}:?',c) for c in rows[1]):
            raise PackageError('table separator required: '+name)
        if any(len(row)!=len(rows[0]) for row in rows):raise PackageError('table column mismatch: '+name)
        table_count+=1
    body='\n'.join(visible)
    definitions={}
    definition=re.compile(r'^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)(?:\s+"[^"\n]*")?\s*$',re.M)
    for match in definition.finditer(body):
        label=match[1].strip().casefold()
        if label in definitions:raise PackageError('duplicate link definition: '+name)
        definitions[label]=match[2]
    links=[]
    def destination(value):
        value=value.strip()
        if value.startswith('<') and value.endswith('>'):return value[1:-1]
        match=re.fullmatch(r'(\S+?)(?:\s+"[^"\n]*")?',value)
        if not match:raise PackageError('unsupported link destination: '+name)
        return match[1]
    inline=re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^()\n]*)\)')
    spans=[]
    for match in inline.finditer(body):
        if '<' in match.group().split('](',1)[0]:raise PackageError('HTML in link label unsupported: '+name)
        links.append(destination(match[1]));spans.append(match.span())
    html_probe=inline.sub('',definition.sub('',body))
    html_probe=re.sub(r'<https?://[^>]+>','',html_probe)
    if re.search(r'<\s*/?\s*[A-Za-z][^>]*>',html_probe):
        raise PackageError('HTML/unsupported angle links must be reviewed explicitly: '+name)
    scrub=list(body)
    for lo,hi in spans:scrub[lo:hi]=' '*(hi-lo)
    remaining=''.join(scrub)
    if '](' in remaining:raise PackageError('unsupported/unclosed inline link: '+name)
    references=re.compile(r'!?\[([^\]\n]+)\]\[([^\]\n]*)\]')
    for match in references.finditer(remaining):
        label=(match[2] or match[1]).strip().casefold()
        if label not in definitions:raise PackageError('undefined reference link: '+name)
        links.append(destination(definitions[label]))
    for match in re.finditer(r'<(https?://[^>]+)>',remaining):links.append(match[1])
    # Check shortcut reference links and unused definitions too; do not silently
    # skip a broken target merely because a renderer would not show it yet.
    for value in definitions.values():links.append(destination(value))
    for match in re.finditer(r'\[([^\]\n]+)\]',remaining):
        label=match[1].strip().casefold()
        if label in definitions:links.append(destination(definitions[label]))
    for match in re.finditer(r'https?://[^\s<>]+',remaining):links.append(match[0])
    return dict(headings=headings,anchors=sorted(anchors),tables=table_count,links=sorted(set(links)),fenced_blocks_valid=True)


def report_graph(root,reports):
    queue=list(reports);documents={};targets=set()
    while queue:
        name=relative(queue.pop(0))
        if name in documents:continue
        if len(documents)>=64:raise PackageError('report graph resource limit')
        document=markdown(root,name);documents[name]=document;resolved=[]
        for href in document.pop('links'):
            parsed=urlsplit(href)
            if parsed.scheme or parsed.netloc:raise PackageError('external/URI link not verified by offline exporter: '+href)
            if parsed.query:raise PackageError('query-bearing local link unsupported: '+href)
            raw=unquote(parsed.path)
            if raw.startswith('/') or '\\' in raw:raise PackageError('absolute local report link rejected')
            target=relative(posixpath.normpath(posixpath.join(posixpath.dirname(name),raw)) if raw else name)
            safe_file(root,target);targets.add(target)
            anchor=unquote(parsed.fragment)
            if anchor:
                if not target.endswith('.md'):raise PackageError('non-Markdown fragment cannot be verified')
                if anchor not in markdown(root,target)['anchors']:raise PackageError('broken report fragment: '+href)
            resolved.append(dict(href=href,target=target,fragment=anchor or None))
            if target.endswith('.md'):queue.append(target)
        document['links']=resolved
    return documents,targets


def _expect(digest):
    if not isinstance(digest,str) or not DIGEST.fullmatch(digest):raise PackageError('SHA-256 must be 64 lowercase hex characters')
    return digest


def inventory(root,receipts,prior_maps,reports,extras):
    expected={};roles={};sizes={};historical={};json_snapshots={}
    def read_record(name):
        path=safe_file(root,name);before=fingerprint(path);value=load_json(path)
        if fingerprint(path)!=before:raise PackageError('record changed while parsing: '+name)
        json_snapshots[name]=before
        return value
    def pin(name,digest,role,size=None,include=True):
        name=relative(name);digest=_expect(digest)
        if name in expected and expected[name]!=digest:raise PackageError('conflicting recorded hashes: '+name)
        expected[name]=digest
        if size is not None:
            if type(size) is not int or size<0:raise PackageError('invalid recorded artifact size')
            if name in sizes and sizes[name]!=size:raise PackageError('conflicting recorded artifact sizes')
            sizes[name]=size
        if include:roles.setdefault(name,set()).add(role)
    def include(name,role):roles.setdefault(relative(name),set()).add(role)
    for name in receipts:
        name=relative(name);value=read_record(name);include(name,'receipt')
        if not isinstance(value,dict) or not isinstance(value.get('source_sha256'),dict) or not isinstance(value.get('artifacts'),dict):
            raise PackageError('receipt source_sha256/artifacts maps required')
        for path,digest in value['source_sha256'].items():pin(path,digest,'source')
        for path,info in value['artifacts'].items():
            if not isinstance(info,dict) or 'sha256' not in info:raise PackageError('artifact hash entry required')
            pin(path,info['sha256'],'artifact',info.get('size_bytes'))
    for name in prior_maps:
        name=relative(name);value=read_record(name);include(name,'prior-map')
        if not isinstance(value,dict):raise PackageError('prior hash map object required')
        for path,digest in value.items():
            pin(path,digest,'historical',include=False);historical[path]=digest
    documents,links=report_graph(root,reports)
    for name in set(documents)|links:include(name,'report' if name.endswith('.md') else 'linked-target')
    for name in extras:include(name,'extra')
    observed={}
    for name in sorted(set(roles)|set(expected)):
        info=fingerprint(safe_file(root,name))
        if name in json_snapshots and info!=json_snapshots[name]:raise PackageError('parsed record changed before snapshot: '+name)
        if name in expected and info['sha256']!=expected[name]:raise PackageError('recorded SHA-256 mismatch: '+name)
        if name in sizes and info['size_bytes']!=sizes[name]:raise PackageError('recorded size mismatch: '+name)
        observed[name]=info
    selected={name:dict(observed[name],roles=sorted(role),recorded_sha256=expected.get(name)) for name,role in sorted(roles.items())}
    if len({name.casefold() for name in selected})!=len(selected):raise PackageError('case-insensitive package path collision')
    return selected,observed,historical,documents


def _write(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())


def _copy_file(source,dest,expected):
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(source,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0));h=hashlib.sha256();size=0
    try:
        with os.fdopen(fd,'rb',closefd=False) as src,dest.open('xb') as output:
            for chunk in iter(lambda:src.read(1024*1024),b''):output.write(chunk);h.update(chunk);size+=len(chunk)
            output.flush();os.fsync(output.fileno())
    finally:os.close(fd)
    if h.hexdigest()!=expected['sha256'] or size!=expected['size_bytes']:raise PackageError('input changed during copying')


def _sums(files):
    return ''.join(digest+'  '+name+'\n' for name,digest in sorted(files.items())).encode()


def export_package(root,destination,*,receipts,prior_maps,reports,extras=()):
    root=Path(root).resolve(strict=True);destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError(destination)
    destination=destination.parent.resolve(strict=True)/destination.name
    if destination==root or destination.name in ('.','..'):raise PackageError('invalid output directory')
    if destination.is_relative_to(root) and not destination.relative_to(root).as_posix().startswith('results/research_development/'):
        raise PackageError('in-repository output must be a new development-results directory')
    before=git_state(root)
    files,observed,historical,documents=inventory(root,receipts,prior_maps,reports,extras)
    destination.mkdir(mode=0o700,exist_ok=False)
    _write(destination/'STARTED.json',canonical(dict(schema=SCHEMA,git=before,status='STARTED_NOT_COMPLETE',gate_b='GATE_B_NOT_AUTHORIZED')))
    for name,info in files.items():_copy_file(safe_file(root,name),destination/'files'/name,info)
    for name,info in observed.items():
        if fingerprint(safe_file(root,name))!=info:raise PackageError('original changed during export: '+name)
    after=git_state(root)
    if after!=before:raise PackageError('Git identity changed during export')
    copied_docs,_=report_graph(destination/'files',reports)
    if copied_docs!=documents:raise PackageError('copied report graph differs')
    manifest=dict(schema=SCHEMA,classification='DEVELOPMENT_INTEGRITY_EXPORT_NOT_ATTESTATION',
        gate_b='GATE_B_NOT_AUTHORIZED',operational_authorization=False,git_before=before,git_after=after,
        files=files,historical_originals_verified=historical,reports=list(reports),report_checks=documents,
        checks=dict(recorded_hashes_matched=True,originals_unchanged_after_copy=True,exclusive_output=True,
                    copied_reports_verified=True,tracked_worktree_and_index_clean=True),
        limitations=['Unkeyed SHA-256 and caller-provided records do not authenticate sources or approvals.',
                     'Offline Markdown subset; external/unsupported links fail rather than being silently accepted.',
                     'Historical-only files are verified in the original checkout, not necessarily copied.',
                     'No replay, clock mapping, runtime restart/deadline, calibration or control limitations are resolved.'])
    _write(destination/'manifest.json',canonical(manifest))
    checksums={'files/'+name:info['sha256'] for name,info in files.items()}
    checksums.update({'STARTED.json':fingerprint(destination/'STARTED.json')['sha256'],
                      'manifest.json':fingerprint(destination/'manifest.json')['sha256']})
    _write(destination/'SHA256SUMS',_sums(checksums))
    _write(destination/'COMPLETE.json',canonical(dict(schema=SCHEMA,status='COMPLETE',
        manifest_sha256=checksums['manifest.json'],checksums_sha256=fingerprint(destination/'SHA256SUMS')['sha256'],
        gate_b='GATE_B_NOT_AUTHORIZED',operational_authorization=False)))
    for parent in sorted({p.parent for p in destination.rglob('*')},key=str):
        fd=os.open(parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return verify_package(destination)


def verify_package(destination):
    """Read-only detached verification. No claim about today's original Git state."""
    destination=Path(destination).resolve(strict=True)
    for name in ('COMPLETE.json','manifest.json','SHA256SUMS','STARTED.json'):
        p=destination/name
        if p.is_symlink() or not p.is_file():raise PackageError('missing/unsafe completion metadata: '+name)
    complete=load_json(destination/'COMPLETE.json');manifest=load_json(destination/'manifest.json')
    if complete.get('status')!='COMPLETE' or complete.get('schema')!=SCHEMA or manifest.get('schema')!=SCHEMA:
        raise PackageError('incomplete/unsupported package')
    if complete.get('gate_b')!='GATE_B_NOT_AUTHORIZED' or manifest.get('gate_b')!='GATE_B_NOT_AUTHORIZED' or complete.get('operational_authorization') is not False or manifest.get('operational_authorization') is not False:
        raise PackageError('development-only governance fields changed')
    if fingerprint(destination/'manifest.json')['sha256']!=complete.get('manifest_sha256') or fingerprint(destination/'SHA256SUMS')['sha256']!=complete.get('checksums_sha256'):
        raise PackageError('metadata hash mismatch')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files:raise PackageError('package file inventory required')
    checksums={};expected={'STARTED.json','manifest.json','SHA256SUMS','COMPLETE.json'}
    for name,info in files.items():
        path=safe_file(destination/'files',name);actual=fingerprint(path)
        if actual['sha256']!=_expect(info['sha256']) or actual['size_bytes']!=info['size_bytes']:raise PackageError('packaged file hash/size mismatch: '+name)
        checksums['files/'+name]=actual['sha256'];expected.add('files/'+name)
    for name in ('STARTED.json','manifest.json'):checksums[name]=fingerprint(destination/name)['sha256']
    if (destination/'SHA256SUMS').read_bytes()!=_sums(checksums):raise PackageError('checksum inventory differs')
    actual=set()
    for base,dirs,names in os.walk(destination,followlinks=False):
        for name in dirs+names:
            if (Path(base)/name).is_symlink():raise PackageError('symlink in package')
        for name in names:actual.add((Path(base)/name).relative_to(destination).as_posix())
    if actual!=expected:raise PackageError('unlisted/missing package file')
    reports,_=report_graph(destination/'files',manifest['reports'])
    if reports!=manifest['report_checks']:raise PackageError('report graph validation differs')
    return dict(status='VERIFIED_DEVELOPMENT_PACKAGE',files_verified=len(files),reports_verified=len(reports),
                links_verified=sum(len(r['links']) for r in reports.values()),
                historical_original_hashes_recorded=len(manifest['historical_originals_verified']),
                manifest_sha256=complete['manifest_sha256'],independent_attestation=False,
                gate_b='GATE_B_NOT_AUTHORIZED',operational_authorization=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    export=sub.add_parser('export');export.add_argument('--repo',type=Path,required=True);export.add_argument('--output',type=Path,required=True)
    export.add_argument('--receipt',action='append',required=True);export.add_argument('--prior-map',action='append',default=[])
    export.add_argument('--report',action='append',required=True);export.add_argument('--include',action='append',default=[])
    verify=sub.add_parser('verify');verify.add_argument('directory',type=Path)
    a=p.parse_args()
    try:
        result=export_package(a.repo,a.output,receipts=a.receipt,prior_maps=a.prior_map,reports=a.report,extras=a.include) if a.mode=='export' else verify_package(a.directory)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        p.exit(1,'Export/verification failed; existing or partial evidence preserved: '+str(exc)+'\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
