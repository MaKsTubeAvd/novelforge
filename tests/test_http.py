import base64,io,json,sys,tempfile,threading,unittest,urllib.request,urllib.error,zipfile,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
class HTTPTests(unittest.TestCase):
    def test_roundtrips(self):
        original=app.PROJECTS
        with tempfile.TemporaryDirectory() as td:
            app.PROJECTS=Path(td);app.save('demo',app.default_project())
            shutil.copytree(original/'demo/assets',app.PROJECTS/'demo/assets',dirs_exist_ok=True)
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)
            def get(path):return urllib.request.urlopen(base+path).read()
            token=json.loads(get('/api/bootstrap'))['token']
            def post(route,data):
                req=urllib.request.Request(base+'/api/'+route,json.dumps(data).encode(),{'Content-Type':'application/json','X-NovelForge-Token':token})
                return json.load(urllib.request.urlopen(req,timeout=120))
            try:
                r=post('new',{'title':'HTTP test'});id_=r['id'];p=r['project']
                self.assertFalse(post('validate',{'id':id_,'project':p})['errors'])
                r=post('save',{'id':id_,'project':p,'revision':p['revision']});p=r['project']
                with self.assertRaises(urllib.error.HTTPError) as caught:post('save',{'id':id_,'project':p,'revision':p['revision']-1})
                self.assertEqual(caught.exception.code,409)
                for kind in ['word','template']:
                    data=get('/download/'+id_+'/'+kind);self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
                    r=post('import-word',{'id':id_,'data':base64.b64encode(data).decode(),'revision':p['revision']});p=r['project'];self.assertEqual(r['count'],13);self.assertFalse(r['report']['errors'])
                for kind in ['backup','export']:
                    data=get('/download/'+id_+'/'+kind)
                    if kind=='export':self.assertIn('Novel/game/script.rpy',zipfile.ZipFile(io.BytesIO(data)).namelist())
                    r=post('import-project',{'data':base64.b64encode(data).decode()});self.assertEqual(r['project']['scenes'],p['scenes'])
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(urllib.request.Request(base+'/api/save',b'{}',{'Content-Type':'application/json'}))
                self.assertEqual(caught.exception.code,403)
            finally:server.shutdown();server.server_close();app.PROJECTS=original
if __name__=='__main__':unittest.main()
