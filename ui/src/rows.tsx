import React from 'react';
import {Box,Text} from 'ink';
import type {Row} from './types.js';
export function Rows({rows,color}: {rows:Row[];color:boolean}):React.ReactElement {
  return <Box flexDirection="column">{rows.map((row,index)=><Text key={index} wrap="truncate">{row.length?row.map((segment,i)=><Text key={i} {...(color&&segment.color?{color:segment.color}:{})} bold={segment.bold??false}>{segment.text}</Text>):' '}</Text>)}</Box>;
}
