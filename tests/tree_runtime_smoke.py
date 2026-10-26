"""Execute structured branches, menu bodies and a nested label call in Ren'Py."""
import os,sys,tempfile,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core import default_project,compile_project
from native_bridge import import_native
from app import asset_name
QA='''init offset = 1000
screen choice(items):
    timer 0.01 action items[0].action
label before_main_menu:
    jump TARGET
'''
raw='$ open(config.basedir + "/PASSED.txt", "w").write(str(score))\n$ renpy.quit()'
if __name__=='__main__':
 sdk=Path(sys.argv[1]).resolve()
 for executable in (sdk/'lib').glob('*/renpy'):executable.chmod(executable.stat().st_mode|0o111)
 for native in (False,True):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   if not native:
    p=default_project();p['intro']={'cards':[],'video':''};p['variables']=[{'id':'score','value':0}];p['interface']['elements']=[];p['start']='main'
    p['scenes']=[{'id':'main','name':'Main','events':[{'type':'branch','branches':[{'condition':'False','events':[{'type':'set','variable':'score','value':'99'}]},{'condition':'','events':[{'type':'set','variable':'score','value':'1'}]}]},{'type':'menu_block','prompt':'Choose','options':[{'text':'Run','condition':'score == 1','events':[{'type':'branch','branches':[{'condition':'score > 0','events':[{'type':'set','variable':'score','value':'score + 3'}]}]},{'type':'call','target':'helper'}]},{'text':'Wrong','condition':'False','events':[{'type':'set','variable':'score','value':'99'}]}]},{'type':'raw','code':raw}]},{'id':'helper','name':'Helper','events':[{'type':'set','variable':'score','value':'score + 2'},{'type':'return'}]}];assets=ROOT/'projects/demo/assets';target='nfscene_main'
   else:
    (root/'native/game').mkdir(parents=True);(root/'native/game/script.rpy').write_text('default score = 0\nlabel start:\n    if False:\n        $ score = 99\n    else:\n        $ score = 1\n    menu:\n        "Run":\n            if score > 0:\n                $ score = score + 3\n            call helper\n        "Hidden" if False:\n            $ score = 99\n    '+raw.replace('\n','\n    ')+'\nlabel helper:\n    $ score = score + 2\n    return\n')
    p,r=import_native(default_project(),root,asset_name);p['scenes'][0]['events'][0]['branches'][0]['events'][0]['value']='100';assets=root/'assets';target='start'
   compile_project(p,assets,root/'out');(root/'out/game/zz_qa.rpy').write_text(QA.replace('TARGET',target))
   env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',RENPY_RENDERER='sw')
   r=subprocess.run(['/bin/sh',str(sdk/'renpy.sh'),str(root/'out')],capture_output=True,text=True,env=env,timeout=60)
   passed=root/'out/PASSED.txt'
   if r.returncode or not passed.exists() or passed.read_text()!='6':
    print(r.stdout,r.stderr)
    if (root/'out/traceback.txt').exists():print((root/'out/traceback.txt').read_text())
    raise SystemExit('Structured runtime failed, native='+str(native))
   print('PASS native structured execution' if native else 'PASS generated structured execution')
