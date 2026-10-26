import copy,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import default_project,upgrade_project,validate,compile_project
from native_bridge import import_native,nested_dialogues,update_nested,visual_changes
from scenario_plain import export_plain,import_plain,SAMPLE,restore_sources
from project_import import import_project
import app
SOURCE='''define e = Character(_("Emma"), color="#88ccff", who_prefix="<")
default points = 0
image bg room = "images/room.png"
image emma happy = "images/emma happy.png"
label start:
    scene bg room
    show emma happy at right
    e "Hello!"
    menu:
        "Go":
            e "Inside menu"
            jump finish
label finish:
    e "Bye."
    return
'''
class BridgeTests(unittest.TestCase):
    def seed(self,root):
        game=root/'native/game';(game/'images').mkdir(parents=True);(game/'script.rpy').write_text(SOURCE)
        (game/'screens.rpy').write_text('screen main_menu():\n    tag menu\n    textbutton "Start" action Start()\nscreen say(who, what):\n    text what id "what"\n')
        (game/'images/room.png').write_bytes(b'image');(game/'images/emma happy.png').write_bytes(b'image2')
        return import_native(default_project(),root,app.asset_name)[0]
    def test_import_labels_characters_resources_screens(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root)
            self.assertEqual([s['name'] for s in p['scenes']],['start','finish']);self.assertEqual(p['characters'][0]['name'],'Emma');self.assertEqual(p['characters'][0]['color'],'#88ccff')
            self.assertTrue(p['characters'][0]['sprite']);self.assertEqual(len(p['native']['screens']),2);self.assertFalse(validate(p,root/'assets')['errors']);self.assertFalse(visual_changes(p))
            compile_project(p,root/'assets',root/'out');self.assertEqual((root/'out/game/script.rpy').read_text(),SOURCE)
    def test_edit_dialogue_character_add_label_and_credits(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);e=next(e for e in p['scenes'][0]['events'] if e['type']=='say');e['text']='Edited dialogue'
            p['characters'][0]['name']='Анна';p['variables'][0]['value']=7
            p['scenes'].append({'id':'extra','name':'Extra','events':[{'type':'say','character':'e','text':'New label'},{'type':'credits'},{'type':'return'}]})
            self.assertTrue(visual_changes(p));compile_project(p,root/'assets',root/'out')
            text=(root/'out/game/script.rpy').read_text();self.assertIn('Edited dialogue',text);self.assertIn('default points = 7',text);self.assertIn('who_prefix', (root/'out/game/zz_novelforge_story.rpy').read_text());self.assertIn('label extra:',(root/'out/game/zz_novelforge_story.rpy').read_text());self.assertIn('menu:',text)
    def test_edit_nested_dialogue_preserves_control(self):
        code='menu:\n    "Go":\n        e "Before"\n        $ points += 1\n        jump finish\n'
        lines=nested_dialogues(code);self.assertEqual(len(lines),1);lines[0]['text']='After | \\ path'
        new=update_nested(code,lines);self.assertIn('menu:',new);self.assertIn('$ points += 1',new);self.assertIn('After |',new)
    def test_export_reimport_native_baselines(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);next(e for e in p['scenes'][0]['events'] if e['type']=='say')['text']='Updated'
            compile_project(p,root/'assets',root/'out');entries={f.relative_to(root/'out').as_posix():f.read_bytes() for f in (root/'out').rglob('*') if f.is_file()}
            q,r=import_project(entries,root/'again',default_project,upgrade_project,app.asset_name);compile_project(q,root/'again/assets',root/'out2')
            self.assertIn('Updated',(root/'out2/game/script.rpy').read_text());self.assertEqual((root/'again/native/game/script.rpy').read_text(),SOURCE)
    def test_external_source_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);(root/'native/game/script.rpy').write_text(SOURCE+'\n# external edit\n')
            with self.assertRaises(ValueError):compile_project(p,root/'assets',root/'out')
    def test_plain_full_roundtrip_and_escaping(self):
        p=default_project();p['scenes'][0]['events'][2]['text']='  Текст | "кавычки" \\n\nновая строка  '
        p['graphicsDocuments']=[{'id':'a','name':'layers','layers':[]}];p['musicProjects']=[{'id':'b','tracks':[]}]
        text=export_plain(p);q,n=import_plain(text,default_project());self.assertEqual(p,q)
        q,n=import_plain(SAMPLE,default_project());self.assertEqual(len(q['scenes']),3);self.assertFalse(validate(q)['errors'])
    def test_native_plain_sources_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);text=export_plain(p,root);q,n=import_plain(text,default_project());dest=root/'txt';dest.mkdir();(dest/'assets').mkdir();restore_sources(q,dest)
            self.assertEqual((dest/'native/game/script.rpy').read_text(),SOURCE);self.assertEqual(q['scenes'],p['scenes'])
    def test_local_labels_and_entry_rename(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'native/game').mkdir(parents=True)
            source='label start:\n    jump .a\nlabel .a:\n    "First"\n    return\nlabel other:\n    jump .a\nlabel .a:\n    return\n'
            (root/'native/game/script.rpy').write_text(source);p,r=import_native(default_project(),root,app.asset_name)
            self.assertEqual([s['name'] for s in p['scenes']],['start','start.a','other','other.a'])
            p['scenes'][0]['id']='beginning';p['start']='beginning';compile_project(p,root/'assets',root/'out')
            self.assertIn('label beginning.a:',(root/'out/game/script.rpy').read_text());self.assertIn('label start:',(root/'out/game/zz_novelforge_story.rpy').read_text())
    def test_crlf_plain_sources_and_path_validation(self):
        from native_bridge import validate_native_paths
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);source=(root/'native/game/script.rpy');source.write_bytes(SOURCE.replace('\n','\r\n').encode());p,r=import_native(default_project(),root,app.asset_name)
            q,n=import_plain(export_plain(p,root),default_project());other=root/'text';other.mkdir();(other/'assets').mkdir();restore_sources(q,other)
            self.assertEqual((other/'native/game/script.rpy').read_bytes(),source.read_bytes())
            q['native']['sourceHashes']['../escape.rpy']='bad'
            with self.assertRaises(ValueError):validate_native_paths(q)
    def test_simple_menu_and_continuation_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);source=root/'native/game/script.rpy'
            source.write_text('default flag = True\nlabel start:\n    menu:\n        "Choose"\n        "Go":\n            jump finish\n    if flag:\n        "Yes"\n    else:\n        "No"\nlabel finish:\n    return\n');p,r=import_native(default_project(),root,app.asset_name)
            events=p['scenes'][0]['events'];self.assertEqual(events[0]['type'],'choice');self.assertEqual(events[0]['prompt'],'Choose');self.assertEqual(events[1]['type'],'branch');self.assertEqual(events[1]['branches'][-1]['condition'],'')
            events[0]['options'][0]['text']='Changed option';compile_project(p,root/'assets',root/'out');self.assertIn('Changed option',(root/'out/game/script.rpy').read_text())
    def test_multiline_and_init_python_definitions(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'native/game').mkdir(parents=True)
            source='init python:\n    e = Character(_("Emma"), color="#88ccff")\n    points = 0\ndefine m = Character(\n    "Me",\n    color="#ffcc88")\nlabel start:\n    e """First\nlabel fake:\nLast"""\n    e "Hello"\n    return\n'
            (root/'native/game/script.rpy').write_text(source);p,r=import_native(default_project(),root,app.asset_name)
            self.assertEqual({c['name'] for c in p['characters']},{'Emma','Me'});self.assertEqual(len(p['scenes']),1);self.assertEqual(len(p['scenes'][0]['events']),3)
            p['scenes'][0]['events'].insert(0,{'type':'say','character':'e','text':'Added'})
            compile_project(p,root/'assets',root/'out');self.assertIn('label fake:',(root/'out/game/script.rpy').read_text());self.assertNotIn('default points',(root/'out/game/zz_novelforge_story.rpy').read_text())
if __name__=='__main__':unittest.main()

class BridgeHTTPTests(unittest.TestCase):
    def test_visual_import_export_and_original_screen_edit(self):
        import threading,urllib.request,base64,shutil
        old=app.PROJECTS
        with tempfile.TemporaryDirectory() as td:
            app.PROJECTS=Path(td);app.save('demo',default_project())
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
            def post(route,data):
                req=urllib.request.Request(base+'/api/'+route,json.dumps(data).encode(),{'X-NovelForge-Token':app.TOKEN,'Content-Type':'application/json'});return json.load(urllib.request.urlopen(req,timeout=120))
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('Game/game/script.rpy','define e = Character("Emma", color="#88ccff")\nlabel start:\n    e "Original"\n    return\n');z.writestr('Game/game/screens.rpy','screen main_menu():\n    tag menu\n    textbutton "Start" action Start()\n')
            try:
                imported=post('import-project',{'name':'game.zip','data':base64.b64encode(archive.getvalue()).decode()});pid=imported['id'];p=imported['project']
                self.assertTrue(p['native']['bridge']);self.assertEqual(len(p['scenes']),1)
                next(e for e in p['scenes'][0]['events'] if e['type']=='say')['text']='Changed in editor'
                p=post('save',{'id':pid,'project':p,'revision':p['revision']})['project']
                compiled=post('compile-preview',{'id':pid});self.assertTrue(any('Changed in editor' in f['text'] for f in compiled['files']))
                txt=urllib.request.urlopen(base+'/download/'+pid+'/scenario-txt').read();self.assertIn('Changed in editor',txt.decode('utf-8-sig'))
                p=post('import-word',{'id':pid,'name':'scenario.txt','data':base64.b64encode(txt).decode(),'revision':p['revision']})['project'];self.assertTrue(p['native']['bridge'])
                sc=p['native']['screens'][0];p=post('native-screen-save',{'id':pid,'index':0,'digest':sc['digest'],'code':sc['code'].replace('"Start"','"Begin"')})['project']
                self.assertIn('Begin',p['native']['screens'][0]['code']);self.assertIn('Changed in editor',p['scenes'][0]['events'][0]['text'])
                compiled=post('compile-preview',{'id':pid});self.assertTrue(any('"Begin"' in f['text'] for f in compiled['files']))
            finally:server.shutdown();server.server_close();app.PROJECTS=old
