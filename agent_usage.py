#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local-only Codex / Claude usage. Python 3.9+, standard library, zero uploads.
Run: python3 agent_usage.py --open
"""
import argparse
import collections
import datetime as dt
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import webbrowser

VERSION = '2.3.0'
PARSER_VERSION = 2
PRICE_DATE = '2026-09-05'
# USD / million tokens: uncached, read, 5m write, output. Claude 1h writes = 2x input.
# A versioned offline price snapshot, not provider invoices or guaranteed historical rates.
RATE_VALUES = {
 'gpt-6-astra': [10,1,12.5,50], 'gpt-5.6-sol': [4,.4,5,20],
 'gpt-5.5':[5,.5,0,30], 'gpt-5.4':[2.5,.25,0,15],
 'gpt-5.3-codex':[1.75,.175,0,14], 'gpt-5.4-mini':[.75,.075,0,4.5],
 'gpt-5.6-terra': [2,.2,2.5,12], 'gpt-5.6-luna': [.2,.02,.25,1.2],
 'claude-fable-5-1': [10,.25,12.5,50], 'claude-fable-5': [10,1,12.5,50],
 'claude-mythos-5-1': [10,.25,12.5,50], 'claude-mythos-5': [10,1,12.5,50],
 'claude-opus-5': [5,.5,6.25,25], 'claude-opus-4-8': [5,.5,6.25,25],
 'claude-opus-4-7': [5,.5,6.25,25], 'claude-opus-4-6': [5,.5,6.25,25],
 'claude-opus-4-5': [5,.5,6.25,25], 'claude-opus-4-1': [15,1.5,18.75,75],
 'claude-opus-4': [15,1.5,18.75,75], 'claude-sonnet-5': [2,.2,2.5,10],
 'claude-sonnet-4-6': [3,.3,3.75,15], 'claude-sonnet-4-5': [3,.3,3.75,15],
 'claude-sonnet-4': [3,.3,3.75,15], 'claude-haiku-4-5': [1,.1,1.25,5],
 'claude-haiku-3-5': [.8,.08,1,4],
}
PRICE_SOURCES = ['https://developers.openai.com/api/docs/pricing',
                 'https://platform.claude.com/docs/en/about-claude/pricing']

def default_prices():
    models = {}
    for model, values in RATE_VALUES.items():
        rule = dict(zip(['input','cached','write_5m','output'], values))
        rule['write_1h'] = values[0]*2
        if model.startswith(('gpt-6-','gpt-5.6-')):
            rule.update(long_threshold=272000,long_input_multiplier=2,long_output_multiplier=1.5,
                        fast_multiplier=2, flex_multiplier=.5, batch_multiplier=.5)
        elif model.startswith('gpt-'):
            rule['no_cache_write_rate']=True
            if model in ('gpt-5.5','gpt-5.4'):
                rule.update(long_threshold=272000,long_input_multiplier=2,long_output_multiplier=1.5,long_scope='session',flex_multiplier=.5,batch_multiplier=.5)
        else:
            if model in ('claude-sonnet-4','claude-sonnet-4-5'):
                rule.update(long_threshold=200000,long_input_multiplier=2,long_output_multiplier=1.5)
            if model in ('claude-opus-5','claude-opus-4-8'):
                rule['fast_multiplier']=2
            rule['batch_multiplier']=.5
        models[model] = rule
    return dict(as_of=PRICE_DATE, currency='USD', sources=PRICE_SOURCES, models=models)

def atom_json(path, obj):
    atom_write(path, json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode())

def atom_write(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def timestamp(value):
    try:
        if isinstance(value,(float,int)): return float(value)/1000 if value>1e11 else float(value)
        d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()
    except (ValueError,TypeError,OverflowError): return None

def canonical_model(model):
    # Only known date suffix formats; arbitrary unknown aliases must remain unknown.
    model=str(model or 'unknown').lower()
    model=re.sub(r'-(?:20\d{2}-\d{2}-\d{2}|20\d{6})$','',model)
    model={'claude-3-5-haiku':'claude-haiku-3-5'}.get(model,model)
    if model.startswith('claude-'): model=model.replace('.', '-')
    return model

def project_name(value):
    # No dependency on a particular checkout folder or username.
    p=Path(str(value or ''))
    if not value:return 'unknown'
    parts=p.parts
    if '.claude' in parts and 'worktrees' in parts:
        return Path(*parts[:parts.index('.claude')]).name or 'home'
    if p==Path.home():return 'home'
    return p.name or 'home'

def title_text(text):
    text=' '.join(re.sub(r'<[^>]+>',' ',str(text or '')).split())[:100]
    if re.search(r'(sk-[\w-]{8,}|Bearer |password=|token=|[\w.+-]+@[\w.-]+\.)',text,re.I): return '[redacted]'
    return text

def number(value):
    if value is None:return 0
    if isinstance(value,bool):raise ValueError('boolean token count')
    result=int(value)
    if result<0 or float(value)!=result:raise ValueError('invalid token count')
    return result

def normalize_usage(u,provider):
    if not isinstance(u,dict):raise ValueError('usage not object')
    incoming=number(u.get('input_tokens'))
    cached=number(u.get('cache_read_input_tokens') if provider=='Claude' else u.get('cached_input_tokens'))
    write=number(u.get('cache_creation_input_tokens') if provider=='Claude' else u.get('cache_write_input_tokens'))
    if provider=='Claude':incoming+=cached+write
    output=number(u.get('output_tokens'))
    if cached+write>incoming:raise ValueError('cache exceeds input')
    ttl=u.get('cache_creation') or {};one=number(ttl.get('ephemeral_1h_input_tokens'));five=number(ttl.get('ephemeral_5m_input_tokens'))
    conflict=one+five>write
    if conflict: one=min(one,write);five=min(five,write-one)
    # Missing TTL stays unknown; pricing becomes a range rather than guessing 5m.
    unknown=max(0,write-one-five) if provider=='Claude' else 0
    return dict(input=incoming,cached=cached,write=write,uncached=incoming-cached-write,
                output=output,total=incoming+output,write_1h=one,write_5m=five,
                write_unknown=unknown,ttl_conflict=conflict)

def read_jsonl(path,quality):
    """Bound reads to the initial file size; tolerate an active/incomplete final record."""
    try:
        with path.open('rb') as f:
            end=os.fstat(f.fileno()).st_size
            while f.tell()<end:
                line=f.readline(end-f.tell())
                if not line.strip():continue
                try:
                    obj=json.loads(line)
                    if isinstance(obj,dict):yield obj
                except (ValueError,UnicodeError):
                    quality['partial_tail' if f.tell()==end and not line.endswith(b'\n') else 'malformed_lines']+=1
    except OSError:
        quality['unreadable_files']+=1

def parse_codex(path,include_titles=False):
    q=collections.Counter();sessions={};requests=[];seen={};sid=None;model='unknown';effort='unknown';tier='unknown';project='unknown';role='main';turn=''
    for x in read_jsonl(path,q):
        p=x.get('payload') or {}
        if not isinstance(p,dict):continue
        typ=x.get('type');ts=timestamp(x.get('timestamp'))
        if typ=='session_meta':
            sid=str(p.get('id') or p.get('session_id') or path.stem)
            project=project_name(p.get('cwd'));model=p.get('model') or 'unknown'
            role='subagent' if 'subagent' in json.dumps(p.get('source',{})).lower() or p.get('agent_path','/root') not in ['/root',None,''] else 'main'
            sessions.setdefault(sid,dict(id='Codex:'+sid,provider='Codex',role=role,project=project,title=sid[:12],trace=True))
        if not sid:continue
        if typ=='turn_context':
            model=p.get('model',model);effort=p.get('effort') or p.get('reasoning_effort') or effort
            tier=p.get('service_tier') or tier;turn=p.get('turn_id') or turn
            if p.get('cwd'):project=project_name(p['cwd'])
        if typ=='event_msg' and p.get('type')=='task_started':turn=p.get('turn_id') or turn
        if typ!='event_msg' or p.get('type')!='token_count' or not p.get('info'):continue
        info=p['info'];u=info.get('last_token_usage');cu=info.get('total_token_usage')
        if not u:q['codex_missing_last_usage']+=1;continue
        signature=json.dumps(cu,sort_keys=True) if cu else None
        # Compare consecutive counters, not a global set: an equal value after a reset is a new request.
        if signature and seen.get(sid)==signature:q['duplicate_usage_blocks']+=1;continue
        if cu and sid in seen:
            previous=json.loads(seen[sid])
            if cu.get('total_tokens',0)<previous.get('total_tokens',0):q['counter_resets']+=1
        if signature:seen[sid]=signature
        try:usage=normalize_usage(u,'Codex')
        except (ValueError,TypeError,OverflowError):q['invalid_usage']+=1;continue
        if ts is None:q['missing_timestamps']+=1;continue
        key=hashlib.sha256(json.dumps([sid,ts,turn,cu or u],sort_keys=True).encode()).hexdigest()
        requests.append(dict(id='cx:'+key,session='Codex:'+sid,provider='Codex',model=model,
                             effort=effort,tier=tier,speed='unknown',geo='unknown',project=project,
                             role=role,ts=ts,web_searches=None,**usage))
    return dict(sessions=list(sessions.values()),requests=requests,reports=[],quality=dict(q))

def parse_claude(path,include_titles=False):
    q=collections.Counter();requests=[];sessions={};reports=[]
    sub='subagents' in path.parts
    sid=(path.parent.parent.name+'/'+path.stem) if sub else path.parent.name if path.name=='audit.jsonl' else path.stem
    skey='Claude:'+sid;project='unknown';role='subagent' if sub else 'main';title=sid[:12]
    for x in read_jsonl(path,q):
        ts=timestamp(x.get('timestamp'));typ=x.get('type')
        if x.get('cwd'):project=project_name(x['cwd'])
        if typ=='result' and isinstance(x.get('total_cost_usd'),(int,float)) and ts is not None:
            # Keep result reports separate: SDK scopes include children and may be cumulative across turns.
            reports.append(dict(id=str(x.get('uuid') or hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()),
                                session=skey,ts=ts,reported_usd=x['total_cost_usd']))
        m=x.get('message') or {}
        if not isinstance(m,dict):continue
        if include_titles and typ=='user' and title==sid[:12] and not x.get('isMeta'):
            content=m.get('content','');texts=content if isinstance(content,str) else ' '.join(a.get('text','') for a in content if isinstance(a,dict))
            if texts and not texts.startswith(('/', '<local-command','<command-name')):title=title_text(texts)
        if typ!='assistant' or not m.get('usage') or m.get('model') in [None,'<synthetic>']:continue
        mid=m.get('id') or x.get('message_id')
        if not mid:q['missing_message_ids']+=1;continue
        if ts is None:q['missing_timestamps']+=1;continue
        u=m['usage']
        try:usage=normalize_usage(u,'Claude')
        except (ValueError,TypeError,OverflowError):q['invalid_usage']+=1;continue
        sessions[skey]=dict(id=skey,provider='Claude',role=role,project=project,title=title,trace=True)
        searches=(u.get('server_tool_use') or {}).get('web_search_requests')
        try: searches=None if searches is None else number(searches)
        except (ValueError,TypeError): searches=None
        requests.append(dict(id='cl:'+str(mid),session=skey,provider='Claude',model=m.get('model'),
                             effort=x.get('effort') or 'unknown',tier=u.get('service_tier') or 'unknown',
                             speed=u.get('speed') or 'unknown',geo=u.get('inference_geo') or 'unknown',
                             project=project,role=role,ts=ts,web_searches=searches,**usage))
    return dict(sessions=list(sessions.values()),requests=requests,reports=reports,quality=dict(q))

def merge_requests(rows,quality):
    merged={}
    for r in rows:
        old=merged.get(r['id'])
        if old is None:merged[r['id']]=r.copy();continue
        quality['duplicate_usage_blocks']+=1
        if old['session']!=r['session']:quality['cross_session_copies']+=1
        # A single coherent input snapshot, with final/max output for streaming duplicates.
        output=max(old['output'],r['output'])
        owner=old if old['role']=='main' else r if r['role']=='main' else old
        chosen=max([old,r],key=lambda a:(a['output'],a['input']))
        result=chosen.copy()
        for k in ['session','role','project']:result[k]=owner[k]
        result['ts']=min(old['ts'],r['ts']);result['output']=output;result['total']=result['input']+output
        searches=[v for v in [old.get('web_searches'),r.get('web_searches')] if v is not None]
        result['web_searches']=max(searches) if searches else None
        merged[r['id']]=result
    return list(merged.values())

def load_prices(path=None):
    catalog=json.loads(Path(path).read_text(encoding='utf-8')) if path else default_prices()
    if catalog.get('currency')!='USD' or not isinstance(catalog.get('models'),dict):raise ValueError('Prices must contain currency=USD and models object')
    for model,rules in catalog['models'].items():
        rules=rules if isinstance(rules,list) else [rules]
        for rule in rules:
            for field in ['input','cached','write_5m','write_1h','output']:
                value=Decimal(str(rule[field]))
                if not value.is_finite() or value<0:raise ValueError('Invalid price for '+model)
            for field in ['long_threshold','long_input_multiplier','long_output_multiplier','fast_multiplier','flex_multiplier','batch_multiplier']:
                if field in rule:
                    value=Decimal(str(rule[field]))
                    if not value.is_finite() or value<=0:raise ValueError('Invalid multiplier / threshold for '+model)
            for field in ['valid_from','valid_to']:
                if rule.get(field):dt.date.fromisoformat(rule[field])
    return catalog

def price_request(row,catalog):
    model=canonical_model(row['model']);rules=catalog['models'].get(model)
    if rules is None:return dict(cost=None,cost_high=None,cost_parts=None,price_status='unknown_model',assumptions=[])
    rules=rules if isinstance(rules,list) else [rules]
    date=dt.datetime.fromtimestamp(row['ts'],dt.timezone.utc).date().isoformat()
    matches=[v for v in rules if (not v.get('valid_from') or date>=v['valid_from']) and (not v.get('valid_to') or date<v['valid_to'])]
    if len(matches)!=1:return dict(cost=None,cost_high=None,cost_parts=None,price_status='missing_or_overlapping_date_rate',assumptions=[])
    rule=matches[0];d=lambda x:Decimal(str(x));million=Decimal(1000000)
    ip,cp,wp,one,op=(d(rule[k]) for k in ['input','cached','write_5m','write_1h','output'])
    assumptions=[];mult=Decimal(1)
    if rule.get('no_cache_write_rate') and row['write']:
        return dict(cost=None,cost_high=None,cost_parts=None,price_status='unpriced_cache_write',assumptions=[])
    pricing_context=row.get('session_max_input',row['input']) if rule.get('long_scope')=='session' else row['input']
    if pricing_context>rule.get('long_threshold',float('inf')):
        im=d(rule['long_input_multiplier']);om=d(rule['long_output_multiplier'])
        ip*=im;cp*=im;wp*=im;one*=im;op*=om
    tier=row.get('tier','unknown');speed=row.get('speed','unknown')
    if tier in ['priority','fast'] or speed=='fast':mode='fast'
    elif tier in ['batch','flex']:mode=tier
    elif tier in ['unknown','standard','default',None]:mode='standard'
    else:return dict(cost=None,cost_high=None,cost_parts=None,price_status='unknown_tier',assumptions=[])
    if mode!='standard':
        if mode+'_multiplier' not in rule:return dict(cost=None,cost_high=None,cost_parts=None,price_status='unpriced_tier',assumptions=[])
        mult*=d(rule[mode+'_multiplier'])
    elif tier in ['unknown','default',None]:assumptions.append('Standard tier assumed')
    if row.get('geo')=='us':mult*=Decimal('1.1')
    elif row.get('geo') not in ['global']:assumptions.append('Global routing assumed')
    if row['provider']=='Claude':
        wlow=d(row['write_5m'])*wp+d(row['write_1h'])*one+d(row['write_unknown'])*min(wp,one)
        whigh=d(row['write_5m'])*wp+d(row['write_1h'])*one+d(row['write_unknown'])*max(wp,one)
        if row['write_unknown']:assumptions.append('Cache write TTL unknown: 5m–1h range')
    else:wlow=whigh=d(row['write'])*wp
    parts=[d(row['uncached'])*ip,d(row['cached'])*cp,wlow,d(row['output'])*op]
    parts=[x*mult/million for x in parts]
    # Only explicit server-side searches are priced. Missing counts stay a stated scope limit.
    search=d(row.get('web_searches') or 0)*Decimal('.01')
    parts.append(search)
    cost=sum(parts);high=cost+(whigh-wlow)*mult/million
    return dict(cost=float(cost),cost_high=float(high),cost_parts=[float(x) for x in parts],
                price_status='range' if high!=cost else 'priced',assumptions=assumptions)

def discover(args):
    home=Path(args.home).expanduser().resolve() if args.home else Path.home()
    codex=Path(args.codex_dir or (os.environ.get('CODEX_HOME') if not args.home else '') or home/'.codex').expanduser().resolve()
    claude=Path(args.claude_dir or (os.environ.get('CLAUDE_CONFIG_DIR') if not args.home else '') or home/'.claude').expanduser().resolve()
    roots=[('Codex',codex/'sessions'),('Codex',codex/'archived_sessions'),('Claude',claude/'projects')]
    if args.cowork:roots.append(('Claude',home/'Library/Application Support/Claude/local-agent-mode-sessions'))
    files={}
    for provider,root in roots:
        if root.is_dir():
            for p in root.rglob('*.jsonl'):
                if p.is_file():files[str(p.resolve())]=(provider,p.resolve())
    return codex,sorted(files.values(),key=lambda pair:('subagents' in pair[1].parts,str(pair[1]))),roots

def registry(codex,include_titles,quality):
    states=sorted(codex.glob('state_*.sqlite'),key=lambda p:int(re.search(r'_(\d+)',p.name).group(1)),reverse=True)
    for path in states:
        try:
            c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2);c.row_factory=sqlite3.Row
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='threads'").fetchone():c.close();continue
            result={}
            for r in c.execute('SELECT * FROM threads'):
                r=dict(r);sid='Codex:'+str(r['id']);model=r.get('model') or 'unknown'
                role='review' if model=='codex-auto-review' else 'subagent' if 'subagent' in str(r.get('source')).lower() or r.get('agent_path','/root') not in ['/root',None,''] else 'main'
                result[sid]=dict(id=sid,provider='Codex',role=role,project=project_name(r.get('cwd')),title=title_text(r.get('title')) if include_titles else str(r['id'])[:12],trace=False,registry_model=model)
            c.close();return result
        except (sqlite3.Error,OSError,KeyError):quality['registry_unreadable']+=1
    return {}

class ParseCache:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT)')
    def parse(self,provider,path,titles,stats):
        st=path.stat();fp=f'{PARSER_VERSION}:{int(titles)}:{st.st_size}:{st.st_mtime_ns}:{st.st_ino}'
        cached=self.c.execute('SELECT fingerprint,payload FROM files WHERE path=?',(str(path),)).fetchone()
        if cached and cached[0]==fp:
            try:result=json.loads(cached[1]);stats['cached_files']+=1;return result
            except ValueError:pass
        result=(parse_codex if provider=='Codex' else parse_claude)(path,titles)
        stats['parsed_files']+=1
        if not result['quality'].get('unreadable_files'):
            self.c.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)',(str(path),fp,json.dumps(result,separators=(',',':'))))
        return result
    def close(self,paths):
        # Removed traces must disappear from subsequent snapshots and derived cache.
        for (path,) in self.c.execute('SELECT path FROM files').fetchall():
            if path not in paths:self.c.execute('DELETE FROM files WHERE path=?',(path,))
        self.c.commit();self.c.close()

def report_timezone(name):
    if not name:return None
    if name=='UTC':return dt.timezone.utc
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)

def source_fingerprint(args):
    codex,files,_=discover(args)
    paths=[p for _,p in files]+list(codex.glob('state_*.sqlite*'))
    if args.prices:paths.append(Path(args.prices))
    day=dt.datetime.now(dt.timezone.utc).astimezone(report_timezone(args.timezone)).date().isoformat()
    return day,tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)

def make_snapshot(args, dashboard=True, include_requests=False):
    output=Path(args.output).expanduser().resolve();output.mkdir(parents=True,exist_ok=True)
    catalog=load_prices(args.prices)
    q=collections.Counter();stats=collections.Counter();codex,files,roots=discover(args)
    sessions=registry(codex,args.include_titles,q);rows=[];reports={}
    cache=ParseCache(output/'parse-cache.sqlite')
    try:
        for provider,path in files:
            try:r=cache.parse(provider,path,args.include_titles,stats)
            except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):q['failed_files']+=1;continue
            q.update(r['quality']);rows.extend(r['requests'])
            for s in r['sessions']:
                previous=sessions.get(s['id'],{})
                # Registry title and role enrich legacy traces; model remains per-request.
                sessions[s['id']]={**s,**previous,'trace':True}
            for report in r['reports']:reports[report['id']]=report
    finally:cache.close({str(p) for _,p in files})
    rows=merge_requests(rows,q)
    tz=report_timezone(args.timezone)
    session_max=collections.defaultdict(int)
    for r in rows:session_max[(r['session'],r['model'])]=max(session_max[(r['session'],r['model'])],r['input'])
    for r in rows:
        r['session_max_input']=session_max[(r['session'],r['model'])]
        s=sessions.get(r['session'])
        if s and s.get('role') in ['subagent','review']:r['role']=s['role']
        if r['model']=='unknown':q['unknown_request_model']+=1 # latest registry model is not safe historical attribution
        r.update(price_request(r,catalog))
        moment=dt.datetime.fromtimestamp(r['ts'],dt.timezone.utc).astimezone(tz)
        r['date']=moment.date().isoformat()
    # Dashboard rows: one date × model × session × project × role, preserving filter correctness.
    grouped={}
    for r in rows:
        key=(r['date'],r['provider'],r['model'],r['session'],r['project'],r['role'])
        if key not in grouped:grouped[key]=dict(zip(['date','provider','model','session','project','role'],key),requests=0,input=0,cached=0,write=0,output=0,total=0,cost=0.,cost_high=0.,unpriced=0,max_context=0,parts=[0.]*5,assumed=0,write_unknown=0)
        g=grouped[key];g['requests']+=1
        for f in ['input','cached','write','output','total','write_unknown']:g[f]+=r[f]
        g['max_context']=max(g['max_context'],r['input'])
        g['assumed']+=bool(r['assumptions'])
        if r['cost'] is None:g['unpriced']+=1
        else:
            g['cost']+=r['cost'];g['cost_high']+=r['cost_high']
            g['parts']=[a+b for a,b in zip(g['parts'],r['cost_parts'])]
    measured={r['session'] for r in rows};traceids={s['id'] for s in sessions.values() if s['trace'] and s['provider']=='Codex'}
    q['ttl_conflicts']=sum(r['ttl_conflict'] for r in rows)
    summary=dict(requests=len(rows),sessions=len(measured),input=sum(r['input'] for r in rows),output=sum(r['output'] for r in rows),cached=sum(r['cached'] for r in rows),
                 cost=sum(r['cost'] or 0 for r in rows),cost_high=sum(r['cost_high'] or 0 for r in rows),unpriced=sum(r['cost'] is None for r in rows),
                 registry_codex=sum(s['provider']=='Codex' for s in sessions.values()),traces_codex=len(traceids),files=len(files))
    assert summary['requests']==sum(g['requests'] for g in grouped.values())
    assert summary['input']==sum(g['input'] for g in grouped.values())
    assert math.isclose(summary['cost'],sum(g['cost'] for g in grouped.values()),abs_tol=1e-7)
    # No source paths, transcript, hidden reasoning or arguments are embedded in the HTML.
    now=dt.datetime.now(dt.timezone.utc)
    snapshot=dict(version=VERSION,generated=now.isoformat(),as_of_date=now.astimezone(tz).date().isoformat(),device=socket.gethostname(),
                  timezone=args.timezone or 'System local timezone',price_as_of=catalog.get('as_of','custom'),price_sources=catalog.get('sources',[]),
                  sources=[dict(provider=p,exists=root.is_dir(),path=str(root)) for p,root in roots],
                  summary=summary,quality=dict(q),scan=dict(stats),rows=list(grouped.values()),
                  titles={s['id']:s['title'] for s in sessions.values() if s['id'] in measured} if args.include_titles else {},
                  unknown_models=sorted({r['model'] for r in rows if r['cost'] is None}),
                  reports=list(reports.values()))
    # Private evidence stays local. Requests are normalized fields only.
    atom_json(output/'usage.json',dict(snapshot,requests=rows,registry=list(sessions.values())))
    atom_json(output/'prices-used.json',catalog)
    if dashboard:
        public={k:v for k,v in snapshot.items() if k!='sources'}
        body=render_html(public)
        atom_write(output/'dashboard.html',body.encode())
        atom_json(output/'status.json',{'generated':snapshot['generated'],'version':VERSION})
    return dict(snapshot,requests=rows) if include_requests else snapshot

def usage_totals(rows):
    fields={'input_tokens':'input','output_tokens':'output','total_tokens':'total',
            'cached_input_tokens':'cached','cache_write_tokens':'write'}
    result={name:sum(row[key] for row in rows) for name,key in fields.items()}
    count=sum(row['requests'] for row in rows)
    missing=sum(row['unpriced'] for row in rows)
    known=sum(row['cost'] for row in rows)
    high=sum(row['cost_high'] for row in rows)
    result.update(requests=count,sessions=len({row['session'] for row in rows}),
                  days_with_records=len({row['date'] for row in rows}),
                  priced_requests=count-missing,unpriced_requests=missing,
                  estimated_cost_usd=known if count>missing else None,
                  estimated_cost_high_usd=high if count>missing else None,
                  known_cost_usd=known,
                  requests_with_assumptions=sum(row['assumed'] for row in rows),
                  unknown_cache_ttl_tokens=sum(row['write_unknown'] for row in rows),
                  max_input_tokens=max((row['max_context'] for row in rows),default=0),
                  cache_share=result['cached_input_tokens']/result['input_tokens'] if result['input_tokens'] else None,
                  cost_parts_usd=dict(zip(['uncached_input','cache_reads','cache_writes','output','web_search'],
                                         [sum(row['parts'][i] for row in rows) for i in range(5)])))
    return result

def usage_period(rows,include_requests=None):
    result=dict(totals=usage_totals(rows),rows=rows)
    for field in ['provider','model','project','role','session','date']:
        groups=collections.defaultdict(list)
        for row in rows:groups[row[field]].append(row)
        values=[dict(name=name,**usage_totals(group)) for name,group in groups.items()]
        result['by_'+field]=sorted(values,key=(lambda value:value['name']) if field=='date' else (lambda value:(-value['known_cost_usd'],value['name'])))
    if include_requests is not None:result['requests']=include_requests
    return result

def usage_changes(current,previous):
    if previous is None:return {'status':'not_requested'}
    a,b=current['totals'],previous['totals']
    if not b['requests']:return {'status':'no_previous_data'}
    if not a['requests']:return {'status':'no_current_data'}
    result={'status':'available'}
    for metric in ['requests','sessions','input_tokens','output_tokens','total_tokens','estimated_cost_usd','cache_share']:
        x,y=a[metric],b[metric]
        if metric=='estimated_cost_usd' and (a['unpriced_requests'] or b['unpriced_requests'] or
                any(value['estimated_cost_usd'] is not None and value['estimated_cost_high_usd']-value['estimated_cost_usd']>1e-9 for value in [a,b])):
            result[metric]={'status':'incomplete_pricing'};continue
        if x is None or y is None:
            result[metric]={'status':'unavailable'};continue
        difference=x-y
        change={'status':'available','previous':y,'absolute':difference}
        if metric=='cache_share':change['percentage_points']=difference*100
        else:
            change['percent']=difference/abs(y)*100 if y else 0. if not x else None
            if change['percent'] is None:change['status']='zero_baseline'
        result[metric]=change
    return result

def usage_report(snapshot,args):
    if args.days<1:raise ValueError('--days must be positive')
    if args.all_time and (args.date_from or args.date_to):raise ValueError('--all-time cannot be combined with --from or --to')
    dates=sorted(row['date'] for row in snapshot['rows'])
    end=dt.date.fromisoformat(args.date_to or (dates[-1] if args.all_time and dates else snapshot['as_of_date']))
    start=dt.date.fromisoformat(args.date_from or (dates[0] if args.all_time and dates else (end-dt.timedelta(days=args.days-1)).isoformat()))
    if start>end:raise ValueError('--from must be on or before --to')
    days=(end-start).days+1
    before=(start-dt.timedelta(days=days),start-dt.timedelta(days=1)) if not args.all_time else None
    provider={'codex':'Codex','openai':'Codex','claude':'Claude','anthropic':'Claude'}.get((args.provider or '').lower())
    if args.provider and not provider:raise ValueError('--provider must be Codex/OpenAI or Claude/Anthropic')
    model=canonical_model(args.model) if args.model else None
    def matching(row,window):
        return bool(window and window[0].isoformat()<=row['date']<=window[1].isoformat() and
                    (not provider or row['provider']==provider) and (not model or canonical_model(row['model'])==model) and
                    (not args.project or row['project']==args.project) and (not args.role or row['role']==args.role))
    def period(window):
        selected=[row for row in snapshot['rows'] if matching(row,window)]
        details=[row for row in snapshot.get('requests',[]) if matching(row,window)] if args.include_requests else None
        return usage_period(selected,details)
    current=period((start,end));previous=period(before) if before else None
    report=dict(schema_version=1,version=VERSION,generated=snapshot['generated'],as_of_date=snapshot['as_of_date'],
                timezone=snapshot['timezone'],price_as_of=snapshot['price_as_of'],price_sources=snapshot.get('price_sources',[]),
                period={'from':start.isoformat(),'to':end.isoformat(),'days':days},
                previous_period={'from':before[0].isoformat(),'to':before[1].isoformat(),'days':days} if before else None,
                filters={'provider':provider,'model':model,'project':args.project,'role':args.role},
                current=current,previous=previous,changes=usage_changes(current,previous),
                quality=snapshot['quality'],scan=snapshot['scan'],source_summary=snapshot['summary'],
                unknown_models=sorted({row['model'] for row in current['rows'] if row['unpriced']}),
                notes=['Costs are API-equivalent estimates, not subscription charges.',
                       'Comparisons use recorded observations; missing records do not prove zero usage.',
                       'A period including the snapshot date may contain a partial day.'])
    return report

def usage_text(report):
    months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
    def date_label(value):
        day=dt.date.fromisoformat(value)
        return months[day.month-1]+' '+str(day.day)
    period=report['period'];a=report['current']['totals']
    cost=a['estimated_cost_usd'];high=a['estimated_cost_high_usd']
    amount='unavailable' if cost is None else f'${cost:,.2f}'+(f'–${high:,.2f}' if high-cost>.005 else '')
    if a['unpriced_requests']:amount+=f" (partial; {a['unpriced_requests']:,} unpriced requests)"
    label=date_label(period['from'])+'–'+date_label(period['to'])
    if period['from'][:4]!=period['to'][:4]:label=period['from']+'–'+period['to']
    lines=[f"For {label}: {a['requests']:,} requests, {a['sessions']:,} sessions, {amount} estimated API cost."]
    changes=report['changes']
    if changes['status']=='available':
        descriptions=[]
        for metric,name in [('requests','requests'),('estimated_cost_usd','estimated cost')]:
            value=changes[metric]
            if value['status']=='available':descriptions.append(f"{name} {value['percent']:+.1f}%")
            else:descriptions.append(name+': '+value['status'].replace('_',' '))
        lines.append('Versus the previous period: '+', '.join(descriptions)+'.')
    elif changes['status']!='not_requested':lines.append(changes['status'].replace('_',' ').capitalize()+'.')
    return '\n'.join(lines)

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'">
<title>AISAD · Claude &amp; Codex usage</title><style>
:root{color-scheme:light dark;--bg:#f7f8fa;--card:#fff;--ink:#17212d;--muted:#626e7b;--line:#e4e8ed;--accent:#147e78;--orange:#bf672b;--shade:#ecf6f4;--previous:#acb8c7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}main{max-width:1440px;margin:auto;padding:34px 32px 70px}header{display:flex;align-items:center;justify-content:space-between;gap:20px}h1{font-size:30px;letter-spacing:-1px;margin:0}h2{font-size:17px;letter-spacing:-.2px;margin:0 0 14px}h3{margin:24px 0 8px}.muted,small{color:var(--muted)}small{font-size:12px}.badge{border:1px solid var(--line);padding:7px 11px;border-radius:30px;color:var(--accent);white-space:nowrap}.coverage{margin:22px 0 16px;border-left:3px solid var(--accent);padding:12px 16px;background:var(--shade);border-radius:4px}.filters{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}label{display:flex;flex-direction:column;gap:5px;color:var(--muted);font-size:12px}select,input,button{font:inherit;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--ink);padding:9px 11px;min-height:38px}select{max-width:240px}button{cursor:pointer}button:hover{border-color:var(--accent)}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:22px 0}.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0}.card .value{font-size:26px;font-weight:650;letter-spacing:-.8px;margin:8px 0;overflow-wrap:anywhere}.card label{display:block;font-size:12px}.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;margin:16px 0}.grid.equal{grid-template-columns:1fr 1fr}.panel{margin-bottom:0}.wide{margin-top:16px}svg{display:block;width:100%;height:auto;max-height:310px;overflow:visible}.chart-text{fill:var(--muted);font-size:11px}.table-wrap{overflow:auto;max-height:630px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:12px 10px;border-bottom:1px solid var(--line);white-space:nowrap}th:first-child,td:first-child{text-align:left}th{position:sticky;top:0;background:var(--card);font-size:12px;color:var(--muted)}td:first-child{max-width:330px;overflow:hidden;text-overflow:ellipsis}th button{padding:2px 0;min-height:0;border:none;font-weight:600;background:none}.barrow{display:grid;grid-template-columns:155px 1fr 100px;align-items:center;gap:12px;margin:13px 0}.barlabel{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bartrack{height:11px;background:var(--line);border-radius:10px;overflow:hidden}.barfill{height:100%;background:var(--accent);border-radius:10px}.barvalue{text-align:right;font-variant-numeric:tabular-nums;font-size:12px}.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-bottom:15px}.insights{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}.insight{padding:16px 20px;background:var(--shade);border-radius:10px}.insight b{font-size:19px;display:block;margin-bottom:4px}details{margin-top:18px}summary{cursor:pointer;font-weight:600}details p,details li{overflow-wrap:anywhere;color:var(--muted);max-width:1080px}a{color:var(--accent)}.empty{padding:40px 10px;text-align:center;color:var(--muted)}.legend{display:flex;gap:16px;margin-top:10px;color:var(--muted);font-size:12px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;background:var(--accent)}footer{margin-top:25px;font-size:12px;color:var(--muted)}.money-note{margin:10px 0;color:var(--muted);font-size:12px}
@media(prefers-color-scheme:dark){:root{--bg:#11161c;--card:#19212a;--ink:#e5edf5;--muted:#9aaabd;--line:#303b48;--accent:#59c6b8;--orange:#eda76b;--shade:#1b302f;--previous:#65778c}}
@media(max-width:1100px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:720px){main{padding:22px 14px}header{align-items:flex-start}h1{font-size:25px}.badge{font-size:11px}.grid,.grid.equal{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}.card,.panel{padding:15px}.card .value{font-size:23px}.insights{grid-template-columns:1fr}.barrow{grid-template-columns:115px 1fr 90px}.filters label{flex:1;min-width:130px}select{max-width:100%}.filters button{align-self:end}svg{min-height:190px}}
.comparison{margin:10px 0 18px;color:var(--muted);font-size:13px}.delta{display:block;margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-size:12px;color:var(--accent)}.provider-button{padding:0;min-height:0;border:none;background:none;text-align:left;color:var(--accent)}.filters{align-items:flex-end}.legend{flex-wrap:wrap}.legend .previous{background:var(--previous)}
</style></head><body><main>
<header><div><h1>AISAD · Agent usage</h1><div class="muted" id="subtitle"></div></div><span class="badge">● This device only</span></header>
<div class="coverage" id="coverage"></div>
<div class="filters">
<label>Period<select id="period"><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="all">All time</option><option value="custom">Custom</option></select></label>
<label>From<input type="date" id="from"></label><label>To<input type="date" id="to"></label>
<label>Provider<select id="provider"></select></label><label>Model<select id="model"></select></label>
<label>Project<select id="project"></select></label><label>Role<select id="role"><option value="">All roles</option><option value="main">Main thread</option><option value="subagent">Subagent</option><option value="review">Auto-review</option></select></label>
<button id="reset">Reset</button></div>
<p class="comparison" id="comparison-note" aria-live="polite"></p>
<div class="cards" id="cards"></div><div class="money-note" id="money-note"></div>
<div class="grid"><section class="panel"><div class="tools"><h2>Daily usage</h2><select id="chartmetric" aria-label="Chart metric"><option value="cost">Estimated cost, USD</option><option value="total">Total tokens</option><option value="output">Output tokens</option><option value="requests">Requests</option></select></div><div id="daily"></div></section><section class="panel"><h2>Top 10 models</h2><div id="models-chart"></div></section></div>
<section class="panel wide"><div class="tools"><h2>Usage by provider</h2><small>Click a provider to filter the dashboard</small></div><div class="table-wrap"><table id="providers-table"></table></div></section>
<div class="insights" id="insights"></div>
<div class="grid equal"><section class="panel"><h2>Estimated cost breakdown</h2><div id="parts"></div></section><section class="panel"><h2>Top 8 projects</h2><div id="projects-chart"></div></section></div>
<section class="panel wide"><div class="tools"><h2>Usage by model</h2><small>Click a heading to sort</small></div><div class="table-wrap"><table id="models-table"></table></div></section>
<section class="panel wide"><div class="tools"><h2>Sessions</h2><input id="search" type="search" placeholder="Search sessions" aria-label="Search the sessions table only"></div><div class="table-wrap"><table id="sessions-table"></table></div><div class="tools" style="margin-top:14px"><small id="page-info"></small><div><button id="prev">←</button> <button id="next">→</button></div></div></section>
<details class="panel wide"><summary>Methodology, pricing and coverage</summary><div id="method"></div></details>
<footer id="footer"></footer></main>
<script id="snapshot" type="application/json">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('snapshot').textContent);const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const compact=n=>new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(n||0);const integer=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n||0);const usd=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n||0);const pct=n=>n==null?'—':(n*100).toFixed(1)+'%';
// Calendar dates use UTC arithmetic to avoid DST and browser-timezone shifts.
const shiftDate=(date,days)=>{const value=new Date(date+'T00:00:00Z');value.setUTCDate(value.getUTCDate()+days);return value.toISOString().slice(0,10)};
const shortDate=date=>new Date(date+'T00:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'});
const rangeLabel=range=>range?range.from+' – '+range.to:'';
const providerLabel=name=>({'Codex':'OpenAI · Codex','Claude':'Anthropic · Claude'}[name]||name);
let page=0,modelSort='cost',ascending=false;
const allDates=D.rows.map(r=>r.date).sort();
const today=D.as_of_date||D.generated.slice(0,10),first=allDates[0]||shiftDate(today,-6),last=allDates[allDates.length-1]||today;
function setPeriod(value){
    $('period').value=value;
    if(value==='custom')return;
    $('from').value=value==='all'?first:shiftDate(today,1-Number(value));
    $('to').value=value==='all'?last:today;
}
function selectedRange(){
    const from=$('from').value,to=$('to').value;
    if(!from||!to||from>to)return null;
    const days=Math.round((Date.parse(to+'T00:00:00Z')-Date.parse(from+'T00:00:00Z'))/86400000)+1;
    return {from,to,days};
}
function previousRange(range){return range&&$('period').value!=='all'?{from:shiftDate(range.from,-range.days),to:shiftDate(range.from,-1),days:range.days}:null}
for(const field of ['provider','model','project']){
    const values=[...new Set(D.rows.map(r=>r[field]))].sort();
    $(field).innerHTML='<option value="">All</option>'+values.map(v=>'<option value="'+esc(v)+'">'+esc(field==='provider'?providerLabel(v):v)+'</option>').join('');
}
setPeriod('7');
$('subtitle').textContent=D.device+' · '+new Date(D.generated).toLocaleString('en-US')+' · '+D.timezone;
if(D.demo)document.querySelector('.badge').textContent='Synthetic demo';
$('coverage').textContent=D.summary.files?`Found ${integer(D.summary.files)} local files. Codex: ${D.summary.traces_codex} traces across ${D.summary.registry_codex} registered threads. Missing traces are not estimated. Cloud chats are not included.`:'No local traces found. Run Codex or Claude Code on this device, or set --codex-dir / --claude-dir.';
function chosen(r,range=selectedRange()){
    return Boolean(range&&r.date>=range.from&&r.date<=range.to&&['provider','model','project'].every(f=>!$(f).value||r[f]===$(f).value)&&(!$('role').value||r.role===$('role').value));
}
function aggregate(rows){const a={requests:0,input:0,cached:0,write:0,output:0,total:0,cost:0,cost_high:0,unpriced:0,max_context:0,parts:[0,0,0,0,0],assumed:0,write_unknown:0,sessions:new Set()};for(const r of rows){for(const f of ['requests','input','cached','write','output','total','cost','cost_high','unpriced','assumed','write_unknown'])a[f]+=r[f]||0;a.max_context=Math.max(a.max_context,r.max_context||0);a.parts=a.parts.map((v,i)=>v+(r.parts?.[i]||0));a.sessions.add(r.session)}a.cache=a.input?a.cached/a.input:null;return a}
function groups(rows,field){const m=new Map();for(const r of rows){if(!m.has(r[field]))m.set(r[field],[]);m.get(r[field]).push(r)}return [...m].map(([name,rs])=>({name,...aggregate(rs)}))}
function cost(a){if(a.requests===a.unpriced)return '—';return usd(a.cost)+(a.cost_high-a.cost>.005?'–'+usd(a.cost_high):'')+(a.unpriced?' + ?':'')}
function bars(id,items,metric='cost'){const entries=[...items].sort((a,b)=>b[metric]-a[metric]);const max=Math.max(...entries.map(x=>x[metric]),1e-9);$(id).innerHTML=entries.length?entries.map((x,i)=>`<div class="barrow"><span class="barlabel" title="${esc(x.name)}">${esc(x.name)}</span><div class="bartrack"><div class="barfill" style="width:${Math.max(0,x[metric]/max*100)}%;opacity:${Math.max(.45,1-i*.06)}"></div></div><span class="barvalue">${metric==='cost'?cost(x):compact(x[metric])}</span></div>`).join(''):'<div class="empty">No data in the selected period</div>'}
function numericDelta(current,previous,format,points=false){
    if(current==null||previous==null)return 'No comparable value';
    const difference=current-previous;
    if(points)return `${difference>0?'+':''}${(difference*100).toFixed(1)} pp · prev ${format(previous)}`;
    if(previous===0)return current===0?'No change · prev '+format(previous):'No nonzero baseline · prev '+format(previous);
    return `${difference>0?'+':''}${(difference/Math.abs(previous)*100).toFixed(1)}% · prev ${format(previous)}`;
}
function usageDelta(current,previous,metric,range){
    if(!range)return '';
    if(!previous.requests)return 'No previous-period data';
    if(!current.requests)return 'No current-period data';
    if(metric==='cost'&&(current.unpriced||previous.unpriced||current.cost_high-current.cost>.005||previous.cost_high-previous.cost>.005))return 'Incomplete pricing · no delta';
    const value=a=>metric==='sessions'?a.sessions.size:metric==='cache'?a.cache:a[metric];
    return numericDelta(value(current),value(previous),metric==='cost'?usd:metric==='cache'?pct:metric==='requests'||metric==='sessions'?integer:compact,metric==='cache');
}
function comparisonNote(range,previous,rows,priorRows){
    if(!range)return 'Choose a valid date range: From must be on or before To.';
    if(!previous)return `${rangeLabel(range)} · All recorded history. Select a bounded period to compare.`;
    const observed=new Set(priorRows.map(r=>r.date)).size;
    const history=priorRows.length?`Previous period: ${observed} of ${previous.days} days have records.`:'No previous-period usage for these filters.';
    const current=rows.length?'':' No current-period usage for these filters.';
    return `${rangeLabel(range)} vs ${rangeLabel(previous)} · ${history}${current} Comparisons use observed records; missing days are not proof of zero usage.${range.to>=today?' Today is partial.':''}`;
}
function providersTable(rows,priorRows,previous){
    const now=new Map(groups(rows,'provider').map(g=>[g.name,g]));
    const before=new Map(groups(priorRows,'provider').map(g=>[g.name,g]));
    const names=[...new Set([...now.keys(),...before.keys()])].sort((a,b)=>(now.get(b)?.cost||0)-(now.get(a)?.cost||0));
    $('providers-table').innerHTML='<thead><tr><th>Provider</th><th>Requests</th><th>Tokens</th><th>Cache</th><th>Estimated cost</th><th>vs previous period</th></tr></thead><tbody>'+names.map(name=>{
        const a=now.get(name)||aggregate([]),b=before.get(name)||aggregate([]);
        return `<tr><td><button class="provider-button" data-provider="${esc(name)}">${esc(providerLabel(name))}</button></td><td>${integer(a.requests)}</td><td>${compact(a.total)}</td><td>${pct(a.cache)}</td><td>${cost(a)}</td><td>${esc(usageDelta(a,b,'cost',previous)||'—')}</td></tr>`;
    }).join('')+'</tbody>';
    if(!names.length)$('providers-table').innerHTML='<tbody><tr><td class="empty">No provider usage in these periods</td></tr></tbody>';
    document.querySelectorAll('[data-provider]').forEach(button=>button.onclick=()=>{$('provider').value=button.dataset.provider;page=0;render()});
}
function daily(rows,priorRows,metric,range,previous){
    if(!range){$('daily').innerHTML='<div class="empty">Choose a valid date range</div>';return}
    const current=new Map(groups(rows,'date').map(g=>[g.name,g])),prior=new Map(groups(priorRows,'date').map(g=>[g.name,g]));
    const compare=Boolean(previous&&priorRows.length),points=[];
    for(let i=0;i<range.days;i++){
        const date=shiftDate(range.from,i),priorDate=previous?shiftDate(previous.from,i):null;
        points.push({date,priorDate,current:current.get(date),previous:prior.get(priorDate)});
    }
    const usable=g=>g&&!(metric==='cost'&&g.requests===g.unpriced);
    const all=points.flatMap(p=>[p.current,compare?p.previous:null]).filter(usable);
    if(!all.length){$('daily').innerHTML='<div class="empty">No priced observations in these periods</div>';if(metric!=='cost')$('daily').textContent='No observations in these periods';return}
    const w=780,h=300,L=58,R=16,T=18,B=35,max=Math.max(...all.map(g=>g[metric]),1e-9),step=(w-L-R)/points.length;
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc($('chartmetric').selectedOptions[0].textContent)} by day">`;
    for(let i=0;i<4;i++){const y=T+(h-T-B)*i/3;svg+=`<line x1="${L}" x2="${w-R}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${L-8}" y="${y+4}" text-anchor="end" class="chart-text">${esc(metric==='cost'?usd(max*(1-i/3)):compact(max*(1-i/3)))}</text>`}
    points.forEach((p,i)=>{
        for(const [series,date,g] of [['current',p.date,p.current],...(compare?[['previous',p.priorDate,p.previous]]:[])]){
            if(!usable(g))continue;
            const width=compare?step*.36:step*.72,x=L+i*step+(series==='previous'?step*.54:step*.1),hh=(h-T-B)*g[metric]/max;
            svg+=`<rect data-series="${series}" x="${x}" y="${h-B-hh}" width="${Math.max(.2,width)}" height="${hh}" rx="2" fill="var(--${series==='previous'?'previous':'accent'})"><title>${esc(series+' · '+date+': '+(metric==='cost'?cost(g):integer(g[metric])))}</title></rect>`;
        }
        if(i%Math.max(1,Math.ceil(points.length/8))===0)svg+=`<text x="${L+(i+.5)*step}" y="${h-10}" text-anchor="middle" class="chart-text">${shortDate(p.date)}</text>`;
    });
    $('daily').innerHTML=svg+'</svg>'+`<div class="legend"><span><i class="dot"></i>Selected period</span>${compare?'<span><i class="dot previous"></i>Previous period, aligned by day</span>':''}</div><small>Missing bars mean no observations${metric==='cost'?' or unavailable prices':''}; today may be incomplete. Hover for the actual date and value.</small>`;
}
function modelsTable(rs){let gs=groups(rs,'model').sort((a,b)=>(a[modelSort]-b[modelSort])*(ascending?1:-1));$('models-table').innerHTML='<thead><tr><th>Model</th>'+[['requests','Requests'],['total','Tokens'],['output','Output'],['cached','Cache'],['cost','Cost, USD']].map(([f,l])=>`<th><button data-sort="${f}">${l}${modelSort===f?(ascending?' ↑':' ↓'):''}</button></th>`).join('')+'<th>Unpriced</th></tr></thead><tbody>'+gs.map(g=>`<tr><td>${esc(g.name)}</td><td>${integer(g.requests)}</td><td>${compact(g.total)}</td><td>${compact(g.output)}</td><td>${pct(g.cache)}</td><td>${cost(g)}</td><td>${g.unpriced||'—'}</td></tr>`).join('')+'</tbody>';document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{ascending=modelSort===b.dataset.sort?!ascending:false;modelSort=b.dataset.sort;modelsTable(rs)})}
function sessionsTable(rs){const search=$('search').value.toLowerCase();let gs=groups(rs,'session').filter(g=>(g.name+' '+(D.titles[g.name]||'')).toLowerCase().includes(search)).sort((a,b)=>b.cost-a.cost);page=Math.min(page,Math.max(0,Math.ceil(gs.length/25)-1));const show=gs.slice(page*25,(page+1)*25);$('sessions-table').innerHTML='<thead><tr><th>Session</th><th>Requests</th><th>Tokens</th><th>Cache</th><th>Max context</th><th>Cost, USD</th></tr></thead><tbody>'+show.map(g=>`<tr><td title="${esc(g.name)}">${esc(D.titles[g.name]||g.name.slice(0,22))}</td><td>${integer(g.requests)}</td><td>${compact(g.total)}</td><td>${pct(g.cache)}</td><td>${compact(g.max_context)}</td><td>${cost(g)}</td></tr>`).join('')+'</tbody>';$('page-info').textContent=`${gs.length? page*25+1:0}–${Math.min((page+1)*25,gs.length)} of ${gs.length} sessions`;$('prev').disabled=page===0;$('next').disabled=(page+1)*25>=gs.length}
function render(){
    const range=selectedRange(),previous=previousRange(range);
    const rs=D.rows.filter(r=>chosen(r,range)),priorRows=D.rows.filter(r=>chosen(r,previous));
    const a=aggregate(rs),b=aggregate(priorRows);
    const values=[
        ['API cost estimate',cost(a),'Token-based estimate, not an invoice',usageDelta(a,b,'cost',previous)],
        ['Input + output',compact(a.total),'Includes repeated cache reads',usageDelta(a,b,'total',previous)],
        ['Requests',integer(a.requests),'Deduplicated usage records',usageDelta(a,b,'requests',previous)],
        ['Sessions',integer(a.sessions.size),'Main threads and subagents',usageDelta(a,b,'sessions',previous)],
        ['Cached input',pct(a.cache),'Cache reads / total input',usageDelta(a,b,'cache',previous)],
    ];
    $('cards').innerHTML=values.map(([label,value,note,delta])=>`<div class="card"><label>${label}</label><div class="value">${value}</div><small>${note}</small>${delta?`<span class="delta">${esc(delta)}</span>`:''}</div>`).join('');
    $('comparison-note').textContent=comparisonNote(range,previous,rs,priorRows);
    $('money-note').textContent=`USD · Rates as of ${D.price_as_of}. ${a.unpriced?`${a.unpriced} requests have no matching rate; total is partial. `:''}${a.write_unknown?'Unknown cache TTL is shown as a range. ':''}API-equivalent estimate; subscription charges are not inferred.`;
    const metric=$('chartmetric').value;daily(rs,priorRows,metric,range,previous);
    bars('models-chart',groups(rs,'model').sort((a,b)=>b[metric]-a[metric]).slice(0,10),metric);
    bars('projects-chart',groups(rs,'project').sort((a,b)=>b[metric]-a[metric]).slice(0,8),metric);
    providersTable(rs,priorRows,previous);
const labels=['Uncached input','Cache reads','Cache writes','Output','Web search'];bars('parts',labels.map((name,i)=>({name,cost:a.parts[i],cost_high:a.parts[i],requests:1,unpriced:0})));const top=groups(rs,'session').sort((a,b)=>b.cost-a.cost).slice(0,10).reduce((s,g)=>s+g.cost,0);const sub=aggregate(rs.filter(r=>r.role==='subagent'));$('insights').innerHTML=`<div class="insight"><b>${pct(a.cost?top/a.cost:null)}</b>of estimated cost comes from the top 10 sessions</div><div class="insight"><b>${pct(a.cost?sub.cost/a.cost:null)}</b>of estimated cost comes from subagents</div><div class="insight"><b>${compact(a.requests?a.input/a.requests:0)}</b>average input tokens per request, including cache</div>`;modelsTable(rs);sessionsTable(rs);
}
for(const field of ['from','to','provider','model','project','role','chartmetric'])$(field).addEventListener('change',()=>{
    if(field==='from'||field==='to')$('period').value='custom';page=0;render();
});
$('period').addEventListener('change',()=>{setPeriod($('period').value);page=0;render()});
$('search').addEventListener('input',()=>{page=0;render()});
$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render()};
$('reset').onclick=()=>{setPeriod('7');for(const field of ['provider','model','project','role','search'])$(field).value='';page=0;render()};
$('method').innerHTML=`<p>The collector reads only local Codex sessions/archived_sessions, the state_*.sqlite registry and Claude projects. Missing traces are not reconstructed from cumulative counters. Claude message IDs and repeated Codex usage notifications are deduplicated. Counter resets preserve subsequent requests. Copied Claude requests are assigned to the first main trace in a stable order.</p><p>Claude input = uncached input + cache reads + cache creation. Codex input already includes cache. Reasoning is not added to output twice. Output token counts are taken from traces; some SDK traces may contain intermediate values, which limits estimate accuracy.</p><p>Cost includes uncached input, cache reads, 5m/1h cache writes and output, using recorded tier, speed, geography and long-context thresholds. Missing tiers default to Standard; missing geography defaults to global. Rates as of ${esc(D.price_as_of)}. Built-in rates are a current-rate scenario; historical rates can be supplied in local JSON with valid_from/valid_to. Explicitly recorded server-side web searches are added separately. Other service fees, discounts and taxes are not reconstructed.</p><p>Cost is a rate-based estimate, not a confirmed charge. Even Claude SDK total_cost_usd is an estimate. Found ${D.reports.length} such reports; they are not added to request totals to avoid double counting. Unknown models or modes have missing prices, not zero prices.</p><p>Unknown models or modes: ${esc(D.unknown_models.join(', ')||'none')}. Diagnostics: ${esc(JSON.stringify(D.quality))}.</p><p><a href="https://developers.openai.com/api/docs/pricing" target="_blank" rel="noreferrer">OpenAI pricing</a> · <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noreferrer">Claude pricing</a> · <a href="https://code.claude.com/docs/en/agent-sdk/cost-tracking" target="_blank" rel="noreferrer">SDK cost tracking limitations</a></p>`;
$('footer').textContent=`AISAD ${D.version} · Python standard library · Offline HTML · ${D.scan.cached_files||0} files from the local cache.`;render();
// Only the loopback watcher serves this endpoint; file:// snapshots never request a network resource.
if(['127.0.0.1','localhost'].includes(location.hostname))setInterval(async()=>{try{const r=await fetch('/status.json',{cache:'no-store'});if(r.ok&&(await r.json()).generated!==D.generated)location.reload()}catch{}},5000);
</script></body></html>'''

def render_html(snapshot):
    payload=json.dumps(snapshot,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return HTML.replace('__DATA__',payload)

def serve(output,port):
    output=Path(output).resolve()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route=self.path.split('?')[0]
            name={'/':'dashboard.html','/dashboard.html':'dashboard.html','/status.json':'status.json'}.get(route)
            if not name:self.send_error(404);return
            try:body=(output/name).read_bytes()
            except OSError:self.send_error(503);return
            self.send_response(200);self.send_header('Content-Type','application/json' if name.endswith('json') else 'text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server

def parser():
    p=argparse.ArgumentParser(description='Local Codex / Claude dashboard. Python 3.9+, no SSH, API keys, uploads or pip packages.')
    p.add_argument('command',nargs='?',choices=['dashboard','usage'],default='dashboard',help='Dashboard (default) or text/JSON usage without HTML')
    p.add_argument('--json',action='store_true',help='Usage: emit a structured JSON report to stdout')
    p.add_argument('--days',type=int,default=7,help='Usage: number of calendar days, default 7')
    p.add_argument('--all-time',action='store_true',help='Usage: include all recorded dates, without a comparison')
    p.add_argument('--from',dest='date_from',help='Usage: inclusive start date, YYYY-MM-DD')
    p.add_argument('--to',dest='date_to',help='Usage: inclusive end date, YYYY-MM-DD')
    p.add_argument('--provider',help='Usage: Codex/OpenAI or Claude/Anthropic')
    p.add_argument('--model',help='Usage: filter by model ID')
    p.add_argument('--project',help='Usage: filter by exact project name')
    p.add_argument('--role',choices=['main','subagent','review'],help='Usage: filter by agent role')
    p.add_argument('--include-requests',action='store_true',help='Usage JSON: include normalized per-request records; no transcripts')
    p.add_argument('--output',default=str(Path(__file__).resolve().parent/'output'),help='Directory for HTML and the local cache')
    p.add_argument('--home',help='Local profile root (for another user or tests)')
    p.add_argument('--codex-dir',help='Codex directory; defaults to CODEX_HOME or ~/.codex')
    p.add_argument('--claude-dir',help='Claude directory; defaults to CLAUDE_CONFIG_DIR or ~/.claude')
    p.add_argument('--cowork',action='store_true',help='Also read local Claude Cowork audit traces on macOS')
    p.add_argument('--timezone',help='IANA timezone, e.g. Europe/Amsterdam; defaults to the system timezone')
    p.add_argument('--prices',help='Local pricing JSON; --write-prices creates a template')
    p.add_argument('--include-titles',action='store_true',help='Include shortened session titles; IDs only by default')
    p.add_argument('--write-prices',metavar='FILE',help='Write the built-in price catalog and exit')
    p.add_argument('--watch',type=float,default=0,metavar='SECONDS',help='Rebuild every N seconds and serve on the loopback interface')
    p.add_argument('--port',type=int,default=0,help='Watcher port: 0 selects an available port')
    p.add_argument('--open',action='store_true',help='Open the HTML or local watcher in a browser')
    p.add_argument('--version',action='version',version=VERSION)
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    if args.watch and args.watch<5:raise SystemExit('--watch must be at least 5 seconds')
    if args.write_prices:atom_json(Path(args.write_prices),default_prices());print(args.write_prices);return
    output=Path(args.output).expanduser().resolve()
    if args.command=='usage':
        if args.watch or args.open:raise SystemExit('usage does not open a dashboard or run a watcher')
        snap=make_snapshot(args,dashboard=False,include_requests=args.include_requests)
        result=usage_report(snap,args)
        atom_json(output/'usage-report.json',result)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False) if args.json else usage_text(result))
        return
    snap=make_snapshot(args)
    def report(s):
        t=s['summary'];print(f"{s['generated']} | {t['requests']:,} requests | {t['sessions']} sessions | API estimate ${t['cost']:.2f}–${t['cost_high']:.2f} | unpriced {t['unpriced']} | parsed {s['scan'].get('parsed_files',0)}, cached {s['scan'].get('cached_files',0)}",flush=True)
    report(snap);print(str(output/'dashboard.html'),flush=True)
    if not args.watch:
        if args.open:webbrowser.open((output/'dashboard.html').as_uri())
        return
    server=serve(output,args.port);url=f'http://127.0.0.1:{server.server_address[1]}/';print(url+' (Ctrl+C to stop)',flush=True)
    if args.open:webbrowser.open(url)
    previous=source_fingerprint(args)
    try:
        while True:
            time.sleep(args.watch)
            try:
                current=source_fingerprint(args)
                if current==previous:continue
                report(make_snapshot(args));previous=current
            except (OSError,ValueError,KeyError,sqlite3.Error) as e:
                print('Refresh failed; previous HTML kept: '+str(e),file=sys.stderr,flush=True)
    except KeyboardInterrupt:print('\nStopped.',flush=True)
    finally:server.shutdown();server.server_close()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit(130)
    except (OSError,ValueError,KeyError,sqlite3.Error) as e:raise SystemExit('Error: '+str(e))
