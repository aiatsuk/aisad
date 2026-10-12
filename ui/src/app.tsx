import React, {useEffect,useReducer,useState} from 'react';
import {Box, Text, useApp, useInput, useWindowSize, useIsScreenReaderEnabled} from 'ink';
import {fittedHeight,frame} from './layout.js';
import {colors, navigate, type Dataset, type State, type Action} from './types.js';
import {Rows} from './rows.js';
export {Rows} from './rows.js';
import {UsageMinimap,MotionGraphRows,FadeRows} from './motion-ui.js';
import {motionEnabled} from './motion.js';
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
  const rowsForView=React.useMemo(()=>frame(selected.report,state.view,dataset.options,columns,rows,stableHeight),[selected,state.view,dataset.options,columns,rows,stableHeight]);
  return <Box flexDirection="column">{state.view==='graph'?<MotionGraphRows rows={rowsForView} width={width} month={selected.month} color={dataset.options.color} enabled={enabled}/>:<FadeRows rows={rowsForView} fadeKey={selected.month} enabled={enabled} color={dataset.options.color}/>}<Box flexDirection="row" height={2}><Box flexGrow={1} flexDirection="column" justifyContent="flex-end"><Text {...(dataset.options.color?{color:colors.muted}:{})}>{ready?(columns>=75?'W graph/weeks  H previous  L next  Q quit':'W view  H/L month  Q quit'):'Preparing keyboard...'}</Text></Box>{!screenReader&&<UsageMinimap width={columns>=75?20:16} report={selected.report} month={selected.month} enabled={enabled} color={dataset.options.color} ascii={dataset.options.ascii}/>}</Box></Box>;
}
