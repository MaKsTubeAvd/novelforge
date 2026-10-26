#!/usr/bin/env python3
"""Local-only NovelForge server. Python standard library, no pip requirements."""
import argparse
import hashlib
import base64
import datetime
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from core import default_project, validate, compile_project, import_docx, make_docx, project_rows, friendly_template, upgrade_project
from project_import import entries_from_zip, import_project, inspect_rpy
from large_import import MAX_BYTES, extract, roots, discover, import_disk, safe_relative
from audio_studio import synthesize
from native_bridge import import_native,visual_changes,nested_dialogues,update_nested,label_regions,validate_native_paths
from story_text import import_text, word_text, simple_docx, SAMPLE
from scenario_plain import import_plain,export_plain,restore_sources,SAMPLE as PLAIN_SAMPLE

ROOT=Path(__file__).resolve().parent
PROJECTS=ROOT/'projects'; PROJECTS.mkdir(exist_ok=True)
TOKEN=secrets.token_urlsafe(32); LOCK=threading.RLock()
EXTENSIONS={'.png','.jpg','.jpeg','.webp','.ogg','.mp3','.wav','.opus','.webm','.mp4','.ogv','.py','.rpy'}
SDK=''
RUNS={}
UPLOAD_TOTAL={}
UPLOADS=ROOT/'uploads'; UPLOADS.mkdir(exist_ok=True)

def batch_import(source):
    results=[]
    candidates=roots(source)
    if not candidates:raise ValueError('Не найдены исходные проекты RenPy или NovelForge')
    for root in candidates:
        new_id='novel_'+secrets.token_hex(4)
        try:
            with tempfile.TemporaryDirectory(dir=PROJECTS) as td:
                stage=Path(td);p,report=import_disk(root,stage,default_project,upgrade_project,asset_name)
                (stage/'project.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
                os.replace(stage,folder(new_id))
            save(new_id,p);results.append({'id':new_id,'title':p['title'],'report':report})
        except Exception as ex:results.append({'source':root.name,'error':str(ex)})
    return {'results':results,'projects':list_projects()}


def safe_id(s):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',s): raise ValueError('Неверный ID проекта')
    return s

def folder(id_):
    return PROJECTS/safe_id(id_)

def load(id_):
    p=upgrade_project(json.loads((folder(id_)/'project.json').read_text(encoding='utf-8')))
    if p.get('native',{}).get('enabled') and not p['native'].get('bridge') and (folder(id_)/'native/game').is_dir():
        p,report=import_native(p,folder(id_),asset_name,preserve_settings=True);save(id_,p)
    return p

def save(id_,p,expected=None):
    with LOCK:
        d=folder(id_); d.mkdir(exist_ok=True); (d/'assets').mkdir(exist_ok=True)
        f=d/'project.json'
        old=json.loads(f.read_text(encoding='utf-8')) if f.exists() else None
        if expected is not None and old and expected!=old.get('revision',0): raise RuntimeError('Проект изменен в другой вкладке. Перезагрузите страницу, чтобы не затереть изменения.')
        if old:
            b=d/'backups'; b.mkdir(exist_ok=True)
            shutil.copy2(f,b/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'))
            for extra in sorted(b.glob('*.json'))[:-30]: extra.unlink()
        p['revision']=(old.get('revision',0)+1) if old else 1
        t=f.with_suffix('.tmp'); t.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(t,f)
        return p

def list_projects():
    result=[]
    for f in PROJECTS.glob('*/project.json'):
        try:
            p=json.loads(f.read_text(encoding='utf-8')); result.append({'id':f.parent.name,'title':p['title'],'scenes':len(p['scenes']),'revision':p.get('revision',0)})
        except (OSError,ValueError,KeyError): pass
    return result

def asset_name(name):
    name=Path(name.replace('\\','/')).name
    stem=re.sub(r'[^a-zA-Z0-9_-]','_',Path(name).stem)[:80] or 'asset'
    ext=Path(name).suffix.lower()
    if ext not in EXTENSIONS: raise ValueError('Неподдерживаемый формат: '+ext)
    return stem+ext

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,data,status=200,mime='application/json',filename=None):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        if filename: self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        try:
            u=urlparse(self.path); path=unquote(u.path)
            if path=='/api/bootstrap': return self.send({'token':TOKEN,'projects':list_projects(),'sdk':SDK})
            if path.startswith('/api/project/'):
                id_=path.split('/')[3]; p=load(id_)
                return self.send({'project':p,'assets':[{'name':f.name,'size':f.stat().st_size} for f in (folder(id_)/'assets').iterdir() if f.is_file()]})
            if path.startswith('/api/backups/'):
                d=folder(path.split('/')[3])/'backups'
                return self.send([f.name for f in sorted(d.glob('*.json'),reverse=True)])
            if path.startswith('/download/'):
                parts=path.strip('/').split('/'); id_=parts[1]; kind=parts[2]; p=load(id_)
                if kind=='simple-template':return self.send(simple_docx(),mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename='NovelForge-simple.docx')
                if kind=='scenario-txt':return self.send(export_plain(p,folder(id_)).encode('utf-8-sig'),mime='text/plain; charset=utf-8',filename='scenario.txt')
                if kind=='text-template':return self.send(PLAIN_SAMPLE.encode('utf-8-sig'),mime='text/plain; charset=utf-8',filename='NovelForge-simple.txt')
                if kind=='word': return self.send(make_docx(project_rows(p),'Сценарий '+p['title']),mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename='scenario.docx')
                if kind=='template':
                    return self.send(friendly_template(p),mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename='NovelForge-template.docx')
                if kind in ('export','backup'):
                    with tempfile.TemporaryDirectory() as td:
                        target=Path(td)/'Novel'
                        if kind=='export':
                            from urllib.parse import parse_qs
                            p['_forceExport']=parse_qs(u.query).get('force')==['1']
                            compile_project(p,folder(id_)/'assets',target)
                        else: shutil.copytree(folder(id_),target,ignore=shutil.ignore_patterns('backups','build','native-backups','run.log','__pycache__'))
                        out=io.BytesIO()
                        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                            for f in target.rglob('*'):
                                if f.is_file(): z.write(f,str(Path('Novel' if kind=='export' else 'Project')/f.relative_to(target)))
                        return self.send(out.getvalue(),mime='application/zip',filename='NovelForge-'+kind+'.zip')
            if path.startswith('/asset/'):
                _,_,id_,name=path.split('/',3); f=folder(id_)/'assets'/name
                if name!=Path(name).name or '\\' in name or name.startswith('.'): raise ValueError('Неверный путь')
                # Source code is text for preview, never active HTML.
                mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
                if f.suffix in ('.py','.rpy'): mime='text/plain; charset=utf-8'
                return self.send(f.read_bytes(),mime=mime)
            f=ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))
            if not f.resolve().is_relative_to((ROOT/'web').resolve()): raise ValueError('Неверный путь')
            return self.send(f.read_bytes(),mime=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        except FileNotFoundError: self.send({'error':'Файл не найден'},404)
        except Exception as e: self.send({'error':str(e)},400)
    def do_POST(self):
        global SDK
        try:
            if self.headers.get('X-NovelForge-Token')!=TOKEN: return self.send({'error':'Обновите страницу редактора'},403)
            length=int(self.headers.get('Content-Length','0'))
            if urlparse(self.path).path=='/api/upload-chunk':
                if length<0 or length>8*1024*1024 or (length==0 and not self.headers.get('X-File-Path')):raise ValueError('Часть должна быть до 8 МБ')
                upload=safe_id(self.headers.get('X-Upload-ID',''));offset=int(self.headers.get('X-Upload-Offset','0'));relative=self.headers.get('X-File-Path','')
                if relative:
                    f=UPLOADS/(upload+'-tree')/safe_relative(unquote(relative));f.parent.mkdir(parents=True,exist_ok=True)
                else:f=UPLOADS/(upload+'.zip')
                with LOCK:
                    current=f.stat().st_size if f.exists() else 0
                    if upload not in UPLOAD_TOTAL:
                        tree=UPLOADS/(upload+'-tree');UPLOAD_TOTAL[upload]=sum(p.stat().st_size for p in tree.rglob('*') if p.is_file()) if relative else current
                    if current!=offset or UPLOAD_TOTAL[upload]+length>MAX_BYTES:raise ValueError('Неверный порядок частей или лимит набора 32 ГБ')
                    with f.open('ab') as out:
                        remaining=length
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise ValueError('Загрузка прервана')
                            out.write(chunk);remaining-=len(chunk)
                    UPLOAD_TOTAL[upload]+=length
                return self.send({'offset':offset+length})
            if length>360*1024*1024: raise ValueError('Используйте загрузку частями для больших файлов')
            body=json.loads(self.rfile.read(length)); path=urlparse(self.path).path
            id_=body.get('id','demo')
            if path=='/api/import-large-folder':
                source=UPLOADS/(safe_id(body['upload'])+'-tree')
                try:result=batch_import(source)
                finally:
                    shutil.rmtree(source,ignore_errors=True);UPLOAD_TOTAL.pop(body['upload'],None)
                return self.send(result)
            if path=='/api/import-large':
                upload=safe_id(body['upload']);archive=UPLOADS/(upload+'.zip')
                try:
                    with tempfile.TemporaryDirectory(dir=UPLOADS) as td:
                        extract(archive,td);result=batch_import(td)
                finally:
                    if archive.exists():archive.unlink()
                    UPLOAD_TOTAL.pop(upload,None)
                return self.send(result)
            if path=='/api/discover':
                search_paths=list(body.get('paths',[]));notes=[]
                if SDK:
                    sdk_path=Path(SDK)
                    cmd=[str(sdk_path/'renpy.exe')] if sys.platform=='win32' else ['/bin/sh',str(sdk_path/'renpy.sh')]
                    cmd += [str(sdk_path/'launcher'),'get_projects_directory']
                    env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
                    try:
                        result=subprocess.run(cmd,env=env,cwd=sdk_path,capture_output=True,text=True,timeout=20)
                        search_paths += [line.strip() for line in result.stdout.splitlines() if line.strip() and Path(line.strip()).is_dir()]
                    except (OSError,subprocess.TimeoutExpired):notes.append('Launcher не сообщил папку проектов; укажите путь вручную.')
                return self.send({'found':discover(SDK,search_paths),'notes':notes})
            if path=='/api/import-path':
                source=Path(body['path']).expanduser().resolve()
                if not source.is_dir():raise ValueError('Папка не найдена')
                return self.send(batch_import(source))
            if path=='/api/native-screen-save':
                p=load(id_);validate_native_paths(p);index=int(body['index']);screens=p.get('native',{}).get('screens',[])
                if not 0<=index<len(screens):raise ValueError('Экран не найден')
                screen=screens[index];f=folder(id_)/'native'/screen['file'];data=f.read_bytes()
                if hashlib.sha256(data).hexdigest()!=body.get('digest'):raise RuntimeError('Исходник экрана изменился, откройте его повторно')
                code=body.get('code','')
                if len(code.encode('utf-8'))>2*1024*1024:raise ValueError('Экран больше 2 МБ')
                if not re.match(r'^screen\s+'+re.escape(screen['name'])+r'\b',code):raise ValueError('Сохраните объявление screen '+screen['name'])
                backup=folder(id_)/'native-backups';backup.mkdir(exist_ok=True);(backup/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+f.name)).write_bytes(data)
                text=data.decode('utf-8-sig');text=text[:screen['start']]+code.rstrip()+'\n\n'+text[screen['end']:];f.write_bytes(text.encode('utf-8'))
                refreshed,report=import_native(p,folder(id_),asset_name,preserve_settings=True)
                p['native']=refreshed['native']
                if screen['name'] in ('main_menu','say','choice','save','load','preferences'):p['native']['useStudioUI']=False
                p=save(id_,p,p.get('revision'));return self.send({'project':p})
            if path=='/api/event-copy':
                from story_tree import walk,rewrite_statements
                from native_bridge import label_destinations
                p=load(id_);event=body['event'];labels,destinations=label_destinations(p)
                for at,node in walk([event]):
                    if node.get('type')=='raw':node['code']=rewrite_statements(node.get('code',''),scope=node.get('_source',{}).get('scope') or body.get('scope',''),destinations=destinations)
                    for key in list(node):
                        if key.startswith('_'):node.pop(key)
                return self.send({'event':event})
            if path=='/api/parse-block':
                p=load(id_);native=p.get('native',{});code=body.get('code','')
                if len(code)>2*1024*1024:raise ValueError('Блок больше 2 МБ')
                from native_bridge import parse_body
                scope=body.get('scope','');labels={s.get('_native',{}).get('originalId',s['id']):s['id'] for s in p['scenes']}
                labels.update({'.'+k.split('.',1)[1]:v for k,v in list(labels.items()) if scope and k.startswith(scope+'.')})
                resources={rel:flat for flat,rel in native.get('resources',{}).items()}
                events=parse_body(code,p['characters'],native.get('images',{}),resources,labels,scope,{v['id'] for v in p['variables']})
                return self.send({'events':events})
            if path=='/api/native-block':
                code=body.get('code','')
                if len(code)>2*1024*1024:raise ValueError('Блок больше 2 МБ')
                if 'changes' in body:code=update_nested(code,body['changes'])
                return self.send({'code':code,'dialogues':nested_dialogues(code)})
            if path=='/api/compile-preview':
                p=body.get('project') or load(id_);p['_sourceOnly']=True
                with tempfile.TemporaryDirectory() as td:
                    compile_project(p,folder(id_)/'assets',td)
                    files=[{'name':f.relative_to(td).as_posix(),'text':f.read_text(encoding='utf-8',errors='replace')} for f in sorted((Path(td)/'game').rglob('*.rpy')) if f.stat().st_size<2*1024*1024 and 'tl' not in f.parts]
                return self.send({'files':files})
            if path=='/api/stock':
                name=body['name']
                if name!=Path(name).name or Path(name).suffix.lower()!='.png':raise ValueError('Неверный ресурс')
                src=ROOT/'web/stock'/name
                if not src.is_file():raise ValueError('Ресурс не найден')
                dest=folder(id_)/'assets'/name
                if dest.exists() and dest.read_bytes()!=src.read_bytes():
                    name=Path(name).stem+'_'+secrets.token_hex(3)+'.png';dest=dest.with_name(name)
                shutil.copy2(src,dest);return self.send({'name':name})
            if path=='/api/audio-create':
                data=synthesize(body);name=asset_name(body.get('name','sound')+'.wav');dest=folder(id_)/'assets'/name
                if dest.exists():name=Path(name).stem+'_'+secrets.token_hex(3)+'.wav';dest=dest.with_name(name)
                dest.write_bytes(data);return self.send({'name':name,'size':len(data)})
            if path=='/api/debug-status':
                process=RUNS.get(id_);logs=[]
                for f in (folder(id_)/'run.log',folder(id_)/'build/log.txt',folder(id_)/'build/traceback.txt',folder(id_)/'build/errors.txt'):
                    if f.exists():
                        with f.open('rb') as stream:stream.seek(max(0,f.stat().st_size-128000));logs.append(f.name+'\n'+stream.read().decode('utf-8',errors='replace'))
                return self.send({'running':process is not None and process.poll() is None,'code':process.poll() if process else None,'output':'\n\n'.join(logs)})
            if path=='/api/debug-stop':
                process=RUNS.get(id_)
                if process and process.poll() is None:process.terminate()
                return self.send({'message':'Игра остановлена'})
            if path=='/api/new':
                id_='novel_'+secrets.token_hex(4); p=default_project(); p['title']=str(body.get('title') or 'Новая история'); save(id_,p)
                # Seed only two built-in art assets.
                for f in (PROJECTS/'demo'/'assets').glob('*.png'): shutil.copy2(f,folder(id_)/'assets'/f.name)
                return self.send({'id':id_,'project':p})
            if path=='/api/save': return self.send({'project':save(id_,body['project'],body.get('revision'))})
            if path=='/api/validate': return self.send(validate(body.get('project') or load(id_),folder(id_)/'assets'))
            if path=='/api/upload':
                dest=folder(id_)/'assets'; dest.mkdir(exist_ok=True)
                data=base64.b64decode(body['data'],validate=True)
                if len(data)>256*1024*1024: raise ValueError('Ресурс больше 256 МБ')
                name=asset_name(body['name']); f=dest/name
                if f.exists() and not body.get('overwrite'): name=Path(name).stem+'_'+secrets.token_hex(3)+Path(name).suffix; f=dest/name
                f.write_bytes(data); return self.send({'name':name,'size':len(data)})
            if path=='/api/import-word':
                data=base64.b64decode(body['data'],validate=True)
                if body.get('name','').lower().endswith('.txt'):p,count=import_plain(data.decode('utf-8-sig'),load(id_))
                else:
                    try:p,count=import_docx(data,load(id_))
                    except ValueError as ex:
                        if 'не найдены строки scene' not in str(ex):raise
                        p,count=import_plain(word_text(data),load(id_))
                p=upgrade_project(p);restore_sources(p,folder(id_));report=validate(p,folder(id_)/'assets')
                # Missing assets are actionable warnings; structural errors can be fixed visually.
                save(id_,p,body.get('revision')); return self.send({'project':p,'count':count,'report':report})
            if path in ('/api/import-project','/api/import-folder'):
                if path.endswith('folder'):
                    entries={}
                    for file in body.get('files',[]):
                        name=file['name'].replace('\\','/');parts=Path(name).parts
                        if name.startswith('/') or '..' in parts or ':' in name:raise ValueError('Неверный путь')
                        if any(part in {'cache','saves','__pycache__','.git'} for part in parts):continue
                        entries[name]=base64.b64decode(file['data'],validate=True)
                    if len(entries)>15000 or sum(map(len,entries.values()))>1024**3:raise ValueError('Проект слишком большой')
                elif body.get('name','').lower().endswith('.json'):
                    entries={'project.json':base64.b64decode(body['data'],validate=True)}
                else:entries=entries_from_zip(base64.b64decode(body['data'],validate=True))
                new_id='novel_'+secrets.token_hex(4)
                with tempfile.TemporaryDirectory(dir=PROJECTS) as td:
                    stage=Path(td)
                    p,report=import_project(entries,stage,default_project,upgrade_project,asset_name)
                    # No partially imported project is exposed if anything fails.
                    (stage/'project.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
                    os.replace(stage,folder(new_id))
                p=save(new_id,p)
                return self.send({'id':new_id,'project':p,'report':report})
            if path in ('/api/native-read','/api/native-save'):
                relative=body.get('file','').replace('\\','/');parts=Path(relative).parts
                if not relative.startswith('game/') or '..' in parts or ':' in relative or not relative.endswith('.rpy'):raise ValueError('Выберите исходный .rpy внутри game')
                target=folder(id_)/'native'/relative
                if not target.is_file():raise ValueError('Исходный файл не найден')
                if target.stat().st_size>16*1024*1024:raise ValueError('Исходник больше 16 МБ: редактируйте его внешним редактором')
                content=target.read_bytes();digest=hashlib.sha256(content).hexdigest()
                if path.endswith('read'):return self.send({'text':content.decode('utf-8-sig'),'digest':digest})
                if digest!=body.get('digest'):raise RuntimeError('Файл уже изменен. Откройте его повторно')
                p=load(id_)
                if label_regions(content.decode('utf-8-sig')) and visual_changes(p):raise RuntimeError('Есть визуальные изменения label. Экспортируйте проект и откройте его заново перед заменой исходника, чтобы не потерять правки.')
                text=body.get('text','')
                if len(text.encode('utf-8'))>16*1024*1024:raise ValueError('Сценарий больше 16 МБ')
                backup=folder(id_)/'native-backups';backup.mkdir(exist_ok=True)
                (backup/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+target.name)).write_bytes(content)
                target.write_bytes(text.encode('utf-8'))
                refreshed,report=import_native(p,folder(id_),asset_name,preserve_settings=True)
                if not label_regions(content.decode('utf-8-sig')):
                    # Screen/gui edits update source hashes without resetting visual story edits.
                    p['native']=refreshed['native'];refreshed=p
                refreshed=save(id_,refreshed,p.get('revision'))
                return self.send({'digest':hashlib.sha256(target.read_bytes()).hexdigest(),'project':refreshed})
            if path=='/api/restore':
                name=body['backup']
                if name!=Path(name).name or not re.fullmatch(r'[0-9-]+\.json',name): raise ValueError('Неверная копия')
                p=json.loads((folder(id_)/'backups'/name).read_text(encoding='utf-8')); return self.send({'project':save(id_,p,body.get('revision'))})
            if path=='/api/sdk':
                sdk=Path(body['path']).expanduser().resolve()
                if not (sdk/'renpy.py').is_file(): raise ValueError('Укажите папку SDK, содержащую renpy.py')
                SDK=str(sdk); (ROOT/'settings.json').write_text(json.dumps({'sdk':SDK}),encoding='utf-8'); return self.send({'sdk':SDK})
            if path in ('/api/lint','/api/run','/api/debug-run'):
                if not SDK: raise ValueError('Сначала укажите папку SDK во вкладке Экспорт')
                process=RUNS.get(id_)
                if process and process.poll() is None:raise ValueError('Сначала остановите уже запущенную игру')
                p=load(id_);p['_forceExport']=bool(body.get('force'));p['_debug']=path.endswith('debug-run'); dest=folder(id_)/'build'; shutil.rmtree(dest,ignore_errors=True); report=compile_project(p,folder(id_)/'assets',dest)
                sdk=Path(SDK)
                if sys.platform=='win32': cmd=[str(sdk/'renpy.exe'),str(dest)]
                else:
                    # ZIP may lose executable bits.
                    for f in (sdk/'lib').glob('*/renpy'): f.chmod(f.stat().st_mode|0o111)
                    cmd=['/bin/sh',str(sdk/'renpy.sh'),str(dest)]
                env=os.environ.copy()
                if path.endswith('lint'):
                    cmd+=['lint']; env['SDL_VIDEODRIVER']='dummy'; env['SDL_AUDIODRIVER']='dummy'
                    result=subprocess.run(cmd,cwd=sdk,env=env,capture_output=True,text=True,timeout=120)
                    output=result.stdout+'\n'+result.stderr
                    failed=result.returncode or (1 if 'Full traceback:' in output or 'While running game code:' in output else 0)
                    return self.send({'code':failed,'output':output,'report':report})
                logfile=open(folder(id_)/'run.log','w',encoding='utf-8')
                RUNS[id_]=subprocess.Popen(cmd,cwd=sdk,stdout=logfile,stderr=logfile); logfile.close()
                return self.send({'message':'Игра запущена отдельным окном. При ошибке проверьте журнал ниже.','report':report})
            raise ValueError('Неизвестная операция')
        except RuntimeError as e: self.send({'error':str(e)},409)
        except Exception as e: self.send({'error':str(e)},400)

def main():
    global SDK
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--no-browser',action='store_true'); parser.add_argument('--sdk',default=''); args=parser.parse_args()
    if (ROOT/'settings.json').exists(): SDK=json.loads((ROOT/'settings.json').read_text()).get('sdk','')
    if args.sdk: SDK=str(Path(args.sdk).resolve())
    if not (PROJECTS/'demo'/'project.json').exists(): save('demo',default_project())
    try: server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError as ex:
        print('Не удалось открыть порт. Закройте прежний экземпляр или запустите с --port 8766.',ex); return
    print('NovelForge: http://127.0.0.1:%d  |  Для остановки: Ctrl+C'%args.port)
    if not args.no_browser: threading.Timer(.6,lambda:webbrowser.open('http://127.0.0.1:%d'%args.port)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
