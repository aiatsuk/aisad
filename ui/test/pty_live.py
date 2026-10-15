"""A stale start shows the cached numbers at once, then morphs to the fresh file."""
import copy,json,os,pty,fcntl,select,struct,subprocess,tempfile,termios,time
from pathlib import Path
from pty_motion import ROOT,Screen,fixture

def check():
    with tempfile.TemporaryDirectory(prefix='aisad-live-') as directory:
        root=Path(directory);stale=fixture();stale['initial_view']='graph';stale['stale']=True
        stale['refresh']=True;fresh=copy.deepcopy(stale);del fresh['stale']
        month=fresh['months'][-1]['report'];month['monthly_budget']['known_cost_usd']=4321.5
        for series in month['series']:series['known_cost_usd']*=3;series['daily']=[dict(d,cost_usd=None if d['cost_usd'] is None else d['cost_usd']*3) for d in series['daily']]
        source=root/'dataset.json';source.write_text(json.dumps(stale))
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0))
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
                    while b'\x1b[?2026l' in wire:
                        frame,wire=wire.split(b'\x1b[?2026l',1)
                        screen.feed(frame+b'\x1b[?2026l');frames.append('\n'.join(screen.lines()))
        try:
            read(1.0)
            assert frames and 'Updating' in frames[-1],'Stale start is not marked'
            before=len(frames)
            partial=root/'next.json';partial.write_text(json.dumps(fresh));os.replace(partial,source)
            read(1.2)
            after=frames[before:]
            assert after and 'Updating' not in after[-1],'Fresh data did not clear the stale mark'
            assert '$4,321.50' in after[-1],'Fresh amounts not shown'
            assert any('$4,321.50' not in frame for frame in after[1:]),'Amounts jumped without rolling'
            braille=[f for f in after if any(0x2800<=ord(c)<=0x28ff for c in f)]
            assert braille,'Changed month did not morph'
            # R asks the collector for another collection and marks the view stale again.
            request=root/'refresh.request';before=len(frames)
            os.write(master,b'r');read(.4)
            assert request.exists(),'R did not request a refresh'
            assert 'Updating' in frames[-1],'Refresh is not marked'
            request.unlink();again=copy.deepcopy(fresh);again['months'][-1]['report']['monthly_budget']['known_cost_usd']=5000
            partial.write_text(json.dumps(again));os.replace(partial,source);read(1.2)
            assert 'Updating' not in frames[-1] and '$5,000.00' in frames[-1],'Second refresh not shown'
            os.write(master,b'q');deadline=time.monotonic()+4
            while process.poll() is None and time.monotonic()<deadline:read(.03)
            assert process.poll()==0
            assert json.loads((root/'state.json').read_text())['month']==fresh['initial_month']
            print('PASS: stale start and R refresh are marked, then roll and morph to the fresh dataset')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
            os.close(master);os.close(slave)
if __name__=='__main__':check()
