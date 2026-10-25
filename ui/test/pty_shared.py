"""A real CLI follows another collector and budget update in an isolated home."""
import datetime,json,os,pty,fcntl,select,struct,subprocess,sys,tempfile,termios,time
from pathlib import Path
from pty_motion import ROOT,Screen

def check():
    with tempfile.TemporaryDirectory(prefix='aisad-shared-pty-') as directory:
        root=Path(directory);home=root/'home';output=root/'output'
        trace=home/'.claude/projects/synthetic/session.jsonl'
        trace.parent.mkdir(parents=True)
        def observation(number):
            return json.dumps(dict(type='assistant',sessionId='synthetic-sync',
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=dict(id='usage-'+str(number),model='claude-sonnet-5.5',
                             usage=dict(input_tokens=1000000,output_tokens=0))))+'\n'
        trace.write_text(observation(1))
        env={**os.environ,'HOME':str(home),'CODEX_HOME':str(home/'.codex'),
             'CLAUDE_CONFIG_DIR':str(home/'.claude'),'XDG_CONFIG_HOME':str(home/'.config'),
             'TERM':'xterm-256color','FORCE_COLOR':'3','AISAD_REDUCED_MOTION':'1'}
        for name in ('CI','CONTINUOUS_INTEGRATION','NO_COLOR','INK_SCREEN_READER','AISAD_TERMINAL_UI'):env.pop(name,None)
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0))
        command=[sys.executable,'-B',str(ROOT/'agent_usage.py')]
        process=subprocess.Popen(command+['chart','--interactive','--output',str(output)],
            stdin=slave,stdout=slave,stderr=slave,env=env,cwd=root)
        screen=Screen(110,30);wire=b'';shown=''
        def wait_for(text,seconds=5):
            nonlocal wire,shown
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if select.select([master],[],[],.03)[0]:
                    wire+=os.read(master,65536)
                    while b'\x1b[?2026l' in wire:
                        frame,wire=wire.split(b'\x1b[?2026l',1)
                        screen.feed(frame+b'\x1b[?2026l');shown='\n'.join(screen.lines())
                if text in shown:return
            raise AssertionError('Missing '+text+' in terminal: '+shown)
        try:
            wait_for('Month $2.00')
            with trace.open('a') as handle:handle.write(observation(2))
            completed=subprocess.run(command+['menubar','--json','--output',str(output)],
                env=env,cwd=root,text=True,capture_output=True,check=True)
            report=json.loads(completed.stdout)
            assert report['periods'][2]['known_cost_usd']==4
            started=time.monotonic();wait_for('Month $4.00')
            latency=time.monotonic()-started
            subprocess.run(command+['budget','--set','100','--json','--output',str(output)],
                env=env,cwd=root,text=True,capture_output=True,check=True)
            wait_for('/ $100.00')
            os.write(master,b'q');process.wait(timeout=4)
            assert process.returncode==0
            print('PASS: real open CLI adopted external menu collection and saved budget; latency %.3fs'%latency)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
            os.close(master);os.close(slave)

if __name__=='__main__':check()
