"""Transactional ZIP/JSON/folder imports; native Ren'Py source stays intact."""
import ast,copy,io,json,re,shutil,zipfile,hashlib
from pathlib import Path,PurePosixPath
RESOURCE={'.png','.jpg','.jpeg','.webp','.ogg','.mp3','.wav','.opus','.webm','.mp4','.ogv','.py','.rpy'}
SKIP={'__pycache__','cache','saves','.git','node_modules'}

def entries_from_zip(data):
    z=zipfile.ZipFile(io.BytesIO(data));entries={}
    infos=z.infolist()
    if len(infos)>15000 or sum(f.file_size for f in infos)>1024**3:raise ValueError('Проект больше 1 ГБ или содержит слишком много файлов')
    for f in infos:
        name=f.filename.replace('\\','/');path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or re.match(r'^[A-Za-z]:',name):raise ValueError('Небезопасный путь в архиве: '+name)
        if f.is_dir() or any(x in SKIP for x in path.parts):continue
        if (f.external_attr>>16)&0o170000==0o120000:raise ValueError('Символические ссылки не поддерживаются')
        if name in entries:raise ValueError('Повтор файла в ZIP: '+name)
        entries[name]=z.read(f)
    return entries

def normalize_native(entries):
    options=[n for n in entries if n.endswith('game/options.rpy')]
    scripts=[n for n in entries if n.endswith('game/script.rpy')]
    anchors=options or scripts
    if not anchors:
        # Also accept a ZIP whose root is the game directory itself.
        if any(n.endswith('.rpy') and '/' not in n for n in entries):return {'game/'+n:b for n,b in entries.items()}
        raise ValueError('Не найден проект. Нужен ZIP NovelForge или Ren’Py с папкой game и исходниками .rpy; .rpa/.rpyc не распаковываются')
    roots={n.rsplit('game/',1)[0] for n in anchors}
    if len(roots)!=1:raise ValueError('В архиве несколько проектов Ren’Py; загрузите один')
    root=roots.pop();out={}
    for n,b in entries.items():
        if n.startswith(root+'game/'):out[n[len(root):]]=b
    return out

def inspect_rpy(files):
    """Read labels/dialogue for navigation; never run imported Python."""
    labels=[];characters=[];diagnostics=[]
    for filename in sorted(files):
        if not filename.endswith('.rpy'):continue
        data=files[filename]
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:diagnostics.append(filename+': неизвестная кодировка, исходник сохранен');continue
        current=None
        for line in text.splitlines():
            m=re.match(r'^define\s+(\w+)\s*=\s*Character\(\s*(["\'])(.*?)\2',line)
            if m:characters.append({'id':m[1],'name':m[3],'color':'#b7a4ff','sprite':'','height':'medium'})
            m=re.match(r'^label\s+(\w+)(?:\([^)]*\))?\s*:',line)
            if m:
                current={'id':m[1],'name':m[1],'events':[]};labels.append(current);continue
            if current:
                m=re.match(r'^\s+(?:(\w+)\s+)?("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')\s*$',line)
                if m:
                    try:current['events'].append({'type':'say','character':m[1] or '', 'text':ast.literal_eval(m[2])})
                    except (ValueError,SyntaxError):pass
    return labels,characters,diagnostics

def import_project(entries,stage,default_project,upgrade,asset_name):
    stage=Path(stage);(stage/'assets').mkdir(parents=True,exist_ok=True)
    candidates=[]
    for n in entries:
        if PurePosixPath(n).name not in ('project.json','NovelForge-project.json') or 'build' in PurePosixPath(n).parts:continue
        data=entries[n]
        try:
            metadata=json.loads(data)
            if isinstance(metadata,dict) and metadata.get('format')==1:candidates.append(n)
        except (ValueError,UnicodeDecodeError):pass
    if candidates:
        shallow=min(len(PurePosixPath(n).parts) for n in candidates)
        candidates=[n for n in candidates if len(PurePosixPath(n).parts)==shallow]
        roots=[n for n in candidates if PurePosixPath(n).name=='project.json']
        if roots:candidates=roots
    if candidates:
        if len(candidates)!=1:raise ValueError('В архиве должен быть один project.json')
        name=candidates[0];p=json.loads(entries[name]);p=upgrade(p);prefix=str(PurePosixPath(name).parent);prefix='' if prefix=='.' else prefix+'/'
        mapping={};contents={}
        for fn in entries:
            if not fn.startswith(prefix):continue
            rel=fn[len(prefix):]
            if rel.startswith(('assets/','game/assets/')):
                # Asset paths in a NovelForge project are always flat; collisions are errors.
                old=PurePosixPath(rel).name
                if Path(old).suffix.lower() not in RESOURCE:continue
                new=asset_name(old);digest=entries.digest(fn) if hasattr(entries,'digest') else hashlib.sha256(entries[fn]).digest()
                if new in contents and contents[new]!=digest:raise ValueError('Конфликт имен ресурсов: '+old)
                contents[new]=digest;mapping[old]=new
                if hasattr(entries,'copy_to'):entries.copy_to(fn,stage/'assets'/new)
                else:(stage/'assets'/new).write_bytes(entries[fn])
        def remap(x):
            if isinstance(x,dict):return {k:remap(v) for k,v in x.items()}
            if isinstance(x,list):return [remap(v) for v in x]
            return mapping.get(x,x) if isinstance(x,str) else x
        # Only asset-bearing fields should be renamed; ordinary dialogue must be preserved.
        def fix(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ('asset','sprite','menuImage','backgroundImage') and isinstance(v,str):x[k]=mapping.get(v,v)
                    else:fix(v)
            elif isinstance(x,list):
                for v in x:fix(v)
        fix(p)
        for plug in p.get('python',[]):
            if not plug.get('asset'):continue
            source=prefix+('game/plugins/nf_'+plug['id']+'.rpy' if plug['mode']=='label' else 'game/nfplugin_'+plug['id']+'.py')
            if source in entries:(stage/'assets'/asset_name(plug['asset'])).write_bytes(entries[source])
        # Backups of imported native projects retain their full original source tree.
        for n in entries:
            rel=n[len(prefix):] if n.startswith(prefix) else ''
            if rel.startswith('native/game/'):
                target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True)
                if hasattr(entries,'copy_to'):entries.copy_to(n,target)
                else:target.write_bytes(entries[n])
        if p.get('native',{}).get('enabled') and not (stage/'native/game').exists():
            for n in entries:
                rel=n[len(prefix):] if n.startswith(prefix) else ''
                if rel.startswith('game/') and not PurePosixPath(rel).name.startswith('zz_novelforge_') and '/nf_ui/' not in rel:
                    target=stage/'native'/rel;target.parent.mkdir(parents=True,exist_ok=True)
                    if hasattr(entries,'copy_to'):entries.copy_to(n,target)
                    else:target.write_bytes(entries[n])
        for n in entries:
            rel=n[len(prefix):] if n.startswith(prefix) else ''
            if rel.startswith('_original_sources/game/') and rel.endswith('.rpy'):
                target=stage/'native'/rel[len('_original_sources/'):];target.parent.mkdir(parents=True,exist_ok=True)
                if hasattr(entries,'copy_to'):entries.copy_to(n,target)
                else:target.write_bytes(entries[n])
        return p,{'kind':'novelforge','warnings':[]}
    native=normalize_native(entries)
    for n,b in native.items():
        target=stage/'native'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    from native_bridge import import_native
    return import_native(upgrade(default_project()),stage,asset_name)
