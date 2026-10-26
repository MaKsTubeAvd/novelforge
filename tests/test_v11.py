import io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import *
from project_import import *
from story_text import *
class UpgradeTests(unittest.TestCase):
    def test_plain_word_and_text(self):
        for text in (SAMPLE,word_text(simple_docx())):
            p,n=import_text(text,default_project());self.assertGreater(n,5);self.assertFalse(validate(p)['errors'])
            self.assertEqual(len({s['id'] for s in p['scenes']}),len(p['scenes']))
    def test_layout_overlap(self):
        p=default_project();p['interface']['textboxX']=.6
        self.assertTrue(validate(p)['errors'])
        p=default_project();p['interface']['fontSize']=24
        self.assertFalse(validate(p)['errors'])
    def test_zip_slip(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('../outside.rpy','label start:\n return')
        with self.assertRaises(ValueError):entries_from_zip(out.getvalue())
    def test_native_preserved_and_themed(self):
        source=b'define e = Character("Emma")\nlabel start:\n    e "Hello"\n    return\n'
        files={'Test/game/script.rpy':source,'Test/game/options.rpy':b'define config.name = "Native Game"\n','Test/game/nested/data.txt':b'KEEP'}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,report=import_project(files,root/'project',default_project,upgrade_project,lambda s:s.replace('/','_'))
            self.assertTrue(p['native']['enabled']);self.assertEqual(report['kind'],'renpy-editable')
            compile_project(p,root/'project/assets',root/'plain')
            self.assertEqual((root/'plain/game/script.rpy').read_bytes(),source)
            self.assertEqual((root/'plain/game/nested/data.txt').read_bytes(),b'KEEP')
            p['native']['useStudioUI']=True;p['interface']['elements']=[{'type':'button','label':'Restart','x':.1,'y':.1,'width':200,'target':p['start']}]
            compile_project(p,root/'project/assets',root/'themed')
            ui=(root/'themed/game/zz_novelforge_ui.rpy').read_text();self.assertIn('Jump("start")',ui)
            self.assertEqual((root/'themed/game/script.rpy').read_bytes(),source)
    def test_unicode_assets_remap(self):
        p=default_project();p['characters'][0]['sprite']='герой.png'
        files={'project.json':json.dumps(p).encode(),'assets/герой.png':b'fake-image'}
        with tempfile.TemporaryDirectory() as td:
            new,r=import_project(files,td,default_project,upgrade_project,lambda s:'hero.png')
            self.assertEqual(new['characters'][0]['sprite'],'hero.png');self.assertTrue((Path(td)/'assets/hero.png').exists())
    def test_layers_validate(self):
        p=default_project();p['credits']['images']=[{'asset':'x.png','x':2,'y':.2,'width':300,'height':100}]
        self.assertTrue(validate(p)['errors'])
    def test_migration_preserves_story(self):
        old=_default_v1() if '_default_v1' in globals() else default_project()
        p=upgrade_project(old);self.assertEqual(p['scenes'],upgrade_project(old)['scenes']);self.assertIn('pattern',p['interface'])
if __name__=='__main__':unittest.main()
