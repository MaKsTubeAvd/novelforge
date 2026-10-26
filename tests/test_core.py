import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import *
ROOT=Path(__file__).resolve().parents[1]
class CoreTests(unittest.TestCase):
    def setUp(self): self.p=default_project()
    def test_demo_valid(self): self.assertEqual(validate(self.p,ROOT/'projects/demo/assets')['errors'],[])
    def test_word_roundtrip(self):
        out,count=import_docx(make_docx(project_rows(self.p)),default_project())
        self.assertEqual(out['scenes'],self.p['scenes']);self.assertEqual(out['characters'],self.p['characters']);self.assertEqual(count,13)
    def test_bad_word_transaction(self):
        old=copy.deepcopy(self.p)
        with self.assertRaises(ValueError): import_docx(make_docx([('scene','{"id":"a"}'),('unknown','{}')]),self.p)
        self.assertEqual(old,self.p)
    def test_no_expression_execution(self):
        for e in ['__import__("os")','trust.real','trust[0]','(lambda: 0)()','open("x")']:
            with self.assertRaises(ValueError): expression(e,{'trust'})
        self.assertEqual(expression('trust >= 2 and not day == 3',{'trust','day'}),'trust >= 2 and not day == 3')
    def test_missing_target_and_asset(self):
        self.p['scenes'][0]['events'][0]['asset']='missing.png'
        self.p['scenes'][0]['events'][-1]['options'][0]['target']='nowhere'
        self.assertGreaterEqual(len(validate(self.p,ROOT/'projects/demo/assets')['errors']),2)
    def test_literal_dialogue(self): self.assertEqual(textq('[evil]{b}'),'"[[evil]{{b}"')
    def test_export(self):
        with tempfile.TemporaryDirectory() as d:
            compile_project(self.p,ROOT/'projects/demo/assets',d)
            script=(Path(d)/'game/script.rpy').read_text()
            self.assertIn('label start:',script);self.assertIn('jump nfscene_play',script)
            self.assertTrue((Path(d)/'game/screens.rpy').exists())
    def test_python_empty_fails(self):
        self.p['scenes'][0]['events'].insert(0,{'type':'python','plugin':'custom'})
        self.assertTrue(validate(self.p)['errors'])
    def test_bad_path(self):
        self.p['characters'][0]['sprite']='../../file.png'
        self.assertTrue(validate(self.p)['errors'])
if __name__=='__main__':unittest.main()
