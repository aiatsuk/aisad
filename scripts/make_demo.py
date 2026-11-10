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


def telemetry_examples(profile, start):
    """Varied contexts, tool payloads and cache counters pass through the real trace parser."""
    patterns = {
        'short-session': ([20000, 22000, 24000], 'standard'),
        'large-tool-result': ([40000, 110000, 115000], 'standard'),
        'growing-context': ([100000, 220000, 240000, 280000, 300000], 'standard'),
        'cache-after-break': ([150000, 155000, 160000, 165000], 'standard'),
        'priority-build': ([80000, 90000, 100000, 110000], 'priority'),
        'managed-pipeline': ([80000, 130000, 200000, 240000], 'standard'),
    }
    for number, (sid, (sizes, tier)) in enumerate(patterns.items()):
        events = [dict(type='session_meta', payload=dict(id=sid, cwd='/demo/projects/atlas-api')),
                  dict(type='turn_context', payload=dict(model='gpt-6-astra', service_tier=tier))]
        cumulative = collections.Counter()
        for index, incoming in enumerate(sizes):
            moment = start + dt.timedelta(days=22 + number % 5, minutes=index * 15)
            cached = int(incoming * (.05 if sid == 'cache-after-break' and index % 2 else .8))
            count = 6 if sid == 'large-tool-result' and index == 1 else 1
            for call in range(count):
                key = sid + '-' + str(index) + '-' + str(call)
                events.append(dict(type='response_item', payload=dict(type='function_call', call_id=key,
                    name='mcp__build__status' if count == 6 else 'mcp__files__read', arguments='{}')))
                size = 46000 if sid == 'large-tool-result' and index == 1 and call == 0 else 1200
                events.append(dict(type='response_item', payload=dict(type='function_call_output', call_id=key,
                    output='x' * size)))
            usage = dict(input_tokens=incoming, cached_input_tokens=cached, output_tokens=1000,
                         total_tokens=incoming + 1000)
            cumulative.update(usage)
            events.append(dict(type='event_msg', timestamp=moment.isoformat(), payload=dict(type='token_count',
                info=dict(last_token_usage=usage, total_token_usage=dict(cumulative)))))
        write_trace(profile / '.codex/sessions' / (sid + '.jsonl'), events)


class FitTrace:
    """One synthetic Claude Code transcript with typed prompts, tool calls and effort.

    Each reply re-reads the previous context from cache and writes the new part;
    a reply after a model switch or a long idle gap writes the whole context again.
    """
    def __init__(self, path, project, when):
        self.path, self.cwd, self.when = path, '/demo/projects/' + project, when
        self.records, self.count, self.context, self.model, self.last = [], 0, 0, None, None

    def prompt(self, text, minutes=1):
        self.when += dt.timedelta(minutes=minutes)
        self.records.append(dict(type='user', timestamp=self.when.isoformat(), origin={'kind': 'human'},
                                 cwd=self.cwd, message=dict(role='user', content=text)))

    def reply(self, model, effort, context, tools=(), minutes=1, output=3000):
        self.when += dt.timedelta(minutes=minutes)
        self.count += 1
        mid = f'{self.path.stem}-r{self.count}'
        idle = self.last is not None and (self.when - self.last).total_seconds() > 300
        fresh = model != self.model or idle or context < self.context
        self.last = self.when
        read = 0 if fresh else self.context
        write = context - read - 300
        content = [dict(type='tool_use', id=f'{mid}-t{i}', name=name, input=args)
                   for i, (name, args) in enumerate(tools)] or [dict(type='text', text='done')]
        self.records.append(dict(type='assistant', timestamp=self.when.isoformat(), cwd=self.cwd, effort=effort,
                                 message=dict(id=mid, model=model, role='assistant', content=content, usage=dict(
                                     input_tokens=300, cache_read_input_tokens=read,
                                     cache_creation_input_tokens=write,
                                     cache_creation={'ephemeral_5m_input_tokens': write},
                                     output_tokens=output, service_tier='standard'))))
        self.model, self.context = model, context

    def save(self, meta=None):
        write_trace(self.path, self.records)
        if meta is not None:
            self.path.with_name(self.path.stem + '.meta.json').write_text(json.dumps(meta), encoding='utf-8')


def fit_examples(profile, start):
    """Claude Code sessions on current models for the Model fit tab: several task classes,
    work above and below the guide's model, effort above its level, subagents with and
    without a model, a model switch, a cold cache rewrite and effort changes."""
    root = profile / '.claude/projects'
    fable, opus, sonnet, haiku = 'claude-fable-5-2', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'
    read = lambda name: ('Read', {'file_path': f'/demo/src/{name}'})
    edit = lambda name: ('Edit', {'file_path': f'/demo/src/{name}'})

    def main(project, sid, day, hour):
        return FitTrace(root / project / f'{sid}.jsonl', project,
                        start + dt.timedelta(days=day, hours=hour - start.hour))

    def agent(parent, name, minutes=1):
        return FitTrace(parent.path.with_suffix('') / 'subagents' / f'agent-{name}.jsonl',
                        parent.cwd.rsplit('/', 1)[1], parent.when + dt.timedelta(minutes=minutes))

    # Small UI work on the largest model: over, plus an Explore subagent that inherited it.
    ui = main('design-system', 'fit-ui-spacing', 22, 10)
    ui.prompt('Tighten the spacing on the settings form buttons')
    ui.reply(fable, 'high', 32000, [('Agent', {'subagent_type': 'Explore', 'prompt': 'find usages'})])
    for step in range(6):
        ui.reply(fable, 'high', 36000 + step * 3000, [edit('Button.tsx') if step % 2 else read('Form.tsx')])
    ui.prompt('What does the gap prop default to?', 4)
    ui.reply(fable, 'high', 56000)
    scout = agent(ui, 'scout')
    scout.prompt('Find every use of the Button gap prop')
    for step in range(7):
        scout.reply(fable, 'high', 18000 + step * 2500, [('Grep', {'pattern': 'gap'}), read(f'View{step}.tsx')])
    scout.save({'agentType': 'Explore', 'description': 'Find every use of the Button gap prop', 'toolUseId': 'fit-ui-spacing-r1-t0'})
    ui.save()

    # Debugging on Opus at xhigh: effort above the guide, effort changes, a cold rewrite, big context.
    queue = main('atlas-api', 'fit-queue-debug', 24, 14)
    queue.prompt('Debug the flaky race condition in the queue worker retries')
    for step in range(22):
        queue.reply(opus, 'xhigh', 90000 + step * 7000,
                    [edit(f'queue/worker{step % 3}.py') if step % 4 == 3 else read(f'queue/retry{step % 5}.py')])
    queue.reply(opus, 'xhigh', 245000, [('Agent', {'subagent_type': 'code-reviewer', 'model': 'sonnet'})])
    reviewer = agent(queue, 'review')
    reviewer.prompt('Review the retry fix for ordering bugs')
    for step in range(12):
        reviewer.reply(sonnet, 'medium', 40000 + step * 3000, [read(f'queue/retry{step % 5}.py')])
    reviewer.save({'agentType': 'code-reviewer', 'description': 'Review the retry fix', 'model': 'sonnet',
                   'toolUseId': 'fit-queue-debug-r23-t0'})
    queue.prompt('Carry on with the retry fix after lunch', 45)
    queue.reply(opus, 'xhigh', 248000, [read('queue/worker0.py')])
    for step in range(8):
        queue.reply(opus, 'high' if step % 2 else 'xhigh', 250000 + step * 2000, [edit(f'queue/worker{step % 3}.py')])
    queue.save()

    # A migration on Haiku: harder than the guide's model for the task, prompts over 100k.
    migration = main('data-pipeline', 'fit-schema-migration', 25, 9)
    migration.prompt('Migrate the ingest jobs to the new event schema')
    for step in range(30):
        migration.reply(haiku, 'medium', 60000 + step * 2500, [edit(f'jobs/ingest_{step % 12}.py')])
    migration.save()

    # A scoped screen on Sonnet, then a switch to Opus for the wider wiring.
    screen = main('mobile-app', 'fit-settings-screen', 26, 11)
    screen.prompt('Add the notification settings screen')
    for step in range(10):
        screen.reply(sonnet, 'medium', 30000 + step * 4000, [edit('screens/Notifications.tsx') if step % 2 else read('screens/Settings.tsx')])
    screen.prompt('Now wire the screen into navigation, the store and the API client', 3)
    for step in range(18):
        screen.reply(opus, 'high', 72000 + step * 4000, [edit('app/' + ('nav', 'store', 'api', 'hooks', 'types', 'routes')[step % 6] + '.ts')])
    screen.save()

    # A lead run on Fable that splits a release over five subagents.
    lead = main('atlas-api', 'fit-release-lead', 23, 16)
    lead.prompt('Run the release checklist with one agent per package')
    lead.reply(fable, 'high', 40000, [('Agent', {'subagent_type': 'general-purpose', 'model': 'sonnet'})] * 3
               + [('Agent', {'subagent_type': 'Explore', 'model': 'haiku'}), ('Agent', {'subagent_type': 'general-purpose'})])
    for step in range(6):
        lead.reply(fable, 'high', 44000 + step * 3000, [read('RELEASE.md')])
    for number in range(3):
        worker = agent(lead, f'pkg{number}', 2)
        worker.prompt(f'Bump and test package {number}')
        for step in range(10):
            worker.reply(sonnet, 'medium', 25000 + step * 2000, [edit(f'pkg{number}/version.py') if step < 2 else read(f'pkg{number}/test.py')])
        worker.save({'agentType': 'general-purpose', 'description': f'Release package {number}',
                     'toolUseId': f'fit-release-lead-r1-t{number}'})
    finder = agent(lead, 'scan', 2)
    finder.prompt('List the packages changed since the last tag')
    for step in range(5):
        finder.reply(haiku, 'medium', 15000 + step * 1500, [('Grep', {'pattern': 'version'})])
    finder.save({'agentType': 'Explore', 'description': 'List changed packages', 'toolUseId': 'fit-release-lead-r1-t3'})
    notes = agent(lead, 'notes', 3)
    notes.prompt('Summarize the changelog entries for the release notes')
    for step in range(9):
        notes.reply(fable, 'high', 30000 + step * 2500, [read('CHANGELOG.md')])
    notes.save({'agentType': 'general-purpose', 'description': 'Summarize the changelog entries',
                'toolUseId': 'fit-release-lead-r1-t4'})
    lead.save()

    # Documents, research and screen work that fit the guide.
    docs = main('docs-site', 'fit-readme', 21, 13)
    docs.prompt('Update the README install section and the changelog')
    for step in range(7):
        docs.reply(sonnet, 'medium', 22000 + step * 2000, [edit('README.md' if step % 2 else 'CHANGELOG.md')])
    # A run recorded under a dated model ID, as Claude Code writes some of them.
    links = agent(docs, 'links')
    links.prompt('Find broken links in the docs')
    for step in range(4):
        links.reply('claude-haiku-4-5-20251001', 'medium', 12000 + step * 1500, [read(f'docs/page{step}.md')])
    links.save({'agentType': 'Explore', 'description': 'Find broken links in the docs'})
    docs.save()
    research = main('data-pipeline', 'fit-warehouse-research', 27, 9)
    research.prompt('Compare warehouse vendors on pricing and limits')
    for step in range(12):
        research.reply(fable, 'high', 30000 + step * 4000, [('WebSearch', {'query': 'warehouse pricing'}), ('WebFetch', {'url': 'https://example.com'})])
    research.save()
    device = main('mobile-app', 'fit-device-check', 19, 15)
    device.prompt('Check the onboarding flow on the simulator')
    for step in range(10):
        device.reply(opus, 'high', 50000 + step * 6000, [('mcp__iOS_Simulator__control', {'action': 'tap'})])
    device.save()

    # Older sessions, so the period filter changes what the tab shows.
    question = main('atlas-api', 'fit-quick-question', 8, 10)
    question.prompt('How do I rotate the API key?')
    question.reply(fable, 'max', 26000)
    question.reply(fable, 'max', 27000)
    question.save()
    tokens = main('design-system', 'fit-token-refactor', 12, 10)
    tokens.prompt('Refactor the theme tokens across the component library')
    for step in range(40):
        tokens.reply(opus, 'high', 50000 + step * 3000, [edit(f'tokens/component{step % 14}.css')])
    tokens.save()


def build_demo():
    rng = random.Random(42)
    start = dt.datetime(2026, 8, 9, 9, tzinfo=dt.timezone.utc)
    models = ['gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra',
              'claude-opus-5', 'claude-sonnet-4-6', 'claude-haiku-4-5']
    projects = ['atlas-api', 'design-system', 'mobile-app', 'data-pipeline', 'docs-site']
    with tempfile.TemporaryDirectory(prefix='asi synthetic demo ') as folder:
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
        telemetry_examples(profile, start)
        fit_examples(profile, start)
        database = sqlite3.connect(profile / '.codex/state_1.sqlite')
        try:
            database.execute('CREATE TABLE threads(id TEXT, model TEXT, cwd TEXT, agent_path TEXT)')
            database.executemany('INSERT INTO threads VALUES (?,?,?,?)', registry)
            database.commit()
        finally:
            database.close()
        args = app.parser().parse_args(['--home', str(profile), '--output', str(Path(folder) / 'report'),
                                       '--timezone', 'UTC', '--budget', '600', '--managed-budget', '50',
                                       '--managed-session', 'Codex:managed-pipeline'])
        snapshot = app.make_snapshot(args)
    snapshot.pop('sources', None)
    snapshot.update(device='demo-device', generated='2026-09-05T12:00:00+00:00', as_of_date='2026-09-05', demo=True)
    destination = ROOT / 'output/demo/dashboard.html'
    app.atom_write(destination, app.render_html(snapshot).encode('utf-8'))
    args.date_to = '2026-09-05'
    app.atom_json(destination.with_name('expected-usage.json'), app.usage_report(snapshot, args))
    print('Synthetic example: ' + str(destination))


if __name__ == '__main__':
    build_demo()
