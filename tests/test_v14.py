import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import default_project,validate,compile_project,event_script
from native_bridge import import_native
from story_tree import walk,rewrite_statements
from scenario_plain import export_plain,import_plain
from app import asset_name
SOURCE='''define e = Character("Emma", color="#88ccff")
default trust = 0
label start:
    if trust > 0:
        e "jump start and nfscene_finish are literal text"
        menu:
            "Pick an action"
            "Talk":
                e "Inside the choice"
                $ trust = trust + 1
            "Leave" if trust > 1:
                jump finish
    elif trust == 0:
        e "No points yet"
    else:
        e "Other"
    jump finish
label finish:
    return
'''
class TreeTests(unittest.TestCase):
    def seed(self,root):
        (root/'native/game').mkdir(parents=True);(root/'native/game/script.rpy').write_text(SOURCE)
        return import_native(default_project(),root,asset_name)[0]
    def test_native_tree_preservation_and_nested_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);event=p['scenes'][0]['events'][0]
            self.assertEqual(event['type'],'branch');self.assertEqual(event['branches'][0]['events'][1]['type'],'menu_block');self.assertFalse(validate(p)['errors'])
            compile_project(p,root/'assets',root/'one');self.assertEqual((root/'one/game/script.rpy').read_text(),SOURCE)
            event['branches'][0]['events'][1]['options'][0]['events'][0]['text']='Changed deeply'
            compile_project(p,root/'assets',root/'two');text=(root/'two/game/script.rpy').read_text();self.assertIn('Changed deeply',text);self.assertIn('elif trust == 0:',text);self.assertIn('jump start and nfscene_finish are literal text',text)
    def test_deep_validation_and_depth_limit(self):
        p=default_project();p['scenes'][0]['events']=[{'type':'branch','branches':[{'condition':'trust > 0','events':[{'type':'set','variable':'missing','value':'0'}]}]}]
        self.assertTrue(validate(p)['errors']);p['scenes'][0]['events'][0]['branches'][0]['condition']='__import__("os")';self.assertTrue(validate(p)['errors'])
        e={'type':'return'}
        for i in range(30):e={'type':'branch','branches':[{'condition':'True','events':[e]}]}
        p['scenes'][0]['events']=[e];self.assertTrue(validate(p)['errors'])
    def test_readable_roundtrip_with_all_tree_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.seed(root);text=export_plain(p);q,n=import_plain(text,default_project());self.assertEqual(p,q);self.assertIn('Конец условия:',text);self.assertIn('Пункт:',text)
            with self.assertRaises(ValueError):import_plain('# NovelForge TXT 2\nСцена: a\nЕсли: True\nРеплика: | Test',p)
    def test_rewrites_skip_literals_comments_and_multiline_strings(self):
        source='label start:\n    "jump start"\n    # jump start\n    jump start\n    e """line\n    jump start\n    e "text"\n    """\n    e "Hello"\n'
        new=rewrite_statements(source,{'start':'new'},{'e':'hero'});self.assertIn('"jump start"',new);self.assertIn('# jump start',new);self.assertIn('    jump new\n',new);self.assertIn('    jump start\n    e "text"',new);self.assertIn('hero "Hello"',new)
    def test_nested_local_references_and_literal_after_rename(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'native/game').mkdir(parents=True);(root/'native/game/script.rpy').write_text('default value = 1\nlabel start:\n    "jump start"\n    if value:\n        jump .a\nlabel .a:\n    jump .b\nlabel .b:\n    return\n')
            p,r=import_native(default_project(),root,asset_name);p['scenes'][0]['id']='opening';p['start']='opening';p['scenes'][1]['id']='local_a'
            for at,e in walk(p['scenes'][0]['events']):
                if e.get('target')=='start_a':e['target']='local_a'
            compile_project(p,root/'assets',root/'out');text=(root/'out/game/script.rpy').read_text();self.assertIn('"jump start"',text);self.assertIn('jump local_a',text);self.assertIn('jump opening.b',text)
    def test_if_with_unsupported_expression_remains_source(self):
        from native_bridge import parse_body
        e=parse_body('    if custom_function():\n        "Text"\n',[],{}, {},{},variables=set())[0];self.assertEqual(e['type'],'raw')

class WorkflowHTTPTests(unittest.TestCase):
    def test_parse_and_source_aware_clipboard_endpoints(self):
        import app,json,threading,urllib.request
        old=app.PROJECTS
        with tempfile.TemporaryDirectory() as td:
            app.PROJECTS=Path(td);root=app.PROJECTS/'demo';(root/'native/game').mkdir(parents=True)
            (root/'native/game/script.rpy').write_text('default trust = 0\nlabel start:\n    jump .a\nlabel .a:\n    return\n')
            p,r=import_native(default_project(),root,asset_name);p['scenes'][0]['id']='opening';p['start']='opening';app.save('demo',p)
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
            def post(route,data):
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/'+route,json.dumps({'id':'demo',**data}).encode(),{'Content-Type':'application/json','X-NovelForge-Token':app.TOKEN});return json.load(urllib.request.urlopen(req))
            try:
                result=post('parse-block',{'code':'if trust > 0:\n    "Yes"\nelse:\n    "No"\n','scope':'start'});self.assertEqual(result['events'][0]['type'],'branch')
                copied=post('event-copy',{'event':{'type':'raw','code':'if True:\n    jump .a\n    "jump .a"\n','_source':{'scope':'start'}}})['event']
                self.assertIn('jump opening.a',copied['code']);self.assertIn('"jump .a"',copied['code']);self.assertNotIn('_source',copied)
            finally:server.shutdown();server.server_close();app.PROJECTS=old

if __name__=='__main__':unittest.main()
