"""No completed target graph may precede a month morph in actual Ink output."""
import json,os,pty,fcntl,select,struct,subprocess,tempfile,termios,time
from pathlib import Path
from pty_motion import ROOT,Screen,fixture

def check():
    with tempfile.TemporaryDirectory(prefix='aisad-first-frame-') as directory:
        root=Path(directory);dataset=fixture();dataset['initial_view']='graph'
        source=root/'dataset.json';source.write_text(json.dumps(dataset))
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0))
        before=termios.tcgetattr(slave)
        env={**os.environ,'TERM':'xterm-256color','FORCE_COLOR':'3'}
        for name in ('CI','CONTINUOUS_INTEGRATION','NO_COLOR','AISAD_REDUCED_MOTION','INK_SCREEN_READER'):env.pop(name,None)
        process=subprocess.Popen([os.environ.get('AISAD_TEST_BUN','bun'),str(ROOT/'ui/dist/aisad-ui.mjs'),str(source),str(root/'state.json')],stdin=slave,stdout=slave,stderr=slave,env=env)
        screen=Screen(110,30);wire=b'';frames=[]
        def read(seconds):
            nonlocal wire
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if select.select([master],[],[],.01)[0]:
                    wire+=os.read(master,65536)
                    # Process every atomic Ink frame, even when the PTY batches writes.
                    while b'\x1b[?2026l' in wire:
                        frame,wire=wire.split(b'\x1b[?2026l',1)
                        screen.feed(frame+b'\x1b[?2026l');frames.append(screen.lines())
        def settled():
            deadline=time.monotonic()+4;quiet=time.monotonic();count=len(frames)
            while time.monotonic()<deadline:
                read(.03)
                if len(frames)!=count:count=len(frames);quiet=time.monotonic()
                elif time.monotonic()-quiet>=.35:return
            raise AssertionError('Animation did not settle')
        def plot(frame):return tuple(line for line in frame if ' ┤ ' in line or ' ┼ ' in line)
        try:
            read(.8);settled();assert any('Q quit' in line for line in frames[-1])
            start=len(frames);os.write(master,b'h');read(.03);settled()
            transition=[frame for frame in frames[start:] if 'Sep 2026' in '\n'.join(frame)]
            assert len(transition)>2,'No intermediate month frames'
            first,last=plot(transition[0]),plot(transition[-1]);assert first and last
            assert any(0x2800<=ord(c)<=0x28ff for row in first for c in row),'First month frame flashed the completed target plot'
            assert first!=last,'Target plot was committed before morph started'
            assert not any(0x2800<=ord(c)<=0x28ff for row in last for c in row),'Final plot did not settle to exact glyphs'
            # Retarget a live transition in the opposite direction.
            os.write(master,b'l');read(.10);start=len(frames);os.write(master,b'h');read(.03);settled()
            reverse=[frame for frame in frames[start:] if 'Sep 2026' in '\n'.join(frame)]
            assert reverse and any(0x2800<=ord(c)<=0x28ff for row in plot(reverse[0]) for c in row),'Interrupted morph flashed a target'
            os.write(master,b'q');deadline=time.monotonic()+4
            while process.poll() is None and time.monotonic()<deadline:read(.03)
            assert process.poll()==0
            after=termios.tcgetattr(slave);before[3]&=~getattr(termios,'PENDIN',0);after[3]&=~getattr(termios,'PENDIN',0);assert before==after
            print('PASS: every atomic month frame starts with the source morph; rapid retargeting and terminal restoration')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
            os.close(master);os.close(slave)
if __name__=='__main__':check()
