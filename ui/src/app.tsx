import React, {useEffect,useReducer,useState} from 'react';
import {Box, Text, useApp, useInput, useWindowSize, useIsScreenReaderEnabled} from 'ink';
import {axisLabelWidth,fittedHeight,frame} from './layout.js';
import {colors, navigate, type Dataset, type State, type Action} from './types.js';
import {Rows} from './rows.js';
export {Rows} from './rows.js';
import {UsageMinimap,MotionGraphRows,FadeRows} from './motion-ui.js';
import {motionEnabled} from './motion.js';
import {MotionClock} from './clock.js';
import {ScreenWriter} from './screen.js';
import {textRow} from './types.js';
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
  const selected=dataset.months[state.index]!,screenReader=useIsScreenReaderEnabled();
  const enabled=motionEnabled(dataset.options,process.env,screenReader),width=Math.max(48,Math.min(240,dataset.options.width??columns));
  // One plot height for every month, so navigation never changes the layout.
  const stableHeight=React.useMemo(()=>Math.min(...dataset.months.map(m=>fittedHeight(m.report,dataset.options,columns,rows))),[dataset,columns,rows]);
  // One y-axis width too: the plot keeps its origin, so a morph starts exactly on screen dots.
  const labelWidth=React.useMemo(()=>Math.max(...dataset.months.map(m=>axisLabelWidth(m.report,stableHeight))),[dataset,stableHeight]);
  const rowsForView=React.useMemo(()=>frame(selected.report,state.view,dataset.options,columns,rows,stableHeight,labelWidth),[selected,state.view,dataset.options,columns,rows,stableHeight,labelWidth]);
  const hint=ready?(columns>=75?'W graph/weeks  H previous  L next  Q quit':'W view  H/L month  Q quit'):'Preparing keyboard...';
  const content=state.view==='graph'?<MotionGraphRows rows={rowsForView} width={width} month={selected.month} color={dataset.options.color} enabled={enabled}/>:<FadeRows rows={rowsForView} fadeKey={selected.month} enabled={enabled} color={dataset.options.color}/>;
  const footer=React.useMemo(()=>textRow(hint,colors.muted),[hint]);
  // Screen readers keep Ink's own text output; otherwise frames are written directly.
  if(screenReader)return <Box flexDirection="column">{content}<Text {...(dataset.options.color?{color:colors.muted}:{})}>{hint}</Text></Box>;
  return <MotionClock><ScreenWriter columns={columns} lines={rows} color={dataset.options.color} footer={footer}>{content}<UsageMinimap width={columns>=75?20:16} report={selected.report} month={selected.month} enabled={enabled} color={dataset.options.color} ascii={dataset.options.ascii}/></ScreenWriter></MotionClock>;
}
