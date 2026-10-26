"""Render all generated screens with an installed Ren'Py 8 SDK.
Usage: python tests/runtime_smoke.py /path/to/renpy-8.5.3-sdk
"""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core import default_project,compile_project
SCRIPT='''label before_main_menu:
    jump nf_smoke
screen nf_test_exit():
    timer 0.1 repeat True action Return(2)
label nf_smoke:
    show screen nf_composition({"text": "Студия\\nпредставляет", "background": "#111126", "images": [{"asset": "sample_logo.png", "x": 0.5, "y": 0.2, "width": 200, "height": 120}]})
    $ renpy.pause(0.1, hard=True)
    hide screen nf_composition
    show screen main_menu
    $ renpy.pause(0.1, hard=True)
    hide screen main_menu
    show screen say("Анна", "Проверка текста")
    $ renpy.pause(0.1, hard=True)
    hide screen say
    show screen choice([__import__("collections").namedtuple("Item", "caption action")("Выбор", NullAction())])
    $ renpy.pause(0.1, hard=True)
    hide screen choice
    show screen nf_test_exit
    call screen nf_mini("Кликер", "clicker", 10, 30)
    call screen nf_mini("Тайминг", "timing", 10, 30)
    call screen nf_mini("Волейбол", "volleyball", 10, 30)
    call screen nf_hotspot({"title":"Поиск", "target":3, "seconds":0.2, "objects":[{"label":"Ключ", "x":100, "y":150, "width":100, "height":100, "points":1}]})
    call screen nf_quiz("Вопрос", [("Ответ", True), ("Нет", False)], 30)
    call screen nf_credits_screen
    call screen preferences
    call screen load
    call screen save
    hide screen nf_test_exit
    $ open(config.basedir + "/PASSED.txt", "w").write("All generated screens rendered successfully")
    $ renpy.quit()
'''
if __name__=='__main__':
    sdk=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        dest=Path(tmp)/'novel';p=default_project();p['intro']['cards']=[]
        p['_debug']=True;p['interface'].update(textAnimation='fade',textAlign='center',textOffsetX=10,lineSpacing=3)
        compile_project(p,ROOT/'projects/demo/assets',dest)
        (dest/'game/qa.rpy').write_text(SCRIPT,encoding='utf-8')
        env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',RENPY_RENDERER='sw')
        if sys.platform=='win32':cmd=[str(sdk/'renpy.exe'),str(dest)]
        else:
            exe=sdk/'lib/py3-linux-x86_64/renpy'
            if exe.exists():exe.chmod(exe.stat().st_mode|0o111)
            cmd=['/bin/sh',str(sdk/'renpy.sh'),str(dest)]
        result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60)
        if result.returncode or not (dest/'PASSED.txt').exists():
            print(result.stdout,result.stderr)
            if (dest/'traceback.txt').exists():print((dest/'traceback.txt').read_text(encoding='utf-8'))
            raise SystemExit('Runtime screen smoke check failed')
        print((dest/'PASSED.txt').read_text())
