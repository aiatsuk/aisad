#!/usr/bin/env python3
"""Render a deterministic example using temporary synthetic profiles only."""
import collections
import datetime as dt
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_usage as app


def write_trace(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')


def build_demo():
    rng = random.Random(42)
    start = dt.datetime(2026, 8, 9, 9, tzinfo=dt.timezone.utc)
    models = ['gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra',
              'claude-opus-5', 'claude-sonnet-4-6', 'claude-haiku-4-5']
    projects = ['atlas-api', 'design-system', 'mobile-app', 'data-pipeline', 'docs-site']
    with tempfile.TemporaryDirectory(prefix='aisad synthetic demo ') as folder:
        profile = Path(folder) / 'profile'
        registry = []
        for day in range(28):
            for session in range(rng.randint(4, 11)):
                model = rng.choices(models, weights=[10, 25, 15, 25, 20, 5])[0]
                project = rng.choices(projects, weights=[35, 20, 25, 15, 5])[0]
                sid = f'demo-{day + 1:02d}-{session + 1:02d}'
                subagent = rng.random() < .28
                claude = model.startswith('claude')
                cwd = '/demo/projects/' + project
                records = []
                if claude:
                    parent = profile / '.claude/projects' / project
                    trace = (parent / sid / 'subagents/agent.jsonl' if subagent
                             else parent / (sid + '.jsonl'))
                else:
                    trace = profile / '.codex/sessions' / (sid + '.jsonl')
                    registry.append((sid, model, cwd, '/root/worker' if subagent else '/root'))
                    records.extend([
                        {'type': 'session_meta', 'payload': {
                            'id': sid, 'cwd': cwd, 'agent_path': registry[-1][3]}},
                        {'type': 'turn_context', 'payload': {
                            'model': model, 'service_tier': 'standard'}},
                    ])
                cumulative = collections.Counter()
                for request in range(rng.randint(8, 32)):
                    moment = start + dt.timedelta(days=day, hours=session, minutes=request)
                    incoming = rng.randint(12000, 140000)
                    cached = int(incoming * rng.uniform(.55, .94))
                    output = rng.randint(300, 6500)
                    if claude:
                        write = min(incoming - cached, rng.randint(500, 2500))
                        usage = dict(input_tokens=incoming-cached-write,
                                     cache_read_input_tokens=cached,
                                     cache_creation_input_tokens=write,
                                     cache_creation={'ephemeral_5m_input_tokens': write},
                                     output_tokens=output, service_tier='standard',
                                     inference_geo='global',
                                     server_tool_use={'web_search_requests': int(rng.random() < .08)})
                        records.append(dict(type='assistant', timestamp=moment.isoformat(), cwd=cwd,
                                            message=dict(id=sid + '-' + str(request), model=model, usage=usage)))
                    else:
                        usage = dict(input_tokens=incoming, cached_input_tokens=cached,
                                     output_tokens=output, total_tokens=incoming+output)
                        cumulative.update(usage)
                        records.append(dict(type='event_msg', timestamp=moment.isoformat(),
                                            payload=dict(type='token_count', info=dict(
                                                last_token_usage=usage, total_token_usage=dict(cumulative)))))
                write_trace(trace, records)
        database = sqlite3.connect(profile / '.codex/state_1.sqlite')
        try:
            database.execute('CREATE TABLE threads(id TEXT, model TEXT, cwd TEXT, agent_path TEXT)')
            database.executemany('INSERT INTO threads VALUES (?,?,?,?)', registry)
            database.commit()
        finally:
            database.close()
        billing = Path(folder) / 'billing.csv'
        billing.write_text('transaction_id,date,provider,amount_usd\n'
                           'demo-payment-1,2026-09-01,Claude,100\n'
                           'demo-payment-2,2026-09-01,Codex,200\n', encoding='utf-8')
        args = app.parser().parse_args(['--home', str(profile), '--output', str(Path(folder) / 'report'),
                                       '--billing', str(billing), '--timezone', 'UTC'])
        snapshot = app.make_snapshot(args)
    snapshot.pop('sources', None)
    snapshot.update(device='demo-device', generated='2026-09-05T12:00:00+00:00', demo=True)
    destination = ROOT / 'output/demo/dashboard.html'
    app.atom_write(destination, app.render_html(snapshot).encode('utf-8'))
    print('Synthetic example: ' + str(destination))


if __name__ == '__main__':
    build_demo()
