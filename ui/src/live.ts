import {readFileSync,statSync} from 'node:fs';
import {parseDataset,type Dataset} from './types.js';
/**
 * Stale-while-revalidate for the cold start.
 *
 * The collector can open the UI on the last dataset it showed (marked `stale`)
 * and replace the file once the fresh one is computed. Unchanged months keep
 * their object identity, so they stay idle; changed months get a new revision,
 * which the dashboard plays as an ordinary morph to the fresh numbers.
 */
const comparable=(value:unknown):string=>JSON.stringify(value,(key,item)=>key==='generated'?undefined:item);
export function mergeDataset(previous:Dataset,next:Dataset):Dataset {
  const old=new Map(previous.months.map(item=>[item.month,item]));
  const months=next.months.map(item=>{
    const before=old.get(item.month);
    if(!before)return item;
    return comparable(before.report)===comparable(item.report)?before:{...item,revision:(before.revision??0)+1};
  });
  return {...next,months};
}
/** Poll the dataset file until a fresh (non-stale) version replaces it. */
export function watchDataset(path:string,onFresh:(dataset:Dataset)=>void,interval=60,continuous=false):()=>void {
  const signature=():string=>{try{const s=statSync(path);return s.ino+':'+s.size+':'+s.mtimeMs;}catch{return '';}};
  let seen=signature(),stopped=false;
  const timer=setInterval(()=>{
    const now=signature();if(stopped||!now||now===seen)return;seen=now;
    let next:Dataset;
    try{next=parseDataset(JSON.parse(readFileSync(path,'utf8')) as unknown);}catch{return;}
    if(next.stale)return;
    if(!continuous)stop();onFresh(next);
  },interval);
  timer.unref?.();
  const stop=():void=>{stopped=true;clearInterval(timer);};
  return stop;
}
