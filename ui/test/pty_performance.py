"""Manual synthetic PTY pacing probe. Run after `bun run build` on POSIX.
Prints input latency, frame spacing and output volume without hardware-sensitive
CI assertions. Pass an older bundle path to reproduce a before/after comparison.
"""
import sys,os,pty,fcntl,termios,struct,subprocess,select,time,json,tempfile
from pathlib import Path
from pty_motion import ROOT,fixture
bundle=sys.argv[1] if len(sys.argv)>1 else str(ROOT/'ui/dist/aisad-ui.mjs')
with tempfile.TemporaryDirectory(prefix='aisad-perf-') as directory:
 root=Path(directory);source=root/'dataset.json';data=fixture();data['initial_view']='graph';source.write_text(json.dumps(data))
 master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,110,0,0))
 env={**os.environ,'TERM':'xterm-256color','FORCE_COLOR':'3'}
 for name in ('CI','NO_COLOR','AISAD_REDUCED_MOTION','INK_SCREEN_READER'):env.pop(name,None)
 p=subprocess.Popen([os.environ.get('AISAD_TEST_BUN','bun'),bundle,str(source),str(root/'state.json')],stdin=slave,stdout=slave,stderr=slave,env=env)
 def capture(seconds):
  deadline=time.monotonic()+seconds;times=[];wire=b'';total=0
  while time.monotonic()<deadline:
   if select.select([master],[],[],.005)[0]:
    part=os.read(master,65536);total+=len(part);wire+=part
    while b'\x1b[?2026l' in wire:
     _,wire=wire.split(b'\x1b[?2026l',1);times.append(time.monotonic())
  return times,total
 try:
  initial,initialbytes=capture(1);measure=[]
  for key in (b'h',b'l',b'h',b'l',b'w',b'h',b'l',b'w'):
   start=time.monotonic();os.write(master,key);times,size=capture(.85);gaps=[1000*(b-a) for a,b in zip(times,times[1:])]
   measure.append(dict(key=key.decode(),first_ms=round(1000*(times[0]-start),1) if times else None,frames=len(times),span_ms=round(1000*(times[-1]-times[0]),1) if times else 0,max_gap_ms=round(max(gaps),1) if gaps else 0,bytes=size))
  os.write(master,b'q');capture(.1);p.wait(timeout=3)
  print(json.dumps(dict(initial_frames=len(initial),measurements=measure)))
 finally:
  if p.poll() is None:p.kill();p.wait()
  os.close(master);os.close(slave)
