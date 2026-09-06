// Unit-test the renderer as JavaScript, without a browser or a network listener.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../agent_usage.py'), 'utf8');
const render = source.slice(source.indexOf('function renderPricingGaps('), source.indexOf('function render(){'));
const nodes = {};
const context = vm.createContext({
  $: id => nodes[id] ||= {}, integer: n => String(n), compact: n => String(n),
  pct: n => `${n * 100}%`, esc: s => String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;'),
});
vm.runInContext(render, context);
context.rows = [{provider:'Codex',model:'codex-auto-review',cost:null,input:100,output:20,price_status:'unknown_model'},
                {provider:'Codex',model:'<unknown>',cost:null,input:50,output:10,price_status:'unknown_model'}];
vm.runInContext('renderPricingGaps(rows, {requests:10,unpriced:2})', context);
assert.equal(nodes['pricing-gaps'].hidden, false);
assert.match(nodes['pricing-coverage'].textContent, /Priced 8 of 10/);
assert.match(nodes['pricing-table'].innerHTML, /codex-auto-review/);
assert.match(nodes['pricing-table'].innerHTML, /Internal approval-review model/);
assert.match(nodes['pricing-table'].innerHTML, /&lt;unknown&gt;/);
assert.doesNotMatch(nodes['pricing-table'].innerHTML, /<unknown>/);
vm.runInContext('renderPricingGaps([], {requests:8,unpriced:0})', context);
assert.equal(nodes['pricing-gaps'].hidden, true);
assert.doesNotMatch(nodes['pricing-table'].innerHTML, /codex-auto-review/);
// The whole embedded program must also parse.
const script = source.split('</script><script>')[1].split('</script>')[0];
new vm.Script(script);
console.log('PASS pricing view: coverage, reason, escaping, filter reset, full script syntax');

// Monetary comparisons use the known subtotal, never an invented zero.
context.usd=n=>'$'+n.toFixed(2);
vm.runInContext(source.slice(source.indexOf('function cost('),source.indexOf('function comparisonNote(')),context);
context.current={requests:10,unpriced:7,cost:20,cost_high:20};
context.previous={requests:8,unpriced:3,cost:10,cost_high:10};
assert.equal(vm.runInContext('cost(current)',context),'$20.00');
assert.equal(vm.runInContext("usageDelta(current,previous,'cost',{})",context),'+100.0% · prev $10.00');
context.current.unpriced=10;
assert.equal(vm.runInContext('cost(current)',context),'—');
assert.equal(vm.runInContext("usageDelta(current,previous,'cost',{})",context),'No priced current-period data');
context.current.unpriced=7;context.previous.unpriced=8;
assert.equal(vm.runInContext("usageDelta(current,previous,'cost',{})",context),'No priced previous-period data');
context.previous.unpriced=3;context.current.cost_high=21;
assert.equal(vm.runInContext("usageDelta(current,previous,'cost',{})",context),'Price range · no delta');
context.current.cost_high=20;context.previous.cost=0;context.previous.cost_high=0;
assert.equal(vm.runInContext("usageDelta(current,previous,'cost',{})",context),'No nonzero baseline · prev $0.00');
context.prior=[{provider:'Codex',model:'future-model',cost:null,input:80,output:4,price_status:'unknown_model'}];
vm.runInContext('renderPricingGaps([], {requests:8,unpriced:0}, {requests:10,unpriced:2}, prior)',context);
assert.equal(nodes['pricing-gaps'].hidden,false);
assert.match(nodes['pricing-coverage'].textContent,/0 current; 2 previous/);
assert.match(nodes['pricing-table'].innerHTML,/future-model/);
assert.match(nodes['pricing-table'].innerHTML,/Model absent from the price catalog/);
console.log('PASS known cost: mixed pricing, missing priced periods, zero baseline, price range, previous-only exclusions');
