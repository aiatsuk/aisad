import {describe,expect,test} from 'bun:test';
import {motionPalette,rasterRows,usageMinimap} from '../src/minimap.js';
import {DOT_BITS} from '../src/motion.js';
import {MinimapMorph} from '../src/minimap-motion.js';
import {compactRow} from '../src/rows.js';
import {providerColor,type Day,type Report,type Series} from '../src/types.js';
const day=(n:number,cost:number|null,observations=1):Day=>({date:`2026-10-${String(n).padStart(2,'0')}`,cost_usd:cost,observations,unpriced_observations:cost===null?observations:0,incomplete:cost===null&&observations>0});
const series=(provider:string,daily:Day[]):Series=>({provider,basis:'synthetic',daily,known_cost_usd:daily.reduce((n,d)=>n+(d.cost_usd??0),0),observations:daily.length,unpriced_observations:0,incomplete:false});
const report=(...data:Series[]):Pick<Report,'period'|'series'>=>({period:{from:'2026-10-01',to:'2026-10-31',days:31},series:data});
const dots=(map:ReturnType<typeof usageMinimap>):[number,number][]=>{
  const result:[number,number][]=[];
  for(let y=0;y<map.raster.height*4;y++)for(let x=0;x<map.raster.width*2;x++)if(map.raster.masks[(y>>2)*map.raster.width+(x>>1)]!&DOT_BITS[y&3]![x&1]!)result.push([x,y]);
  return result;
};
const text=(map:ReturnType<typeof usageMinimap>,ascii=false)=>rasterRows(map.raster,ascii,map.unknown).map(row=>row.map(s=>s.text).join(''));
describe('real monthly usage minimap',()=>{
  test('calendar endpoints, daily prices and a common provider scale determine the dots',()=>{
    const map=usageMinimap(report(series('Claude',[day(1,0),day(15,50),day(31,100)]),series('Codex',[day(15,100)])),16);
    expect(map.maximum).toBe(100);
    expect(dots(map)).toEqual([[14,0],[31,0],[14,4],[0,7]]);
    expect(map.raster.colors[7]).toBe(motionPalette.indexOf(providerColor('Codex')));
    expect(map.raster.colors[15]).toBe(motionPalette.indexOf(providerColor('Claude')));
    expect(new MinimapMorph(map).render(16,2).masks).toEqual(map.raster.masks);
  });
  test('only consecutive priced days connect; missing, future and unpriced days are gaps',()=>{
    const map=usageMinimap(report(series('Claude',[day(1,0),day(2,100),day(3,null),day(4,50),day(5,null,0),day(6,100)])),16);
    expect(dots(map)).toContainEqual([0,7]);
    expect(dots(map)).toContainEqual([1,0]);
    expect(dots(map).filter(([x])=>x<2)).toHaveLength(8);
    expect(dots(map).some(([x])=>x===2||x===4||x>5)).toBe(false);
    expect(map.unknown).toEqual([17]);
    expect(text(map)[1]).toContain('?');
    expect(text(map).every(row=>[...row].length===16)).toBe(true);
  });
  test('empty/unpriced months cannot fabricate a wave or zero-cost activity',()=>{
    const absent=usageMinimap(report(series('Claude',[day(1,null,0)])),16);
    expect(dots(absent)).toEqual([]);expect(text(absent)).toEqual([' '.repeat(16),' '.repeat(16)]);
    const unpriced=usageMinimap(report(series('Claude',[day(1,null)])),16);
    expect(dots(unpriced)).toEqual([]);expect(text(unpriced)[1]).toBe('?'+ ' '.repeat(15));
    const free=usageMinimap(report(series('Claude',[day(1,0)])),16);
    expect(dots(free)).toEqual([[0,7]]);
  });
  test('dates determine positioning and no input aggregates mutate',()=>{
    const source=report(series('Grok',[day(31,50),day(1,100)])),before=JSON.stringify(source);
    const map=usageMinimap(source,16);expect(dots(map)).toEqual([[0,0],[31,4]]);
    expect(map.raster.colors[0]).toBe(motionPalette.indexOf(providerColor('Grok')));
    expect(JSON.stringify(source)).toBe(before);
    expect(usageMinimap(source,16)).toEqual(map);
    const feb={...source,period:{from:'2026-02-01',to:'2026-02-28',days:28},series:[series('Other',[{...day(28,100),date:'2026-02-28'}])]};
    expect(dots(usageMinimap(feb,16))).toEqual([[31,0]]);
  });
  test('provider/day curve morphs keep lines connected, fade missing data in place and can retarget',()=>{
    const first=usageMinimap(report(series('Claude',[day(1,100),day(2,0)])),20);
    const target=usageMinimap(report(series('Claude',[day(1,0),day(2,100),day(6,40)])),20);
    const engine=new MinimapMorph(first);engine.morphTo(target,0,360);
    expect(engine.render(20,2).masks).toEqual(first.raster.masks);
    engine.update(180);const middle=engine.render(20,2);
    expect(middle.masks).not.toEqual(target.raster.masks);
    // New day six stays at its target height and fades without zero-cost flight.
    expect([...middle.opacity!].some(value=>value>0&&value<255)).toBe(true);
    const interrupted=engine.copy();interrupted.morphTo(first,180,360);
    expect(interrupted.render(20,2)).toEqual(middle);
    expect(engine.update(360)).toBe(false);expect(engine.render(20,2)).toEqual(target.raster);
    expect(interrupted.update(540)).toBe(false);expect(interrupted.render(20,2).masks).toEqual(first.raster.masks);
    const empty=usageMinimap(report());engine.morphTo(empty,360,360);engine.update(720);
    expect([...engine.render(20,2).masks].every(mask=>mask===0)).toBe(true);
  });
  test('compact terminal text preserves styles and amounts without changing input',()=>{
    const source=[{text:'$10',color:'#cccccc'},{text:'.35',color:'#cccccc'},{text:' ',color:'#cccccc',bold:true},{text:'$50',color:'#d77757',bold:true}];
    const before=JSON.stringify(source),compacted=compactRow(source);
    expect(compacted).toHaveLength(3);expect(compacted.map(s=>s.text).join('')).toBe('$10.35 $50');
    expect(compacted[1]!.bold).toBe(true);expect(JSON.stringify(source)).toBe(before);
  });
  test('ASCII still plots actual activity and known/unpriced markers',()=>{
    const map=usageMinimap(report(series('Claude',[day(1,0),day(2,100),day(3,null)])),16);
    const rows=text(map,true);expect(rows.every(row=>/^[ .?]{16}$/.test(row))).toBe(true);
    expect(rows.join('')).toContain('.');expect(rows.join('')).toContain('?');
    expect(()=>usageMinimap(report(),0)).toThrow();expect(()=>usageMinimap(report(),16,0)).toThrow();
  });
});
