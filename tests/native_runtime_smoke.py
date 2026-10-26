"""Real engine check for native import edits and both original/replaced UI modes."""
import json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from native_bridge import import_native
from core import default_project,compile_project
from app import asset_name
SCRIPT='''screen nf_native_test_exit():
    timer 0.1 repeat True action Return(1)
label before_main_menu:
    jump qa_native_run
label qa_native_run:
    if config.screen_width != EXPECTED_WIDTH:
        $ raise Exception("Native screen resolution changed unexpectedly")
    show screen nf_native_test_exit
    call extra_test
    if renpy.showing("sylvie"):
        $ raise Exception("Imported character tag was not hidden")
    if book != 3:
        $ raise Exception("Visual variable event did not execute")
    call nfcut_qa_cut
    call screen say("Edited name", "Native imported dialogue and custom screens")
    show screen main_menu
    $ renpy.pause(0.1, hard=True)
    hide screen main_menu
    hide screen nf_native_test_exit
    $ open(config.basedir + "/PASSED.txt", "w").write("Native import, edited code, object, variable, credits and cutscene passed")
    $ renpy.quit()
'''
if __name__=='__main__':
    sdk=Path(sys.argv[1]).resolve()
    for replace in (False,True):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);shutil.copytree(sdk/'the_question/game',root/'native/game')
            gui=root/'native/game/gui.rpy';gui.write_text(gui.read_text(encoding='utf-8-sig').replace('gui.init(1280, 720)','gui.init(1920, 1080)'),encoding='utf-8')
            p,r=import_native(default_project(),root,asset_name);p['native']['useStudioUI']=replace;p['credits']['style']='scroll'
            p['characters'][0]['name']='Edited name';p['variables']=[v for v in p['variables'] if v['id']!='book']+[{'id':'book','value':0,'_native':{'file':'game/script.rpy','baseline':False}}]
            flat=next(n for n in p['native']['resources'] if n.endswith('.png'))
            p['scenes'].append({'id':'extra_test','name':'Test label','events':[{'type':'set','variable':'book','value':'3'},{'type':'show','character':p['characters'][0]['id'],'position':'left','x':.2,'y':.9,'scale':.8,'effect':'none'},{'type':'raw','code':'hide '+p['characters'][0]['_native']['imageTag']+'\n'},{'type':'image','id':'test_image','asset':flat,'x':.5,'y':.3,'width':200,'height':100,'opacity':1},{'type':'credits'},{'type':'return'}]})
            p['cutscenes']=[{'id':'qa_cut','cards':[{'text':'Test title','seconds':.1,'background':'#111126','images':[],'textX':.5,'textY':.5,'fontSize':32,'textColor':'#ffffff'}]}]
            compile_project(p,root/'assets',root/'out');(root/'out/game/zz_test.rpy').write_text(SCRIPT.replace('EXPECTED_WIDTH',str(1280 if replace else 1920)),encoding='utf-8')
            env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',RENPY_RENDERER='sw')
            result=subprocess.run(['/bin/sh',str(sdk/'renpy.sh'),str(root/'out')],env=env,capture_output=True,text=True,timeout=60)
            if result.returncode or not (root/'out/PASSED.txt').exists():
                print(result.stdout,result.stderr)
                if (root/'out/traceback.txt').exists():print((root/'out/traceback.txt').read_text())
                raise SystemExit('Native runtime check failed: replacement UI='+str(replace))
            print('PASS original UI' if not replace else 'PASS replacement UI')
