import {describe,expect,test} from 'bun:test';
import {amountFrame,readAmounts,renderAmounts} from '../src/amounts.js';
import type {Row} from '../src/types.js';
const rows=(claude:string,codex:string|null,month:string,pct:string):Row[]=>[
  [{text:'Cost per Day · Oct 2026',color:'#cccccc'}],
  [{text:'● Claude '+claude,color:'#d77757'},...(codex?[{text:' · '},{text:'● Codex '+codex+' (reported)',color:'#a5a9ff'}]:[])],
  [{text:'Month '+month+' / $2,000.00 · '+pct+'%',color:'#707070'}],
];
const text=(r:Row[])=>r.map(row=>row.map(s=>s.text).join(''));
describe('rolling provider amounts',()=>{
  const from=rows('$796.00','$477.60','$1,273.60','63.7'),to=rows('$3,015.00','$1,809.00','$4,824.00','241.2');
  test('reads only legend and budget amounts by stable key',()=>{
    expect([...readAmounts(to)]).toEqual([['p:Claude',[3015]],['p:Codex',[1809]],['month',[4824,241.2]]]);
    expect(readAmounts([[{text:'● Claude unpriced'}],[{text:'$10 ┤ '}]]).size).toBe(0);
  });
  test('interpolates mid-roll, glows changing digits and keeps every other row identical',()=>{
    const frame=amountFrame(readAmounts(from),readAmounts(to),.45),result=renderAmounts(to,frame);
    const claude=frame.values.get('p:Claude')![0]!;expect(claude).toBeGreaterThan(796);expect(claude).toBeLessThan(3015);
    expect(result[0]).toBe(to[0]!);
    expect(text(result)[1]).toMatch(/^● Claude \$[\d,]+\.\d{2} · ● Codex \$[\d,]+\.\d{2} \(reported\)$/);
    expect(text(result)[2]).toMatch(/^Month \$[\d,]+\.\d{2} \/ \$2,000\.00 · \d+\.\d%$/);
    expect(result[1]!.length).toBeGreaterThan(to[1]!.length);
  });
  test('Codex appears by counting up from zero; staggered providers and exact settle',()=>{
    const early=amountFrame(readAmounts(rows('$796.00',null,'$796.00','39.8')),readAmounts(to),.12);
    expect(early.values.get('p:Codex')![0]!).toBeLessThan(1809);
    expect(early.values.get('p:Claude')![0]!-796).toBeGreaterThan(0);
    const start=renderAmounts(to,amountFrame(readAmounts(from),readAmounts(to),0));
    expect(text(start)[1]).toBe('● Claude $796.00 · ● Codex $477.60 (reported)');expect(text(start)[2]).toBe('Month $1,273.60 / $2,000.00 · 63.7%');
    const done=amountFrame(readAmounts(from),readAmounts(to),1);
    expect(renderAmounts(to,done)).toEqual(to);expect(text(renderAmounts(to,done))).toEqual(text(to));
  });
});
