#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local-only Codex / Claude usage. Python 3.9+, standard library, zero uploads.
Run: python3 agent_usage.py --open
"""
import argparse
import base64
import gzip
import html
import collections
import datetime as dt
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
import tempfile
import webbrowser
from urllib.parse import unquote

VERSION = '1.1.0'
PARSER_VERSION = 8
PRICE_DATE = '2026-09-05'
# USD / million tokens: uncached, read, 5m write, output. Claude 1h writes = 2x input.
# A versioned offline price snapshot, not provider invoices or guaranteed historical rates.
RATE_VALUES = {
 'gpt-6-astra': [10,1,12.5,50], 'gpt-5.6-sol': [4,.4,5,20],
 'gpt-5.5':[5,.5,0,30], 'gpt-5.4':[2.5,.25,0,15],
 'gpt-5-codex':[1.25,.125,0,10], 'gpt-5.1-codex':[1.25,.125,0,10],
 'gpt-5.1-codex-mini':[.25,.025,0,2], 'gpt-5.1-codex-max':[1.25,.125,0,10],
 'gpt-5.2-codex':[1.75,.175,0,14],
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
                 'https://platform.claude.com/docs/en/about-claude/pricing'] + [
    'https://developers.openai.com/api/docs/models/' + model for model in
    ['gpt-5-codex','gpt-5.1-codex','gpt-5.1-codex-mini','gpt-5.1-codex-max','gpt-5.2-codex']]

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
    return dict(as_of=PRICE_DATE, basis='current_rates', currency='USD', sources=PRICE_SOURCES, models=models)

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
        if isinstance(value,bool):return None
        if isinstance(value,(float,int)):
            value=float(value)/1000 if value>1e11 else float(value)
            if not math.isfinite(value):return None
            dt.datetime.fromtimestamp(value,dt.timezone.utc) # Validate the representable range.
            return value
        d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()
    except (ValueError,TypeError,OverflowError,OSError): return None

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

def read_jsonl(path,quality,locations=False):
    """Bound reads to the initial file size; tolerate an active/incomplete final record."""
    try:
        with path.open('rb') as f:
            end=os.fstat(f.fileno()).st_size
            line_number=0
            while f.tell()<end:
                offset=f.tell();line_number+=1
                line=f.readline(end-f.tell())
                if not line.strip():continue
                try:
                    obj=json.loads(line)
                    if isinstance(obj,dict):yield (obj,line_number,offset) if locations else obj
                except (ValueError,UnicodeError):
                    quality['partial_tail' if f.tell()==end and not line.endswith(b'\n') else 'malformed_lines']+=1
    except OSError:
        quality['unreadable_files']+=1

def evidence_id(*values):
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def trace_identifier(value):
    """Identifiers only; never use an arbitrary event field as display text."""
    value=str(value or '')
    return value if re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',value) else 'unknown'

class Evidence:
    """An allowlisted projection. Original content stays in the source file."""
    def __init__(self,path,provider):
        self.source=evidence_id(str(path.resolve()));self.provider=provider;self.events=[];self.occurrences=collections.Counter()
    def add(self,raw,line,offset,session,turn,kind,model=None,identity=None,**values):
        digest=evidence_id(raw)
        # Native call/message identifiers deduplicate copied and streamed items.
        if not identity:
            self.occurrences[(kind,digest)]+=1
            identity=[digest,self.occurrences[(kind,digest)]] if timestamp(raw.get('timestamp')) is None else [digest]
        owner=None if self.provider=='Claude' and not isinstance(identity,list) else session
        event=dict(id=evidence_id(self.provider,owner,kind,identity),session=session,
                   provider=self.provider,turn_id=turn or None,kind=kind,
                   ts=timestamp(raw.get('timestamp')),model=model,
                   evidence=[dict(source_id=self.source,line=line,byte_offset=offset,record_sha256=digest)],
                   **values)
        self.events.append(event);return event['id']
    def capture(self,raw,line,offset,session,turn,model):
        provider=self.provider
        p=raw.get('payload') if provider=='Codex' else raw
        if not isinstance(p,dict):return None
        typ=raw.get('type');sub=p.get('type')
        add=lambda kind,**kw:self.add(raw,line,offset,session,turn,kind,model,**kw)
        if provider=='Codex':
            if typ=='session_meta':return add('session_metadata')
            if typ=='turn_context':return add('turn_context')
            if typ in ('compacted','context_compacted') or (typ=='event_msg' and sub in ('context_compacted','compaction')):
                return add('compaction')
            if typ=='event_msg':
                kind={'task_started':'turn_started','task_complete':'turn_completed',
                      'task_completed':'turn_completed','turn_aborted':'turn_aborted',
                      'error':'error','token_count':'usage'}.get(sub)
                if kind:
                    info=p.get('info') or {};limit=info.get('model_context_window') if isinstance(info,dict) else None
                    return add(kind,context_limit=limit if isinstance(limit,int) and not isinstance(limit,bool) and limit>0 else None)
            if typ!='response_item':return None
            if sub in ('function_call','custom_tool_call'):
                call=trace_identifier(p.get('call_id'))
                return add('tool_call',identity=call if call!='unknown' else None,call_id=call,tool=trace_identifier(p.get('name')))
            if sub in ('function_call_output','custom_tool_call_output'):
                call=trace_identifier(p.get('call_id'));value=p.get('output')
                size=None if value is None else len((value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,separators=(',',':'))).encode())
                return add('tool_result',identity=call if call!='unknown' else None,call_id=call,result_bytes=size,
                           error=p.get('is_error') if isinstance(p.get('is_error'),bool) else None)
            if sub=='message':return add('message',role=p.get('role') if p.get('role') in ('user','assistant','system','developer') else 'unknown')
        else:
            if typ=='system' and p.get('subtype')=='compact_boundary':return add('compaction')
            if typ=='result':return add('run_result',error=p.get('is_error') if isinstance(p.get('is_error'),bool) else None)
            m=p.get('message') or {}
            if not isinstance(m,dict):return None
            mid=m.get('id') or p.get('uuid');content=m.get('content')
            if typ not in ('assistant','user'):return None
            if isinstance(content,(str,list)):
                add('message',identity=mid,role=typ)
            for item in content if isinstance(content,list) else []:
                if not isinstance(item,dict):continue
                if item.get('type')=='tool_use':
                    call=trace_identifier(item.get('id'))
                    add('tool_call',identity=call if call!='unknown' else None,call_id=call,tool=trace_identifier(item.get('name')))
                elif item.get('type')=='tool_result':
                    call=trace_identifier(item.get('tool_use_id'));value=item.get('content')
                    size=None if value is None else len((value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,separators=(',',':'))).encode())
                    add('tool_result',identity=call if call!='unknown' else None,call_id=call,result_bytes=size,
                        error=item.get('is_error') if isinstance(item.get('is_error'),bool) else None)
            if typ=='assistant' and m.get('usage'):return add('usage',identity=mid)
        return None

class TraceSignals:
    """Keep sizes and counts, never tool payloads, arguments or message text."""
    def __init__(self):
        self.pending=collections.Counter();self.calls={};self.results=set();self.observed=False
    def call(self,key,name):
        if not key or key in self.calls:return
        name=str(name or '').lower()
        self.calls[key]='mcp' if name.startswith('mcp__') or '.mcp__' in name else 'tool'
        self.pending['tool_calls']+=1
        if re.search(r'(^|[_.])(wait|poll|status|get_status|write_stdin)([_.]|$)',name):self.pending['poll_calls']+=1
    def result(self,key,content,error=False):
        if not key or key in self.results:return
        self.results.add(key)
        size=len((content if isinstance(content,str) else json.dumps(content,ensure_ascii=False,separators=(',',':'))).encode('utf-8'))
        self.pending['tool_results']+=1;self.pending['tool_bytes']+=size
        self.pending['max_tool_bytes']=max(self.pending['max_tool_bytes'],size)
        self.pending['tool_errors']+=bool(error)
        if size>=40000:self.pending['large_results']+=1
        if self.calls.get(key)=='mcp':
            self.pending['mcp_results']+=1;self.pending['mcp_bytes']+=size
            self.pending['max_mcp_bytes']=max(self.pending['max_mcp_bytes'],size)
    def take(self):
        value=dict(self.pending);self.pending.clear();return value

def parent_thread(source):
    if not isinstance(source,dict):return None
    for key in ['parent_thread_id','parent_session_id']:
        if isinstance(source.get(key),str):return 'Codex:'+source[key]
    for value in source.values():
        if isinstance(value,dict):
            found=parent_thread(value)
            if found:return found
    return None

def parse_codex(path,include_titles=False):
    q=collections.Counter();sessions={};requests=[];seen={};sid=None;model='unknown';effort='unknown';tier='unknown';project='unknown';role='main';turn=''
    signals=TraceSignals();parent=None;fork_owner=None;fork_live=False
    observed={};evidence=Evidence(path,'Codex')
    for x,line,offset in read_jsonl(path,q,locations=True):
        p=x.get('payload') or {}
        if not isinstance(p,dict):continue
        typ=x.get('type');ts=timestamp(x.get('timestamp'))
        if typ=='session_meta':
            next_sid=str(p.get('id') or p.get('session_id') or path.stem)
            is_fork_owner=sid is None and bool(p.get('forked_from_id'))
            if fork_live and next_sid!=fork_owner['id']:
                q['codex_foreign_fork_metadata']+=1;continue
            # Resumes/compactions append session_meta without a model. They do not
            # revoke the last explicit turn_context for the same session.
            if next_sid!=sid:
                model='unknown';effort='unknown';tier='unknown';turn='';signals=TraceSignals()
            sid=next_sid
            project=project_name(p.get('cwd'));model=p.get('model') or model
            role='subagent' if 'subagent' in json.dumps(p.get('source',{})).lower() or p.get('agent_path','/root') not in ['/root',None,''] else 'main'
            parent=parent_thread(p.get('source'))
            sessions.setdefault(sid,dict(id='Codex:'+sid,provider='Codex',role=role,project=project,title=sid[:12],trace=True,parent_session=parent))
            if is_fork_owner:
                fork_owner=dict(id=sid,project=project,role=role,parent=parent,session=dict(sessions[sid]))
        if not sid:continue
        if typ=='response_item':
            signals.observed=True;observed[sid]=True
            if p.get('type') in ['function_call','custom_tool_call']:signals.call(p.get('call_id'),p.get('name'))
            if p.get('type') in ['function_call_output','custom_tool_call_output']:signals.result(p.get('call_id'),p.get('output',''))
            if p.get('type')=='message' and p.get('role')=='user':signals.pending['user_messages']+=1
        if typ=='turn_context':
            if fork_owner and not fork_live:
                # Fork prefixes replay parent history with rewritten timestamps
                # and parent session_meta records. The first local turn_context
                # ends that prefix; only subsequent usage belongs to this fork.
                q['codex_fork_history_requests']+=len(requests)
                requests=[];seen={};evidence.events=[]
                if not turn or turn!=p.get('turn_id'):signals=TraceSignals()
                sid=fork_owner['id'];project=fork_owner['project'];role=fork_owner['role'];parent=fork_owner['parent']
                sessions={sid:fork_owner['session']}
                model='unknown';effort='unknown';tier='unknown';turn='';fork_live=True
                observed={sid:True} if signals.observed else {}
            model=p.get('model',model);effort=p.get('effort') or p.get('reasoning_effort') or effort
            tier=p.get('service_tier') or tier;turn=p.get('turn_id') or turn
            if p.get('cwd'):project=project_name(p['cwd'])
        if typ=='event_msg' and p.get('type')=='task_started':
            turn=p.get('turn_id') or turn
            if fork_owner and not fork_live:signals=TraceSignals();observed.pop(sid,None)
        event_id=evidence.capture(x,line,offset,'Codex:'+sid,turn,model)
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
                             role=role,ts=ts,web_searches=None,parent_session=parent,turn_id=turn or None,
                             trace_stats=signals.take(),event_ids=[event_id] if event_id else [],**usage))
    if fork_owner and not fork_live:
        q['codex_fork_without_turn_context']+=1
    for row in requests:row['trace_observed']=observed.get(row['session'].split(':',1)[-1],False)
    return dict(sessions=list(sessions.values()),requests=requests,reports=[],events=evidence.events,quality=dict(q))

def parse_claude(path,include_titles=False):
    q=collections.Counter();requests=[];sessions={};reports=[]
    signals=TraceSignals();turn=None
    sub='subagents' in path.parts
    sid=(path.parent.parent.name+'/'+path.stem) if sub else path.parent.name if path.name=='audit.jsonl' else path.stem
    skey='Claude:'+sid;project='unknown';role='subagent' if sub else 'main';title=sid[:12]
    evidence=Evidence(path,'Claude')
    for x,line,offset in read_jsonl(path,q,locations=True):
        ts=timestamp(x.get('timestamp'));typ=x.get('type')
        if x.get('cwd'):project=project_name(x['cwd'])
        if typ=='result' and isinstance(x.get('total_cost_usd'),(int,float)) and ts is not None:
            # Keep result reports separate: SDK scopes include children and may be cumulative across turns.
            reports.append(dict(id=str(x.get('uuid') or hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()),
                                session=skey,ts=ts,reported_usd=x['total_cost_usd']))
        m=x.get('message') or {}
        if not isinstance(m,dict):continue
        content=m.get('content')
        if isinstance(content,list):
            signals.observed=True
            tool_result=False
            for item in content:
                if not isinstance(item,dict):continue
                if item.get('type')=='tool_use':signals.call(item.get('id'),item.get('name'))
                if item.get('type')=='tool_result':
                    tool_result=True;signals.result(item.get('tool_use_id'),item.get('content',''),item.get('is_error',False))
            if typ=='user' and not tool_result and not x.get('isMeta'):
                signals.pending['user_messages']+=1;turn=x.get('uuid') or (str(ts) if ts is not None else None)
        elif isinstance(content,str) and typ=='user' and not x.get('isMeta'):
            signals.observed=True;signals.pending['user_messages']+=1;turn=x.get('uuid') or (str(ts) if ts is not None else None)
        event_id=evidence.capture(x,line,offset,skey,turn,m.get('model'))
        # A session with only user/tool/lifecycle events is still observable.
        sessions[skey]=dict(id=skey,provider='Claude',role=role,project=project,title=title,trace=True,parent_session='Claude:'+path.parent.parent.name if sub else None)
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
        sessions[skey]=dict(id=skey,provider='Claude',role=role,project=project,title=title,trace=True,parent_session='Claude:'+path.parent.parent.name if sub else None)
        searches=(u.get('server_tool_use') or {}).get('web_search_requests')
        try: searches=None if searches is None else number(searches)
        except (ValueError,TypeError): searches=None
        requests.append(dict(id='cl:'+str(mid),session=skey,provider='Claude',model=m.get('model'),
                             effort=x.get('effort') or 'unknown',tier=u.get('service_tier') or 'unknown',
                             speed=u.get('speed') or 'unknown',geo=u.get('inference_geo') or 'unknown',
                             project=project,role=role,ts=ts,web_searches=searches,turn_id=turn,
                             parent_session='Claude:'+path.parent.parent.name if sub else None,
                             trace_stats=signals.take(),event_ids=[event_id] if event_id else [],**usage))
    for row in requests:row['trace_observed']=signals.observed
    return dict(sessions=list(sessions.values()),requests=requests,reports=reports,events=evidence.events,quality=dict(q))

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
        result['trace_observed']=old.get('trace_observed',False) or r.get('trace_observed',False)
        result['trace_stats']={key:max(old.get('trace_stats',{}).get(key,0),r.get('trace_stats',{}).get(key,0))
                               for key in set(old.get('trace_stats',{}))|set(r.get('trace_stats',{}))}
        searches=[v for v in [old.get('web_searches'),r.get('web_searches')] if v is not None]
        result['web_searches']=max(searches) if searches else None
        result['event_ids']=sorted(set(old.get('event_ids',[]))|set(r.get('event_ids',[])))
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

def request_statistics(rows,managed_sessions=()):
    """Measured per-request context, timing and tool counters; no advice or scenarios."""
    sessions=collections.defaultdict(list);children=collections.defaultdict(set)
    for row in rows:
        sessions[row['session']].append(row)
        if row.get('parent_session'):children[row['parent_session']].add(row['session'])
    managed=set(managed_sessions);queue=collections.deque(managed)
    while queue:
        for child in children[queue.popleft()]-managed:managed.add(child);queue.append(child)
    records=[]
    for session,observations in sessions.items():
        observations.sort(key=lambda r:(r['ts'],r['id']))
        previous=None
        for index,row in enumerate(observations):
            row['pool']='managed' if session in managed else 'interactive'
            fields=['id','session','provider','model','project','role','date','ts','input','output','cached','write','uncached','cost','cost_high','pool']
            record={key:row[key] for key in fields}
            record.update(step=index+1,gap_seconds=max(0.,row['ts']-previous['ts']) if previous else None,
                trace_stats=row.get('trace_stats',{}),trace_observed=row.get('trace_observed',False),
                parts=row.get('cost_parts'),effort=row.get('effort','unknown'),
                price_status=row.get('price_status','unknown_model' if row['cost'] is None else 'priced'),
                event_ids=row.get('event_ids',[]),turn_id=row.get('turn_id'),parent_session=row.get('parent_session'))
            records.append(record);previous=row
    return records

def telemetry_summary(records):
    stats=collections.Counter()
    for row in records:
        for key,value in row.get('trace_stats',{}).items():
            if key.startswith('max_'):stats[key]=max(stats[key],value)
            else:stats[key]+=value
    return dict(trace_records=sum(r['trace_observed'] for r in records),
                total_records=len(records),tool_stats=dict(stats))

EVIDENCE_SCHEMA = 1
MEASUREMENT_BASIS = {
    'tokens': {'kind':'measured','basis':'Usage fields recorded in local traces; coverage may be incomplete.'},
    'requests': {'kind':'measured','basis':'Deduplicated usage observations, not independently verified network requests.'},
    'cost': {'kind':'estimated','basis':'Recorded usage multiplied by the selected offline price catalog.'},
    'tool_bytes': {'kind':'measured','basis':'UTF-8 bytes of the logged result, or compact JSON for structured results; not billed tokens.'},
    'elapsed': {'kind':'measured','basis':'Time between first and last timestamped observations; includes idle time.'},
    'active_time': {'kind':'unavailable','basis':'Local traces do not establish complete active/idle intervals.'},
    'context_composition': {'kind':'unavailable','basis':'No complete model-input snapshots are recorded by this collector.'},
    'tool_definitions': {'kind':'unavailable','basis':'Installed tools do not establish which definitions reached a request.'},
    'repeated_tool_input': {'kind':'unavailable','basis':'A logged tool result does not prove later inclusion in model input.'},
    'invoice': {'kind':'unavailable','basis':'Session traces do not establish subscription charges or invoices.'},
}

def merge_events(events):
    merged={}
    for event in events:
        old=merged.get(event['id'])
        if old is None:merged[event['id']]=dict(event);continue
        refs={json.dumps(ref,sort_keys=True):ref for ref in old['evidence']+event['evidence']}
        old['evidence']=list(refs.values())
        if event.get('result_bytes') is not None and (old.get('result_bytes') is None or event['result_bytes']>old['result_bytes']):old['result_bytes']=event['result_bytes']
        if event.get('error') is True:old['error']=True
    return sorted(merged.values(),key=lambda e:(e['ts'] is None,e['ts'] or 0,e['evidence'][0]['line'],e['id']))

def recorded_cost(rows):
    missing=sum(r['cost'] is None for r in rows)
    return dict(known_cost_usd=sum(r['cost'] or 0 for r in rows),
                estimated_cost_usd=sum(r['cost'] or 0 for r in rows) if len(rows)>missing else None,
                estimated_cost_high_usd=sum(r['cost_high'] or 0 for r in rows) if len(rows)>missing else None,
                unpriced_requests=missing,requests=len(rows),
                input_tokens=sum(r['input'] for r in rows),output_tokens=sum(r['output'] for r in rows))

def session_evidence(events,requests,sessions):
    by_session=collections.defaultdict(list);observations=collections.defaultdict(list)
    for event in events:by_session[event['session']].append(event)
    children=collections.defaultdict(set);parents={}
    for sid,meta in sessions.items():
        if meta.get('parent_session') and meta['parent_session']!=sid:
            parents[sid]=meta['parent_session'];children[meta['parent_session']].add(sid)
    for row in requests:
        observations[row['session']].append(row)
        if row.get('parent_session') and row['parent_session']!=row['session']:
            parents[row['session']]=row['parent_session'];children[row['parent_session']].add(row['session'])
    details=[];calls=[];turns=[]
    for sid in sorted(set(by_session)|set(observations)):
        local=by_session[sid];rows=sorted(observations[sid],key=lambda r:(r['ts'],r['id']))
        meta=sessions.get(sid,{})
        stamps=[e['ts'] for e in local if e['ts'] is not None]+[r['ts'] for r in rows]
        starts={};ends={}
        for event in local:
            key=event.get('call_id') if event.get('call_id') not in (None,'unknown') else event['id']
            if event['kind']=='tool_call':starts.setdefault(key,event)
            if event['kind']=='tool_result':ends.setdefault(key,event)
        own_calls=[]
        for call in sorted(set(starts)|set(ends)):
            start=starts.get(call);end=ends.get(call)
            first=start['ts'] if start else None;last=end['ts'] if end else None
            own_calls.append(dict(id=evidence_id(sid,call),session=sid,call_id=call,
                turn_id=(start or end).get('turn_id'),tool=(start or {}).get('tool','unknown'),
                started_at=first,finished_at=last,
                observed_latency_seconds=last-first if first is not None and last is not None and last>=first else None,
                result_bytes=end.get('result_bytes') if end else None,error=end.get('error') if end else None,
                status='result_recorded' if end else 'unknown',
                event_ids=[e['id'] for e in (start,end) if e]))
        calls.extend(own_calls)
        local_turns=collections.defaultdict(list)
        for event in local:
            if event.get('turn_id'):local_turns[event['turn_id']].append(event)
        for turn,items in local_turns.items():
            times=[e['ts'] for e in items if e['ts'] is not None]
            turns.append(dict(id=evidence_id(sid,turn),session=sid,turn_id=turn,
                              first_seen=min(times) if times else None,last_seen=max(times) if times else None,
                              event_ids=[e['id'] for e in items]))
        # Reachable sets prevent both duplicate descendants and malformed cycles.
        tree={sid};queue=collections.deque([sid])
        while queue:
            for child in children[queue.popleft()]-tree:tree.add(child);queue.append(child)
        tree_rows=[r for child in tree for r in observations[child]]
        latest=rows[-1] if rows else None
        compact=[e for e in local if e['kind']=='compaction']
        after=not latest or bool(compact and any(e['ts'] is None or e['ts']>=latest['ts'] for e in compact))
        lifecycle=[e for e in local if e['kind'] in ('turn_started','turn_completed','turn_aborted','run_result')]
        details.append(dict(id=sid,provider=meta.get('provider',sid.split(':')[0]),project=meta.get('project','unknown'),
            role=meta.get('role','main'),parent_session=parents.get(sid),children=sorted(children[sid]),
            first_seen=min(stamps) if stamps else None,last_seen=max(stamps) if stamps else None,
            elapsed_seconds=max(stamps)-min(stamps) if stamps else None,active_seconds=None,status='unknown',
            last_recorded_lifecycle=lifecycle[-1]['kind'] if lifecycle else None,
            own=recorded_cost(rows),tree=recorded_cost(tree_rows),tree_sessions=sorted(tree),
            observed_dates=sorted({e['date'] for e in local if e.get('date')}),
            event_count=len(local),turn_count=len(local_turns),tool_calls=len(starts),tool_results=len(ends),
            result_bytes=sum(c['result_bytes'] or 0 for c in own_calls),
            tool_errors=sum(c['error'] is True for c in own_calls),compactions=len(compact),
            max_request_input_tokens=max((r['input'] for r in rows),default=None),
            latest_request_input_tokens=latest['input'] if latest else None,
            latest_usage_at=latest['ts'] if latest else None,context_since_compaction='unavailable' if after else 'last_recorded_input',
            usage_event_ids=sorted({event for r in rows for event in r.get('event_ids',[])})))
    return details,calls,turns

def write_event_store(path,sources,events,requests,sessions,calls,turns,catalog,generated):
    """Replace derived tables in one transaction. Readers see a coherent snapshot."""
    connection=sqlite3.connect(path,timeout=30)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        version=connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,EVIDENCE_SCHEMA):raise ValueError('Unsupported evidence database schema; preserve this file and use a compatible version.')
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_files (id TEXT PRIMARY KEY,path TEXT NOT NULL,size INTEGER,mtime_ns INTEGER);
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY,parent_session TEXT,provider TEXT,project TEXT,record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),turn_id TEXT,kind TEXT NOT NULL,ts REAL,record_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_session_time ON events(session_id,ts);
        CREATE TABLE IF NOT EXISTS event_sources (event_id TEXT REFERENCES events(id),source_id TEXT REFERENCES source_files(id),line INTEGER,byte_offset INTEGER,record_sha256 TEXT,PRIMARY KEY(event_id,source_id,line));
        CREATE TABLE IF NOT EXISTS usage_observations (id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(id),turn_id TEXT,ts REAL,model TEXT,input_tokens INTEGER,output_tokens INTEGER,cache_read_tokens INTEGER,cache_write_tokens INTEGER,estimated_cost_usd REAL,record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observation_events (observation_id TEXT REFERENCES usage_observations(id),event_id TEXT REFERENCES events(id),PRIMARY KEY(observation_id,event_id));
        CREATE TABLE IF NOT EXISTS tool_calls (id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(id),tool TEXT,result_bytes INTEGER,record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(id),turn_id TEXT,record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS context_snapshots (observation_id TEXT PRIMARY KEY REFERENCES usage_observations(id),input_tokens INTEGER,cache_read_tokens INTEGER,context_limit INTEGER,composition TEXT NOT NULL);
        ''')
        encode=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        with connection:
            for table in ('observation_events','context_snapshots','usage_observations','event_sources','tool_calls','turns','events','sessions','source_files','metadata'):
                connection.execute('DELETE FROM '+table)
            connection.executemany('INSERT INTO source_files VALUES (?,?,?,?)',[(s['id'],s['path'],s['size'],s['mtime_ns']) for s in sources])
            connection.executemany('INSERT INTO sessions VALUES (?,?,?,?,?)',[(s['id'],s['parent_session'],s['provider'],s['project'],encode(s)) for s in sessions])
            connection.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',[(e['id'],e['session'],e.get('turn_id'),e['kind'],e['ts'],encode(e)) for e in events])
            connection.executemany('INSERT INTO event_sources VALUES (?,?,?,?,?)',[(e['id'],r['source_id'],r['line'],r['byte_offset'],r['record_sha256']) for e in events for r in e['evidence']])
            connection.executemany('INSERT INTO usage_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',[(r['id'],r['session'],r.get('turn_id'),r['ts'],r['model'],r['input'],r['output'],r['cached'],r['write'],r['cost'],encode(r)) for r in requests])
            event_map={e['id']:e for e in events}
            connection.executemany('INSERT INTO observation_events VALUES (?,?)',[(r['id'],event) for r in requests for event in r.get('event_ids',[]) if event in event_map])
            connection.executemany('INSERT INTO context_snapshots VALUES (?,?,?,?,?)',[(r['id'],r['input'],r['cached'],next((event_map[e].get('context_limit') for e in r.get('event_ids',[]) if e in event_map and event_map[e].get('context_limit')),None),'unavailable') for r in requests])
            connection.executemany('INSERT INTO tool_calls VALUES (?,?,?,?,?)',[(c['id'],c['session'],c['tool'],c['result_bytes'],encode(c)) for c in calls])
            connection.executemany('INSERT INTO turns VALUES (?,?,?,?)',[(t['id'],t['session'],t['turn_id'],encode(t)) for t in turns])
            connection.executemany('INSERT INTO metadata VALUES (?,?)',[(k,encode(v)) for k,v in dict(schema_version=EVIDENCE_SCHEMA,version=VERSION,generated=generated,price_catalog=catalog,measurement_basis=MEASUREMENT_BASIS).items()])
            connection.execute('PRAGMA user_version='+str(EVIDENCE_SCHEMA))
    finally:connection.close()

def budget_status(records,budget):
    if budget is not None and (not math.isfinite(budget) or budget<=0):raise ValueError('Budgets must be finite positive USD amounts')
    missing=sum(r['cost'] is None for r in records);known=sum(r['cost'] or 0 for r in records);high=sum(r['cost_high'] or 0 for r in records)
    ratio=known/budget if budget and records else None
    level=max((n for n in (50,80,100) if ratio is not None and ratio*100>=n),default=0)
    return dict(budget_usd=budget,known_cost_usd=known,cost_high_usd=high,unpriced_requests=missing,
        observed_requests=len(records),
        used_percent=ratio*100 if ratio is not None else None,nudge_percent=level,
        pricing_complete=not missing and math.isclose(known,high,abs_tol=1e-9),
        status='not_configured' if budget is None else 'no_data' if not records else 'partial_pricing' if missing else 'range' if high-known>1e-9 else 'over_budget' if level==100 else 'attention' if level else 'within_budget')

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

def grok_usage(args, quality):
    """Grok persists completed-turn summaries, not per-request context sizes.

    Keep its reported cost separate: repricing aggregated inputs would apply
    long-context thresholds incorrectly and Build model aliases are not API IDs.
    """
    home=Path(args.home).expanduser().resolve() if args.home else Path.home()
    root=home/'.grok/sessions';records={}
    for path in sorted(root.rglob('updates.jsonl')) if root.is_dir() else []:
        for item in read_jsonl(path,quality):
            params=item.get('params') or {};update=params.get('update') or {}
            if not isinstance(update,dict) or update.get('sessionUpdate')!='turn_completed':continue
            usage=update.get('usage');sid=params.get('sessionId');pid=update.get('prompt_id');ts=timestamp(item.get('timestamp'))
            if not isinstance(usage,dict) or not sid or not pid or ts is None:continue
            try:
                values={key:number(usage.get(field)) for key,field in [('input','inputTokens'),('cached','cachedReadTokens'),('output','outputTokens'),('model_calls','modelCalls')]}
                ticks=usage.get('costUsdTicks');ticks=None if ticks is None else number(ticks)
            except (ValueError,TypeError,OverflowError):quality['grok_invalid_usage']+=1;continue
            records[(str(sid),str(pid))]=dict(session='Grok:'+str(sid),turn_id=str(pid),ts=ts,
                date=dt.datetime.fromtimestamp(ts,dt.timezone.utc).astimezone(report_timezone(args.timezone)).date().isoformat(),
                project=project_name(unquote(path.parent.parent.name)),models=sorted(str(m) for m in (usage.get('modelUsage') or {})),
                reported_cost_ticks=ticks,reported_cost_usd=ticks/1e10 if ticks is not None else None,
                incomplete=bool(usage.get('usageIsIncomplete')) or ticks is None,**values)
    return list(records.values())

def grok_totals(records):
    return dict(turns=len(records),sessions=len({r['session'] for r in records}),
                **{key:sum(r[key] for r in records) for key in ['input','cached','output','model_calls']},
                known_reported_cost_usd=sum(r['reported_cost_ticks'] or 0 for r in records)/1e10,
                incomplete_turns=sum(r['incomplete'] for r in records),basis='provider_reported_turn_totals',
                included_in_api_estimate=False)

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

def make_snapshot(args, dashboard=True, include_requests=False):
    output=Path(args.output).expanduser().resolve();output.mkdir(parents=True,exist_ok=True)
    catalog=load_prices(args.prices)
    q=collections.Counter();stats=collections.Counter();codex,files,roots=discover(args)
    sessions=registry(codex,args.include_titles,q);rows=[];reports={};events=[];source_files=[]
    cache=ParseCache(output/'parse-cache.sqlite')
    try:
        for provider,path in files:
            try:
                st=path.stat();r=cache.parse(provider,path,args.include_titles,stats)
            except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):q['failed_files']+=1;continue
            q.update(r['quality']);rows.extend(r['requests'])
            source_files.append(dict(id=evidence_id(str(path.resolve())),path=str(path),size=st.st_size,mtime_ns=st.st_mtime_ns))
            events.extend(r.get('events',[]))
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
    request_stats=request_statistics(rows,getattr(args,'managed_session',[]))
    events=merge_events(events)
    event_refs={e['id']:e['evidence'] for e in events}
    for record in request_stats:
        record['evidence']=[ref for event in record['event_ids'] for ref in event_refs.get(event,[])]
    for event in events:
        event['date']=dt.datetime.fromtimestamp(event['ts'],dt.timezone.utc).astimezone(tz).date().isoformat() if event['ts'] is not None else None
    session_details,tool_calls,turns=session_evidence(events,rows,sessions)
    # Dashboard rows: one date × model × session × project × role, preserving filter correctness.
    grouped={}
    for r in rows:
        key=(r['date'],r['provider'],r['model'],r['session'],r['project'],r['role'])
        if key not in grouped:grouped[key]=dict(zip(['date','provider','model','session','project','role'],key),requests=0,input=0,cached=0,write=0,output=0,total=0,cost=0.,cost_high=0.,unpriced=0,max_context=0,parts=[0.]*5,assumed=0,write_unknown=0)
        g=grouped[key];g['requests']+=1
        g['pool']=r['pool']
        for f in ['input','cached','write','output','total','write_unknown']:g[f]+=r[f]
        g['max_context']=max(g['max_context'],r['input'])
        g['assumed']+=bool(r['assumptions'])
        if r['cost'] is None:g['unpriced']+=1
        else:
            g['cost']+=r['cost'];g['cost_high']+=r['cost_high']
            g['parts']=[a+b for a,b in zip(g['parts'],r['cost_parts'])]
    measured={r['session'] for r in rows};traceids={s['id'] for s in sessions.values() if s['trace'] and s['provider']=='Codex'}
    q['registry_without_trace']=sum(not s['trace'] for s in sessions.values() if s['provider']=='Codex')
    history={}
    for provider in ['Claude','Codex']:
        dates=[r['date'] for r in rows if r['provider']==provider]
        history[provider]=dict(first_date=min(dates) if dates else None,last_date=max(dates) if dates else None,
                               observed_days=len(set(dates)))
    grok_records=grok_usage(args,q)
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
                  price_basis=catalog.get('basis','custom_rates'),history_coverage=history,grok_records=grok_records,
                  sources=[dict(provider=p,exists=root.is_dir(),path=str(root)) for p,root in roots],
                  summary=summary,quality=dict(q),scan=dict(stats),rows=list(grouped.values()),
                  titles={s['id']:s['title'] for s in sessions.values() if s['id'] in measured} if args.include_titles else {},
                  unknown_models=sorted({r['model'] for r in rows if r['cost'] is None}),
                  reports=list(reports.values()),request_stats=request_stats,
                  evidence_schema_version=EVIDENCE_SCHEMA,measurement_basis=MEASUREMENT_BASIS,
                  session_details=session_details,
                  budgets=dict(interactive=getattr(args,'budget',None),managed=getattr(args,'managed_budget',None)))
    write_event_store(output/'sessions.sqlite',source_files,events,rows,session_details,tool_calls,turns,catalog,snapshot['generated'])
    # Private evidence stays local. Requests are normalized fields only.
    atom_json(output/'usage.json',dict(snapshot,requests=rows,registry=list(sessions.values())))
    atom_json(output/'prices-used.json',catalog)
    if dashboard:
        previews=collections.defaultdict(lambda:collections.deque(maxlen=200))
        for event in events:previews[event['session']].append(event)
        snapshot['event_previews']={sid:list(items) for sid,items in previews.items()}
        public={k:v for k,v in snapshot.items() if k!='sources'}
        body=render_html(public)
        atom_write(output/'dashboard.html',body.encode())
        atom_json(output/'status.json',{'generated':snapshot['generated'],'version':VERSION})
    if getattr(args,'include_events',False) or args.command in ('collect','sessions','session'):
        snapshot.update(events=events,tool_calls=tool_calls,turns=turns,source_files=source_files)
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
    result['uncached_input_tokens']=result['input_tokens']-result['cached_input_tokens']-result['cache_write_tokens']
    result['cost_parts_high_usd']=dict(result['cost_parts_usd'])
    result['cost_parts_high_usd']['cache_writes']+=max(0.,high-known)
    return result

def pricing_coverage(records):
    """Count unpriced observations without inventing a model, rate or zero cost."""
    groups={}
    for row in records:
        if row['cost'] is not None:continue
        status=row.get('price_status','unknown_model')
        reason=('missing_model' if row['model']=='unknown' else
                'internal_model' if row['model']=='codex-auto-review' and status=='unknown_model' else status)
        key=(row['provider'],row['model'],reason)
        group=groups.setdefault(key,dict(provider=key[0],model=key[1],reason=key[2],requests=0,
                                         input_tokens=0,output_tokens=0))
        group['requests']+=1
        group['input_tokens']+=row['input'];group['output_tokens']+=row['output']
    missing=sum(g['requests'] for g in groups.values())
    return dict(observed_requests=len(records),priced_requests=len(records)-missing,
                unpriced_requests=missing,
                unpriced_groups=sorted(groups.values(),key=lambda g:(-g['requests'],g['provider'],g['model'],g['reason'])))

def usage_period(rows,include_requests=None,request_stats=None):
    result=dict(totals=usage_totals(rows),rows=rows)
    for field in ['provider','model','project','role','session','date']:
        groups=collections.defaultdict(list)
        for row in rows:groups[row[field]].append(row)
        values=[dict(name=name,**usage_totals(group)) for name,group in groups.items()]
        result['by_'+field]=sorted(values,key=(lambda value:value['name']) if field=='date' else (lambda value:(-value['known_cost_usd'],value['name'])))
    if request_stats is not None:
        result['telemetry']=telemetry_summary(request_stats)
        result['pricing_coverage']=pricing_coverage(request_stats)
    if include_requests is not None:
        result['requests']=include_requests
        if request_stats is not None:result['request_stats']=request_stats
    return result

def usage_changes(current,previous):
    if previous is None:return {'status':'not_requested'}
    a,b=current['totals'],previous['totals']
    if not b['requests']:return {'status':'no_previous_data'}
    if not a['requests']:return {'status':'no_current_data'}
    result={'status':'available'}
    for metric in ['requests','sessions','input_tokens','output_tokens','total_tokens','estimated_cost_usd','cache_share']:
        x,y=a[metric],b[metric]
        if metric=='estimated_cost_usd' and (any(value['estimated_cost_usd'] is not None and value['estimated_cost_high_usd']-value['estimated_cost_usd']>1e-9 for value in [a,b])):
            result[metric]={'status':'incomplete_pricing'};continue
        if x is None or y is None:
            result[metric]={'status':'unavailable'};continue
        difference=x-y
        change={'status':'available','previous':y,'absolute':difference}
        if metric=='estimated_cost_usd':
            change.update(basis='known_priced_requests',excluded_current_requests=a['unpriced_requests'],excluded_previous_requests=b['unpriced_requests'])
        if metric=='cache_share':change['percentage_points']=difference*100
        else:
            change['percent']=difference/abs(y)*100 if y else 0. if not x else None
            if change['percent'] is None:change['status']='zero_baseline'
        result[metric]=change
    return result

def usage_report(snapshot,args):
    if args.days<1:raise ValueError('--days must be positive')
    if args.all_time and (args.date_from or args.date_to):raise ValueError('--all-time cannot be combined with --from or --to')
    dates=sorted(row['date'] for row in snapshot['rows']+snapshot.get('grok_records',[]))
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
                    (not args.project or row['project']==args.project) and (not args.role or row['role']==args.role) and
                    (not getattr(args,'pool',None) or row.get('pool','interactive')==args.pool))
    def period(window):
        selected=[row for row in snapshot['rows'] if matching(row,window)]
        details=[row for row in snapshot.get('requests',[]) if matching(row,window)] if args.include_requests else None
        observations=[row for row in snapshot.get('request_stats',[]) if matching(row,window)]
        return usage_period(selected,details,observations)
    current=period((start,end));previous=period(before) if before else None
    report=dict(schema_version=2,version=VERSION,generated=snapshot['generated'],as_of_date=snapshot['as_of_date'],
                timezone=snapshot['timezone'],price_as_of=snapshot['price_as_of'],price_sources=snapshot.get('price_sources',[]),
                period={'from':start.isoformat(),'to':end.isoformat(),'days':days},
                previous_period={'from':before[0].isoformat(),'to':before[1].isoformat(),'days':days} if before else None,
                filters={'provider':provider,'model':model,'project':args.project,'role':args.role,'pool':getattr(args,'pool',None)},
                current=current,previous=previous,changes=usage_changes(current,previous),
                quality=snapshot['quality'],scan=snapshot['scan'],source_summary=snapshot['summary'],
                cost_comparison_basis='known_priced_requests',price_basis=snapshot.get('price_basis','custom_rates'),history_coverage=snapshot.get('history_coverage',{}),
                unknown_models=sorted({row['model'] for row in current['rows'] if row['unpriced']}),
                notes=['Costs are API-equivalent estimates, not subscription charges.',
                       'Cost totals and comparisons exclude unpriced requests; usage counts and tokens include all recorded requests.',
                       'The default catalog applies current prices to all recorded dates; it is not historical billing.',
                       'Comparisons use recorded observations; missing records do not prove zero usage.',
                       'A period including the snapshot date may contain a partial day.'])
    pool_records=[row for row in snapshot.get('request_stats',[]) if start.isoformat()<=row['date']<=end.isoformat()]
    report['pools']={pool:budget_status([r for r in pool_records if r['pool']==pool],getattr(args,option,None))
                     for pool,option in [('interactive','budget'),('managed','managed_budget')]}
    grok_records=[r for r in snapshot.get('grok_records',[]) if start.isoformat()<=r['date']<=end.isoformat()]
    report['grok_usage']=dict(grok_totals(grok_records),scope='Selected dates, all Grok models/projects; separate from Claude/Codex filters.',records=grok_records)
    report['pool_scope']='Selected dates, all providers and projects. Managed sessions are explicitly tagged; confirmed children inherit the pool.'
    report['measurement_basis']=MEASUREMENT_BASIS
    report['evidence_store']={'file':'sessions.sqlite','schema_version':EVIDENCE_SCHEMA,'generated':snapshot['generated']}
    if getattr(args,'include_events',False):report['session_evidence']=evidence_report(snapshot,args,report)
    return report

def evidence_report(snapshot,args,usage=None):
    """Bounded metadata queries over this invocation's freshly collected snapshot."""
    if usage is None:
        query=argparse.Namespace(**vars(args));query.include_events=False
        usage=usage_report(snapshot,query)
    period=dict(usage['period']);filters=usage['filters'];wanted=getattr(args,'session',None)
    if args.all_time:
        dates=[e['date'] for e in snapshot.get('events',[]) if e['date']]+[r['date'] for r in snapshot['rows']]
        if dates:
            period={'from':min(dates),'to':max(dates),'days':(dt.date.fromisoformat(max(dates))-dt.date.fromisoformat(min(dates))).days+1}
    details=snapshot.get('session_details',[])
    if wanted:
        matched=[s for s in details if s['id']==wanted or s['id'].split(':',1)[-1]==wanted]
        if len(matched)!=1:raise ValueError('Session not found or ambiguous; use the full provider-prefixed ID from sessions --json.')
        ids=set(matched[0]['tree_sessions'] if getattr(args,'tree',False) else [matched[0]['id']])
    else:ids={s['id'] for s in details}
    ids &= {s['id'] for s in details if (not filters['provider'] or s['provider']==filters['provider']) and
            (not filters['project'] or s['project']==filters['project']) and (not filters['role'] or s['role']==filters['role'])}
    def in_period(value):return value is not None and period['from']<=value<=period['to']
    all_rows=snapshot.get('requests',[])
    scoped=[r for r in all_rows if in_period(r['date']) and
            (not filters['model'] or canonical_model(r['model'])==filters['model']) and
            (not filters['pool'] or r.get('pool','interactive')==filters['pool'])]
    metadata={s['id']:s for s in details}
    pool_sessions={r['session'] for r in scoped}
    selected_events=[e for e in snapshot.get('events',[]) if e['session'] in ids and in_period(e['date']) and
                     (not filters['model'] or not e.get('model') or canonical_model(e['model'])==filters['model']) and
                     (not filters['pool'] or e['session'] in pool_sessions)]
    observed_ids={r['session'] for r in scoped}|{e['session'] for e in selected_events}
    ids &= observed_ids if not wanted else ids
    rows_by_session=collections.defaultdict(list);events_by_session=collections.defaultdict(list)
    for row in scoped:rows_by_session[row['session']].append(row)
    for event in selected_events:events_by_session[event['session']].append(event)
    results=[]
    for sid in sorted(ids):
        source=metadata[sid];tree=set(source['tree_sessions'])
        local=events_by_session[sid]
        results.append(dict(id=sid,provider=source['provider'],project=source['project'],role=source['role'],
            parent_session=source['parent_session'],children=source['children'],
            own=recorded_cost(rows_by_session[sid]),
            tree=recorded_cost([r for child in tree for r in rows_by_session[child]]),event_count=len(local),
            lifecycle={'status':'unknown','last_recorded':source['last_recorded_lifecycle'],'last_seen':source['last_seen']},
            lifetime={'first_seen':source['first_seen'],'last_seen':source['last_seen'],'elapsed_seconds':source['elapsed_seconds'],
                      'active_seconds':None,'max_request_input_tokens':source['max_request_input_tokens'],
                      'context_since_compaction':source['context_since_compaction']}))
    results.sort(key=lambda s:(-s['own']['known_cost_usd'],s['id']))
    event_ids={e['id'] for e in selected_events}
    calls=[c for c in snapshot.get('tool_calls',[]) if c['session'] in ids and event_ids.intersection(c['event_ids'])]
    tools={};kinds={e['id']:e['kind'] for e in selected_events}
    for call in calls:
        group=tools.setdefault(call['tool'],dict(tool=call['tool'],calls=0,results=0,result_bytes=0,results_without_size=0,known_errors=0,unknown_error_status=0,observed_latency_seconds=0.,timed_calls=0))
        present={kinds[e] for e in call['event_ids'] if e in kinds};started='tool_call' in present;finished='tool_result' in present
        group['calls']+=started;group['results']+=finished;group['result_bytes']+=(call['result_bytes'] or 0) if finished else 0
        group['results_without_size']+=finished and call['result_bytes'] is None
        group['known_errors']+=finished and call['error'] is True;group['unknown_error_status']+=not finished or call['error'] is None
        if started and finished and call['observed_latency_seconds'] is not None:
            group['timed_calls']+=1;group['observed_latency_seconds']+=call['observed_latency_seconds']
    offset=getattr(args,'offset',0);limit=getattr(args,'limit',200)
    if offset<0 or not 1<=limit<=10000:raise ValueError('--offset must be nonnegative and --limit must be between 1 and 10000')
    page=selected_events[offset:offset+limit]
    return dict(schema_version=EVIDENCE_SCHEMA,version=VERSION,generated=snapshot['generated'],period=period,filters=filters,
        scope='Own/tree costs use selected dates and model/pool filters. Lifecycle and lifetime fields use all observed history. Tree totals overlap: do not sum them.',
        sessions=results,tools=sorted(tools.values(),key=lambda t:(-t['result_bytes'],t['tool'])),
        events=page,events_total=len(selected_events),undated_events=sum(e['session'] in ids and e['date'] is None for e in snapshot.get('events',[])),offset=offset,limit=limit,
        next_offset=offset+limit if offset+limit<len(selected_events) else None,
        source_files=[s for s in snapshot.get('source_files',[]) if s['id'] in {r['source_id'] for e in page for r in e['evidence']}],
        measurement_basis=MEASUREMENT_BASIS)

def compact_tokens(value):
    units=('', 'K', 'M', 'B', 'T');unit=0
    while value>=1000 and unit<len(units)-1:value/=1000;unit+=1
    if not unit:return str(value)
    if round(value,2)>=1000 and unit<len(units)-1:value/=1000;unit+=1
    return f'{value:.2f}'.rstrip('0').rstrip('.')+units[unit]

def usage_text(report):
    months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
    def date_label(value):
        day=dt.date.fromisoformat(value)
        return months[day.month-1]+' '+str(day.day)
    period=report['period'];a=report['current']['totals']
    cost=a['estimated_cost_usd'];high=a['estimated_cost_high_usd']
    amount='unavailable' if cost is None else f'${cost:,.2f}'+(f'–${high:,.2f}' if high-cost>.005 else '')
    if a['unpriced_requests']:amount+=f" ({a['unpriced_requests']:,} requests excluded from cost)"
    label=date_label(period['from'])+'–'+date_label(period['to'])
    if period['from'][:4]!=period['to'][:4]:label=period['from']+'–'+period['to']
    lines=[f"For {label}: {amount} estimated API cost. In: {compact_tokens(a['input_tokens'])}, Out: {compact_tokens(a['output_tokens'])}"]
    previous=report.get('previous')
    if previous and (a['unpriced_requests'] or previous['totals']['unpriced_requests']):
        lines.append(f"Cost comparison uses priced requests only; excluded: {a['unpriced_requests']:,} current, {previous['totals']['unpriced_requests']:,} previous.")
    changes=report['changes']
    if changes['status']=='available':
        descriptions=[]
        for metric,name in [('estimated_cost_usd','estimated cost'),('input_tokens','input'),('output_tokens','output')]:
            value=changes[metric]
            if value['status']=='available':descriptions.append(f"{name} {value['percent']:+.1f}%")
            else:descriptions.append(name+': '+value['status'].replace('_',' '))
        lines.append('Versus the previous period: '+', '.join(descriptions)+'.')
    elif changes['status']!='not_requested':lines.append(changes['status'].replace('_',' ').capitalize()+'.')
    return '\n'.join(lines)

def statusline_report(snapshot,report,args):
    records=snapshot['request_stats'];wanted=args.session or os.environ.get('CODEX_THREAD_ID')
    matching=[r for r in records if wanted and (r['session']==wanted or r['session'].split(':',1)[-1]==wanted)]
    if len({r['session'] for r in matching})>1:raise ValueError('Ambiguous session ID; include the Codex: or Claude: prefix')
    selection='explicit' if wanted else 'latest_observed'
    if not wanted:
        candidates=[r for r in records if not report['filters']['provider'] or r['provider']==report['filters']['provider']]
        latest=max(candidates,key=lambda r:r['ts'],default=None)
        matching=[r for r in records if latest and r['session']==latest['session']]
    latest=max(matching,key=lambda r:r['ts'],default=None)
    provider=latest['provider'] if latest else report['filters']['provider']
    period=report['period']
    harness=[r for r in records if r['provider']==provider and period['from']<=r['date']<=period['to']]
    return dict(schema_version=2,version=VERSION,generated=snapshot['generated'],period=period,
        session=dict(id=latest['session'] if latest else wanted,selection=selection,records=len(matching),
            model=latest['model'] if latest else None,context_tokens=latest['input'] if latest else None,
            cache_share=latest['cached']/latest['input'] if latest and latest['input'] else None,
            **budget_status(matching,None)),
        harness=dict(provider=provider,records=len(harness),**budget_status(harness,None)),
        pools=report['pools'])

def statusline_text(result,color=False):
    def money(value):
        if value['observed_requests']==0:return 'unavailable'
        if value['observed_requests']==value['unpriced_requests']:return 'unpriced'
        amount=f"${value['known_cost_usd']:,.2f}"
        if value['cost_high_usd']-value['known_cost_usd']>.005:amount+=f"–${value['cost_high_usd']:,.2f}"
        return amount+(' (priced only)' if value['unpriced_requests'] else '')
    pool=result['pools']['interactive'];managed=result['pools']['managed'];session=result['session'];harness=result['harness']
    scope='Session' if session['selection']=='explicit' else 'Latest session'
    text=f"AISAD est · {scope} {money(session)} · {harness['provider'] or 'Harness'} {result['period']['days']}d {money(harness)} · Shared {money(pool)}"
    if pool['budget_usd']:text+=f"/${pool['budget_usd']:,.0f}"
    if managed['budget_usd'] or managed['known_cost_usd']:text+=f" · Managed {money(managed)}"+(f"/${managed['budget_usd']:,.0f}" if managed['budget_usd'] else '')
    level=max(pool['nudge_percent'],managed['nudge_percent'])
    for name,value in [('Shared',pool),('Managed',managed)]:
        if value['nudge_percent']:text+=f" · {name} {value['nudge_percent']}% threshold"
    if session['context_tokens'] is not None:text+=' · Ctx '+compact_tokens(session['context_tokens'])
    if session['cache_share'] is not None:text+=f" · Cache {session['cache_share']*100:.0f}%"
    text=re.sub(r'[\x00-\x1f\x7f-\x9f]',' ',text)
    if color:text='\x1b['+('31' if level==100 else '33' if level else '36')+'m'+text+'\x1b[0m'
    return text

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'">
<title>AISAD · Usage statistics</title><style>
:root{color-scheme:light;--bg:#fff;--card:#fff;--ink:#000;--muted:#6b6b6b;--line:#e2e2e2;--accent:#000;--shade:#f6f6f6;--previous:#afafaf;--green:#0e8345;--green-bg:#eaf6ed;--orange:#9f6402;--red:#de1135;--focus:#276ef1}
:root[data-theme="dark"]{color-scheme:dark;--bg:#141414;--card:#1f1f1f;--ink:#fff;--muted:#afafaf;--line:#3d3d3d;--accent:#eee;--shade:#292929;--previous:#6b6b6b;--green:#66d19e;--green-bg:#163526;--orange:#ffc043;--red:#ff8f9e;--focus:#a0bff8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px Arial,Helvetica,sans-serif;line-height:1.5}main{max-width:1536px;margin:auto;padding:32px 40px 48px}header{display:flex;align-items:center;justify-content:space-between;gap:24px;border-bottom:1px solid var(--line);padding-bottom:22px}.brand{display:flex;gap:20px;align-items:center}.wordmark{font-size:27px;font-weight:800;letter-spacing:-1.3px;border-right:1px solid var(--line);padding-right:20px}.eyebrow{font-size:11px;letter-spacing:1.3px;text-transform:uppercase;color:var(--muted);font-weight:600}h1{font-size:25px;line-height:1.2;letter-spacing:-.8px;margin:3px 0 0}h2{font-size:18px;letter-spacing:-.4px;margin:0}h3{font-size:16px;margin:0 0 8px}p{margin:8px 0}.muted,small{color:var(--muted)}small{font-size:12px}.header-tools{display:flex;align-items:center;gap:12px}.badge,.tag{display:inline-flex;align-items:center;gap:6px;border-radius:6px;background:var(--shade);padding:5px 9px;font-size:12px;white-space:nowrap}.badge:before{content:'';width:6px;height:6px;border-radius:50%;background:var(--green)}button,select,input{font:inherit;color:var(--ink);border:1px solid transparent;background:var(--shade);border-radius:8px;min-height:40px;padding:9px 12px}button{cursor:pointer;font-weight:500}button:hover,select:hover{background:var(--line)}button:disabled{cursor:default;opacity:.4}button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid var(--focus);outline-offset:3px}select{max-width:220px}a{color:inherit;text-underline-offset:3px}label{display:flex;flex-direction:column;gap:6px;color:var(--muted);font-size:12px}label select,label input{color:var(--ink);font-size:13px}.tabs{display:flex;gap:8px;padding:24px 0 20px;overflow:auto}.tabs button{white-space:nowrap;border-radius:30px;padding:9px 18px;background:var(--shade)}.tabs button[aria-selected="true"]{background:var(--ink);color:var(--bg)}.count{font-size:11px;opacity:.65;margin-left:5px}.filters{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;padding:16px;background:var(--shade);border-radius:12px}.filters select,.filters input,.filters button{background:var(--card);border-color:var(--line)}.filters label{flex:1;min-width:118px}.filters label:first-child{flex:1.1}.filters select,.filters input{width:100%;max-width:none;min-width:0}.filters label.dates{flex:.9}.comparison{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:16px 0 12px}.comparison p{margin:0;font-size:12px;color:var(--muted);max-width:1100px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card,.panel{border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0;background:var(--card)}.card{padding:20px 18px}.card label{display:block;color:var(--muted);font-size:13px}.value{font-size:29px;letter-spacing:-1.1px;line-height:1.2;font-weight:600;margin:12px 0 8px;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.delta{display:block;border-top:1px solid var(--line);padding-top:10px;margin-top:16px;font-size:12px;color:var(--muted)}.usage-strip{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin:16px 0;font-size:12px;color:var(--muted)}.usage-strip b{color:var(--ink);font-weight:600}.money-note{font-size:11px;color:var(--muted);margin:10px 0 20px}.grid{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin:16px 0}.grid.equal{grid-template-columns:1fr 1fr}.tools{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.tools h2{margin:0}.tools p{font-size:12px;color:var(--muted)}.wide{margin-top:16px}.panel-intro{color:var(--muted);font-size:12px;margin:6px 0 18px}.barrow{display:grid;grid-template-columns:140px 1fr 90px;align-items:center;gap:12px;margin:14px 0}.barlabel{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bartrack{height:8px;background:var(--shade);border-radius:3px;overflow:hidden}.barfill{height:100%;background:var(--accent);border-radius:3px}.barvalue{text-align:right;font-size:12px;font-variant-numeric:tabular-nums}svg{display:block;width:100%;height:auto;max-height:300px;overflow:visible}.chart-text{fill:var(--muted);font-size:11px}.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:11px;color:var(--muted);margin:10px 0}.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:var(--accent)}.dot.previous{background:var(--previous)}.table-wrap{overflow:auto;max-height:660px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{white-space:nowrap;text-align:right;padding:13px 12px;border-bottom:1px solid var(--line);font-size:12px}th:first-child,td:first-child{text-align:left}th{position:sticky;top:0;background:var(--card);color:var(--muted);font-weight:500}td:first-child{max-width:300px;overflow:hidden;text-overflow:ellipsis}th button{padding:0;min-height:0;border-radius:0;background:none;color:var(--muted);font-size:12px}.provider-button,.session-button{background:none;padding:0;min-height:0;color:inherit;border-radius:2px;font:inherit;text-align:left;text-decoration:underline;text-decoration-color:var(--line);text-underline-offset:4px}.provider-button:hover,.session-button:hover{background:none;text-decoration-color:var(--ink)}.empty{padding:40px 16px;text-align:center;color:var(--muted)}.empty h3{color:var(--ink)}.pool-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.pool-card+.pool-card{border-left:1px solid var(--line);padding-left:24px}.pool-card strong{font-size:25px;font-weight:600;letter-spacing:-.7px}.pool-track{height:6px;border-radius:3px;background:var(--shade);margin:14px 0 8px;overflow:hidden}.pool-track span{display:block;background:var(--ink);height:100%}.nudge{color:var(--orange);font-size:12px}.mini-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:16px 0}.mini-grid .value{font-size:26px}.mini-grid .card{background:var(--shade);border:0}.coverage{font-size:12px;color:var(--muted)}details{margin-top:20px}summary{cursor:pointer;font-weight:600}details p,details li{color:var(--muted);overflow-wrap:anywhere;font-size:13px;max-width:1100px}footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:24px;font-size:11px;color:var(--muted)}[hidden]{display:none!important}dialog{width:min(1100px,calc(100% - 32px));max-height:90vh;border:1px solid var(--line);border-radius:16px;background:var(--card);color:var(--ink);padding:28px}dialog::backdrop{background:#0008}dialog .tools{position:sticky;top:-28px;background:var(--card);padding-top:4px;z-index:2}dialog h2{overflow-wrap:anywhere}#session-caption{overflow-wrap:anywhere}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1150px){main{padding:24px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.grid{grid-template-columns:1.3fr 1fr}.barrow{grid-template-columns:110px 1fr 82px}.card .value{font-size:27px}}
@media(max-width:760px){main{padding:20px 16px}.wordmark{padding-right:12px;font-size:22px}.brand{gap:12px}h1{font-size:21px}.eyebrow{font-size:9px}.header-tools{gap:6px}.header-tools .badge{display:none}#theme{padding:8px;font-size:12px}header{gap:10px}.tabs{padding-top:18px;gap:6px}.tabs button{padding:8px 13px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.card,.panel{padding:16px}.grid,.grid.equal,.pool-grid,.mini-grid{grid-template-columns:1fr}.pool-card+.pool-card{border-left:0;padding:16px 0 0;border-top:1px solid var(--line)}.tools{flex-wrap:wrap}#search{max-width:100%}.usage-strip{gap:12px}.comparison{display:block}dialog{padding:18px}dialog .tools{top:-18px}.barrow{grid-template-columns:130px 1fr 82px}}

/* Keep everyday controls visible and secondary filters out of the way. */
main{padding-top:20px}header{padding-bottom:14px}.eyebrow{display:none}.tabs{padding:14px 0 10px;gap:4px}.tabs button{min-height:36px;padding:7px 13px;font-size:13px}
.filters{display:block;padding:6px 0 12px;background:none;border-radius:0;border-bottom:1px solid var(--line)}
.filter-bar,.date-fields{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}.filters label,.filters label:first-child{flex:0 1 165px;min-width:0;gap:3px;font-size:11px}
.filters select,.filters input,.filters button{min-height:34px;padding:6px 9px;font-size:12px}.filters .quiet-button{border-color:transparent;background:transparent;color:var(--muted)}
.date-fields label,.date-fields label:first-child{flex:0 1 140px}.extra-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}
.comparison{margin:10px 0 12px;align-items:center;flex-wrap:wrap}.comparison p{color:var(--ink);font-size:12px}.comparison details{margin:0;font-size:11px;color:var(--muted)}.comparison summary{font-weight:400}.comparison details p{color:var(--muted);font-size:11px;margin-top:5px}
.pricing-details{margin:0 0 14px;padding:10px 12px;background:var(--shade);border-radius:8px;font-size:12px}.pricing-details summary{font-weight:500}.pricing-details .panel-intro{margin:8px 0}.card{padding:15px}.value{margin:8px 0 6px}.delta{margin-top:10px;padding-top:8px}
footer{justify-content:flex-start;align-items:baseline;gap:6px 16px;margin-top:18px;padding-top:12px;border-top:1px solid var(--line)}.method-details{margin:0}.method-details summary{font-weight:400}.method-details[open]{flex-basis:100%}.method-details p{font-size:11px;margin:6px 0}
@media(max-width:760px){.filter-bar{gap:8px}.filters label,.filters label:first-child{flex:1 1 130px}.filter-bar>label{max-width:200px}.extra-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.date-fields{flex-basis:100%;order:1}.date-fields label{max-width:180px}.comparison{display:flex;gap:4px 12px}.tabs button{padding:7px 10px}.card label{font-size:12px}.card .value{font-size:25px}.brand h1{font-size:19px}}
@media(max-width:420px){.filter-bar>label{flex-basis:calc(50% - 8px);max-width:none}.tabs button{font-size:12px;padding:7px 8px}.wordmark{font-size:20px}.brand h1{font-size:17px}}
</style></head><body><main>
<header><div class="brand"><span class="wordmark">AISAD</span><div><div class="eyebrow">Understand your agent spend</div><h1>Usage statistics</h1></div></div><div class="header-tools"><span class="badge">This device only</span><button id="theme" aria-label="Switch to dark theme">Dark theme</button></div></header>
<section id="saved-summary" class="panel wide">__SAVED_SUMMARY__</section>
<div id="interactive-dashboard" hidden>
<nav class="tabs" role="tablist" aria-label="Usage views"><button id="tab-overview" role="tab" aria-selected="true" aria-controls="view-overview" data-tab="overview">Charts</button><button id="tab-sessions" role="tab" aria-selected="false" aria-controls="view-sessions" tabindex="-1" data-tab="sessions">Sessions <span class="count" id="session-count"></span></button><button id="tab-context" role="tab" aria-selected="false" aria-controls="view-context" tabindex="-1" data-tab="context">Context</button><button id="tab-cache" role="tab" aria-selected="false" aria-controls="view-cache" tabindex="-1" data-tab="cache">Cache usage</button></nav>
<div class="filters">
<div class="filter-bar"><label>Period<select id="period"><option value="7">Last 7 days</option><option value="this-week">This week (Mon–today)</option><option value="last-week">Last week (Mon–Sun)</option><option value="30">Last 30 days</option><option value="all">All time</option><option value="custom">Custom dates</option></select></label>
<div id="custom-dates" class="date-fields" hidden><label>From<input type="date" id="from"></label><label>To<input type="date" id="to"></label></div>
<label>Provider<select id="provider"></select></label><button id="filter-toggle" aria-expanded="false" aria-controls="extra-filters">More filters</button><button id="reset" class="quiet-button">Reset</button></div>
<div id="extra-filters" class="extra-filters" hidden><label>Model<select id="model"></select></label><label>Project<select id="project"></select></label><label>Role<select id="role"><option value="">All roles</option><option value="main">Main thread</option><option value="subagent">Subagent</option><option value="review">Auto-review</option></select></label><label>Pool<select id="pool"><option value="">All pools</option><option value="interactive">Interactive</option><option value="managed">Managed</option></select></label></div></div>
<div class="comparison"><p id="comparison-note" aria-live="polite"></p><details id="comparison-details"><summary>Coverage</summary><p id="comparison-coverage"></p></details></div>
<div id="view-overview" role="tabpanel" aria-labelledby="tab-overview">
<div class="cards" id="cards"></div><div class="usage-strip" id="usage-strip"></div><div class="money-note" id="money-note"></div>
<details class="pricing-details" id="pricing-gaps" hidden><summary id="pricing-title">Requests without a price</summary><p id="pricing-coverage" class="panel-intro"></p><div class="table-wrap"><table id="pricing-table"></table></div></details>
<div class="grid"><section class="panel"><div class="tools"><h2>Spend over time</h2><select id="chartmetric" aria-label="Chart metric"><option value="cost">Estimated cost, USD</option><option value="total">Total tokens</option><option value="output">Output tokens</option><option value="requests">Requests</option></select></div><div id="daily"></div></section><section class="panel"><div class="tools"><h2>Top models</h2><small>Selected period</small></div><div id="models-chart"></div></section></div>
<section class="panel wide" id="token-breakdown"><div class="tools"><h2>Token &amp; cost breakdown</h2><small>Selected dates and filters</small></div><p class="panel-intro">All recorded tokens, split into non-overlapping categories. Costs include priced requests only; cache-write uncertainty is shown as a range.</p><div id="token-cards" class="cards"></div><p id="search-cost" class="panel-intro" hidden></p></section>
<section class="panel wide"><div class="tools"><h2>Usage by provider</h2><small>Select a provider to filter every view</small></div><div class="table-wrap"><table id="providers-table"></table></div></section>
<div class="grid equal"><section class="panel"><h2>What the estimate pays for</h2><p class="panel-intro">Known priced components, including the cache-write cost range.</p><div id="parts"></div></section><section class="panel"><h2>Top projects</h2><div id="projects-chart"></div></section></div>
<section class="panel wide"><div class="tools"><h2>Usage by model</h2><small>Select a heading to sort</small></div><div class="table-wrap"><table id="models-table"></table></div></section></div>
<section id="view-sessions" role="tabpanel" aria-labelledby="tab-sessions" class="panel" hidden><div class="tools"><h2>Sessions</h2><div><input id="search" type="search" placeholder="Search sessions" aria-label="Search the sessions table only"> <select id="session-sort" aria-label="Sort sessions"><option value="cost">Highest cost</option><option value="max_context">Largest input</option><option value="requests">Most requests</option></select></div></div><p class="panel-intro">Open a session to inspect its usage and request timeline within the selected filters.</p><div class="table-wrap"><table id="sessions-table"></table></div><div class="tools" style="margin-top:16px"><small id="page-info"></small><div><button id="prev" aria-label="Previous sessions page">←</button> <button id="next" aria-label="Next sessions page">→</button></div></div></section>
<section id="view-context" role="tabpanel" aria-labelledby="tab-context" hidden><div class="mini-grid" id="context-cards"></div><section class="panel"><h2>What these traces establish</h2><div id="measurement-basis"></div><p class="panel-intro">Input includes cached tokens. A cache hit changes price, not context size. Compaction does not establish which original blocks survive in the summary.</p></section><div class="grid equal"><section class="panel"><h2>Largest recorded input</h2><p class="panel-intro">Peak input per session, including cached input.</p><div id="context-chart"></div></section><section class="panel"><h2>Tool payload footprint</h2><p class="panel-intro">Result bytes recorded in local logs. Billed tokens and repeated inclusion are unavailable.</p><div id="tool-chart"></div><p class="panel-intro" id="tool-coverage"></p></section></div></section>
<section id="view-cache" role="tabpanel" aria-labelledby="tab-cache" hidden><div class="cards" id="cache-cards"></div><section class="panel"><h2>Cache by model</h2><p class="panel-intro">Uncached input + cache reads + cache writes equals total input. Costs include priced requests only; unknown cache-write TTLs produce ranges.</p><div class="table-wrap"><table id="cache-table"></table></div></section></section>
<details class="pricing-details" id="grok-usage" hidden><summary id="grok-title">Grok reported usage</summary><p id="grok-note"></p></details>
<footer><span id="footer"></span><span id="subtitle"></span><details class="method-details"><summary>About the data</summary><div id="method"></div><p class="coverage" id="coverage"></p></details></footer></div></main>
<dialog id="session-dialog" aria-labelledby="session-title"><div class="tools"><div><div class="eyebrow">Session detail</div><h2 id="session-title"></h2></div><button id="close-session" aria-label="Close session detail">Close ×</button></div><p class="panel-intro" id="session-caption"></p><div class="mini-grid" id="session-cards"></div><div id="session-lifecycle" class="panel-intro"></div><h3>Input per usage observation</h3><div id="session-timeline"></div><section id="observation-detail" class="panel" hidden></section><h3 style="margin-top:24px">Recorded events</h3><p id="events-note" class="panel-intro"></p><div class="table-wrap"><table id="events-table"></table></div></dialog>
<script id="snapshot" type="application/json">__DATA__</script><script>
'use strict';
async function loadSnapshot(node){
    const data=JSON.parse(node.textContent);
    if(data.encoding!=='gzip-base64')return data;
    if(typeof DecompressionStream==='undefined')throw new Error('This browser cannot decompress the saved report');
    const bytes=Uint8Array.from(atob(data.data),c=>c.charCodeAt(0));
    const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).json();
}
(async()=>{
const D=await loadSnapshot(document.getElementById('snapshot'));const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const compact=n=>new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(n||0);const integer=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n||0);const usd=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n||0);const pct=n=>n==null?'—':(n*100).toFixed(1)+'%';
// Calendar dates use UTC arithmetic to avoid DST and browser-timezone shifts.
const shiftDate=(date,days)=>{const value=new Date(date+'T00:00:00Z');value.setUTCDate(value.getUTCDate()+days);return value.toISOString().slice(0,10)};
const shortDate=date=>new Date(date+'T00:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'});
const rangeLabel=range=>range?range.from+' – '+range.to:'';
const providerLabel=name=>({'Codex':'OpenAI · Codex','Claude':'Anthropic · Claude'}[name]||name);
let page=0,modelSort='cost',ascending=false;
const allDates=[...D.rows,...(D.grok_records||[]),...(D.session_details||[]).flatMap(s=>(s.observed_dates||[]).map(date=>({date})))].map(r=>r.date).filter(Boolean).sort();
const today=D.as_of_date||D.generated.slice(0,10),first=allDates[0]||shiftDate(today,-6),last=allDates[allDates.length-1]||today;
function setPeriod(value){
    $('period').value=value;
    $('custom-dates').hidden=value!=='custom';
    if(value==='custom')return;
    const monday=shiftDate(today,-((new Date(today+'T00:00:00Z').getUTCDay()+6)%7));
    if(value==='this-week'){
        $('from').value=monday;$('to').value=today;
    }else if(value==='last-week'){
        $('from').value=shiftDate(monday,-7);$('to').value=shiftDate(monday,-1);
    }else{
        $('from').value=value==='all'?first:shiftDate(today,1-Number(value));
        $('to').value=value==='all'?last:today;
    }
}
function selectedRange(){
    const from=$('from').value,to=$('to').value;
    if(!from||!to||from>to)return null;
    const days=Math.round((Date.parse(to+'T00:00:00Z')-Date.parse(from+'T00:00:00Z'))/86400000)+1;
    return {from,to,days};
}
function previousRange(range){
    if(!range||$('period').value==='all')return null;
    // Compare a partial calendar week with the same weekdays one week earlier.
    const offset=$('period').value==='this-week'?7:range.days;
    return {from:shiftDate(range.from,-offset),to:shiftDate(range.to,-offset),days:range.days};
}
for(const field of ['provider','model','project']){
    const values=[...new Set([...D.rows,...(field==='model'?[]:D.session_details||[])].map(r=>r[field]).filter(Boolean))].sort();
    $(field).innerHTML='<option value="">All</option>'+values.map(v=>'<option value="'+esc(v)+'">'+esc(field==='provider'?providerLabel(v):v)+'</option>').join('');
}
setPeriod('7');
let generatedLabel;try{generatedLabel=new Date(D.generated).toLocaleString('en-US',{timeZone:D.timezone==='System local timezone'?undefined:D.timezone})}catch{generatedLabel=D.generated}
$('subtitle').textContent='Updated '+generatedLabel;
if(D.demo)document.querySelector('.badge').textContent='Synthetic demo';
$('coverage').textContent=Object.entries(D.history_coverage||{}).map(([provider,h])=>provider+': '+(h.first_date?h.first_date+' – '+h.last_date:'no records')).join(' · ')+(D.quality.registry_without_trace?' · '+integer(D.quality.registry_without_trace)+' registered Codex sessions have no trace. ':' · ')+(D.summary.files?`Found ${integer(D.summary.files)} local files. Codex: ${D.summary.traces_codex} traces across ${D.summary.registry_codex} registered threads. Missing traces are not estimated. Cloud chats are not included.`:'No local traces found. Run Codex or Claude Code on this device, or set --codex-dir / --claude-dir.');
function chosen(r,range=selectedRange()){
    return Boolean(range&&r.date>=range.from&&r.date<=range.to&&['provider','model','project'].every(f=>!$(f).value||r[f]===$(f).value)&&(!$('role').value||r.role===$('role').value)&&(!$('pool').value||(r.pool||'interactive')===$('pool').value));
}
function aggregate(rows){const a={requests:0,input:0,cached:0,write:0,output:0,total:0,cost:0,cost_high:0,unpriced:0,max_context:0,parts:[0,0,0,0,0],assumed:0,write_unknown:0,sessions:new Set()};for(const r of rows){for(const f of ['requests','input','cached','write','output','total','cost','cost_high','unpriced','assumed','write_unknown'])a[f]+=r[f]||0;a.max_context=Math.max(a.max_context,r.max_context||0);a.parts=a.parts.map((v,i)=>v+(r.parts?.[i]||0));a.sessions.add(r.session)}a.cache=a.input?a.cached/a.input:null;return a}
function groups(rows,field){const m=new Map();for(const r of rows){if(!m.has(r[field]))m.set(r[field],[]);m.get(r[field]).push(r)}return [...m].map(([name,rs])=>({name,...aggregate(rs)}))}
function cost(a){if(a.requests===a.unpriced)return '—';return usd(a.cost)+(a.cost_high-a.cost>.005?'–'+usd(a.cost_high):'')}
function bars(id,items,metric='cost'){const entries=[...items].sort((a,b)=>b[metric]-a[metric]);const max=Math.max(...entries.map(x=>x[metric]),1e-9);$(id).innerHTML=entries.length?entries.map((x,i)=>`<div class="barrow"><span class="barlabel" title="${esc(x.name)}">${['models-chart','projects-chart','context-chart'].includes(id)?`<button data-breakdown="${id}" data-value="${esc(x.name)}">${esc(x.label||x.name)}</button>`:esc(x.name)}</span><div class="bartrack"><div class="barfill" style="width:${Math.max(0,x[metric]/max*100)}%;opacity:${Math.max(.45,1-i*.06)}"></div></div><span class="barvalue">${metric==='cost'?cost(x):compact(x[metric])}</span></div>`).join(''):'<div class="empty">No data in the selected period</div>'}
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
    if(metric==='cost'){
        if(current.requests===current.unpriced)return 'No priced current-period data';
        if(previous.requests===previous.unpriced)return 'No priced previous-period data';
        if(current.cost_high-current.cost>.005||previous.cost_high-previous.cost>.005)return 'Price range · no delta';
    }
    const value=a=>metric==='sessions'?a.sessions.size:metric==='cache'?a.cache:a[metric];
    return numericDelta(value(current),value(previous),metric==='cost'?usd:metric==='cache'?pct:metric==='requests'||metric==='sessions'?integer:compact,metric==='cache');
}
function comparisonNote(range,previous,rows,priorRows){
    if(!range)return 'Choose a valid date range.';
    const label=r=>shortDate(r.from)+' – '+shortDate(r.to)+(r.from.slice(0,4)!==today.slice(0,4)||r.to.slice(0,4)!==today.slice(0,4)?' ('+r.from.slice(0,4)+(r.from.slice(0,4)!==r.to.slice(0,4)?'–'+r.to.slice(0,4):'')+')':'');
    return label(range)+(previous?' · compared with '+label(previous):' · All time');
}
function comparisonCoverage(range,previous,rows,priorRows){
    if(!range)return 'The start date must be on or before the end date.';
    const current=new Set(rows.map(r=>r.date)).size,prior=new Set(priorRows.map(r=>r.date)).size;
    return `${current} of ${range.days} days have records${previous?`; previous period: ${prior} of ${previous.days}`:''}. Missing days are not counted as zero usage.${range.to>=today?' Today is still in progress.':''}`;
}
function syncFilterControls(){
    $('custom-dates').hidden=$('period').value!=='custom';
    const count=['model','project','role','pool'].filter(f=>$(f).value).length;
    $('filter-toggle').textContent=count?`More filters (${count})`:'More filters';
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
            svg+=`<rect tabindex="0" role="button" data-day="${date}" aria-label="Show sessions for ${date}" data-series="${series}" x="${x}" y="${h-B-hh}" width="${Math.max(.2,width)}" height="${hh}" rx="2" fill="var(--${series==='previous'?'previous':'accent'})"><title>${esc(series+' · '+date+': '+(metric==='cost'?cost(g):integer(g[metric])))}</title></rect>`;
        }
        if(i%Math.max(1,Math.ceil(points.length/8))===0)svg+=`<text x="${L+(i+.5)*step}" y="${h-10}" text-anchor="middle" class="chart-text">${shortDate(p.date)}</text>`;
    });
    $('daily').innerHTML=svg+'</svg>'+`<div class="legend"><span><i class="dot"></i>Selected period</span>${compare?'<span><i class="dot previous"></i>Previous period, aligned by day</span>':''}</div><small>Missing bars mean no observations${metric==='cost'?' or unavailable prices':''}; today may be incomplete. Hover for the value; select a bar to inspect its sessions.</small>`;
}
function modelsTable(rs){let gs=groups(rs,'model').sort((a,b)=>(a[modelSort]-b[modelSort])*(ascending?1:-1));$('models-table').innerHTML='<thead><tr><th>Model</th>'+[['requests','Requests'],['total','Tokens'],['output','Output'],['cached','Cache'],['cost','Cost, USD']].map(([f,l])=>`<th><button data-sort="${f}">${l}${modelSort===f?(ascending?' ↑':' ↓'):''}</button></th>`).join('')+'<th>Unpriced</th></tr></thead><tbody>'+gs.map(g=>`<tr><td>${esc(g.name)}</td><td>${integer(g.requests)}</td><td>${compact(g.total)}</td><td>${compact(g.output)}</td><td>${pct(g.cache)}</td><td>${cost(g)}</td><td>${g.unpriced||'—'}</td></tr>`).join('')+'</tbody>';document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{ascending=modelSort===b.dataset.sort?!ascending:false;modelSort=b.dataset.sort;modelsTable(rs)})}
const records=D.request_stats||[];
const moneyRange=(low,high)=>low==null?'—':usd(low)+(high-low>.005?'–'+usd(high):'');
const bytes=n=>n>=1e6?(n/1e6).toFixed(1)+' MB':n>=1000?(n/1000).toFixed(1)+' KB':integer(n)+' B';
function selectedRecords(){return records.filter(r=>chosen(r))}
function recordRows(rs){return rs.map(r=>({...r,requests:1,total:r.input+r.output,unpriced:r.cost==null?1:0,max_context:r.input}))}
function telemetry(rs){
    const stats={};let traceRecords=0;
    for(const r of rs){
        if(r.trace_observed)traceRecords++;
        for(const [k,v] of Object.entries(r.trace_stats||{}))stats[k]=k.startsWith('max_')?Math.max(stats[k]||0,v):(stats[k]||0)+v;
    }
    return {stats,traceRecords,totalRecords:rs.length};
}
function sessionLabel(id){return D.titles?.[id]||id}
function sessionsTable(rs){
    const search=$('search').value.toLowerCase(),metric=$('session-sort').value;
    const grouped=groups(rs,'session'),seen=new Set(grouped.map(g=>g.name)),range=selectedRange();
    for(const meta of D.session_details||[]){
        if(seen.has(meta.id)||!range||$('model').value||$('pool').value)continue;
        if(['provider','project','role'].some(f=>$(f).value&&meta[f]!==$(f).value))continue;
        const observed=(meta.observed_dates||[]).some(date=>date>=range.from&&date<=range.to);
        if(observed)grouped.push({name:meta.id,...aggregate([])});
    }
    $('session-count').textContent=grouped.length;
    let gs=grouped.filter(g=>(g.name+' '+(D.titles?.[g.name]||'')).toLowerCase().includes(search)).sort((a,b)=>b[metric]-a[metric]);
    page=Math.min(page,Math.max(0,Math.ceil(gs.length/25)-1));const show=gs.slice(page*25,(page+1)*25);
    $('sessions-table').innerHTML='<thead><tr><th>Session</th><th>Requests</th><th>Input + output</th><th>Cache</th><th>Peak input</th><th>API estimate</th></tr></thead><tbody>'+show.map(g=>`<tr><td title="${esc(g.name)}"><button class="session-button" data-session="${esc(g.name)}">${esc(sessionLabel(g.name))}</button></td><td>${integer(g.requests)}</td><td>${compact(g.total)}</td><td>${pct(g.cache)}</td><td>${g.requests?compact(g.max_context):'—'}</td><td>${cost(g)}</td></tr>`).join('')+'</tbody>';
    $('page-info').textContent=`${gs.length?page*25+1:0}–${Math.min((page+1)*25,gs.length)} of ${gs.length} sessions`;$('prev').disabled=page===0;$('next').disabled=(page+1)*25>=gs.length;
}
function showTab(name){
    for(const button of document.querySelectorAll('[data-tab]')){const active=button.dataset.tab===name;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;$(button.getAttribute('aria-controls')).hidden=!active}
}
function openSession(id){
    const rs=selectedRecords().filter(r=>r.session===id).sort((a,b)=>a.ts-b.ts||a.step-b.step),a=aggregate(recordRows(rs)),d=telemetry(rs);
    $('session-title').textContent=sessionLabel(id);$('session-caption').textContent=`${rangeLabel(selectedRange())} · Selected filters · ${[...new Set(rs.map(r=>r.model))].join(', ')} · ${integer(d.traceRecords)} of ${integer(rs.length)} usage records have message/tool telemetry.`;
    $('session-cards').innerHTML=miniCards([['API estimate',cost(a),'For requests within these filters'],['Peak input',rs.length?compact(a.max_context):'—','Measured request input, including cache'],['Cache read share',pct(a.cache),'Weighted by input tokens']]);
    if(rs.length){
        const w=900,h=200,L=54,R=18,T=18,B=30,max=Math.max(...rs.map(r=>r.input),1),x=i=>L+i*(w-L-R)/Math.max(1,rs.length-1),y=v=>h-B-v/max*(h-T-B);
        let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Input context and cached input for each recorded request">`;
        for(let i=0;i<3;i++){const value=max*(1-i/2);svg+=`<line x1="${L}" x2="${w-R}" y1="${y(value)}" y2="${y(value)}" stroke="var(--line)"/><text x="${L-7}" y="${y(value)+4}" class="chart-text" text-anchor="end">${compact(value)}</text>`}
        svg+=`<polyline points="${rs.map((r,i)=>x(i)+','+y(r.input)).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/><polyline points="${rs.map((r,i)=>x(i)+','+y(r.cached)).join(' ')}" fill="none" stroke="var(--green)" stroke-width="2"/>`;
        rs.forEach((r,i)=>{svg+=`<circle tabindex="0" role="button" aria-label="Inspect usage observation ${r.step}" data-observation="${esc(r.id)}" cx="${x(i)}" cy="${y(r.input)}" r="3" fill="var(--accent)"><title>${esc('Request '+r.step+' · '+r.date+' · '+integer(r.input)+' input · '+integer(r.cached)+' cached · '+moneyRange(r.cost,r.cost_high))}</title></circle>`;if(i%Math.max(1,Math.ceil(rs.length/10))===0)svg+=`<text x="${x(i)}" y="${h-5}" class="chart-text" text-anchor="middle">${r.step}</text>`});
        $('session-timeline').innerHTML=svg+'</svg><div class="legend"><span><i class="dot"></i>Total input</span><span><i class="dot" style="background:var(--green)"></i>Cached input</span><span>Horizontal axis: request number in the recorded session</span></div>';
    }else $('session-timeline').innerHTML='<div class="empty">No usage observations within the selected filters.</div>';
    renderSessionEvidence(id,rs);
    if(!$('session-dialog').open)$('session-dialog').showModal();
}
function miniCards(values){return values.map(([label,value,note])=>`<div class="card"><label>${esc(label)}</label><div class="value">${value}</div><small>${esc(note)}</small></div>`).join('')}
function componentCost(a,index){
    return a.requests>a.unpriced?moneyRange(a.parts[index],a.parts[index]+(index===2?Math.max(0,a.cost_high-a.cost):0)):'—';
}
function renderTokenBreakdown(a){
    $('search-cost').hidden=!(a.parts[4]>0);$('search-cost').textContent='Web search: '+componentCost(a,4)+' estimated API cost, included in the total in addition to token costs.';
    const parts=[['uncached_input','Uncached input',a.input-a.cached-a.write],['cache_reads','Cache reads',a.cached],['cache_writes','Cache writes',a.write],['output','Output',a.output]];
    $('token-cards').innerHTML=parts.map(([id,label,tokens],index)=>`<div class="card" data-component="${id}"><label>${label}</label><div class="value" title="${integer(tokens)} tokens">${a.requests?compact(tokens):'—'}</div><div class="component-cost">${componentCost(a,index)} <small>estimated API cost</small></div><small>${integer(tokens)} recorded tokens</small></div>`).join('');
}
function renderStatistics(rs,ar,a,d){
    $('context-cards').innerHTML=miniCards([['Largest input',ar.length?compact(a.max_context):'—','Peak input in the selected requests'],['Largest tool result',d.traceRecords?bytes(d.stats.max_tool_bytes||0):'—','Observed local UTF-8 payload'],['Tool calls',d.traceRecords?integer(d.stats.tool_calls||0):'—','Recorded structured calls']]);
    bars('context-chart',groups(rs,'session').sort((a,b)=>b.max_context-a.max_context).slice(0,8).map(g=>({...g,label:sessionLabel(g.name)})),'max_context');
    $('tool-chart').innerHTML=d.traceRecords?`<div class="mini-grid">${miniCards([['Recorded tool results',bytes(d.stats.tool_bytes||0),integer(d.stats.tool_results||0)+' results'],['Tool calls',integer(d.stats.tool_calls||0),'Structured calls before usage observations']])}</div>`:'<div class="empty">No message/tool telemetry available.</div>';
    $('tool-coverage').textContent=`${integer(d.traceRecords)} / ${integer(ar.length)} records have message/tool telemetry. Payloads are associated with the next observed usage event; their exact billed token impact is unavailable.`;
    $('cache-cards').innerHTML=miniCards([['Cache reads',a.requests?compact(a.cached):'—',componentCost(a,1)+' estimated API cost'],['Cache writes',a.requests?compact(a.write):'—',componentCost(a,2)+' estimated API cost'],['Uncached input',a.requests?compact(a.input-a.cached-a.write):'—',componentCost(a,0)+' estimated API cost'],['Cache read share',pct(a.cache),'Cache reads / all input tokens']]);
    $('cache-table').innerHTML='<thead><tr><th>Model</th><th>Total input</th><th>Uncached input</th><th>Cache reads</th><th>Cache writes</th><th>Read share</th><th>Uncached cost</th><th>Read cost</th><th>Write cost</th></tr></thead><tbody>'+groups(rs,'model').sort((a,b)=>b.input-a.input).map(g=>`<tr><td>${esc(g.name)}</td><td>${integer(g.input)}</td><td>${integer(g.input-g.cached-g.write)}</td><td>${integer(g.cached)}</td><td>${integer(g.write)}</td><td>${pct(g.cache)}</td><td>${componentCost(g,0)}</td><td>${componentCost(g,1)}</td><td>${componentCost(g,2)}</td></tr>`).join('')+'</tbody>';

}
function renderPricingGaps(ar,a,previous=null,priorRecords=[]){
    const missing=[...ar,...priorRecords].filter(r=>r.cost==null),groups=new Map();
    for(const r of missing){
        const status=r.price_status||'unknown_model';
        const reason=r.model==='unknown'?'Model not recorded in the trace':r.model==='codex-auto-review'&&status==='unknown_model'?'Internal approval-review model; no verified API rate':({unknown_model:'Model absent from the price catalog',unpriced_tier:'No rate for this processing mode',unknown_tier:'Unknown processing mode',unpriced_cache_write:'No cache-write rate',missing_or_overlapping_date_rate:'Missing or overlapping dated rates'}[status]||status);
        const key=JSON.stringify([r.provider,r.model,reason]);
        if(!groups.has(key))groups.set(key,{provider:r.provider,model:r.model,reason,requests:0,input:0,output:0});
        const g=groups.get(key);g.requests++;g.input+=r.input;g.output+=r.output;
    }
    $('pricing-gaps').hidden=!(a.unpriced||previous?.unpriced);
    $('pricing-title').textContent='Excluded from cost · Details';
    $('pricing-coverage').textContent=`Priced ${integer(a.requests-a.unpriced)} of ${integer(a.requests)} requests (${pct(a.requests?(a.requests-a.unpriced)/a.requests:null)}). Cost totals and comparisons use priced requests only. Excluded: ${integer(a.unpriced)} current${previous?'; '+integer(previous.unpriced)+' previous':''}. Usage counts and tokens still include all recorded requests.`;
    $('pricing-table').innerHTML='<thead><tr><th>Provider / model</th><th>Requests</th><th>Input</th><th>Output</th><th>Why no price</th></tr></thead><tbody>'+[...groups.values()].sort((a,b)=>b.requests-a.requests).map(g=>`<tr><td>${esc(g.provider+' / '+g.model)}</td><td>${integer(g.requests)}</td><td>${compact(g.input)}</td><td>${compact(g.output)}</td><td>${esc(g.reason)}</td></tr>`).join('')+'</tbody>';
}
function render(){
    const range=selectedRange(),previous=previousRange(range),rs=D.rows.filter(r=>chosen(r,range)),priorRows=D.rows.filter(r=>chosen(r,previous)),ar=selectedRecords(),d=telemetry(ar),a=aggregate(rs),b=aggregate(priorRows);
    const values=[
        ['cost','API cost · priced requests',cost(a),'Known prices only · compared on the same basis',usageDelta(a,b,'cost',previous)],
        ['sessions','Sessions',integer(a.sessions.size),'Distinct recorded sessions',usageDelta(a,b,'sessions',previous)],
        ['cache','Cache read share',pct(a.cache),'Cache reads / total input',usageDelta(a,b,'cache',previous)],
        ['uncached','Uncached input cost',a.requests>a.unpriced?usd(a.parts[0]):'—','Includes fresh prompts and prefixes',''],
    ];
    $('cards').innerHTML=values.map(([id,label,value,note,delta])=>`<div class="card" id="card-${id}"><label>${label}</label><div class="value">${value}</div><small>${note}</small>${delta?`<span class="delta">${esc(delta)}</span>`:''}</div>`).join('');
    $('usage-strip').innerHTML=`<span><b id="requests-value">${integer(a.requests)}</b> requests</span><span>In <b>${compact(a.input)}</b></span><span>Out <b>${compact(a.output)}</b></span>${previous?`<span id="requests-delta">Requests: ${esc(usageDelta(a,b,'requests',previous))}</span>`:''}`;
    $('comparison-note').textContent=comparisonNote(range,previous,rs,priorRows);
    $('comparison-coverage').textContent=comparisonCoverage(range,previous,rs,priorRows);
    const grok=(D.grok_records||[]).filter(r=>range&&r.date>=range.from&&r.date<=range.to);
    $('grok-usage').hidden=!grok.length;
    const grokMissing=grok.filter(r=>r.incomplete).length,grokSum=key=>grok.reduce((n,r)=>n+(r[key]||0),0);
    $('grok-title').textContent='Grok · '+usd(grokSum('reported_cost_usd'))+(grokMissing?' known reported · ':' reported · ')+integer(grokSum('model_calls'))+' model calls';
    $('grok-note').textContent=integer(grok.length)+' completed turns · '+compact(grokSum('input'))+' input / '+compact(grokSum('output'))+' output tokens. Selected dates, all Grok projects. '+(grokMissing?integer(grokMissing)+' turn has incomplete usage. ':'')+'Shown separately from the Claude/Codex API estimate: Grok records turn totals and provider-reported cost, which cannot be repriced reliably per request.';
    syncFilterControls();
    $('money-note').textContent='Claude + Codex · '+(D.price_basis==='current_rates'?'Current rates ('+D.price_as_of+') for all dates':'Custom rates')+' · Priced requests only for cost and comparison · API estimate, not a bill.'+(a.write_unknown?' Cache-write price shown as a range.':'');
    const metric=$('chartmetric').value;daily(rs,priorRows,metric,range,previous);bars('models-chart',groups(rs,'model').sort((a,b)=>b[metric]-a[metric]).slice(0,8),metric);bars('projects-chart',groups(rs,'project').sort((a,b)=>b[metric]-a[metric]).slice(0,8),metric);providersTable(rs,priorRows,previous);
    bars('parts',['Uncached input','Cache reads','Cache writes','Output','Web search'].map((name,i)=>({name,cost:a.parts[i],cost_high:a.parts[i]+(i===2?Math.max(0,a.cost_high-a.cost):0),requests:a.requests,unpriced:a.unpriced})));
    modelsTable(rs);sessionsTable(rs);renderTokenBreakdown(a);renderStatistics(rs,ar,a,d);renderPricingGaps(ar,a,previous?b:null,previous?records.filter(r=>chosen(r,previous)):[]);
}
for(const field of ['from','to','provider','model','project','role','pool','chartmetric','session-sort'])$(field).addEventListener('change',()=>{if(field==='from'||field==='to')$('period').value='custom';page=0;render()});
$('period').addEventListener('change',()=>{setPeriod($('period').value);page=0;render()});$('search').addEventListener('input',()=>{page=0;render()});$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render()};
$('filter-toggle').onclick=()=>{const expanded=$('extra-filters').hidden;$('extra-filters').hidden=!expanded;$('filter-toggle').setAttribute('aria-expanded',String(expanded))};
$('reset').onclick=()=>{setPeriod('7');for(const f of ['provider','model','project','role','pool','search'])$(f).value='';$('extra-filters').hidden=true;$('filter-toggle').setAttribute('aria-expanded','false');page=0;render()};
document.addEventListener('click',event=>{const b=event.target.closest('[data-session]');if(b)openSession(b.dataset.session)});
const tabs=[...document.querySelectorAll('[data-tab]')];tabs.forEach((button,index)=>{button.onclick=()=>showTab(button.dataset.tab);button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;showTab(tabs[next].dataset.tab);tabs[next].focus()}});

const sessionMetadata=new Map((D.session_details||[]).map(s=>[s.id,s]));
const observedTime=ts=>ts==null?'Not recorded':new Date(ts*1000).toISOString().replace('T',' ').replace('.000Z',' UTC');
function sourceReferences(refs){
    return refs.length?'<ul>'+refs.map(ref=>`<li><code>${esc(ref.source_id.slice(0,12))}</code> · line ${integer(ref.line)} · byte ${integer(ref.byte_offset)}<details><summary>Record fingerprint</summary><code style="overflow-wrap:anywhere">${esc(ref.record_sha256)}</code></details></li>`).join('')+'</ul>':'<p>No source reference recorded.</p>';
}
function renderSessionEvidence(id,rs){
    const meta=sessionMetadata.get(id),range=selectedRange();
    $('observation-detail').hidden=true;
    if(meta){
        const tree=new Set(meta.tree_sessions),total=aggregate(recordRows(selectedRecords().filter(r=>tree.has(r.session))));
        $('session-cards').innerHTML+=miniCards([['Tree API estimate',cost(total),'Session + confirmed descendants; selected filters'],['Last seen',observedTime(meta.last_seen),'Lifetime observation; current state unknown'],['Recorded compactions',integer(meta.compactions),'Lifetime events; composition unavailable']]);
        const links=[...(meta.parent_session?[['Parent',meta.parent_session]]:[]),...meta.children.map(child=>['Child',child])];
        $('session-lifecycle').innerHTML=`<p>Observed span: ${meta.elapsed_seconds==null?'unavailable':integer(meta.elapsed_seconds)+' seconds'}, including idle time. Active time is unavailable. Last lifecycle event: ${esc(meta.last_recorded_lifecycle||'not recorded')}. ${meta.context_since_compaction==='unavailable'?(meta.compactions?'No fresh input observation after the latest compaction.':'No recorded input observation.'):''}</p>`+links.map(([label,sid])=>`<span>${label}: <button data-session="${esc(sid)}">${esc(sessionLabel(sid))}</button></span>`).join(' ');
    }else $('session-lifecycle').textContent='No lifecycle evidence in this snapshot.';
    const preview=D.event_previews?.[id]||[],events=preview.filter(e=>e.date&&range&&e.date>=range.from&&e.date<=range.to&&(!$('model').value||!e.model||e.model===$('model').value));
    $('events-note').textContent=`${integer(events.length)} events shown for these dates from the latest ${integer(preview.length)} retained in this session’s offline preview. Full history and pagination: session --session ${id} --json. The database contains ${integer(meta?.event_count||preview.length)} lifetime events. Missing timestamps cannot be placed in this date range.`;
    $('events-table').innerHTML='<thead><tr><th>Observed time</th><th>Event</th><th>Recorded details</th><th>Evidence</th></tr></thead><tbody>'+events.map(e=>`<tr><td>${esc(observedTime(e.ts))}</td><td>${esc(e.kind.replaceAll('_',' '))}</td><td>${esc(e.tool||e.role||e.model||'')}${e.result_bytes!=null?' · '+bytes(e.result_bytes):e.kind==='tool_result'?' · size unavailable':''}${e.error===true?' · error recorded':''}</td><td><details><summary>Source ${integer(e.evidence[0]?.line||0)}</summary>${sourceReferences(e.evidence)}</details></td></tr>`).join('')+'</tbody>';
}
function inspectObservation(id){
    const r=records.find(r=>r.id===id);if(!r)return;
    $('observation-detail').innerHTML=`<h3>Usage observation ${integer(r.step)}</h3><p>${esc(observedTime(r.ts))} · ${esc(r.model)}</p><p>Measured input: ${integer(r.input)} · cache reads: ${integer(r.cached)} · output: ${integer(r.output)}.</p><p>Estimated API cost: ${moneyRange(r.cost,r.cost_high)}. Price status: ${esc(r.price_status||'unknown')}.</p><p>Context composition and billed tool attribution: unavailable.</p><h3>Source records</h3>${sourceReferences(r.evidence||[])}<small>File paths are available in the local session JSON and sessions.sqlite. Conversation text and tool payloads are not copied into this report.</small>`;
    $('observation-detail').hidden=false;$('observation-detail').scrollIntoView({block:'nearest'});
}
function navigateEvidence(target){
    if(target.dataset.day){$('from').value=target.dataset.day;$('to').value=target.dataset.day;$('period').value='custom';page=0;render();showTab('sessions')}
    else if(target.dataset.observation)inspectObservation(target.dataset.observation);
    else if(target.dataset.breakdown){
        if(target.dataset.breakdown==='context-chart'){openSession(target.dataset.value);return}
        const name=target.dataset.breakdown==='models-chart'?'model':'project';$(name).value=target.dataset.value;page=0;render();showTab('sessions');
    }
}
document.addEventListener('click',event=>{const target=event.target.closest('[data-day],[data-observation],[data-breakdown]');if(target)navigateEvidence(target)});
document.addEventListener('keydown',event=>{if(!['Enter',' '].includes(event.key)||event.target.tagName.toLowerCase()==='button')return;const target=event.target.closest('[data-day],[data-observation]');if(target){event.preventDefault();navigateEvidence(target)}});
$('measurement-basis').innerHTML=Object.entries(D.measurement_basis||{}).map(([name,value])=>`<p><span class="tag">${esc(value.kind)}</span> <b>${esc(name.replaceAll('_',' '))}</b> — ${esc(value.basis)}</p>`).join('');
$('close-session').onclick=()=>$('session-dialog').close();
$('theme').onclick=()=>{const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';$('theme').textContent=dark?'Light theme':'Dark theme';$('theme').setAttribute('aria-label','Switch to '+(dark?'light':'dark')+' theme')};
$('method').innerHTML=`<p>Local Claude and Codex traces. Duplicate usage records are removed. Missing traces cannot be recovered; chat contents stay on this device.</p><p>API-equivalent prices as of ${esc(D.price_as_of)}, not subscription charges. Unknown prices stay unknown; cache-write uncertainty is shown as a range. Input includes cached tokens.</p><p><a href="https://developers.openai.com/api/docs/pricing" target="_blank" rel="noreferrer">OpenAI pricing</a> · <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noreferrer">Claude pricing</a></p>`;
$('footer').textContent=`AISAD ${D.version} · On-demand snapshot · Rerun the command to update`;render();
$('interactive-dashboard').hidden=false;$('saved-summary').hidden=true;
// Release the serialized copy after the interactive report is ready.
$('snapshot').textContent='';
// A saved snapshot makes no polling or collection requests.
})().catch(error=>{
    console.error('AISAD report could not initialize',error);
    document.getElementById('startup-note').textContent='Interactive charts could not load. The saved totals below remain available. Try reopening this file in an up-to-date browser.';
});
</script></body></html>'''

def saved_summary(snapshot):
    """Render useful totals before JavaScript, including script-disabled previews."""
    rows=snapshot.get('rows',[])
    today=snapshot.get('as_of_date') or snapshot.get('generated','')[:10]
    intro='<h2>Saved usage summary</h2><p id="startup-note" class="panel-intro">Interactive charts require JavaScript. These saved totals are available without it.</p>'
    if not today:
        return intro+'<p>No usage snapshot is available.</p>'
    end=dt.date.fromisoformat(today);monday=end-dt.timedelta(days=end.weekday())
    periods=[('Last 7 days',end-dt.timedelta(days=6),end),
             ('This week · Mon–today',monday,end),
             ('Last week · Mon–Sun',monday-dt.timedelta(days=7),monday-dt.timedelta(days=1)),
             ('All time',None,None)]
    cards=[]
    for label,start,stop in periods:
        selected=[r for r in rows if start is None or start.isoformat()<=r['date']<=stop.isoformat()]
        dates=[r['date'] for r in selected]
        bounds=(start.isoformat()+' – '+stop.isoformat()) if start else (min(dates)+' – '+max(dates) if dates else 'No recorded dates')
        count=sum(r.get('requests',0) for r in selected);missing=sum(r.get('unpriced',0) for r in selected)
        low=sum(r.get('cost') or 0 for r in selected);high=sum(r.get('cost_high') or r.get('cost') or 0 for r in selected)
        amount=(f'${low:,.2f}'+(f'–${high:,.2f}' if high-low>.005 else '')) if count>missing else '—'
        sessions=len({r['session'] for r in selected})
        tokens=sum(r.get('input',0) for r in selected);output=sum(r.get('output',0) for r in selected)
        note=f'{missing:,} requests excluded from cost.' if missing else ('No records in this period.' if not count else 'All recorded requests have prices.')
        cards.append('<article class="card"><h3>'+html.escape(label)+'</h3><small>'+html.escape(bounds)+'</small><div class="value">'+amount+'</div><p>'+f'{count:,} requests · {sessions:,} sessions'+'</p><small>'+f'Input {tokens:,} · Output {output:,}'+'</small><p class="muted">'+note+'</p></article>')
    basis='Current rates for all dates' if snapshot.get('price_basis')=='current_rates' else 'Snapshot rates'
    return intro+'<div class="cards">'+''.join(cards)+'</div><p class="money-note">Claude + Codex · '+basis+' · Known API estimates, not subscription charges. Unpriced requests excluded from cost. Updated '+html.escape(snapshot.get('generated',today))+'</p>'

def render_html(snapshot):
    payload=json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))
    # Large histories otherwise put hundreds of MB in one HTML text node.
    # Embedded compression preserves every field and needs no fetch or server.
    if len(payload)>1_000_000:
        packed=base64.b64encode(gzip.compress(payload.encode('utf-8'),compresslevel=6,mtime=0)).decode('ascii')
        payload=json.dumps(dict(encoding='gzip-base64',data=packed),separators=(',',':'))
    payload=payload.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return HTML.replace('__SAVED_SUMMARY__',saved_summary(snapshot)).replace('__DATA__',payload)

def parser():
    p=argparse.ArgumentParser(description='Local Codex / Claude dashboard. Python 3.9+, no SSH, API keys, uploads or pip packages.')
    p.add_argument('command',nargs='?',choices=['dashboard','usage','analyze','statusline','collect','sessions','session'],default='dashboard',help='One-shot dashboard, usage, collection, or session evidence; analyze aliases usage')
    p.add_argument('--json',action='store_true',help='Emit one JSON object to stdout')
    p.add_argument('--days',type=int,default=7,help='Usage: number of calendar days, default 7')
    p.add_argument('--all-time',action='store_true',help='Usage: include all recorded dates, without a comparison')
    p.add_argument('--from',dest='date_from',help='Usage: inclusive start date, YYYY-MM-DD')
    p.add_argument('--to',dest='date_to',help='Usage: inclusive end date, YYYY-MM-DD')
    p.add_argument('--provider',help='Usage: Codex/OpenAI or Claude/Anthropic')
    p.add_argument('--model',help='Usage: filter by model ID')
    p.add_argument('--project',help='Usage: filter by exact project name')
    p.add_argument('--role',choices=['main','subagent','review'],help='Usage: filter by agent role')
    p.add_argument('--pool',choices=['interactive','managed'],help='Filter the report by spend pool')
    p.add_argument('--managed-session',action='append',default=[],metavar='PROVIDER:ID',help='Tag a managed session and its confirmed descendants; repeat as needed')
    p.add_argument('--budget',type=float,help='Optional shared interactive budget in USD for the selected period, across providers and projects')
    p.add_argument('--managed-budget',type=float,help='Optional separate managed-agent budget in USD')
    p.add_argument('--session',help='Session detail or one-shot status: provider-prefixed session ID')
    p.add_argument('--stdin',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--no-color',action='store_true',help='Status line: disable ANSI colors')
    p.add_argument('--include-events',action='store_true',help='Include a paginated metadata timeline and source references in usage JSON')
    p.add_argument('--tree',action='store_true',help='Session detail: include confirmed descendants')
    p.add_argument('--limit',type=int,default=200,help='Maximum timeline events returned, 1–10000')
    p.add_argument('--offset',type=int,default=0,help='Timeline pagination offset')
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
    p.add_argument('--watch',type=float,default=None,metavar='SECONDS',help=argparse.SUPPRESS)
    p.add_argument('--open',action='store_true',help='Open the saved offline HTML in a browser; the collector exits')
    p.add_argument('--version',action='version',version=VERSION)
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    if args.watch is not None or args.stdin:
        raise SystemExit('AISAD runs on demand. Rerun usage, collect, sessions, session or dashboard when needed; watching and status hooks are no longer supported.')
    for value in [args.budget,args.managed_budget]:
        if value is not None and (not math.isfinite(value) or value<=0):raise SystemExit('Budgets must be finite positive USD amounts')
    if args.offset<0 or not 1<=args.limit<=10000:raise SystemExit('--offset must be nonnegative and --limit must be between 1 and 10000')
    if args.command=='session' and not args.session:raise SystemExit('session requires --session PROVIDER:ID; use sessions --json to find an ID')
    if args.open and args.command!='dashboard':raise SystemExit('--open is available only for dashboard')
    if args.write_prices:atom_json(Path(args.write_prices),default_prices());print(args.write_prices);return
    output=Path(args.output).expanduser().resolve()
    snap=make_snapshot(args,dashboard=args.command=='dashboard',include_requests=True)
    if args.command=='dashboard':
        t=snap['summary']
        print(f"{snap['generated']} | {t['requests']:,} usage observations | {t['sessions']} sessions | API estimate ${t['cost']:.2f}–${t['cost_high']:.2f} | unpriced {t['unpriced']}")
        print(str(output/'dashboard.html'))
        if args.open:webbrowser.open((output/'dashboard.html').as_uri())
        return
    if args.command=='collect':
        result=dict(schema_version=EVIDENCE_SCHEMA,version=VERSION,generated=snap['generated'],
                    database=str(output/'sessions.sqlite'),events=len(snap['events']),sessions=len(snap['session_details']),
                    usage_observations=len(snap['requests']),sources=len(snap['source_files']),quality=snap['quality'],scan=snap['scan'])
        print(json.dumps(result,ensure_ascii=False,allow_nan=False) if args.json else
              f"Collected {result['events']:,} events, {result['usage_observations']:,} usage observations and {result['sessions']:,} sessions. Database: {result['database']}")
        return
    if args.command in ('sessions','session'):
        result=evidence_report(snap,args);atom_json(output/'session-report.json',result)
        if args.json:print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        else:
            print('Recorded sessions for '+result['period']['from']+'–'+result['period']['to']+':')
            for item in result['sessions']:
                value=item['own']['estimated_cost_usd'];cost='unpriced' if value is None else f'${value:,.2f}'
                if item['own']['unpriced_requests']:cost+=' + unpriced observations'
                print(f"{item['id']} | {item['project']} | {item['own']['requests']} usage observations | {cost} estimated API cost | {item['event_count']} events")
            print(f"Timeline: {result['events_total']} events. Use --json for source references and --offset/--limit for pagination.")
        return
    result=usage_report(snap,args);atom_json(output/'usage-report.json',result)
    if args.command=='statusline':
        result=statusline_report(snap,result,args);atom_json(output/'statusline.json',result)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False) if args.json else statusline_text(result))
    else:print(json.dumps(result,ensure_ascii=False,allow_nan=False) if args.json else usage_text(result))

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit(130)
    except (OSError,ValueError,KeyError,sqlite3.Error) as e:raise SystemExit('Error: '+str(e))
