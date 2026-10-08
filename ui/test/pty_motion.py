"""Synthetic PTY checks for the built UI; run after `bun run build` on POSIX."""
import codecs,fcntl,json,os,pty,re,select,signal,struct,subprocess,tempfile,termios,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import agent_usage as app

class Screen:
    """Read-only model for Ink's emitted cursor/erase commands (not a renderer)."""
    def __init__(self,columns,rows):
        self.columns=columns;self.rows=rows;self.cells=[[' ']*columns for _ in range(rows)];self.x=0;self.y=0;self.pending='';self.decoder=codecs.getincrementaldecoder('utf-8')()
    def resize(self,columns,rows):
        self.cells=[(row+[' ']*columns)[:columns] for row in (self.cells+[[' ']*columns for _ in range(rows)])[:rows]];self.columns=columns;self.rows=rows;self.x=min(self.x,columns-1);self.y=min(self.y,rows-1)
    def feed(self,raw):
        self.pending+=self.decoder.decode(raw)
        while self.pending:
            if self.pending.startswith('\x1b['):
                match=re.match(r'\x1b\[([?\d;]*)([A-Za-z~])',self.pending)
                if not match:return
                args,command=match.groups();self.pending=self.pending[match.end():]
                if args.startswith('?'):continue
                values=[int(v) if v else 0 for v in args.split(';')];n=values[0] or 1
                if command=='A':self.y=max(0,self.y-n)
                elif command=='B':self.y=min(self.rows-1,self.y+n)
                elif command=='C':self.x=min(self.columns-1,self.x+n)
                elif command=='D':self.x=max(0,self.x-n)
                elif command=='E':self.y=min(self.rows-1,self.y+n);self.x=0
                elif command=='F':self.y=max(0,self.y-n);self.x=0
                elif command=='G':self.x=min(self.columns-1,n-1)
                elif command in ('H','f'):self.y=min(self.rows-1,n-1);self.x=min(self.columns-1,(values[1] or 1)-1 if len(values)>1 else 0)
                elif command=='K':
                    a=0 if values[0] in (1,2) else self.x;b=self.columns if values[0] in (0,2) else self.x+1;self.cells[self.y][a:b]=[' ']*(b-a)
                elif command=='J':
                    if values[0] in (2,3):self.cells=[[' ']*self.columns for _ in range(self.rows)]
                    elif values[0]==0:
                        self.cells[self.y][self.x:]=[' ']*(self.columns-self.x)
                        for y in range(self.y+1,self.rows):self.cells[y]=[' ']*self.columns
                continue
            c=self.pending[0];self.pending=self.pending[1:]
            if c=='\r':self.x=0
            elif c=='\n':self.y=min(self.rows-1,self.y+1)
            elif ord(c)>=32:
                self.cells[self.y][self.x]=c;self.x=min(self.columns-1,self.x+1)
    def lines(self):return [''.join(row).rstrip() for row in self.cells]
    def body(self):
        lines=self.lines();controls=next(i for i,line in enumerate(lines) if 'Q quit' in line)
        return lines[:max(0,controls-1)]

def fixture():
    args=app.parser().parse_args(['chart','--view','weeks']);rows=[];requests=[]
    for month,days in [('2026-09',30),('2026-10',8)]:
        for day in range(1,days+1):
            for provider,model,factor in [('Claude','claude-opus-5',1),('Codex','gpt-5',.6)]:
                date=f'{month}-{day:02d}';cost=(20+(day*31%160))*factor
                rows.append(dict(date=date,cost=cost,cost_high=cost,provider=provider,requests=1,unpriced=0,model=model,project='synthetic',role='main',pool='interactive'))
                requests.append(dict(date=date,cost=cost,cost_high=cost,provider=provider))
    snapshot=dict(as_of_date='2026-10-08',generated='2026-10-08T12:00:00Z',timezone='UTC',rows=rows,request_stats=requests,grok_records=[])
    return app.terminal_ui_dataset(snapshot,args,True)

def check(root,env_overrides=None,ascii=False,color=True,exit_key=b'q',expected_code=0):
    dataset=fixture();dataset['options'].update(ascii=ascii,color=color)
    source=root/'dataset.json';source.write_text(json.dumps(dataset));source.chmod(0o600)
    master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0));before=termios.tcgetattr(slave)
    env={**os.environ,'TERM':'xterm-256color',**(env_overrides or {})}
    for name in ('CI','CONTINUOUS_INTEGRATION','NO_COLOR','FORCE_COLOR'):env.pop(name,None)
    if color:env['FORCE_COLOR']='3'
    screen=Screen(110,30)
    command=[os.environ.get('AISAD_TEST_BUN','bun'),'--preload',str(root/'guard.mjs'),str(ROOT/'ui/dist/aisad-ui.mjs'),str(source),str(root/'state.json')]
    process=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,env=env)
    def read(seconds):
        out=b'';deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if select.select([master],[],[],.02)[0]:out+=os.read(master,65536)
        screen.feed(out);return out
    def settle():
        deadline=time.monotonic()+3;quiet_since=time.monotonic();out=b''
        while time.monotonic()<deadline:
            part=read(.05);out+=part
            if part:quiet_since=time.monotonic()
            elif time.monotonic()-quiet_since>=.3:return out
        raise AssertionError(('Animation did not stop',out[-300:]))
    def expect(marker):
        out=b'';deadline=time.monotonic()+8
        while marker not in out and time.monotonic()<deadline:out+=read(.05)
        assert marker in out,(marker,out[-500:]);return out
    try:
        initial=expect(b'Q quit')+settle()
        assert b'Total' in initial and b'Insights' in initial
        assert b'enlarge the terminal' not in initial
        assert read(.25)==b'', 'Idle UI must stop rendering'
        os.write(master,b'w');expect(b'Cost per Day');settle()
        assert read(.25)==b''
        assert not any(0x2800<=ord(c)<=0x28ff for line in screen.body() for c in line), ('Particles remain in settled plot',list(enumerate(screen.lines())))
        os.write(master,b'h');expect(b'Sep 2026');middle=read(.09)
        # Interrupt both plot and badge mid-morph; the target table must be exact.
        os.write(master,b'w');expect(b'Cost by Weekday');settle()
        assert read(.25)==b''
        if env.get('INK_SCREEN_READER')!='true':
            content='\n'.join(screen.lines());expected=app.terminal_week_text(dataset['months'][0]['report'],110,color=False,ascii_only=ascii)
            for line in expected.splitlines():
                if line.startswith('Total      '):assert line.rstrip() in content, 'Weekly total changed or particle artifacts remained'
            assert not any(0x2800<=ord(c)<=0x28ff for line in screen.body() for c in line), 'Particles remain in settled table'
        for key in [b'l',b'h',b'l']:
            os.write(master,key);read(.07)
        screen.resize(80,24);fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0));process.send_signal(signal.SIGWINCH)
        resized=settle();assert b'enlarge the terminal' not in resized
        assert read(.25)==b'', 'Resize must not leave a running clock'
        if not env_overrides and not ascii and color:
            assert any(0x2800<=ord(c)<=0x28ff for c in middle.decode(errors='replace')), 'No morph frames'
        else:
            # A static badge may contain Braille, but no delayed animation writes.
            os.write(master,b'h');expect(b'Sep 2026');read(.08)
            assert read(.3)==b'', 'Static mode must not animate'
            os.write(master,b'l');expect(b'Oct 2026');read(.08)
        os.write(master,b'h');read(.05);os.write(master,exit_key)
        deadline=time.monotonic()+5;ending=b''
        while process.poll() is None and time.monotonic()<deadline:ending+=read(.05)
        assert process.poll()==expected_code,(process.poll(),ending[-500:])
        after=termios.tcgetattr(slave);before[3]&=~getattr(termios,'PENDIN',0);after[3]&=~getattr(termios,'PENDIN',0);assert before==after
        state=json.loads((root/'state.json').read_text());assert state=={'month':'2026-09','view':'weeks'},state
        if env.get('INK_SCREEN_READER')!='true':assert b'\x1b[?1049l' in ending
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        os.close(master);os.close(slave)

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='aisad-motion-pty-') as directory:
        root=Path(directory)
        (root/'guard.mjs').write_text("import net from 'node:net';import tls from 'node:tls';const block=()=>{throw new Error('Unexpected network operation')};const originalFetch=globalThis.fetch;globalThis.fetch=(url,...args)=>String(url).startsWith('data:')?originalFetch(url,...args):block();net.connect=block;net.createConnection=block;tls.connect=block;Bun.connect=block;Bun.listen=block;\n")
        for name,options in [('animated',{}),('reduced',{'env_overrides':{'AISAD_REDUCED_MOTION':'1'}}),('ascii',{'ascii':True}),('no color',{'color':False}),('screen reader',{'env_overrides':{'INK_SCREEN_READER':'true'}}),('Ctrl+C',{'exit_key':b'\x03','expected_code':130})]:
            check(root,**options);print('PASS:',name,flush=True)
