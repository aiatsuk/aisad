import React, {useEffect,useReducer,useState} from 'react';
import {Box, Text, useApp, useInput, useWindowSize} from 'ink';
import {frame} from './layout.js';
import {colors, navigate, type Dataset, type Row, type State, type Action} from './types.js';
export function Rows({rows,color}: {rows: Row[]; color: boolean}): React.ReactElement {
  return <Box flexDirection="column">{rows.map((row,index)=><Text key={index} wrap="truncate">{row.length?row.map((segment,i)=><Text key={i} {...(color&&segment.color?{color:segment.color}:{})} bold={segment.bold??false}>{segment.text}</Text>):' '}</Text>)}</Box>;
}
export function Dashboard({dataset,onExit}: {dataset:Dataset; onExit:(state:State,code:number)=>void}):React.ReactElement {
  const [state,dispatch]=useReducer((current:State,action:Action)=>navigate(current,action,dataset.months.length),{index:dataset.months.findIndex(m=>m.month===dataset.initial_month),view:dataset.initial_view});
  const {columns,rows}=useWindowSize();const {exit}=useApp();const [ready,setReady]=useState(false);
  useInput((input,key)=>{
    if(input.toLowerCase()==='q'||key.escape||key.ctrl&&(input==='c'||input==='d')) {onExit(state,key.ctrl&&input==='c'?130:0);exit();return;}
    if(input.toLowerCase()==='w')dispatch('toggle');
    else if(input.toLowerCase()==='h'||key.leftArrow)dispatch('previous');
    else if(input.toLowerCase()==='l'||key.rightArrow)dispatch('next');
  });
  useEffect(()=>{setReady(true);},[]);
  const selected=dataset.months[state.index]!;
  return <Box flexDirection="column"><Rows rows={frame(selected.report,state.view,dataset.options,columns,rows)} color={dataset.options.color}/><Box marginTop={1}><Text {...(dataset.options.color?{color:colors.muted}:{})}>{ready?'W graph/weeks  H previous  L next  Q quit':'Preparing keyboard...'}</Text></Box></Box>;
}
