import io,json,sys,tempfile,unittest,wave,zipfile,threading,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from large_import import *
from core import default_project,upgrade_project,validate,compile_project,event_script
from audio_studio import synthesize
import app

class AdvancedTests(unittest.TestCase):
    def test_multigame_disk_import_and_discovery(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in ('One','Two'):
                game=root/name/'game';game.mkdir(parents=True);(game/'script.rpy').write_text('label start:\n    "Hello"\n    return\n');(game/'large.bin').write_bytes(b'x'*100000)
            self.assertEqual(len(roots(root)),2);self.assertEqual(len(discover('',[str(root)])),2)
            p,report=import_disk(root/'One',root/'out',default_project,upgrade_project,app.asset_name)
            self.assertTrue(p['native']['enabled']);self.assertEqual((root/'out/native/game/large.bin').stat().st_size,100000)
    def test_extract_traversal_and_duplicates(self):
        for name in ('../bad','C:/bad','/bad'):
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:z.writestr(name,'bad')
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError):extract(io.BytesIO(b.getvalue()),td)
    def test_audio_valid_wave(self):
        for kind in ('music','tone','bell','noise','rain'):
            data=synthesize({'kind':kind,'seconds':.1})
            with wave.open(io.BytesIO(data)) as w:self.assertEqual(w.getnframes(),2205)
        with self.assertRaises(ValueError):synthesize({'seconds':121})
    def test_mini_rewards_branches_and_dialogue(self):
        p=default_project();g=p['minigames'][0];g.update(kind='hotspot',objects=[{'x':100,'y':200,'width':120,'height':100,'points':5}],winTarget='win',loseTarget='finish',rewardVariable='trust',rewardWin=3,rewardLose=-1)
        p['interface'].update(textOffsetX=20,textOffsetY=3,textAlign='center',textSpeed=50,textAnimation='fade')
        self.assertFalse(validate(p)['errors'])
        code='\n'.join(event_script({'type':'minigame','game':g['id'],'variable':'trust'},p));self.assertIn('nf_hotspot',code);self.assertIn('trust +=',code);self.assertIn('jump nfscene_win',code)
        with tempfile.TemporaryDirectory() as td:
            compile_project(p,Path(__file__).resolve().parents[1]/'projects/demo/assets',td)
            screens=(Path(td)/'game/screens.rpy').read_text();self.assertIn('at nf_text_fade',screens);self.assertIn('text_align 0.5',screens)
    def test_force_keeps_diagnostics(self):
        p=default_project();p['interface']['textboxX']=.99
        self.assertTrue(validate(p)['errors']);p['_forceExport']=True
        r=validate(p);self.assertFalse(r['errors']);self.assertTrue(r['ignoredErrors'])
    def test_http_chunked_multi_and_debug_log(self):
        old_projects,old_uploads=app.PROJECTS,app.UPLOADS
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);app.PROJECTS=root/'projects';app.PROJECTS.mkdir();app.UPLOADS=root/'uploads';app.UPLOADS.mkdir();app.save('demo',default_project())
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
            def post(path,data,headers=None):
                raw=data if isinstance(data,bytes) else json.dumps(data).encode()
                req=urllib.request.Request(base+'/api/'+path,raw,{'X-NovelForge-Token':app.TOKEN,**(headers or {})})
                return json.load(urllib.request.urlopen(req))
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:
                for name in ('A','B'):z.writestr(name+'/game/script.rpy','label start:\n    return\n')
            data=b.getvalue();cut=len(data)//2
            try:
                for offset,part in ((0,data[:cut]),(cut,data[cut:])):post('upload-chunk',part,{'X-Upload-ID':'test','X-Upload-Offset':str(offset)})
                with self.assertRaises(urllib.error.HTTPError):post('upload-chunk',b'bad',{'X-Upload-ID':'test','X-Upload-Offset':'0'})
                result=post('import-large',{'upload':'test'});self.assertEqual(len([r for r in result['results'] if 'id' in r]),2)
                self.assertFalse((app.UPLOADS/'test.zip').exists())
                post('upload-chunk',b'label start:\n    return\n',{'X-Upload-ID':'folder','X-Upload-Offset':'0','X-File-Path':'Game/game/script.rpy'})
                post('upload-chunk',b'',{'X-Upload-ID':'folder','X-Upload-Offset':'0','X-File-Path':'Game/game/__init__.py'})
                folder_result=post('import-large-folder',{'upload':'folder'});folder_id=folder_result['results'][0]['id']
                self.assertTrue((app.PROJECTS/folder_id/'native/game/__init__.py').is_file())
                with self.assertRaises(urllib.error.HTTPError):post('upload-chunk',b'x',{'X-Upload-ID':'badpath','X-Upload-Offset':'0','X-File-Path':'../escape'})
                self.assertFalse(post('debug-status',{'id':'demo'})['running'])
                sound=post('audio-create',{'id':'demo','kind':'bell','seconds':.1});self.assertTrue((app.PROJECTS/'demo/assets'/sound['name']).exists())
            finally:server.shutdown();server.server_close();app.PROJECTS=old_projects;app.UPLOADS=old_uploads
if __name__=='__main__':unittest.main()
