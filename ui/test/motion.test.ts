import {describe,expect,test} from 'bun:test';
import {badgeShape,braille,DOT_BITS,Morph,morton,motionEnabled,shape,easeInOut} from '../src/motion.js';
import {graphScene,overlayGraph} from '../src/motion-ui.js';
import type {Row} from '../src/types.js';
const point=(x:number,y:number)=>shape([{x,y}],1);
const text=(rows:Row[])=>rows.map(row=>row.map(s=>s.text).join('')).join('\n');
describe('normalized motion core',()=>{
  test('all eight Braille positions and an empty cell',()=>{
    const all:number[]=[];
    for(let y=0;y<4;y++)for(let x=0;x<2;x++){
      const controller=new Morph(point((x+.5)/2,(y+.5)/4)),mask=controller.render(1,1).masks[0]!;
      expect(mask).toBe(DOT_BITS[y]![x]!);expect(braille(mask).charCodeAt(0)).toBe(0x2800+mask);all.push(mask);
    }
    expect(all.reduce((a,b)=>a|b,0)).toBe(255);expect(braille(0)).toBe(' ');
  });
  test('Morton ordering and deterministic shape sampling',()=>{
    expect(morton(0,0)).toBe(0);expect(morton(1,1)).toBe(1048575);
    expect(badgeShape('graph')).toEqual(badgeShape('graph'));
    const first=new Morph(badgeShape('ring')),second=new Morph(badgeShape('ring'));
    for(const engine of [first,second]){engine.morphTo(badgeShape('weeks'),100,420);engine.update(270);}
    expect(first.render(10,2)).toEqual(second.render(10,2));
  });
  test('interruption starts at the current visual position and settles exactly',()=>{
    const engine=new Morph(point(.1,.1));engine.morphTo(point(.9,.9),0,400);engine.update(160);
    const before=[...engine.x,...engine.y];engine.morphTo(point(.2,.8),160,420);
    expect([...engine.x,...engine.y]).toEqual(before);expect(engine.update(580)).toBe(false);
    expect(engine.x[0]).toBeCloseTo(.2,6);expect(engine.y[0]).toBeCloseTo(.8,6);
    expect(engine.update(900)).toBe(false);
  });
  test('quintic curve is monotone with quiet starts and exact stops',()=>{
    expect(easeInOut(0)).toBe(0);expect(easeInOut(1)).toBe(1);expect(easeInOut(.5)).toBe(.5);
    expect(easeInOut(.1)).toBeLessThan(.02);expect(easeInOut(.9)).toBeGreaterThan(.98);
    const values=Array.from({length:101},(_,i)=>easeInOut(i/100));
    expect(values.every((value,i)=>value>=0&&value<=1&&(!i||value>=values[i-1]!))).toBe(true);
    const engine=new Morph(point(.1,.2));engine.morphTo(point(.9,.8),0,500);engine.update(.5);
    expect(Math.abs(engine.x[0]!-.1)).toBeLessThan(1e-6);expect(Math.abs(engine.y[0]!-.2)).toBeLessThan(1e-6);
    engine.update(499.5);expect(Math.abs(engine.x[0]!-.9)).toBeLessThan(1e-6);expect(Math.abs(engine.y[0]!-.8)).toBeLessThan(1e-6);
    expect(engine.update(500)).toBe(false);expect(engine.x[0]).toBe(point(.9,.8).points[0]!);
  });
  test('forked retargets preserve the visible pose and do not mutate a committed transition',()=>{
    const original=new Morph(point(.1,.1));original.morphTo(point(.9,.9),0,500);original.update(150);
    const visible=[...original.x,...original.y,...original.alpha],fork=original.copy();fork.morphTo(point(.2,.8),150);
    expect([...fork.x,...fork.y,...fork.alpha]).toEqual(visible);expect([...original.x,...original.y,...original.alpha]).toEqual(visible);
    original.update(500);fork.update(650);expect(original.x[0]).toBeCloseTo(.9,6);expect(fork.x[0]).toBeCloseTo(.2,6);
    const fading=new Morph(point(.1,.1));fading.morphTo(shape([],1),0,500);fading.update(200);
    expect(fading.copy().alpha).toEqual(fading.alpha);
  });
  test('reuses and clears buffers; empty shapes fade to no cells',()=>{
    const engine=new Morph(point(.1,.1)),raster=engine.render(10,2),buffer=raster.masks;
    engine.morphTo(point(.9,.9),0,0);expect(engine.render(10,2).masks).toBe(buffer);
    expect(buffer[0]).toBe(0);expect([...buffer].filter(Boolean)).toHaveLength(1);
    engine.morphTo(shape([],1),1,100);engine.update(101);
    expect([...engine.render(10,2).masks].every(mask=>mask===0)).toBe(true);
  });
  test('resize keeps normalized in-flight coordinates and clips all edges',()=>{
    const engine=new Morph(badgeShape('ring'));engine.morphTo(badgeShape('graph'),0);engine.update(180);
    const before=[...engine.x,...engine.y];expect(engine.render(240,80).masks).toHaveLength(19200);
    expect(engine.render(10,2).masks).toHaveLength(20);expect([...engine.x,...engine.y]).toEqual(before);
    const edge=new Morph(shape([{x:-2,y:3},{x:1,y:0}],2));expect([...edge.render(1,1).masks]).toEqual([72]);
    expect(()=>engine.render(0,2)).toThrow();expect(()=>shape([{x:NaN,y:0}],1)).toThrow();
  });
  test('ASCII, no color, screen readers, reduced motion and CI are static',()=>{
    const options={ascii:false,color:true};expect(motionEnabled(options,{TERM:'xterm'})).toBe(true);
    for(const env of [{AISAD_REDUCED_MOTION:'1'},{CI:'true'},{TERM:'dumb'},{INK_SCREEN_READER:'1'}])expect(motionEnabled(options,env)).toBe(false);
    expect(motionEnabled(options,{},true)).toBe(false);
    expect(motionEnabled({...options,ascii:true},{})).toBe(false);expect(motionEnabled({...options,color:false},{})).toBe(false);
  });
});
describe('data-preserving plot adapter',()=>{
  const rows:Row[]=[[{text:'Cost per Day · Oct 2026'}],[{text:'$10 ┤ '},{text:'╭─╮',color:'#d77757'}],[{text:' $0 ┼ '},{text:'│ ? ',color:'#d77757'}],[{text:'01 02 03'}],[{text:'Month $100 / $2,000'}]];
  test('morph layer cannot change axes, exact amounts or unknown markers',()=>{
    const scene=graphScene(rows,80)!;expect(scene.top).toBe(1);expect(scene.left).toBe(6);expect(scene.height).toBe(2);
    const engine=new Morph(scene.shape);engine.morphTo(badgeShape('ring',512),0);engine.update(200);
    const result=overlayGraph(rows,scene,engine.render(scene.width,scene.height));
    expect(result[0]).toBe(rows[0]!);expect(result[3]).toBe(rows[3]!);expect(result[4]).toBe(rows[4]!);
    expect(text(result)).toContain('Month $100 / $2,000');expect(result[2]![0]!.text).toBe(' $0 ┼ ');
    expect(text(result[2]?[result[2]]:[])).toContain('?');expect(text(rows)).toContain('╭─╮');
    expect(result.every(row=>row.reduce((n,s)=>n+s.text.length,0)<=80)).toBe(true);
  });
  test('missing data and multiple plot panels stay static',()=>{
    expect(graphScene([[{text:'No observations'}]],80)).toBeNull();
    expect(graphScene([...rows,{text:'$10 ┤ '}].map(r=>Array.isArray(r)?r:[r]),80)).toBeNull();
  });
});
