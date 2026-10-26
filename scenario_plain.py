"""Readable scenario v2: line commands; optional JSON section preserves advanced settings."""
import copy,csv,io,json
from pathlib import Path

SAMPLE='''# NovelForge TXT 2
# Одна команда на строку. Поля разделяются знаком |.
# Для текста с | используйте кавычки; перенос строки обозначается \\n.
Проект: Моя история
Старт: opening
Персонаж: anna | Анна | anime_woman.png | #b7a4ff | medium
Переменная: trust | 0
Сцена: opening | Знакомство
Фон: room_photo.png | dissolve
Показать: anna | right | | dissolve
Реплика: anna | Привет! Выберем, что делать дальше?
Выбор:
Вариант: Поговорить | talk
Вариант: Уйти | ending
Сцена: talk | Разговор
Значение: trust | trust + 1
Реплика: anna | Спасибо, что остался.
Переход: ending
Сцена: ending | Конец
Реплика: | До новой встречи!
Титры:
Возврат:
'''
MARKER='[Расширенные настройки — можно не редактировать]'

def encode(v):return str(v).replace('\\','\\\\').replace('\r','\\r').replace('\n','\\n')
def decode(v):
    out=[];i=0
    while i<len(v):
        if v[i]=='\\' and i+1<len(v) and v[i+1] in 'nr\\':out.append({'n':'\n','r':'\r','\\':'\\'}[v[i+1]]);i+=2
        else:out.append(v[i]);i+=1
    return ''.join(out)
def join(values):
    fields=[]
    for value in values:
        v=encode(value)
        if '|' in v or '"' in v or v[:1].isspace() or v[-1:].isspace():v='"'+v.replace('"','""')+'"'
        fields.append(v)
    return '|'.join(fields)
def split(value):
    raw=[];start=0;quoted=False;i=0
    while i<len(value):
        if value[i]=='"':
            if quoted and i+1<len(value) and value[i+1]=='"':i+=2;continue
            quoted=not quoted
        if value[i]=='|' and not quoted:raw.append(value[start:i]);start=i+1
        i+=1
    raw.append(value[start:]);values=next(csv.reader([value],delimiter='|',skipinitialspace=True))
    return [decode(v if r.lstrip().startswith('"') else v.strip()) for v,r in zip(values,raw)]

def event_lines(e):
    t=e['type']
    if t in ('branch','menu_block'):
        lines=[]
        if t=='branch':
            for i,arm in enumerate(e['branches']):
                lines.append(('Если: ' if i==0 else 'Иначе если: ')+join([arm['condition']]) if arm.get('condition') else 'Иначе:')
                for child in arm.get('events',[]):lines.extend('  '+line for line in event_lines(child)[0])
            lines.append('Конец условия:')
        else:
            lines=['Меню: '+join([e.get('prompt','')])]
            for arm in e['options']:
                lines.append('Пункт: '+join([arm['text'],arm.get('condition','')]))
                for child in arm.get('events',[]):lines.extend('  '+line for line in event_lines(child)[0])
            lines.append('Конец меню:')
        return lines,{'type','branches','options','prompt'}
    maps={'say':('Реплика',['character','text']),'background':('Фон',['asset','effect']),'show':('Показать',['character','position','variant','effect']),'hide':('Скрыть',['character','effect']),'music':('Музыка',['asset','volume','fadein','loop']),'sound':('Звук',['asset','volume','fadein','loop']),'stop_music':('Стоп музыки',[]),'jump':('Переход',['target']),'call':('Вызов',['target']),'return':('Возврат',[]),'set':('Значение',['variable','value']),'condition':('Условие',['expression','yes','no']),'day':('День',['value']),'pause':('Пауза',['value']),'ending':('Концовка',['text','credits']),'video':('Видео',['asset']),'cutscene':('Катсцена',['id']),'credits':('Титры',[]),'minigame':('Мини-игра',['game','variable']),'achievement':('Достижение',['id']),'effect':('Эффект',['effect']),'python':('Модуль',['plugin','variable']),'raw':('Код RenPy',['code']),'hide_image':('Убрать изображение',['id']),'image':('Изображение',['id','asset','x','y','width','height','opacity'])}
    if t=='choice':return ['Выбор: '+join([e['prompt']]) if e.get('prompt') else 'Выбор:']+['Вариант: '+join([o.get('text',''),o.get('target',''),o.get('condition','')]) for o in e.get('options',[])],{'type','options','prompt'}
    command,fields=maps[t]
    return [command+': '+join([e.get(k,'') for k in fields])],set(fields)|{'type'}

def export_plain(p,project_dir=None):
    lines=['# NovelForge TXT 2','# Основной сценарий можно редактировать как обычный текст.','Проект: '+join([p['title']]),'Старт: '+p['start']]
    for c in p['characters']:lines.append('Персонаж: '+join([c['id'],c['name'],c.get('sprite',''),c['color'],c.get('height','medium')]))
    for v in p['variables']:lines.append('Переменная: '+join([v['id'],json.dumps(v['value'],ensure_ascii=False)]))
    scene_meta={};event_meta={}
    for s in p['scenes']:
        lines+=['','Сцена: '+join([s['id'],s['name']])];scene_meta[s['id']]={k:v for k,v in s.items() if k not in ('id','name','events')};event_meta[s['id']]=[]
        for e in s['events']:
            emitted,keys=event_lines(e);lines+=emitted
            meta={k:v for k,v in e.items() if k not in keys}
            if e['type'] in ('branch','menu_block'):meta['_treeOriginal']=copy.deepcopy(e)
            if e['type']=='choice':meta['_optionExtras']=[{k:v for k,v in o.items() if k not in ('text','target','condition')} for o in e['options']]
            event_meta[s['id']].append(meta)
    settings={k:v for k,v in p.items() if k not in ('title','start','scenes','revision') and not k.startswith('_')}
    supplemental={'project':settings,'sceneMeta':scene_meta,'eventMeta':event_meta}
    if project_dir and p.get('native',{}).get('bridge'):
        root=Path(project_dir)/'native'
        supplemental['sourceFiles']={name:(root/name).read_bytes().decode('utf-8-sig') for name in p['native'].get('sourceHashes',{}) if (root/name).is_file()}
    lines+=['',MARKER,json.dumps(supplemental,ensure_ascii=False,indent=2)]
    return '\n'.join(lines)+'\n'

def import_plain(text,base):
    if not text.lstrip('\ufeff').startswith('# NovelForge TXT 2'):
        from story_text import import_text
        return import_text(text,base)
    script,sep,extra=text.partition(MARKER);data=json.loads(extra) if sep else {};p=copy.deepcopy(base)
    p.update(data.get('project',{}));p['scenes']=[];current=None;count=0;characters={c['id']:copy.deepcopy(c) for c in p['characters']};variables={v['id']:copy.deepcopy(v) for v in p['variables']};declared_chars=[];declared_vars=[]
    reverse={'реплика':('say',['character','text']),'фон':('background',['asset','effect']),'показать':('show',['character','position','variant','effect']),'скрыть':('hide',['character','effect']),'музыка':('music',['asset','volume','fadein','loop']),'звук':('sound',['asset','volume','fadein','loop']),'стоп музыки':('stop_music',[]),'переход':('jump',['target']),'вызов':('call',['target']),'возврат':('return',[]),'значение':('set',['variable','value']),'условие':('condition',['expression','yes','no']),'день':('day',['value']),'пауза':('pause',['value']),'концовка':('ending',['text','credits']),'видео':('video',['asset']),'катсцена':('cutscene',['id']),'титры':('credits',[]),'мини-игра':('minigame',['game','variable']),'достижение':('achievement',['id']),'эффект':('effect',['effect']),'модуль':('python',['plugin','variable']),'код renpy':('raw',['code']),'убрать изображение':('hide_image',['id']),'изображение':('image',['id','asset','x','y','width','height','opacity'])}
    explicit_start=None;stack=[]
    def target_events():
        if not current:raise ValueError('Сначала добавьте сцену')
        if stack and stack[-1]['events'] is None:raise ValueError('Сначала добавьте Пункт:')
        return stack[-1]['events'] if stack else current['events']
    def append_event(e):
        nonlocal count
        events=target_events()
        if not stack:
            meta=data.get('eventMeta',{}).get(current['id'],[]);index=len(events)
            if index<len(meta):e={**copy.deepcopy(meta[index]),**e}
        events.append(e);count+=1;return e
    for number,line in enumerate(script.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,colon,value=line.partition(':');key=key.lower().strip()
        if not colon:raise ValueError('Строка %d: нужна команда с двоеточием'%number)
        try:
            args=split(value.strip()) if value.strip() else []
            if stack and key in ('сцена','персонаж','переменная','проект','старт'):raise ValueError('Завершите вложенный блок перед объявлением')
            if key in ('если','меню'):
                e=append_event({'type':'branch','branches':[{'condition':args[0] if args else 'True','events':[]}]} if key=='если' else {'type':'menu_block','prompt':args[0] if args else '', 'options':[]})
                stack.append({'event':e,'events':e['branches'][0]['events'] if key=='если' else None});continue
            if key in ('иначе','иначе если'):
                if not stack or stack[-1]['event']['type']!='branch':raise ValueError('Иначе без Если')
                arm={'condition':args[0] if key=='иначе если' and args else '', 'events':[]};stack[-1]['event']['branches'].append(arm);stack[-1]['events']=arm['events'];continue
            if key=='пункт':
                if not stack or stack[-1]['event']['type']!='menu_block':raise ValueError('Пункт без Меню')
                arm={'text':args[0],'condition':args[1] if len(args)>1 else '', 'events':[]};stack[-1]['event']['options'].append(arm);stack[-1]['events']=arm['events'];continue
            if key in ('конец условия','конец меню'):
                expected='branch' if key=='конец условия' else 'menu_block'
                if not stack or stack[-1]['event']['type']!=expected:raise ValueError('Неверный конец блока')
                stack.pop();continue
            if key=='проект':p['title']=args[0]
            elif key=='старт':explicit_start=args[0]
            elif key=='персонаж':
                cid=args[0];c=characters.get(cid,{'id':cid,'variants':[]});c.update(name=args[1],sprite=args[2] if len(args)>2 else '',color=args[3] if len(args)>3 and args[3] else '#b7a4ff',height=args[4] if len(args)>4 and args[4] else 'medium');characters[cid]=c;declared_chars.append(cid)
            elif key=='переменная':
                vid=args[0];v=variables.get(vid,{'id':vid});v['value']=json.loads(args[1]);variables[vid]=v;declared_vars.append(vid)
            elif key=='сцена':
                current=copy.deepcopy(data.get('sceneMeta',{}).get(args[0],{}));current.update(id=args[0],name=args[1] if len(args)>1 else args[0],events=[]);p['scenes'].append(current)
            else:
                if current is None:raise ValueError('Сначала добавьте Сцена: id | Название')
                if key=='вариант':
                    if not target_events() or target_events()[-1]['type']!='choice':raise ValueError('Перед вариантом нужна команда Выбор:')
                    o={'text':args[0],'target':args[1]}
                    if len(args)>2 and args[2]:o['condition']=args[2]
                    target_events()[-1]['options'].append(o);continue
                if key=='выбор':
                    e={'type':'choice','options':[]}
                    if args and args[0]:e['prompt']=args[0]
                elif key in reverse:
                    typ,fields=reverse[key];e={'type':typ}
                    for i,k in enumerate(fields):
                        if i<len(args) and (args[i]!='' or k in ('character','text','asset','variant','code','variable')):e[k]=args[i]
                    for k in ('x','y','opacity','width','height','volume','fadein'):
                        if k in e:e[k]=float(e[k])
                    if typ in ('day','pause') and 'value' in e:e['value']=float(e['value'])
                    if typ=='show':e.setdefault('position','center');e.setdefault('variant','')
                    if typ in ('show','hide','background'):e.setdefault('effect','dissolve')
                    for k in ('loop','credits'):
                        if k in e:e[k]=str(e[k]).lower() in ('true','1','да','yes')
                    if typ=='ending' and not sep:e.setdefault('credits',True)
                else:raise ValueError('Неизвестная команда '+key)
                append_event(e)
        except (ValueError,IndexError,KeyError,csv.Error) as ex:raise ValueError('Строка %d: %s'%(number,ex))
    if stack:raise ValueError('Не закрыт блок: добавьте Конец условия: или Конец меню:')
    if not p['scenes']:raise ValueError('Нет ни одной сцены')
    def restore_tree(event,original):
        if event.get('type')!=original.get('type'):return event
        merged={**copy.deepcopy(original),**event}
        key='branches' if event['type']=='branch' else 'options' if event['type']=='menu_block' else None
        if key:
            for i,arm in enumerate(merged[key]):
                old=original.get(key,[])[i] if i<len(original.get(key,[])) else {};newarm={**copy.deepcopy(old),**arm};newarm['events']=[restore_tree(child,old.get('events',[])[j]) if j<len(old.get('events',[])) else child for j,child in enumerate(arm.get('events',[]))];merged[key][i]=newarm
        return merged
    for s in p['scenes']:
        for i,e in enumerate(s['events']):
            if '_treeOriginal' in e:
                old=e.pop('_treeOriginal');e=restore_tree(e,old);s['events'][i]=e
            extras=e.pop('_optionExtras',[])
            for i,o in enumerate(e.get('options',[])):
                if i<len(extras):o.update(extras[i])
    p['characters']=[characters[k] for k in declared_chars];p['variables']=[variables[k] for k in declared_vars];p['start']=explicit_start or p['scenes'][0]['id']
    if data.get('sourceFiles'):p['_sourceFiles']=data['sourceFiles']
    if not sep:p.pop('native',None)
    return p,count

def restore_sources(p,project_dir):
    files=p.pop('_sourceFiles',{})
    if not files:return
    if len(files)>1000 or sum(len(t.encode('utf-8')) for t in files.values())>64*1024*1024:raise ValueError('Исходники в TXT превышают лимит 64 МБ / 1000 файлов')
    root=Path(project_dir)/'native';root.mkdir(exist_ok=True)
    for name,text in files.items():
        parts=Path(name).parts
        if not name.startswith('game/') or '..' in parts or ':' in name or '\\' in name or not name.endswith('.rpy'):raise ValueError('Неверный путь исходника в сценарии')
    from native_bridge import digest,validate_native_paths
    if p.get('native',{}).get('bridge'):validate_native_paths(p)
    for name,text in files.items():
        f=root/name
        # Original source bytes on this project take priority if matching the exported baseline.
        if f.exists():continue
        f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(text.encode('utf-8'));p['native']['sourceHashes'][name]=digest(f.read_bytes())
    for flat,rel in p.get('native',{}).get('resources',{}).items():
        if '..' in Path(rel).parts or Path(rel).is_absolute() or ':' in rel:raise ValueError('Неверный путь ресурса')
        src=Path(project_dir)/'assets'/flat;target=root/'game'/rel
        if src.is_file() and not target.exists():
            import shutil
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
