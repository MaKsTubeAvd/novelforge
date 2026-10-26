"""Conservative, source-preserving Ren'Py bridge. Imported code is never executed.
Known statements become visual events; arbitrary blocks remain editable source.
"""
import ast,copy,hashlib,json,os,re,shutil,textwrap,bisect
from functools import lru_cache
from pathlib import Path

MEDIA={'.png','.jpg','.jpeg','.webp','.ogg','.mp3','.wav','.opus','.webm','.mp4','.ogv'}
LABEL=re.compile(r'(?m)^label\s+([\w.]+)([^\r\n]*):[^\r\n]*(?:\r?\n|$)')
@lru_cache(maxsize=4)
def logical_lines(text):
    result=[];quote=None;depth=0;line_start=True;i=0;line_position=0;continuation=False
    while i<len(text):
        ch=text[i]
        if line_start and ch not in ' \t\r\n':
            if quote is None and depth==0 and ch!='#' and not continuation:result.append((line_position,i-line_position))
            line_start=False;continuation=False
        if ch=='\n':line_start=True;line_position=i+1
        if quote:
            if ch=='\\':i+=2;continue
            if text.startswith(quote,i):i+=len(quote);quote=None;continue
            i+=1;continue
        if ch=='\\' and (text.startswith('\n',i+1) or text.startswith('\r\n',i+1)):
            i+=3 if text.startswith('\r\n',i+1) else 2;line_start=True;line_position=i;continuation=True;continue
        if ch=='#':
            end=text.find('\n',i)
            if end<0:break
            i=end;continue
        if ch in ('"',"'"):
            quote=ch*3 if text.startswith(ch*3,i) else ch;i+=len(quote);continue
        if ch in '([{':depth+=1
        elif ch in ')]}':depth=max(0,depth-1)
        i+=1
    return tuple(result)

class TopMatch:
    def __init__(self,offset):self.offset=offset
    def start(self):return self.offset
class TopLevel:
    def search(self,text,pos=0):
        positions=[offset for offset,indent in logical_lines(text) if indent==0];i=bisect.bisect_left(positions,pos)
        return TopMatch(positions[i]) if i<len(positions) else None
TOP=TopLevel()
STR=r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
DIALOG=re.compile(r'^(?:(?P<who>[A-Za-z_]\w*)(?P<attrs>(?:\s+[A-Za-z_]\w*)*)\s+)?(?P<literal>'+STR+r')(?P<tail>\s*(?:nointeract)?\s*(?:#.*)?)$')


def digest(data):return hashlib.sha256(data).hexdigest()
def clean_id(name,prefix='label'):
    s=re.sub(r'[^a-zA-Z0-9_]','_',name)
    from core import ident,RESERVED
    if not ident(s) or (s in RESERVED and prefix!='label'):s=prefix+'_'+s
    return s

def literal(node):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('_','__') and node.args:return literal(node.args[0])
    return ast.literal_eval(node)

def character_record(cid,node,expression,filename):
    dynamic=False
    try:
        name_node=node.args[0] if node.args else next(k.value for k in node.keywords if k.arg=='name');name=literal(name_node)
    except (ValueError,TypeError,StopIteration):name=cid;dynamic=True
    kw={}
    for k in node.keywords:
        if k.arg in ('color','who_color','image'):
            try:kw[k.arg]=literal(k.value)
            except (ValueError,TypeError):pass
    image=kw.get('image',cid);image=image if isinstance(image,str) else cid
    return {'id':cid,'name':name if isinstance(name,str) else cid,'color':kw.get('who_color',kw.get('color','#b7a4ff')),'sprite':'','height':'medium','variants':[],'_native':{'file':filename,'expression':expression,'imageTag':image,'dynamicName':dynamic}}

def semantic(event):
    if isinstance(event,dict):return {k:semantic(v) for k,v in event.items() if not k.startswith('_')}
    if isinstance(event,list):return [semantic(v) for v in event]
    return copy.deepcopy(event)
def events_signature(events):return [semantic(e) for e in events]

def dialogue(line):
    m=DIALOG.fullmatch(line.strip())
    if not m or line.lstrip().startswith(('"""',"'''")):return None
    if m['who'] in {'play','queue','stop','scene','show','hide','voice','define','default','image','jump','call','return','with','window','nvl','pause','text','textbutton','add'}:return None
    try:return {'type':'say','character':m['who'] or '', 'text':ast.literal_eval(m['literal']), 'attributes':(m['attrs'] or '').strip(),'nointeract':'nointeract' in m['tail']}
    except (ValueError,SyntaxError):return None

def nested_dialogues(code):
    result=[];logical={offset for offset,indent in logical_lines(code)};offset=0
    for i,line in enumerate(code.splitlines(keepends=True)):
        d=dialogue(line) if offset in logical else None
        if d:result.append(dict(d,line=i))
        offset+=len(line)
    return result

def update_nested(code,changes):
    lines=code.splitlines(keepends=True)
    for item in changes:
        i=int(item['line'])
        if not 0<=i<len(lines):raise ValueError('Реплика отсутствует в блоке')
        old=dialogue(lines[i])
        if not old:raise ValueError('Строка больше не является репликой; перечитайте блок')
        indent=re.match(r'^\s*',lines[i]).group().rstrip('\r\n');end='\r\n' if lines[i].endswith('\r\n') else '\n' if lines[i].endswith('\n') else ''
        who=item.get('character',old['character']);attrs=item.get('attributes',old['attributes'])
        prefix=(who+(' '+attrs if attrs else '')+' ') if who else ''
        # Literal interpolation/tags in native code retain Ren'Py semantics.
        lines[i]=indent+prefix+json.dumps(str(item.get('text',old['text'])),ensure_ascii=False)+(' nointeract' if old['nointeract'] else '')+end
    return ''.join(lines)

def label_regions(text):
    result=[];global_name=''
    top_positions={offset for offset,indent in logical_lines(text) if indent==0}
    for m in LABEL.finditer(text):
        if m.start() not in top_positions:continue
        following=TOP.search(text,m.end());end=following.start() if following else len(text)
        # Top-level comment lines preceding the next definition stay in this label's region.
        raw=m[1]
        if not raw.startswith('.'):global_name=raw.split('.')[0]
        name=global_name+raw if raw.startswith('.') else raw
        result.append({'name':name,'rawName':raw,'header':m.group(),'start':m.start(),'bodyStart':m.end(),'end':end,'body':text[m.end():end]})
    return result

def parse_statement(code,characters,images,path_to_asset,labelmap,variables=(),depth=0):
    stripped=code.strip()
    if stripped.startswith('menu:'):
        content=[l for l in stripped.splitlines()[1:] if l.strip() and not l.lstrip().startswith('#')];options=[];prompt='';i=0;valid=True
        while i<len(content):
            line=content[i];m=re.fullmatch(r'\s*('+STR+r')(?:\s+if\s+(.+))?:\s*',line)
            if m:
                if i+1>=len(content):valid=False;break
                jump=re.fullmatch(r'\s+jump\s+([\w.]+)\s*',content[i+1])
                if not jump:valid=False;break
                option={'text':ast.literal_eval(m[1]),'target':labelmap.get(jump[1],jump[1])}
                if m[2]:
                    from core import expression
                    try:expression(m[2],variables)
                    except (ValueError,SyntaxError):valid=False;break
                    option['condition']=m[2]
                options.append(option);i+=2;continue
            d=dialogue(line)
            if d and not d['character'] and not options:prompt=d['text'];i+=1;continue
            valid=False;break
        if valid and options:
            event={'type':'choice','options':options}
            if prompt:event['prompt']=prompt
            return event
    from story_tree import parse_control
    control=parse_control(code,lambda body:parse_body(body,characters,images,path_to_asset,labelmap,variables=variables,depth=depth+1),variables,logical_lines,STR,depth)
    if control:return control
    d=dialogue(stripped)
    if d and (not d['character'] or any(c['id']==d['character'] for c in characters)):return d
    m=re.fullmatch(r'(scene|show|hide)\s+(.+?)(?:\s+with\s+(dissolve|fade|hpunch|vpunch))?',stripped)
    if m:
        typ,tag,effect=m.groups();effect=effect or 'none';position='center'
        at=re.search(r'\s+at\s+(left|center|right)$',tag)
        if at:position=at[1];tag=tag[:at.start()]
        if typ=='scene' and tag in images:return {'type':'background','asset':images[tag],'effect':effect}
        if typ in ('show','hide') and not tag.startswith(('screen ','expression ')):
            image_tag=tag.split()[0];char=next((c for c in characters if c.get('_native',{}).get('imageTag')==image_tag or c['id']==image_tag),None)
            if char:
                e={'type':'hide' if typ=='hide' else 'show','character':char['id'],'effect':effect}
                if typ=='show':
                    variant=next((v['id'] for v in char.get('variants',[]) if v.get('_tag')==tag),'')
                    if tag not in images and not char.get('sprite'):return None
                    e.update(position=position,variant=variant)
                return e
    m=re.fullmatch(r'play\s+(music|sound)\s+('+STR+r')(.*)',stripped)
    if m:
        path=ast.literal_eval(m[2]);asset=path_to_asset.get(path.replace('\\','/'))
        if asset:
            e={'type':m[1],'asset':asset};extra=m[3]
            for name in ('fadein','volume'):
                number=re.search(r'\b'+name+r'\s+([0-9.]+)',extra)
                if number:e[name]=float(number[1])
            if 'noloop' in extra:e['loop']=False
            elif 'loop' in extra:e['loop']=True
            return e
    if stripped.startswith('stop music'):return {'type':'stop_music'}
    m=re.fullmatch(r'(jump|call)\s+([\w.]+)',stripped)
    if m and m[2] in labelmap:return {'type':m[1],'target':labelmap[m[2]]}
    m=re.fullmatch(r'\$\s+([A-Za-z_]\w*)\s*=\s*(.+)',stripped)
    if m:
        from core import expression
        try:
            expression(m[2],variables)
            if m[1] in variables:return {'type':'set','variable':m[1],'value':m[2]}
        except (ValueError,SyntaxError):pass
    m=re.fullmatch(r'pause\s+([\d.]+)',stripped)
    if m:return {'type':'pause','value':float(m[1])}
    m=re.fullmatch(r'with\s+(dissolve|fade|hpunch|vpunch)',stripped)
    if m:return {'type':'effect','effect':m[1]}
    if stripped=='return':return {'type':'return'}
    return None

def parse_body(body,characters,images,path_to_asset,labelmap,scope='',variables=(),depth=0):
    # Chunk at the label's base indentation; nested code and comments stay together.
    lines=body.splitlines(keepends=True);logical={offset for offset,indent in logical_lines(body)};offset=0;base=min((indent for pos,indent in logical_lines(body)),default=4)
    chunks=[];current=[]
    for line in lines:
        indentation=len(line)-len(line.lstrip(' \t'))
        if offset in logical and line.strip() and not line.lstrip().startswith('#') and indentation==base and current and not re.match(r'(?:elif\b|else\s*:|except\b|finally\s*:)',line.lstrip()):
            chunks.append(''.join(current));current=[]
        current.append(line);offset+=len(line)
    if current:chunks.append(''.join(current))
    events=[]
    for chunk in chunks:
        code=''.join(line[base:] if len(line)>=base and line[:base].isspace() else line for line in chunk.splitlines(keepends=True))
        e=parse_statement(code,characters,images,path_to_asset,labelmap,variables,depth)
        if not e:e={'type':'raw','code':code,'description':code.strip().splitlines()[0][:100] if code.strip() else 'Комментарий'}
        e['_source']={'code':chunk,'baseline':semantic(e),'scope':scope}
        if scope:
            from story_tree import walk
            for at,child in walk([e]):
                if child.get('_source') and not child['_source'].get('scope'):child['_source']['scope']=scope
        events.append(e)
    return events

def import_native(p,project_dir,asset_name,preserve_settings=False):
    root=Path(project_dir);game=root/'native/game';assets=root/'assets';assets.mkdir(exist_ok=True)
    sources={};file_hashes={};warnings=[];path_to_asset={};resource_map={}
    for f in game.rglob('*'):
        if not f.is_file() or f.is_symlink():continue
        rel=f.relative_to(game).as_posix()
        if f.suffix=='.rpy' and not any(x in ('tl','cache') for x in f.relative_to(game).parts):
            if f.stat().st_size>16*1024*1024:warnings.append(rel+': файл больше 16 МБ, сохранён без визуального разбора');continue
            data=f.read_bytes()
            try:sources['game/'+rel]=data.decode('utf-8-sig');file_hashes['game/'+rel]=digest(data)
            except UnicodeDecodeError:warnings.append(rel+': неизвестная кодировка')
        if f.suffix.lower() in MEDIA:
            flat='n_'+digest(rel.encode())[:10]+'_'+asset_name(f.name);path_to_asset[rel]=flat;resource_map[flat]=rel
            dest=assets/flat
            if not dest.exists():
                try:os.link(f,dest)
                except OSError:shutil.copy2(f,dest)
    images={};definitions=[];variables=[];screen_sources=[];gui_values={}
    for filename,text in sources.items():
        metric=re.search(r'gui\.init\(\s*(\d+)\s*,\s*(\d+)',re.sub(r'(?m)^\s*#.*$','',text))
        if metric:gui_values.update({'config.screen_width':int(metric[1]),'config.screen_height':int(metric[2])})
        # One-line literal definitions are editable; all other definitions remain source.
        top_positions={offset for offset,indent in logical_lines(text) if indent==0}
        for m in re.finditer(r'(?m)^(?:define|default)\s+(\w+)\s*=\s*(.+)$',text):
            if m.start() not in top_positions:continue
            expression=m[2].split(' #',1)[0]
            try:node=ast.parse(expression,mode='eval').body
            except SyntaxError:
                following=TOP.search(text,m.end());expression=text[m.start(2):following.start() if following else len(text)].strip()
                try:node=ast.parse(expression,mode='eval').body
                except SyntaxError:continue
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('Character','DynamicCharacter'):
                definitions.append(character_record(m[1],node,expression,filename))
            else:
                try:
                    val=literal(node)
                    if isinstance(val,(int,float,str,bool)) or val is None:variables.append({'id':m[1],'value':val,'_native':{'file':filename,'baseline':val}})
                except (ValueError,TypeError):pass
        for init in re.finditer(r'(?m)^init(?:\s+-?\d+)?\s+python\s*:[^\r\n]*(?:\r?\n|$)',text):
            if init.start() not in top_positions:continue
            end=TOP.search(text,init.end());body=textwrap.dedent(text[init.end():end.start() if end else len(text)])
            try:module=ast.parse(body)
            except SyntaxError:continue
            for assignment in module.body:
                if not isinstance(assignment,ast.Assign) or len(assignment.targets)!=1 or not isinstance(assignment.targets[0],ast.Name):continue
                cid=assignment.targets[0].id;node=assignment.value
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('Character','DynamicCharacter'):definitions.append(character_record(cid,node,ast.unparse(node),filename))
                else:
                    try:value=literal(node)
                    except (ValueError,TypeError):continue
                    if isinstance(value,(int,float,str,bool)) or value is None:variables.append({'id':cid,'value':value,'_native':{'file':filename,'baseline':value,'assignment':True}})
        for m in re.finditer(r'(?m)^image\s+([\w ]+?)\s*=\s*(.+)$',text):
            if m.start() not in top_positions:continue
            try:
                node=ast.parse(m[2],mode='eval').body
                val=literal(node.args[0]) if isinstance(node,ast.Call) and node.args else literal(node)
                if isinstance(val,str) and val in path_to_asset:images[m[1].strip()]=path_to_asset[val]
            except (ValueError,SyntaxError,TypeError):pass
        for m in re.finditer(r'(?m)^(?:define\s+)?(gui\.\w+|config\.screen_width|config\.screen_height)\s*=\s*(.+)$',text):
            try:
                value=literal(ast.parse(m[2],mode='eval').body);json.dumps(value);gui_values[m[1]]=value
            except (ValueError,SyntaxError,TypeError):pass
        for m in re.finditer(r'(?m)^screen\s+(\w+)[^\r\n]*:\s*(?:\r?\n|$)',text):
            if m.start() not in top_positions:continue
            following=TOP.search(text,m.end());end=following.start() if following else len(text)
            screen_sources.append({'name':m[1],'file':filename,'start':m.start(),'end':end,'code':text[m.start():end],'digest':file_hashes[filename]})
    # Ren'Py auto-image convention for files under images/.
    for rel,flat in path_to_asset.items():
        if rel.startswith('images/') and Path(rel).suffix.lower() in {'.png','.jpg','.jpeg','.webp'}:
            tag=Path(rel).stem.replace('_',' ');images.setdefault(tag,flat)
    from core import ident
    for filename,text in sources.items():
        for region in label_regions(text):
            body=region['body'];starts={offset for offset,indent in logical_lines(body)};offset=0
            for line in body.splitlines(keepends=True):
                d=dialogue(line) if offset in starts else None;offset+=len(line)
                if d and d['character'] and ident(d['character']) and not any(c['id']==d['character'] for c in definitions):definitions.append({'id':d['character'],'name':d['character'],'color':'#b7a4ff','sprite':'','height':'medium','variants':[],'_native':{'file':filename,'imageTag':d['character'],'passThrough':True}})
    chars=list({c['id']:c for c in definitions}.values())
    # Resolve image tags from actual show statements if Character has no image= keyword.
    shown=set(re.findall(r'(?m)^\s+show\s+([A-Za-z_]\w*)\b','\n'.join(sources.values())))
    for c in chars:
        tag=c['_native']['imageTag']
        if not any(t==tag or t.startswith(tag+' ') for t in images):
            possible=[t for t in shown if any(n==t or n.startswith(t+' ') for n in images)]
            match=next((t for t in possible if str(c['name']).lower().startswith(t.lower()) or t.lower().startswith(str(c['name']).lower())),None)
            if match:c['_native']['imageTag']=match
    for tag in shown:
        if tag not in ('screen','expression') and not any(c['_native']['imageTag']==tag for c in chars) and any(t==tag or t.startswith(tag+' ') for t in images):
            chars.append({'id':clean_id(('actor_'+tag) if tag in {v['id'] for v in variables} else tag,'char'),'name':tag,'color':'#b7a4ff','sprite':'','height':'medium','variants':[],'_native':{'imageTag':tag,'generated':True}})
    for c in chars:
        tag=c['_native']['imageTag'];variants=[(t,a) for t,a in images.items() if t==tag or t.startswith(tag+' ')]
        c['variants']=[{'id':clean_id(t[len(tag):].strip() or 'base','pose'),'name':t,'asset':a,'_tag':t} for t,a in variants]
        c['sprite']=images.get(tag,variants[0][1] if variants else '')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(c.get('color',''))):c['color']='#b7a4ff'
        c['_native']['baseline']=copy.deepcopy({k:v for k,v in c.items() if k!='_native'})
    all_regions=[(fn,r) for fn,text in sources.items() for r in label_regions(text)]
    labelmap={};used=set()
    for fn,r in all_regions:
        name=r['name'];sid=clean_id(name)
        while sid in used:sid+='x'
        if name in labelmap:raise ValueError('Повтор label '+name+' в исходном проекте')
        used.add(sid);labelmap[name]=sid
    scenes=[]
    for fn,r in all_regions:
        scope=r['name'].split('.')[0];localmap={**labelmap,**{'.'+name.split('.',1)[1]:sid for name,sid in labelmap.items() if name.startswith(scope+'.')}}
        events=parse_body(r['body'],chars,images,path_to_asset,localmap,scope,{v['id'] for v in variables})
        scenes.append({'id':labelmap[r['name']],'name':r['name'],'events':events,'_native':dict(r,file=fn,originalId=r['name'],baseline=events_signature(events),baselineId=labelmap[r['name']])})
    if not scenes:raise ValueError('Не найдено ни одной label с исходным сценарием. Скомпилированные .rpyc не декомпилируются.')
    p=copy.deepcopy(p);native=p.setdefault('native',{});native.update(enabled=True,bridge=True,bridgeVersion=2,labels=[s['id'] for s in scenes],files=sorted('game/'+f.relative_to(game).as_posix() for f in game.rglob('*') if f.is_file()),screens=screen_sources,resources=resource_map,images=images,sourceHashes=file_hashes,guiValues=gui_values,diagnostics=warnings)
    p['scenes']=scenes;p['start']=labelmap.get('start',scenes[0]['id']);p['characters']=chars
    from core import ident,RESERVED
    if preserve_settings:
        source_ids={v['id'] for v in variables}
        variables += [copy.deepcopy(v) for v in p.get('variables',[]) if v['id'] not in source_ids]
    variables=list({v['id']:v for v in variables}.values())
    p['variables']=[v for v in variables if ident(v['id']) and v['id'] not in RESERVED and v['id'] not in {c['id'] for c in chars}]
    # Imported dummy demo mini-games must never reference absent variables.
    if not preserve_settings:
        p['minigames']=[];p['python']=[];p['achievements']=[];p['cutscenes']=[];p['intro']={'video':'','cards':[]};p['interface']['elements']=[];p['interface']['images']=[];p['credits']['images']=[];p['credits']['backgroundImage']=''
        ui=p['interface']
        for source,target in {'gui.text_color':'text','gui.accent_color':'accent','gui.name_text_size':'nameSize','gui.text_size':'fontSize'}.items():
            if source in gui_values:ui[target]=gui_values[source]
        height=gui_values.get('gui.textbox_height');width=gui_values.get('config.screen_width',1280);screen_h=gui_values.get('config.screen_height',720)
        native['resolution']=[width,screen_h]
        if isinstance(height,(int,float)):
            ui['textboxH']=max(.2,min(.5,height/screen_h));ui['textboxY']=max(0,.935-ui['textboxH'])
        menu=gui_values.get('gui.main_menu_background','gui/main_menu.png')
        ui['menuImage']=path_to_asset.get(menu,'');ui['fontSize']=max(12,min(48,round(int(ui['fontSize'])*720/screen_h)));ui['nameSize']=max(12,min(48,round(int(ui['nameSize'])*720/screen_h)))
        name_match=re.search(r'config\.name\s*=\s*(?:_\()?('+STR+r')','\n'.join(sources.values()))
        if name_match:p['title']=ast.literal_eval(name_match[1])
    native['modelBaseline']={'scenes':[s['_native']['originalId'] for s in scenes],'characters':[c['id'] for c in chars],'variables':{v['id']:v['value'] for v in p['variables']}}
    native['overview']=[]
    return p,{'kind':'renpy-editable','labels':len(scenes),'characters':len(chars),'resources':len(resource_map),'screens':len(screen_sources),'warnings':warnings}

def visual_changes(p):
    baseline=p.get('native',{}).get('modelBaseline',{})
    if baseline:
        if {s.get('_native',{}).get('originalId') for s in p.get('scenes',[])}!=set(baseline['scenes']):return True
        if {c['id'] for c in p.get('characters',[])}!=set(baseline['characters']):return True
        if json.dumps({v['id']:v['value'] for v in p.get('variables',[])},sort_keys=True)!=json.dumps(baseline['variables'],sort_keys=True):return True
    for s in p.get('scenes',[]):
        old=s.get('_native')
        if not old or s['id']!=old.get('baselineId') or events_signature(s['events'])!=old.get('baseline'):return True
    for c in p.get('characters',[]):
        old=c.get('_native',{}).get('baseline')
        if old and {k:v for k,v in c.items() if k!='_native'}!=old:return True
    return False

def valid_source_path(name):
    return isinstance(name,str) and name.startswith('game/') and name.endswith('.rpy') and '..' not in Path(name).parts and ':' not in name and '\\' not in name and '\x00' not in name

def validate_native_paths(p):
    native=p['native']
    for name in native.get('sourceHashes',{}):
        if not valid_source_path(name):raise ValueError('Неверный путь исходника: '+str(name))
    for obj in p.get('scenes',[])+p.get('characters',[])+p.get('variables',[]):
        meta=obj.get('_native')
        if isinstance(meta,dict) and meta.get('file') and not valid_source_path(meta['file']):raise ValueError('Неверный путь исходника в метаданных')
    for screen in native.get('screens',[]):
        if not valid_source_path(screen.get('file')):raise ValueError('Неверный путь экрана')
    for flat,rel in native.get('resources',{}).items():
        if Path(flat).name!=flat or flat.startswith('.') or '\\' in flat or Path(rel).is_absolute() or '..' in Path(rel).parts or ':' in rel or '\\' in rel:raise ValueError('Неверный путь ресурса в метаданных')

def label_destinations(p):
    scenes=p['scenes']
    global_renames={s['_native']['originalId']:s['id'] for s in scenes if s.get('_native') and '.' not in s['_native']['originalId'] and s['id']!=s['_native']['baselineId']}
    labelnames={s['id']:s.get('_native',{}).get('originalId',s['id']) if s['id']==s.get('_native',{}).get('baselineId') else s['id'] for s in scenes}
    for sid,name in list(labelnames.items()):
        if '.' in name and name.split('.')[0] in global_renames:labelnames[sid]=global_renames[name.split('.')[0]]+'.'+name.split('.',1)[1]
    originals={s['_native']['originalId']:labelnames[s['id']] for s in scenes if s.get('_native')}
    return labelnames,originals

def compile_native(p,original,dest,event_compiler):
    from story_tree import rewrite_statements,walk
    validate_native_paths(p)
    original=Path(original);dest=Path(dest);game=dest/'game';native=p['native'];scenes=p['scenes']
    labelnames,destinations=label_destinations(p)
    any_renames=any(s.get('_native') and s['id']!=s['_native']['baselineId'] for s in scenes)
    edits={};new=[];renames={s['_native']['originalId']:labelnames[s['id']] for s in scenes if s.get('_native') and s['id']!=s['_native']['baselineId']}
    height_changes={c['id'] for c in p['characters'] if c.get('_native',{}).get('baseline') and c.get('height')!=c['_native']['baseline'].get('height')}
    character_renames={c['_native']['baseline']['id']:c['id'] for c in p['characters'] if c.get('_native',{}).get('baseline',{}).get('id') and c['_native']['baseline']['id']!=c['id']}
    for s in scenes:
        old=s.get('_native');name=labelnames[s['id']]
        if old and s['id']!=old['baselineId']:renames[old['originalId']]=name
        if old and s['id']==old['baselineId'] and events_signature(s['events'])==old['baseline'] and not (any_renames and old.get('rawName','').startswith('.')) and not any(e.get('type')=='show' and e.get('character') in height_changes for path,e in walk(s['events'])):continue
        body=[]
        for e in s['events']:
            if e.get('_source') and semantic(e)==e['_source']['baseline'] and old and not any(child.get('type')=='show' and child.get('character') in height_changes for at,child in walk([e])):
                code=e['_source']['code'];scope=e['_source'].get('scope','')
                if any_renames:code=rewrite_statements(code,scope=scope,destinations=destinations)
                body.append(code);continue
            if e['type']=='raw':
                code=e.get('code','')
                if any_renames or not old:code=rewrite_statements(code,scope=e.get('_source',{}).get('scope') or (old['originalId'].split('.')[0] if old else ''),destinations=destinations)
                body.append(textwrap.indent(code.rstrip()+'\n','    '));continue
            context=dict(p,_nativeDestinations=destinations,_nativeScope=old['originalId'].split('.')[0] if old else e.get('_source',{}).get('scope',''))
            lines=event_compiler(e,context)
            text='\n'.join(lines)+'\n'
            text=rewrite_statements(text,targets={'nfscene_'+sid:label for sid,label in labelnames.items()})
            body.append(text)
        header=(old['header'] if s['id']==old['baselineId'] and not (any_renames and old.get('rawName','').startswith('.')) else re.sub(r'^label\s+[\w.]+','label '+name,old['header'])) if old else 'label '+name+':\n'
        block=header+(''.join(body) if body else '    pass\n')
        if old:edits.setdefault(old['file'],[]).append((old['start'],old['end'],block))
        else:new.append(block)
    # Removed labels are removed from their original source; opaque source outside labels remains.
    active={s.get('_native',{}).get('originalId') for s in scenes}
    for filename,expected in native.get('sourceHashes',{}).items():
        source=original/filename
        data=source.read_bytes()
        if digest(data)!=expected:raise ValueError('Исходник изменился вне визуального редактора: '+filename+'. Обновите индекс проекта перед экспортом.')
        text=data.decode('utf-8-sig');regions=label_regions(text)
        for r in regions:
            if r['name'] not in active:edits.setdefault(filename,[]).append((r['start'],r['end'],''))
        if filename not in edits and not renames and not character_renames:continue
        for a,b,replacement in sorted(edits.get(filename,[]),reverse=True):
            if '\r\n' in text:replacement=replacement.replace('\r\n','\n').replace('\n','\r\n')
            text=text[:a]+replacement+text[b:]
        text=rewrite_statements(text,targets=renames,speakers=character_renames)
        target=dest/filename;target.write_bytes((b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b'')+text.encode('utf-8'))
        cached=target.with_suffix('.rpyc')
        if cached.exists():cached.unlink()
    extra=['# NovelForge imported project additions — UTF-8','']+new
    # Preserve existing Character arguments when changing a literal name or colour.
    used_speakers={e.get('character') for s in scenes for path,e in walk(s['events']) if e.get('type')=='say'}
    for c in p['characters']:
        old=c.get('_native',{});baseline=old.get('baseline',{})
        if not old or (old.get('generated') and c['id'] in used_speakers) or any(c.get(k)!=baseline.get(k) for k in ('id','name','color')):
            if old.get('expression'):
                try:
                    node=ast.parse(old['expression'],mode='eval').body
                    if node.args:node.args[0]=ast.Constant(c['name'])
                    else:node.args=[ast.Constant(c['name'])]
                    if isinstance(node.func,ast.Name) and node.func.id=='DynamicCharacter' and c['name']!=baseline.get('name'):node.func=ast.Name(id='Character',ctx=ast.Load())
                    node.keywords=[k for k in node.keywords if k.arg not in ('color','who_color','name')]+[ast.keyword(arg='color',value=ast.Constant(c['color']))];expression=ast.unparse(node)
                except (SyntaxError,IndexError,AttributeError):expression='Character('+json.dumps(c['name'],ensure_ascii=False)+', color='+json.dumps(c['color'])+')'
            else:expression='Character('+json.dumps(c['name'],ensure_ascii=False)+', color='+json.dumps(c['color'])+')'
            extra+=['init 950 python:','    '+c['id']+' = '+expression] if old.get('expression') else ['init 950:','    define '+c['id']+' = '+expression]
        tag=old.get('imageTag',c['id']);current=[(tag,c.get('sprite',''))]+[(v.get('_tag',tag+' '+v['id']),v.get('asset','')) for v in c.get('variants',[])]
        base_assets={tag:baseline.get('sprite','')};base_assets.update({v.get('_tag',tag+' '+v['id']):v.get('asset','') for v in baseline.get('variants',[])})
        for image,asset in current:
            if asset and asset!=base_assets.get(image):extra+=['init 950 python:','    renpy.image('+repr(image)+', Image('+repr('assets/'+asset)+'))']
    defined='\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in (original/'game').rglob('*.rpy'))
    for v in p['variables']:
        old=v.get('_native')
        if isinstance(old,dict) and old.get('assignment'):
            if type(old.get('baseline')) is not type(v['value']) or old.get('baseline')!=v['value']:extra+=['init 950 python:','    '+v['id']+' = '+repr(v['value'])]
            continue
        if isinstance(old,dict) and (type(old.get('baseline')) is not type(v['value']) or old.get('baseline')!=v['value']):
            f=dest/old['file'];text=f.read_text(encoding='utf-8-sig');text=re.sub(r'(?m)^((?:define|default)\s+'+re.escape(v['id'])+r'\s*=)[^\r\n]*',lambda m:m[1]+' '+repr(v['value']),text);f.write_text(text,encoding='utf-8')
        if not re.search(r'(?m)^(?:define|default)\s+'+re.escape(v['id'])+r'\s*=',defined):extra+=['default '+v['id']+' = '+repr(v['value'])]
    extra+=['init 950 python:','    import importlib','    nf_modules = {}'] if any(plug.get('asset') and plug['mode']=='function' for plug in p.get('python',[])) else ['init 950 python:','    pass']
    for plug in p.get('python',[]):
        if not plug.get('asset'):continue
        source=Path(original).parent/'assets'/plug['asset']
        if Path(plug['asset']).name!=plug['asset'] or not re.fullmatch(r'[A-Za-z_]\w*',plug['id']):raise ValueError('Неверный модуль Python')
        if plug['mode']=='label':
            target=game/'plugins'/('nf_'+plug['id']+'.rpy');target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
        else:
            shutil.copy2(source,game/('nfplugin_'+plug['id']+'.py'));extra.append('    nf_modules['+repr(plug['id'])+'] = importlib.import_module('+repr('nfplugin_'+plug['id'])+')')
    for achievement in p.get('achievements',[]):extra.append('    achievement.register('+repr(achievement['id'])+', steam='+repr(achievement.get('steam') or achievement['id'])+')')
    if p.get('steam',{}).get('enabled') and p['steam'].get('appid'):extra.append('    config.steam_appid = '+str(int(p['steam']['appid'])))
    # A new start selection can route the original entry label without deleting it.
    if p.get('start') and labelnames.get(p['start'])!='start':
        start_scene=next((s for s in scenes if labelnames[s['id']]=='start'),None)
        if start_scene and p['start']!=start_scene['id']:
            # Rewrite only the entry body, leaving selected target and every other label intact.
            fn=start_scene['_native']['file'];target=dest/fn;text=target.read_text(encoding='utf-8-sig')
            r=next((r for r in label_regions(text) if r['name']=='start'),None)
            if r:target.write_text(text[:r['bodyStart']]+'    jump '+labelnames[p['start']]+'\n'+text[r['end']:],encoding='utf-8')
        elif not start_scene:extra+=['label start:','    jump '+labelnames[p['start']]]
    # Credits/cutscenes can be inserted in any imported label using normal visual events.
    from core import card_script,RUNTIME,screen_script
    for cut in p.get('cutscenes',[]):extra+=['label nfcut_'+cut['id']+':']+card_script(cut.get('cards',[]))+['    return']
    extra+=['label nf_credits:','    call screen nf_credits_screen','    return']
    if p.get('intro',{}).get('cards') or p.get('intro',{}).get('video'):
        intro=['    $ renpy.movie_cutscene('+repr('assets/'+p['intro']['video'])+')'] if p['intro'].get('video') else card_script(p['intro']['cards'])
        existing=next((s for s in scenes if s.get('_native',{}).get('originalId')=='splashscreen'),None)
        if existing:
            fn=existing['_native']['file'];f=dest/fn;text=f.read_text(encoding='utf-8-sig');r=next(r for r in label_regions(text) if r['name']=='splashscreen');f.write_text(text[:r['bodyStart']]+'\n'.join(intro)+'\n'+text[r['bodyStart']:],encoding='utf-8')
        else:extra+=['label splashscreen:']+intro+['    return']
    extra_text='\n'.join(extra)+'\n'
    extra_text=rewrite_statements(extra_text,targets=renames,speakers=character_renames)
    (game/'zz_novelforge_story.rpy').write_text(extra_text,encoding='utf-8')
    (game/'zz_novelforge_runtime.rpy').write_text(RUNTIME,encoding='utf-8')
    # Supplemental screens do not replace the original game UI unless explicitly selected.
    if not native.get('useStudioUI'):
        screens=screen_script(p);parts=[]
        for m in re.finditer(r'(?m)^screen\s+(nf_composition|nf_credits_screen|nf_card)[^\r\n]*:(?:\r?\n|$)',screens):
            end=TOP.search(screens,m.end());block=screens[m.start():end.start() if end else len(screens)];lines=block.splitlines();properties=[line for line in lines[1:] if line.startswith('    modal ')];body=[line for line in lines[1:] if not line.startswith('    modal ')]
            background='    add Solid(data.get("background", "#111126"))\n' if m[1]=='nf_composition' else '    add Solid('+repr(p['interface']['background'])+')\n' if m[1]=='nf_credits_screen' else ''
            wrap=lines[0]+'\n'+'\n'.join(properties)+'\n'+background+'    fixed:\n        xsize 1280\n        ysize 720\n        at Transform(xalign=0.5, yalign=0.5, zoom=min(config.screen_width / 1280.0, config.screen_height / 720.0))\n'+textwrap.indent('\n'.join(body),'    ')+'\n'
            parts.append(wrap)
        for m in re.finditer(r'(?m)^transform\s+(nf_card_appear|nf_credit_roll)[^\r\n]*:',screens):
            end=TOP.search(screens,m.end());parts.insert(0,screens[m.start():end.start() if end else len(screens)])
        (game/'zz_novelforge_cinema.rpy').write_text('init offset = 900\n'+'\n'.join(parts),encoding='utf-8')
    return labelnames
