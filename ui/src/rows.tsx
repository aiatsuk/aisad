import React,{memo,useMemo} from 'react';
import {Box,Text} from 'ink';
import type {Row} from './types.js';
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
const RenderRow=memo(function RenderRow({row,color}:{row:Row;color:boolean}):React.ReactElement {
  const segments=useMemo(()=>compactRow(row),[row]);
  return <Text wrap="truncate">{segments.length?segments.map((segment,i)=><Text key={i} {...(color&&segment.color?{color:segment.color}:{})} bold={segment.bold??false}>{segment.text}</Text>):' '}</Text>;
});
export const Rows=memo(function Rows({rows,color}: {rows:Row[];color:boolean}):React.ReactElement {
  return <Box flexDirection="column">{rows.map((row,index)=><RenderRow key={index} row={row} color={color}/>)}</Box>;
});
