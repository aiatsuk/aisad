import React,{createContext,useCallback,useContext,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useAnimation} from 'ink';
/** 120 Hz motion clock; main.tsx keeps Ink's render throttle (~5 ms) below this interval. */
export const FRAME_MS=8;
type Clock={frame:number;register:(id:symbol,active:boolean)=>void};
const ClockContext=createContext<Clock>({frame:0,register:()=>{}});
/**
 * One shared clock for every animation on screen. Ink aligns each useAnimation
 * subscriber to its own start time, so several independent subscribers fire at
 * offset moments and render several uneven frames per period. Here a single
 * subscriber drives all motion, and it only runs while something is moving.
 */
export function MotionClock({children}:{children:React.ReactNode}):React.ReactElement {
  const active=useRef(new Set<symbol>()),[count,setCount]=useState(0);
  const register=useCallback((id:symbol,on:boolean)=>{
    const set=active.current;
    if(on===set.has(id))return;
    if(on)set.add(id);else set.delete(id);
    setCount(set.size);
  },[]);
  const {frame}=useAnimation({interval:FRAME_MS,isActive:count>0});
  const value=useMemo(()=>({frame,register}),[frame,register]);
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>;
}
/** Re-render on every shared tick while `active`; returns the tick counter. */
export function useClock(active:boolean):number {
  const {frame,register}=useContext(ClockContext),id=useRef<symbol>(Symbol('motion')).current;
  useLayoutEffect(()=>{register(id,active);},[active,register,id]);
  useLayoutEffect(()=>()=>register(id,false),[register,id]);
  return frame;
}
