"""Disk-backed, bounded multi-project imports. Never execute imported source."""
import json, os, re, shutil, zipfile, hashlib
from pathlib import Path, PurePosixPath
from collections.abc import Mapping
from project_import import SKIP

MAX_BYTES = 32 * 1024**3
MAX_FILES = 200000

def safe_relative(name):
    name=name.replace('\\','/'); p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or ':' in name or '\x00' in name:
        raise ValueError('Небезопасный путь: '+name)
    return name

class DiskEntries(Mapping):
    def __init__(self, root):
        self.root=Path(root); self.names={}
        total=0
        for base,dirs,files in os.walk(self.root,followlinks=False):
            dirs[:]=[d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink()]
            for name in files:
                f=Path(base)/name
                if f.is_symlink():continue
                total+=f.stat().st_size
                self.names[f.relative_to(self.root).as_posix()]=f
                if total>MAX_BYTES or len(self.names)>MAX_FILES:raise ValueError('Лимит: 32 ГБ / 200 000 файлов')
    def __iter__(self):return iter(self.names)
    def __len__(self):return len(self.names)
    def __getitem__(self,key):return self.names[key].read_bytes()
    def copy_to(self,key,target):
        shutil.copy2(self.names[key],target)
    def digest(self,key):
        h=hashlib.sha256()
        with self.names[key].open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        return h.digest()
    def items(self):
        for name in self.names:yield name,self[name]

def extract(archive,dest):
    total=0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>MAX_FILES:raise ValueError('Слишком много файлов')
        seen=set()
        for info in z.infolist():
            name=safe_relative(info.filename);p=PurePosixPath(name)
            if info.is_dir() or any(part in SKIP for part in p.parts):continue
            if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Символические ссылки запрещены')
            if name in seen:raise ValueError('Повтор имени в ZIP')
            seen.add(name);total+=info.file_size
            if total>MAX_BYTES:raise ValueError('Распакованный архив больше 32 ГБ')
            target=Path(dest)/name;target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as src,target.open('wb') as out:shutil.copyfileobj(src,out,1024*1024)

def roots(root):
    root=Path(root);found=[]
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink()]
        b=Path(base)
        metadata=None
        for name in ('project.json','NovelForge-project.json'):
            if name in files:
                if (b/name).stat().st_size>64*1024*1024:continue
                try:
                    if json.loads((b/name).read_text(encoding='utf-8')).get('format')==1:metadata=b;break
                except (ValueError,AttributeError,UnicodeDecodeError):pass
        if metadata or ('game' in dirs and any((b/'game').glob('*.rpy'))):
            found.append(b);dirs[:]=[]
    if not found and any(root.glob('*.rpy')):found=[root]
    return found

def discover(sdk,extra=()):
    candidates=[]
    if sdk:
        s=Path(sdk);candidates.extend([s,s.parent,s.parent/'projects'])
    candidates.extend([Path.home()/'RenPy',Path.home()/'renpy',Path.home()/'Documents'/'RenPy'])
    candidates.extend(Path(p).expanduser() for p in extra if p)
    result=[];seen=set()
    for parent in candidates:
        if not parent.is_dir():continue
        # Only two directory levels: no whole-disk crawling.
        probes=[parent]+[d for d in parent.iterdir() if d.is_dir() and not d.is_symlink() and not d.name.startswith('.')]
        for p in probes:
            if p.name in ('launcher','renpy','lib','doc','tutorial'):continue
            if (p/'game').is_dir() and any((p/'game').glob('*.rpy')) and str(p.resolve()) not in seen:
                seen.add(str(p.resolve()));result.append({'path':str(p.resolve()),'name':p.name})
    return result

def import_disk(root,stage,default,upgrade,asset_name):
    from project_import import import_project,inspect_rpy
    root=Path(root);stage=Path(stage);entries=DiskEntries(root)
    if any(n in entries for n in ('project.json','NovelForge-project.json')):
        return import_project(entries,stage,default,upgrade,asset_name)
    game=root/'game' if (root/'game').is_dir() else root
    stage.mkdir(parents=True,exist_ok=True);(stage/'assets').mkdir(exist_ok=True)
    shutil.copytree(game,stage/'native/game',ignore=lambda base,names:[n for n in names if n in SKIP or (Path(base)/n).is_symlink()],symlinks=False)
    from native_bridge import import_native
    return import_native(upgrade(default()),stage,asset_name)
