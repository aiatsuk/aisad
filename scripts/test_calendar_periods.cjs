// Exercise the dashboard's actual date functions without a browser or listener.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../agent_usage.py'), 'utf8');
const shift = source.slice(source.indexOf('const shiftDate='), source.indexOf('const shortDate='));
const periods = source.slice(source.indexOf('function setPeriod('), source.indexOf("for(const field of ['provider','model','project'])"));
const chosen = source.slice(source.indexOf('function chosen('), source.indexOf('function aggregate('));
function dashboard(today) {
  const nodes = {};
  const context = vm.createContext({today, first:'2024-01-01', last:today,
    $: id => nodes[id] ||= {value:''},
  });
  vm.runInContext(shift + periods + chosen, context);
  const run = code => JSON.parse(JSON.stringify(vm.runInContext(code, context)));
  return {nodes, context, run, select(value) {
    context.value = value;
    return run('setPeriod(value); ({current:selectedRange(),previous:previousRange(selectedRange())})');
  }};
}
const range = (from,to,days) => ({from,to,days});
const cases = [
  // Saturday, Sunday and Monday; month/year rollover; leap day and US DST changes.
  ['2026-09-05','2026-08-31','2026-08-24','2026-08-30','2026-08-29',6],
  ['2026-09-06','2026-08-31','2026-08-24','2026-08-30','2026-08-30',7],
  ['2026-09-07','2026-09-07','2026-08-31','2026-09-06','2026-08-31',1],
  ['2025-01-01','2024-12-30','2024-12-23','2024-12-29','2024-12-25',3],
  ['2024-02-29','2024-02-26','2024-02-19','2024-02-25','2024-02-22',4],
  ['2024-03-10','2024-03-04','2024-02-26','2024-03-03','2024-03-03',7],
  ['2026-11-01','2026-10-26','2026-10-19','2026-10-25','2026-10-25',7],
];
for (const [today,monday,priorMonday,priorSunday,sameDay,days] of cases) {
  const d = dashboard(today);
  assert.deepEqual(d.select('this-week'), {
    current:range(monday,today,days),previous:range(priorMonday,sameDay,days),
  }, `This week at ${today}`);
  assert.equal(d.nodes['custom-dates'].hidden,true);
  assert.deepEqual(d.select('last-week').current,range(priorMonday,priorSunday,7));
  assert.equal(d.run("new Date(previousRange(selectedRange()).from+'T00:00:00Z').getUTCDay()"),1);
  assert.equal(d.run("new Date(previousRange(selectedRange()).to+'T00:00:00Z').getUTCDay()"),0);
  assert.equal(d.run('previousRange(selectedRange()).days'),7);
}
const d = dashboard('2026-09-05');
assert.deepEqual(d.select('last-week'), {
  current:range('2026-08-24','2026-08-30',7),previous:range('2026-08-17','2026-08-23',7),
});
// Monday and Sunday are included, adjacent dates excluded, filters still apply.
d.context.rows = ['2026-08-23','2026-08-24','2026-08-30','2026-08-31'].map(date=>({date,provider:'Codex'}));
assert.deepEqual(d.run('rows.filter(r=>chosen(r)).map(r=>r.date)'),['2026-08-24','2026-08-30']);
d.nodes.provider.value='Claude';
assert.deepEqual(d.run('rows.filter(r=>chosen(r))'),[]);
d.nodes.provider.value='';
assert.deepEqual(d.select('7'), {
  current:range('2026-08-30','2026-09-05',7),previous:range('2026-08-23','2026-08-29',7),
});
assert.deepEqual(d.select('30'), {
  current:range('2026-08-07','2026-09-05',30),previous:range('2026-07-08','2026-08-06',30),
});
assert.equal(d.select('all').previous,null);
assert.equal(d.nodes.from.value,'2024-01-01');
d.select('this-week');d.select('custom');
assert.equal(d.nodes['custom-dates'].hidden,false);
assert.equal(d.nodes.from.value,'2026-08-31');
d.nodes.from.value='2026-08-20';d.nodes.to.value='2026-08-22';
assert.deepEqual(d.run('previousRange(selectedRange())'),range('2026-08-17','2026-08-19',3));
d.nodes.from.value='2026-08-23';
assert.equal(d.run('selectedRange()'),null);
for (const name of ['this-week','last-week']) assert.match(source,new RegExp(`<option value="${name}">`));
new vm.Script(source.split('</script><script>')[1].split('</script>')[0]);
console.log('PASS calendar periods: Monday/Sunday, year/leap/DST boundaries, partial-week comparison, inclusive filtering, existing presets, syntax');
