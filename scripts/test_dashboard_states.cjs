// Run the shipped report logic with synthetic data and small DOM stubs.
// No browser, file navigation, server, screenshot or personal data is involved.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../agent_usage.py'), 'utf8');
const code = source.split('</script><script>')[1].split('</script>')[0].replace(
  '// Dashboard initialization complete.',
  'Object.assign(testApi,{render,setPeriod,selectedRange,aggregate,showTab,openSession,comparisonData,applyLiveSnapshot,startLiveUpdates});');
const row = (provider, session, date, cost) => ({
  provider, session, date, cost, cost_high:cost, requests:1, unpriced:0,
  model:provider==='Claude'?'claude-sonnet-5.5':'gpt-6.1-sol', project:'web', role:'main',
  pool:'interactive', input:100, cached:80, write:0, output:20, total:120,
  max_context:100, parts:[cost,0,0,0,0], assumed:0, write_unknown:0,
});
const rows = [
  row('Claude','Claude:one','2026-10-22',10),
  row('Codex','Codex:two','2026-10-22',20),
  row('Claude','Claude:previous','2026-10-15',5),
];
const snapshot = {
  version:'test', generated:'2026-10-22T09:00:00Z', as_of_date:'2026-10-22', timezone:'UTC',
  price_as_of:'2026-10-22',price_basis:'models_dev_rates', rows, quality:{},summary:{},
  request_stats:rows.map((r,i)=>({...r, id:'r'+i, step:i+1, ts:Date.parse(r.date)/1000})),
  session_details:[{id:'Claude:events',provider:'Claude',role:'main',project:'web',
    observed_dates:['2026-10-22'],tree_sessions:['Claude:events'],children:[],compactions:0}],
};
async function report(overrides={}, preferences={}) {
  const nodes=new Map(), errors=[], saved=[], scripts=[], lifecycle={};
  const node=id=>{
    if(!nodes.has(id)) nodes.set(id,{
      id,value:'',hidden:false,textContent:'',innerHTML:'',dataset:{},
      attributes:{},events:{},addEventListener(name,fn){this.events[name]=fn;},
      setAttribute(name,value){this.attributes[name]=value;},
      getAttribute(name){return this.attributes[name];},
      showModal(){this.open=true;},close(){this.open=false;},
      scrollIntoView(){},focus(){this.focused=true;},
    });
    return nodes.get(id);
  };
  const tabs=['overview','sessions','context','cache'].map(name=>{
    const n=node('tab-'+name);n.dataset.tab=name;n.attributes['aria-controls']='view-'+name;return n;
  });
  node('snapshot').textContent=JSON.stringify({...snapshot,...overrides});
  node('chartmetric').value='cost';node('chartmetric').selectedOptions=[{textContent:'Estimated cost, USD'}];node('session-sort').value='cost';
  const context=vm.createContext({
    document:{
      getElementById:node,querySelector:s=>node(s),
      querySelectorAll:s=>s==='[data-tab]'?tabs:[],
      addEventListener(name,fn){lifecycle['document:'+name]=fn;},
      removeEventListener(name){delete lifecycle['document:'+name];},documentElement:{dataset:{}},
      createElement:()=>({remove(){this.removed=true;}}),head:{append:tag=>scripts.push(tag)},
    },
    console:{error:(...args)=>errors.push(args.map(value=>value?.stack||String(value)).join(' '))},
    testApi:{},Intl,Date,Blob,Response,DecompressionStream,atob,Uint8Array,
    location:{protocol:preferences.live?'file:':'https:'},
    setTimeout:()=>1,clearTimeout(){},addEventListener:(name,fn)=>{lifecycle[name]=fn;},
    matchMedia:()=>({matches:!!preferences.darkSystem}),
    localStorage:{
      getItem(){if(preferences.storageDenied)throw Error('Storage denied');return preferences.storedTheme;},
      setItem(key,value){if(preferences.storageDenied)throw Error('Storage denied');saved.push([key,value]);},
    },
  });
  await vm.runInContext(code,context);
  assert.deepEqual(errors,[],'report initialization');
  return {node,context,api:context.testApi,saved,scripts,lifecycle};
}
(async()=>{
  const unknown=await report({grok_records:[{date:'2026-10-22',reported_cost_usd:null,incomplete:true,model_calls:1}]});
  assert.match(unknown.node('grok-title').textContent,/cost unavailable/i);
  assert.doesNotMatch(unknown.node('grok-title').textContent,/\$0\.00/);
  const zero=await report({grok_records:[{date:'2026-10-22',reported_cost_usd:0,incomplete:false,model_calls:1}]});
  assert.match(zero.node('grok-title').textContent,/\$0\.00 reported/);
  const partial=await report({grok_records:[
    {date:'2026-10-22',reported_cost_usd:1.25,incomplete:false,model_calls:2},
    {date:'2026-10-22',reported_cost_usd:null,incomplete:true,model_calls:1},
    {date:'2026-10-22',reported_cost_usd:0.5,incomplete:true,model_calls:1},
  ]});
  assert.match(partial.node('grok-title').textContent,/\$1\.75 known reported/);
  assert.match(partial.node('grok-note').textContent,/2 turns have incomplete/);
  assert.equal((await report()).node('grok-usage').hidden,true);
  const r=await report();
  assert.equal(r.node('session-count').textContent,3);
  assert.match(r.node('cards').innerHTML,/Sessions with usage records/);
  assert.match(r.node('cards').innerHTML,/>2<\/div>/);
  r.node('search').value='missing session';r.api.render();
  assert.match(r.node('sessions-table').innerHTML,/No sessions match this search/);
  assert.match(r.node('sessions-table').innerHTML,/colspan="6"/);
  r.node('search').value='';r.api.setPeriod('custom');
  r.node('from').value='2026-10-01';r.node('to').value='2026-10-02';r.api.render();
  for(const id of ['sessions-table','models-table','cache-table'])
    assert.match(r.node(id).innerHTML,/No .* in (this|the) (period|date range)/);
  r.node('from').value='2026-10-22';r.node('to').value='2026-10-22';r.api.render();
  assert.equal(r.node('custom-dates').hidden,false);
  assert.match(r.node('cards').innerHTML,/\$30\.00/);
  r.node('provider').value='Claude';r.api.render();
  assert.match(r.node('cards').innerHTML,/\$10\.00/);
  r.api.showTab('cache');
  assert.equal(r.node('view-cache').hidden,false);
  assert.equal(r.node('view-overview').hidden,true);
  r.api.openSession('Claude:events');
  assert.equal(r.node('session-dialog').open,true);
  assert.match(r.node('session-timeline').innerHTML,/No usage observations/);
  assert.match(r.node('events-table').innerHTML,/No recorded events/);
  assert.match(r.node('footer').textContent,/Open Dashboard in AISAD/);
  assert.match(r.node('subtitle').textContent,/UTC/);

  // Exercise actual local-script callbacks, including asynchronous compressed
  // payloads, stale generations and shutdown; no browser or listener is used.
  const rev=n=>String(n).padStart(20,'0');
  const live=await report({live_updates:true,sync_revision:rev(1)},{live:true});
  assert.match(live.scripts[0].src,/^usage-live[.]js/);
  live.api.setPeriod('today');live.node('provider').value='Claude';live.api.showTab('cache');
  const updated={...snapshot,live_updates:true,sync_revision:rev(3),
    generated:'2026-10-22T10:00:00Z',evidence_generated:'2026-10-22T09:00:00Z',
    rows:rows.map(r=>({...r,cost:r.cost*2,cost_high:r.cost_high*2})),
    request_stats:snapshot.request_stats.map(r=>({...r,cost:r.cost*2,cost_high:r.cost_high*2}))};
  live.context.aisadLiveRevision({revision:rev(3)});
  assert.match(live.scripts[1].src,/^usage-live-data[.]js/);
  const {gzipSync}=require('node:zlib');
  await live.context.aisadLiveData(rev(3),{encoding:'gzip-base64',
    data:gzipSync(JSON.stringify(updated)).toString('base64')});
  live.scripts[1].onload();
  assert.match(live.node('cards').innerHTML,/[$]20[.]00/);
  assert.equal(live.node('provider').value,'Claude');
  assert.equal(live.node('period').value,'today');
  assert.equal(live.node('view-cache').hidden,false);
  assert.match(live.node('footer').textContent,/Shared local data/);
  assert.equal(live.api.applyLiveSnapshot({...updated,sync_revision:rev(2),rows:[]}),false);
  await live.context.aisadLiveData(rev(4),{encoding:'gzip-base64',data:'broken'});
  assert.match(live.node('cards').innerHTML,/[$]20[.]00/);
  // A prepared payload cannot be accepted before its commit marker.
  await live.context.aisadLiveData(rev(9),{...updated,sync_revision:rev(9),rows:[]});
  assert.match(live.node('cards').innerHTML,/[$]20[.]00/);
  const beforeVisible=live.scripts.length;
  live.context.document.hidden=false;live.lifecycle['document:visibilitychange']();
  assert.equal(live.scripts.length,beforeVisible+1);
  const callback=live.context.aisadLiveData;
  live.lifecycle.pagehide();
  assert.equal(live.context.aisadLiveData,undefined);
  await callback(rev(4),{...updated,sync_revision:rev(4),rows:[]});
  assert.match(live.node('cards').innerHTML,/[$]20[.]00/);

  // Compare real shipped JS with independently computed canonical Python windows.
  // This executes no browser and reads only the synthetic values supplied on stdin.
  const {execFileSync}=require('node:child_process');
  async function calendarReport(observations,generated='2026-10-22T09:00:00Z',timezone='UTC') {
    const raw=observations.map(([stamp,amount,provider='Claude'],i)=>({
      ...row(provider,provider+':'+i,stamp.slice(0,10),amount),
      ts:Date.parse(stamp)/1000,
    }));
    const day=generated.slice(0,10);
    const summary=JSON.parse(execFileSync('python3',['-B','-c',
      "import json,sys; import agent_usage as a; s=json.load(sys.stdin); print(json.dumps(a.menubar_report(s,a.parser().parse_args(['menubar','--output','/nonexistent/aisad-synthetic','--timezone',s['timezone']]))))"
    ],{cwd:path.join(__dirname,'..'),input:JSON.stringify({
      generated,timezone,as_of_date:day,request_stats:raw,
    }),encoding:'utf8'}));
    return {summary,ui:await report({rows:raw,request_stats:raw,
      generated,timezone,as_of_date:day,spend_summary:summary})};
  }
  const aligned=await calendarReport([
    ['2026-10-22T08:00:00Z',30],['2026-10-21T08:00:00Z',10],
    ['2026-10-21T18:00:00Z',900],
    ['2026-10-19T08:00:00Z',20,'Codex'],
    ['2026-10-12T08:00:00Z',5],['2026-10-15T08:00:00Z',5],
    ['2026-10-15T18:00:00Z',900],
    ['2026-10-01T08:00:00Z',50],['2026-09-01T08:00:00Z',25],
    ['2026-09-22T08:00:00Z',10],['2026-09-22T18:00:00Z',900],
  ]);
  for(const [preset,id] of [['today','today'],['this-week','week'],['this-month','month']]){
    aligned.ui.api.setPeriod(preset);aligned.ui.api.render();
    const period=aligned.summary.periods.find(p=>p.id===id),c=period.comparison;
    const money=value=>'$'+value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    assert.ok(aligned.ui.node('cards').innerHTML.includes(money(period.known_cost_usd)));
    assert.ok(aligned.ui.node('cards').innerHTML.includes(
      (c.percent>0?'+':'')+c.percent.toFixed(1)+'% · prev '+money(c.previous.known_cost_usd)));
  }
  const overview=aligned.ui.node('calendar-totals').innerHTML;
  aligned.ui.node('provider').value='Codex';aligned.ui.api.render();
  assert.equal(aligned.ui.node('calendar-totals').innerHTML,overview,'global summary ignores detail filters');
  assert.match(aligned.ui.node('cards').innerHTML,/\$20\.00/);
  assert.equal(aligned.ui.node('monthly-target-label').textContent,'Monthly limit $2,000.00');
  assert.match(aligned.ui.node('comparison-coverage').textContent,/same local time/);
  const shortMonth=await calendarReport([
    ['2027-03-01T08:00:00Z',5],['2027-03-28T23:00:00Z',20],
    ['2027-03-29T08:00:00Z',1000],['2027-02-01T08:00:00Z',10],
    ['2027-02-28T23:00:00Z',5],
  ],'2027-03-31T12:00:00Z');
  shortMonth.ui.api.setPeriod('this-month');shortMonth.ui.api.render();
  assert.match(shortMonth.ui.node('cards').innerHTML,/\$1,025\.00/);
  assert.match(shortMonth.ui.node('cards').innerHTML,/\+66\.7% · prev \$15\.00/);
  assert.match(shortMonth.ui.node('comparison-coverage').textContent,/first 28 days/);
  assert.match(shortMonth.ui.node('calendar-totals').innerHTML,/\$1,025\.00/);
  assert.match(shortMonth.ui.node('calendar-totals').innerHTML,/\+\$10\.00 · \+66\.7%/);
  assert.match(shortMonth.ui.node('providers-table').innerHTML,/\+66\.7% · prev \$15\.00/);
  const dst=await calendarReport([
    ['2026-03-09T11:00:00-04:00',20],
    ['2026-03-08T11:59:00-04:00',10],
    ['2026-03-08T12:01:00-04:00',900],
  ],'2026-03-09T12:00:00-04:00','America/New_York');
  dst.ui.api.setPeriod('today');dst.ui.api.render();
  assert.match(dst.ui.node('cards').innerHTML,/\+100\.0% · prev \$10\.00/);
  assert.equal((await report()).node('calendar-spend').hidden,true,'legacy snapshot remains usable');
  const dark=await report({}, {darkSystem:true});
  assert.equal(dark.context.document.documentElement.dataset.theme,'dark');
  dark.node('theme').onclick();
  assert.equal(dark.context.document.documentElement.dataset.theme,'light');
  assert.deepEqual(dark.saved,[['aisad-theme','light']]);
  const light=await report({}, {darkSystem:true,storedTheme:'light'});
  assert.equal(light.context.document.documentElement.dataset.theme,'light');
  const restricted=await report({}, {darkSystem:true,storageDenied:true});
  assert.equal(restricted.context.document.documentElement.dataset.theme,'dark');
  restricted.node('theme').onclick(); // Storage restrictions must not break the report.
  console.log('PASS non-browser dashboard states: unknown/zero/partial Grok cost, session scope, empty tables, dates/filters/tabs, event-only detail, freshness, theme preferences and Python/JS calendar parity including DST/short months');
})().catch(error=>{console.error(error);process.exitCode=1});
