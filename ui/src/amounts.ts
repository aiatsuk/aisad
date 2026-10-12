/** Rolling provider and monthly amounts during month changes.
 * Only the legend (`● Provider $X`) and budget (`Month $X / $Y · Z%`) rows are touched;
 * every other row and all settled text stay byte-identical. */
import {easeInOut} from './motion.js';
import {band,hexToRgb,HIGHLIGHT_RGB,mix,rgbToHex} from './light.js';
import {colors,money,type Row,type Segment} from './types.js';
export type Amounts=Map<string,number[]>;
const LEGEND=/^([●*] )(.+?) (\$[\d,]+\.\d{2})(.*)$/,BUDGET=/^Month (\$[\d,]+\.\d{2}) \/ (\$[\d,]+\.\d{2})( [·|] )(\d+\.\d)%$/;
const parseMoney=(text:string):number=>Number(text.replace(/[$,]/g,''));
/** Numbers per stable key: `p:<provider>` → [cost]; `month` → [known cost, percent]. */
export function readAmounts(rows:readonly Row[]):Amounts {
  const result:Amounts=new Map();
  for(const row of rows)for(const segment of row) {
    const legend=LEGEND.exec(segment.text);if(legend){result.set('p:'+legend[2],[parseMoney(legend[3]!)]);continue;}
    const budget=BUDGET.exec(segment.text);if(budget)result.set('month',[parseMoney(budget[1]!),Number(budget[4])]);
  }
  return result;
}
/** Text plus per-character emphasis: digits still rolling glow, settled ones keep the base color. */
function rolled(text:string,final:string,base:string,glow:number,flash:number):Segment[] {
  const baseRgb=hexToRgb(base),hot=rgbToHex(mix(baseRgb,HIGHLIGHT_RGB,Math.min(1,.25+.6*glow+flash))),warm=rgbToHex(mix(baseRgb,HIGHLIGHT_RGB,Math.min(1,.18*glow+flash)));
  const out:Segment[]=[];
  // Align from the right so cents line up while the integer part grows or shrinks.
  const offset=final.length-text.length;
  for(let i=0;i<text.length;i++) {
    const ch=text[i]!,same=final[i+offset]===ch,color=/\d/.test(ch)&&!same?hot:warm,previous=out.at(-1);
    if(previous?.color===color)previous.text+=ch;else out.push({text:ch,color});
  }
  return out;
}
export type AmountFrame={values:Amounts;glow:Map<string,number>;flash:Map<string,number>;settled:Set<string>};
/** Interpolate each key with a small stagger; absent sources count up from zero. */
export function amountFrame(from:Amounts,to:Amounts,t:number):AmountFrame {
  const values:Amounts=new Map(),glow=new Map<string,number>(),flash=new Map<string,number>(),settled=new Set<string>();
  let order=0;
  for(const [key,target] of to) {
    const source=from.get(key)??target.map(()=>0),delay=key==='month'?.22:Math.min(.18,.07*order++);
    const p=Math.max(0,Math.min(1,(t-delay)/(1-.22))),e=easeInOut(p);
    values.set(key,target.map((value,i)=>p>=1?value:source[i]!+(value-source[i]!)*e));
    if(p>=1)settled.add(key);
    glow.set(key,p>=1?0:Math.sin(Math.PI*p));flash.set(key,p>=1?0:band(p-.9,.12)*.55);
  }
  return {values,glow,flash,settled};
}
export function renderAmounts(rows:Row[],frame:AmountFrame):Row[] {
  return rows.map(row=>{
    if(!row.some(s=>LEGEND.test(s.text)||BUDGET.test(s.text)))return row;
    return row.flatMap(segment=>{
      const legend=LEGEND.exec(segment.text);
      if(legend) {
        const key='p:'+legend[2],value=frame.values.get(key)?.[0],glow=frame.glow.get(key)??0,flash=frame.flash.get(key)??0;
        if(value===undefined||frame.settled.has(key))return [segment];
        const base=segment.color??colors.text;
        return [{...segment,text:legend[1]!+legend[2]+' '},...rolled(money(value),legend[3]!,base,glow,flash),...(legend[4]?[{...segment,text:legend[4]}]:[])];
      }
      const budget=BUDGET.exec(segment.text);
      if(budget) {
        const values=frame.values.get('month'),glow=frame.glow.get('month')??0,flash=frame.flash.get('month')??0;
        if(!values||frame.settled.has('month'))return [segment];
        const base=segment.color??colors.muted;
        return [{...segment,text:'Month '},...rolled(money(values[0]!),budget[1]!,base,glow,flash),{...segment,text:' / '+budget[2]+budget[3]},...rolled(values[1]!.toFixed(1)+'%',budget[4]+'%',base,glow,flash)];
      }
      return [segment];
    });
  });
}
