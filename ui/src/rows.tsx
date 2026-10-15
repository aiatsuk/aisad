import React,{memo} from 'react';
import {Box,Text} from 'ink';
import chalk from 'chalk';
import type {Row} from './types.js';
import {useScreen,useSlot} from './screen.js';
/** Merge adjacent styles without changing text, color or emphasis. */
export function compactRow(row:Row):Row {
  const result:Row=[];
  for(const segment of row) {
    if(!segment.text)continue;
    const previous=result.at(-1);
    if(previous&&previous.color===segment.color&&(previous.bold??false)===(segment.bold??false))previous.text+=segment.text;
    else result.push({...segment});
  }
  return result;
}
// Ink's own chalk instance: the same 16/256/truecolor downsampling as <Text color>.
const styles=new Map<string,(text:string)=>string>();
const style=(color:string|undefined,bold:boolean):((text:string)=>string)=>{
  const key=(color??'')+(bold?'!':'');let fn=styles.get(key);
  if(!fn){let c=color?chalk.hex(color):chalk;if(bold)c=c.bold;fn=(text:string)=>c(text);if(styles.size<4096)styles.set(key,fn);}
  return fn;
};
/** One pre-styled string per row: one Ink text node instead of one per color run.
 * Animation frames rebuild rows, so this keeps React/Yoga work per frame small. */
export function encodeRow(row:Row,color:boolean):string {
  let line='';
  for(const segment of compactRow(row)) {
    const tint=color?segment.color:undefined,bold=segment.bold??false;
    line+=tint||bold?style(tint,bold)(segment.text):segment.text;
  }
  return line||' ';
}
const RenderRow=memo(function RenderRow({line}:{line:string}):React.ReactElement {
  return <Text wrap="truncate">{line}</Text>;
});
const InkRows=memo(function InkRows({rows,color}: {rows:Row[];color:boolean}):React.ReactElement {
  return <Box flexDirection="column">{rows.map((row,index)=><RenderRow key={index} line={encodeRow(row,color)}/>)}</Box>;
});
function SlotRows({screen,slot,rows}:{screen:NonNullable<ReturnType<typeof useScreen>>;slot:string;rows:Row[]}):null {
  useSlot(screen,slot,rows);return null;
}
/** Inside a ScreenWriter rows go to its slot; elsewhere (screen readers, tests) Ink renders them. */
export const Rows=memo(function Rows({rows,color,slot='main'}: {rows:Row[];color:boolean;slot?:string}):React.ReactElement|null {
  const screen=useScreen();
  return screen?<SlotRows screen={screen} slot={slot} rows={rows}/>:<InkRows rows={rows} color={color}/>;
});
