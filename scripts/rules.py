#!/usr/bin/env python3
"""Maintain three service-grouped .list files. Python standard library only."""
import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import io
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('cn-services.list', 'global-direct.list', 'explicit-proxy.list')
UPSTREAM = 'v2fly/domain-list-community'
SHA = re.compile(r'[0-9a-f]{40}')
BROAD = {'apple.com','icloud.com','microsoft.com','googleapis.com','gstatic.com',
         'cloudfront.net','amazonaws.com','akamaized.net','akamaihd.net','azureedge.net',
         'azurefd.net','blob.core.windows.net','cloudflare.net','cloudflare.com',
         'storage.googleapis.com','livekit.cloud','auth0.com','fastly.net','b-cdn.net',
         'cloudinary.com','aliyuncs.com','qcloud.com'}

Rule = tuple[str, str]

def within(d, root): return d == root or d.endswith('.' + root)
def overlap(a, b):
    ta, da = a; tb, db = b
    if ta == tb == 'full': return da == db
    if ta == 'full': return within(da, db)
    if tb == 'full': return within(db, da)
    return within(da, db) or within(db, da)
def covers(a, b): return (a == b) or (a[0] == 'domain' and within(b[1], a[1]))
def valid(rule):
    kind, d = rule
    return (kind in ('full','domain') and '.' in d and len(d) <= 253 and
            all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in d.split('.')) and
            not (kind == 'domain' and d in BROAD))
def encode(r): return ('DOMAIN' if r[0] == 'full' else 'DOMAIN-SUFFIX') + ',' + r[1]
def spec(r): return ':'.join(r)

@dataclass
class Group:
    name: str
    comments: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    mode: str = 'maintain'
    allow_cn: set[Rule] = field(default_factory=set)

@dataclass
class ListFile:
    header: list[str]
    revision: str
    groups: list[Group]


def parse(text):
    groups=[]; header=[]; group=None; revision=None
    for line in text.splitlines():
        if line.startswith('# Upstream: '):
            m=re.fullmatch(r'# Upstream: v2fly/domain-list-community @ ([0-9a-f]{40})',line)
            if not m or revision: raise ValueError('Invalid or duplicate upstream revision')
            revision=m[1]
        m=re.fullmatch(r'# ===== (.+) =====',line)
        if m:
            group=Group(m[1]); groups.append(group); continue
        if not line.strip(): continue
        if line.startswith('#'):
            if group is None: header.append(line); continue
            group.comments.append(line)
            if line.startswith('# @sources: '): group.sources=line.removeprefix('# @sources: ').split()
            elif line.startswith('# @sync: '): group.mode=line.removeprefix('# @sync: ')
            elif line.startswith('# @allow-cn: '):
                r=tuple(line.removeprefix('# @allow-cn: ').split(':',1))
                if not valid(r): raise ValueError('Invalid attribute override')
                group.allow_cn.add(r)
            elif line.startswith('# @'): raise ValueError('Unknown metadata: '+line)
            continue
        if group is None: raise ValueError('Rule outside a service group')
        parts=line.split(',')
        if len(parts)!=2 or parts[0] not in ('DOMAIN','DOMAIN-SUFFIX'):
            raise ValueError('Invalid rule: '+line)
        r=('full' if parts[0]=='DOMAIN' else 'domain',parts[1])
        if not valid(r): raise ValueError('Invalid/overbroad rule: '+line)
        group.rules.append(r)
    if not revision or not groups: raise ValueError('Missing source revision or groups')
    if len({g.name for g in groups}) != len(groups): raise ValueError('Duplicate group name')
    for g in groups:
        if not g.sources or any(not re.fullmatch('[a-z0-9!-]+',s) for s in g.sources): raise ValueError('Invalid source list')
        if g.mode not in ('maintain','delta'): raise ValueError('Unknown synchronization mode')
    return ListFile(header,revision,groups)

def render(doc):
    lines=[re.sub(r'(?<= @ )[0-9a-f]{40}$',doc.revision,l) if l.startswith('# Upstream: ') else l for l in doc.header]+['']
    for g in doc.groups:
        lines += ['# ===== '+g.name+' =====']+g.comments+[encode(r) for r in sorted(g.rules)]+['']
    return '\n'.join(lines)

def all_rules(doc): return [r for g in doc.groups for r in g.rules]

def check(docs):
    for name,doc in docs.items():
        rules=all_rules(doc)
        if not rules: raise ValueError('Empty rule set: '+name)
        if len(set(rules)) != len(rules): raise ValueError('Duplicate rules: '+name)
        for i,a in enumerate(rules):
            for c in rules[i+1:]:
                if overlap(a,c): raise ValueError(f'Redundant/overlapping rules in {name}: {a}, {c}')
    names=list(docs)
    for i,name in enumerate(names):
        for other in names[i+1:]:
            for a in all_rules(docs[name]):
                for c in all_rules(docs[other]):
                    if overlap(a,c): raise ValueError(f'Cross-list conflict: {name} {a} / {other} {c}')


class Source:
    def __init__(self, files):
        self.records=defaultdict(list); self.includes=defaultdict(list); self.cache={}
        for name,text in files.items():
            self.records[name]  # Keep empty but valid lists distinct from missing lists.
            for line in text.splitlines():
                parts=line.split('#',1)[0].split()
                if not parts: continue
                token=parts[0]; kind,value=token.split(':',1) if ':' in token else ('domain',token)
                attrs=frozenset(t[1:] for t in parts[1:] if t.startswith('@'))
                affiliations=[t[1:] for t in parts[1:] if t.startswith('&')]
                if any(not t.startswith(('@','&')) for t in parts[1:]): raise ValueError('Unknown upstream token')
                if kind=='include':
                    if affiliations: raise ValueError('Unexpected affiliation on include')
                    self.includes[name].append((value,attrs))
                elif kind in ('domain','full','regexp','keyword'):
                    record=(kind,value.lower(),attrs)
                    self.records[name].append(record)
                    for target in affiliations: self.records[target].append(record)
                else: raise ValueError('Unknown upstream rule type: '+kind)
        self.tags={a:{(k,d) for rs in self.records.values() for k,d,attrs in rs
                      if k in ('full','domain') and a in attrs} for a in ('cn','!cn','ads')}

    def resolve(self,name,stack=()):
        if name in stack: raise ValueError('Include cycle')
        if name in self.cache: return self.cache[name]
        if name not in self.records and name not in self.includes: raise ValueError('Missing upstream list: '+name)
        result=set(self.records[name])
        for target,filters in self.includes[name]:
            for record in self.resolve(target,stack+(name,)):
                attrs=record[2]
                if all((a[1:] not in attrs) if a.startswith('-') else (a in attrs) for a in filters): result.add(record)
        self.cache[name]=result
        return result

    def group(self,g): return set().union(*(self.resolve(s) for s in g.sources))


def source_at(repo,revision):
    if not SHA.fullmatch(revision): raise ValueError('Invalid Git revision')
    raw=subprocess.check_output(['git','-C',str(repo),'archive',revision,'data'])
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for item in archive:
            if item.isfile() and re.fullmatch(r'data/[a-z0-9!-]+',item.name):
                files[item.name[5:]]=archive.extractfile(item).read().decode('utf-8')
    if len(files)<100: raise ValueError('Incomplete upstream data')
    return Source(files)


def supported(rule,records):
    return any('ads' not in attrs and covers((kind,d),rule) for kind,d,attrs in records if kind in ('full','domain'))

def forbidden(rule,g,source,action):
    tag='cn' if action=='PROXY' else '!cn'
    if tag=='cn' and rule in g.allow_cn: return False
    return any(overlap(rule,r) for r in source.tags[tag])


def update(doc,old,new,revision,action):
    changes=[]; skipped=[]
    for g in doc.groups:
        current=new.group(g); previous=old.group(g); kept=[]
        for rule in g.rules:
            if supported(rule,current) and not forbidden(rule,g,new,action): kept.append(rule)
            else: changes.append(f'- Remove {g.name}: `{encode(rule)}` (source removed or contrary attribute)')
        g.rules=kept
        # Delta mode adds only newly introduced upstream records, never the whole existing list.
        if g.mode=='delta':
            before={(k,d) for k,d,attrs in previous}
            for kind,domain,attrs in sorted(current):
                rule=(kind,domain)
                if rule in before or kind not in ('full','domain') or 'ads' in attrs: continue
                if not valid(rule) or forbidden(rule,g,new,action):
                    skipped.append(f'{g.name}: {kind}:{domain}'); continue
                if any(covers(r,rule) for r in all_rules(doc)): continue
                if any(covers(rule,r) for r in all_rules(doc)):
                    skipped.append(f'{g.name}: broader new parent {domain}'); continue
                g.rules.append(rule);changes.append(f'- Add {g.name}: `{encode(rule)}`')
    if changes: doc.revision=revision
    return changes,skipped


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['check','update'])
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--target',choices=FILES)
    parser.add_argument('--upstream',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    docs={n:parse((args.root/n).read_text()) for n in FILES}; check(docs)
    if args.command=='check':
        print('OK: '+', '.join(f'{n}: {len(all_rules(d))}' for n,d in docs.items()));return
    if not args.target or not args.upstream: parser.error('update requires --target and --upstream')
    revision=subprocess.check_output(['git','-C',str(args.upstream),'rev-parse','HEAD'],text=True).strip()
    doc=docs[args.target];old_revision=doc.revision
    old=source_at(args.upstream,old_revision);new=source_at(args.upstream,revision)
    # Baseline must support the curated rules. A broken source mapping must not silently erase a group.
    for g in doc.groups:
        for r in g.rules:
            if not supported(r,old.group(g)): raise ValueError(f'Baseline source does not support {g.name}: {r}')
    changes,skipped=update(doc,old,new,revision,'PROXY' if args.target=='explicit-proxy.list' else 'DIRECT')
    check(docs)
    before=parse((args.root/args.target).read_text())
    removed=set(all_rules(before))-set(all_rules(doc))
    if len(removed)>max(5,len(all_rules(before))//10): raise ValueError('More than 10%/5 rules removed; manual review required')
    for previous,now in zip(before.groups,doc.groups):
        if previous.rules and not now.rules: raise ValueError('Entire service group removed: '+now.name)
    if changes: (args.root/args.target).write_text(render(doc))
    report='\n'.join(['## '+args.target,'',f'Upstream: https://github.com/{UPSTREAM}/compare/{old_revision}...{revision}',
        '', 'Changes are based on source data, not live connectivity testing.',
        'Only this list is changed. All three lists passed overlap checks and regression tests run in this workflow.',
        '',*(changes or ['No rule changes; source revision left unchanged to avoid empty PRs.']),
        '',f'Skipped unsafe/overbroad new candidates: {len(skipped)}',*['- '+x for x in skipped[:30]]])+'\n'
    if args.report: args.report.write_text(report)
    print(report)

if __name__=='__main__': main()
