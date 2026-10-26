"""NovelForge project model, Word interchange, validation and Ren'Py compiler.
Editor requires Python 3.10+; generated scripts target Ren'Py 7.4+ and 8.x.
"""
import ast
import copy
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
RESERVED = {'start', 'splashscreen', 'nf_credits', 'nf_runtime', 'nf_mini', 'nf_intro', 'nf_video', 'nf_pause'}
KEYWORDS = {'True','False','None','and','or','not','if','else','for','while','return','class','def','import','from','pass','in','is','lambda','global','print','exec','renpy','config','store','gui','persistent','achievement'}
EVENTS = ['say','background','show','hide','music','sound','stop_music','choice','jump','condition','set','day','ending','video','cutscene','credits','minigame','python','achievement','pause','effect','raw','return','call','image','hide_image','branch','menu_block']
COLORS = re.compile(r'^#[0-9a-fA-F]{6}$')

def ident(v):
    return bool(IDENT.fullmatch(str(v))) and v not in KEYWORDS and not str(v).startswith('nf_')

def q(v):
    return json.dumps(str(v), ensure_ascii=False)

def textq(v):
    # Ren'Py interpolation and text tags must not execute arbitrary script text.
    return q(str(v).replace('[','[[').replace('{','{{'))

def expression(value, variables):
    tree = ast.parse(str(value), mode='eval')
    allowed = (ast.Expression,ast.Constant,ast.Name,ast.Load,ast.BoolOp,ast.And,ast.Or,ast.UnaryOp,ast.Not,ast.USub,ast.UAdd,ast.BinOp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Mod,ast.Compare,ast.Eq,ast.NotEq,ast.Lt,ast.LtE,ast.Gt,ast.GtE)
    for node in ast.walk(tree):
        if not isinstance(node,allowed):
            raise ValueError('Допустимы значения, переменные, арифметика, сравнения, and/or/not')
        if isinstance(node,ast.Name) and node.id not in variables:
            raise ValueError('Неизвестная переменная: '+node.id)
    return str(value)

def default_project():
    return {'format':1,'revision':0,'title':'Лето на площадке','target':'8','start':'arrival',
      'characters':[{'id':'anna','name':'Анна','color':'#b7a4ff','sprite':'anna.png','height':'medium'}],
      'variables':[{'id':'trust','value':0},{'id':'day','value':1}],
      'scenes':[{'id':'arrival','name':'Знакомство','events':[
        {'type':'background','asset':'court.png','effect':'dissolve'},
        {'type':'day','value':1},
        {'type':'show','character':'anna','position':'right','effect':'dissolve'},
        {'type':'say','character':'anna','text':'Привет! Сыграем в волейбол?'},
        {'type':'choice','options':[{'text':'Конечно!','target':'play'},{'text':'Сначала познакомимся','target':'talk'}]}]},
        {'id':'talk','name':'Разговор','events':[{'type':'say','character':'anna','text':'Я Анна. Рада знакомству!'}, {'type':'set','variable':'trust','value':'trust + 1'},{'type':'jump','target':'play'}]},
        {'id':'play','name':'Первый матч','events':[{'type':'minigame','game':'volley','variable':'trust'},{'type':'condition','expression':'trust >= 3','yes':'win','no':'finish'}]},
        {'id':'win','name':'Победа','events':[{'type':'achievement','id':'FIRST_WIN'},{'type':'ending','text':'Отличная команда!','credits':True}]},
        {'id':'finish','name':'До встречи','events':[{'type':'ending','text':'Продолжим тренировку завтра!','credits':True}]}],
      'interface':{'preset':'violet','accent':'#ad93ff','background':'#111126','panel':'#191831','text':'#f7f4ff','textboxY':0.74,'textboxH':0.24,'fontSize':28,'nameSize':30,'elements':[{'type':'bar','label':'Доверие','variable':'trust','max':10,'x':0.78,'y':0.04,'width':240},{'type':'text','label':'Лето на площадке','x':0.03,'y':0.04,'width':400}]},
      'intro':{'video':'','cards':[{'text':'SimplePen Studio представляет','background':'#12132e','seconds':2},{'text':'Лето на площадке','background':'#27204d','seconds':2}]},
      'cutscenes':[{'id':'opening','cards':[{'text':'За день до финала…','background':'#12132e','seconds':2}]}],
      'credits':{'title':'Над игрой работали','lines':'Автор — ваше имя\nМузыка — укажите авторов\nСпасибо за игру!','seconds':10},
      'minigames':[{'id':'volley','title':'Тренировка подачи','kind':'volleyball','target':5,'seconds':25,'question':'','answers':[]},{'id':'quiz','title':'Правила волейбола','kind':'quiz','target':1,'seconds':30,'question':'Сколько игроков в команде на площадке?','answers':[{'text':'Шесть','correct':True},{'text':'Семь','correct':False}]}],
      'achievements':[{'id':'FIRST_WIN','name':'Первая победа','description':'Завершить тренировку','steam':'FIRST_WIN'}],
      'steam':{'appid':'','enabled':False},'python':[{'id':'custom','asset':'','function':'run','mode':'function'}]}

def validate(p, assets=None):
    errors=[]; warnings=[]
    def error(s): errors.append(s)
    if p.get('format')!=1: error('Неизвестный формат проекта')
    if p.get('target') not in ('7','8'): error('Целевая версия должна быть 7 или 8')
    collections=['characters','variables','scenes','cutscenes','minigames','python']
    indexes={}
    global_ids={}
    for key in collections:
        seen=set()
        for obj in p.get(key,[]):
            id_=obj.get('id','')
            if not ident(id_) or (id_ in RESERVED and key!='scenes'): error(key+': некорректный ID '+str(id_))
            if id_ in seen: error(key+': повтор ID '+str(id_))
            seen.add(id_)
            if key in ('characters','variables'):
                if id_ in global_ids: error('Персонажи и переменные должны иметь разные ID: '+id_)
                global_ids[id_]=True
        indexes[key]=seen
    if p.get('start') not in indexes['scenes']: error('Стартовая сцена не найдена')
    def asset(a,where,ext=None):
        if not a: return
        if Path(a).name != a or a.startswith('.') or '\\' in a: error(where+': неверное имя файла')
        elif assets is not None and not (Path(assets)/a).is_file(): error(where+': отсутствует '+a)
        elif ext and Path(a).suffix.lower() not in ext: error(where+': неподходящий формат '+a)
    images={'.png','.jpg','.jpeg','.webp'}
    for c in p.get('characters',[]):
        if not COLORS.fullmatch(c.get('color','')): error('Цвет персонажа '+c.get('id',''))
        if c.get('height') not in ('small','medium','large'): error('Неверный рост персонажа')
        asset(c.get('sprite'),'Спрайт',images)
    vars_=indexes['variables']
    for v in p.get('variables',[]):
        if not isinstance(v.get('value'),(str,int,float,bool)): error('Начальное значение переменной должно быть простым')
    a_ids=set()
    for a in p.get('achievements',[]):
        if not IDENT.fullmatch(a.get('id','')) or a['id'] in a_ids: error('Неверный или повторный ID достижения')
        a_ids.add(a.get('id'))
    def cards(cs):
        for c in cs:
            if not COLORS.fullmatch(c.get('background','#111126')): error('Неверный цвет карточки')
            try:
                if not 0.1<=float(c.get('seconds',2))<=3600: raise ValueError()
            except (TypeError,ValueError): error('Длительность карточки должна быть от 0.1 до 3600')
            asset(c.get('asset'),'Карточка',images)
    cards(p.get('intro',{}).get('cards',[]))
    asset(p.get('intro',{}).get('video'),'Заставка',{'.webm','.ogv','.mp4'})
    for c in p.get('cutscenes',[]): cards(c.get('cards',[]))
    for g in p.get('minigames',[]):
        if g.get('kind') not in ('quiz','clicker','timing','volleyball'): error('Неизвестный тип мини-игры')
        try:
            if not 1<=int(g.get('target',5))<=1000 or not 1<=float(g.get('seconds',30))<=3600: raise ValueError()
        except (TypeError,ValueError): error('Неверные параметры мини-игры')
        if g.get('kind')=='quiz' and (len(g.get('answers',[]))<2 or not any(a.get('correct') for a in g.get('answers',[]))): error('В викторине нужны 2 ответа и правильный ответ')
    for plug in p.get('python',[]):
        asset(plug.get('asset'),'Python',{'.py','.rpy'})
        if not IDENT.fullmatch(plug.get('function','')): error('Неверное имя функции/label')
        if plug.get('mode') not in ('function','label'): error('Режим Python должен быть function или label')
        if plug.get('asset') and ((plug['mode']=='label') != plug['asset'].endswith('.rpy')): error('Для label нужен .rpy; для function — .py')
    def target(t,where):
        if t not in indexes['scenes']: error(where+': неизвестная сцена '+str(t))
    edges={s['id']:set() for s in p.get('scenes',[])}
    for scene in p.get('scenes',[]):
        es=scene.get('events',[])
        if not es: warnings.append('Пустая сцена '+scene['id'])
        terminated=False
        for n,e in enumerate(es):
            where=scene['id']+' / '+str(n+1)
            t=e.get('type')
            if terminated: warnings.append(where+': событие недостижимо после перехода/концовки')
            if t not in EVENTS: error(where+': неизвестное событие'); continue
            if t in ('show','hide') and e.get('character') not in indexes['characters']: error(where+': неизвестный персонаж')
            if t=='say' and e.get('character') and e['character'] not in indexes['characters']: error(where+': неизвестный говорящий')
            if t=='show' and e.get('position','center') not in ('left','center','right'): error(where+': неверная позиция')
            if t in ('background','music','sound','video'): asset(e.get('asset'),where)
            if t in ('background','music','sound','video') and not e.get('asset'): error(where+': выберите файл')
            if t in ('background','show','hide','effect') and e.get('effect','dissolve') not in ('none','dissolve','fade','hpunch','vpunch'): error(where+': неизвестный эффект')
            if t=='jump': target(e.get('target'),where); edges[scene['id']].add(e.get('target')); terminated=True
            if t=='call':target(e.get('target'),where);edges[scene['id']].add(e.get('target'))
            if t=='return':terminated=True
            if t=='condition':
                for k in ('yes','no'): target(e.get(k),where); edges[scene['id']].add(e.get(k))
                terminated=True
            if t=='choice':
                if not e.get('options'): error(where+': добавьте варианты выбора')
                for o in e.get('options',[]):
                    target(o.get('target'),where); edges[scene['id']].add(o.get('target'))
                    if o.get('condition'):
                        try: expression(o['condition'],vars_)
                        except Exception as ex: error(where+': '+str(ex))
                terminated=True
            if t in ('set','condition'):
                try: expression(e.get('value','0') if t=='set' else e.get('expression','True'),vars_)
                except Exception as ex: error(where+': '+str(ex))
            if t=='set' and e.get('variable') not in vars_: error(where+': переменная не найдена')
            if t=='minigame':
                if e.get('game') not in indexes['minigames']: error(where+': мини-игра не найдена')
                if e.get('variable') and e['variable'] not in vars_: error(where+': переменная результата не найдена')
            if t=='python' and e.get('plugin') not in indexes['python']: error(where+': Python модуль не найден')
            elif t=='python' and not next(x for x in p['python'] if x['id']==e['plugin']).get('asset'): error(where+': для Python модуля не выбран файл')
            if t=='python' and e.get('variable') and e['variable'] not in vars_: error(where+': переменная результата не найдена')
            if t=='achievement' and e.get('id') not in a_ids: error(where+': достижение не найдено')
            if t=='cutscene' and e.get('id') not in indexes['cutscenes']: error(where+': катсцена не найдена')
            if t in ('day','pause'):
                try:
                    if not 0<=float(e.get('value',1))<=100000: raise ValueError()
                except (ValueError,TypeError): error(where+': неверное числовое значение')
            if t=='day' and 'day' not in vars_: error('Для события День нужна переменная day')
            if t=='ending': terminated=True
    seen=set(); todo=[p.get('start')]
    while todo:
        cur=todo.pop()
        if cur in seen: continue
        seen.add(cur); todo.extend(edges.get(cur,set())-seen)
    for s in indexes['scenes']-seen: warnings.append('Нет пути от старта к сцене '+s)
    ui=p.get('interface',{})
    for k in ('accent','background','panel','text'):
        if not COLORS.fullmatch(ui.get(k,'')): error('Интерфейс: неверный цвет '+k)
    try:
        for k in ('textboxY','textboxH'):
            if not 0<=float(ui.get(k,.25))<=1: raise ValueError()
        if not 12<=int(ui.get('fontSize',28))<=100 or not 12<=int(ui.get('nameSize',30))<=100: raise ValueError()
        for el in ui.get('elements',[]):
            if el.get('type') not in ('text','bar','button'): error('Неизвестный элемент интерфейса')
            if not 0<=float(el.get('x',0))<=1 or not 0<=float(el.get('y',0))<=1 or not 20<=int(el.get('width',200))<=1280: raise ValueError()
            if el.get('type')=='bar' and (el.get('variable') not in vars_ or float(el.get('max',10))<=0): error('Шкала: неизвестная переменная или максимум')
            if el.get('type')=='button': target(el.get('target'),'Кнопка интерфейса')
    except (ValueError,TypeError): error('Интерфейс: неверные размеры или координаты')
    appid=p.get('steam',{}).get('appid','')
    if appid and not str(appid).isdigit(): error('Steam App ID должен быть числом')
    if p.get('steam',{}).get('enabled'): warnings.append('Steam требует Ren’Py Steam support и опубликованные API-имена достижений в Steamworks; редактор не поставляет Steam SDK')
    if p.get('target')=='7': warnings.append('Экспорт использует общий синтаксис Ren’Py 7.4+/8.x. Проверьте lint в выбранном SDK 7; Python-модули должны поддерживать Python 2.7')
    return {'errors':errors,'warnings':warnings}

# DOCX is read/written with standard library only. No Word installation needed.
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def docx_rows(data):
    if len(data)>32*1024*1024: raise ValueError('Word файл больше 32 МБ')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist())>64*1024*1024: raise ValueError('Слишком большой распакованный документ')
        root=ET.fromstring(z.read('word/document.xml'))
    tables=[]
    for table in root.findall('.//{%s}tbl'%W):
        for row in table.findall('{%s}tr'%W):
            cells=[]
            for cell in row.findall('{%s}tc'%W):
                cells.append('\n'.join(''.join(t.text or '' for t in p.findall('.//{%s}t'%W)) for p in cell.findall('{%s}p'%W)).strip())
            if cells: tables.append(cells)
    return tables

FRIENDLY = {'проект':'project','персонаж':'character','переменная':'variable','сцена':'scene','реплика':'say','фон':'background','показать':'show','скрыть':'hide','музыка':'music','звук':'sound','остановить музыку':'stop_music','выбор':'choice','переход':'jump','условие':'condition','значение':'set','день':'day','концовка':'ending','видео':'video','катсцена':'cutscene','титры':'credits','мини-игра':'minigame','python':'python','достижение':'achievement','пауза':'pause','эффект':'effect'}

def friendly_row(row):
    command=FRIENDLY.get(row[0].strip().lower(),row[0].strip().lower())
    obj=row[1].strip(); text=row[2].strip(); params={}
    for pair in row[3].split(';'):
        if '=' in pair:
            k,v=pair.split('=',1); params[k.strip().lower()]=v.strip()
    def param(*keys,default=''):
        for k in keys:
            if k in params:return params[k]
        return default
    eff={'плавно':'dissolve','затемнение':'fade','встряска':'hpunch','нет':'none'}
    effect=eff.get(param('эффект','effect',default='плавно'),param('эффект','effect',default='dissolve'))
    d={}
    if command=='project':d={'title':text or obj,'start':param('старт','start',default='arrival'),'target':param('версия','target',default='8')}
    elif command=='character':d={'id':obj,'name':text,'sprite':param('спрайт','sprite'),'color':param('цвет','color',default='#ad93ff'),'height':{'маленький':'small','средний':'medium','большой':'large'}.get(param('рост','height',default='средний'),param('рост','height',default='medium'))}
    elif command=='variable':
        try:value=json.loads(text)
        except ValueError:value=text
        d={'id':obj,'value':value}
    elif command=='scene':d={'id':obj,'name':text or obj}
    elif command=='say':d={'character':obj if obj.lower() not in ('рассказчик','автор','') else '', 'text':text}
    elif command=='show':d={'character':obj,'position':{'слева':'left','центр':'center','справа':'right'}.get(param('позиция','position',default='центр'),param('позиция','position',default='center')),'effect':effect}
    elif command=='hide':d={'character':obj,'effect':effect}
    elif command in ('background','music','sound','video'):d={'asset':text or obj,'effect':effect}
    elif command=='choice':
        choices=[]
        for line in text.splitlines():
            if '->' not in line:raise ValueError('Вариант выбора: Текст -> ID_сцены')
            caption,target=line.rsplit('->',1);choices.append({'text':caption.strip(),'target':target.strip()})
        d={'options':choices}
    elif command=='jump':d={'target':obj or text}
    elif command=='condition':d={'expression':text,'yes':param('да','yes'),'no':param('нет','no')}
    elif command=='set':d={'variable':obj,'value':text}
    elif command in ('day','pause'):d={'value':float(text or obj)}
    elif command=='ending':d={'text':text,'credits':param('титры','credits',default='да').lower() in ('да','true','1')}
    elif command=='minigame':d={'game':obj,'variable':param('результат','variable')}
    elif command=='python':d={'plugin':obj,'variable':param('результат','variable')}
    elif command in ('achievement','cutscene'):d={'id':obj}
    elif command=='effect':d={'effect':eff.get(text or obj,text or obj)}
    return [command,json.dumps(d,ensure_ascii=False)]

def friendly_template(project=None):
    rows=[('Проект','','Моя первая новелла','старт=arrival; версия=8'),('Персонаж','anna','Анна','цвет=#b7a4ff; спрайт=anna.png; рост=средний'),('Переменная','trust','0',''),('Переменная','day','1',''),('Сцена','arrival','Знакомство',''),('Фон','','court.png','эффект=плавно'),('День','','1',''),('Показать','anna','','позиция=справа; эффект=плавно'),('Реплика','anna','Привет! Сыграем в волейбол?',''),('Выбор','','Конечно! -> play\nСначала познакомимся -> talk',''),('Сцена','talk','Разговор',''),('Реплика','anna','Я Анна. Рада знакомству!',''),('Значение','trust','trust + 1',''),('Переход','play','',''),('Сцена','play','Первый матч',''),('Мини-игра','volley','','результат=trust'),('Условие','','trust >= 3','да=win; нет=finish'),('Сцена','win','Победа',''),('Достижение','FIRST_WIN','',''),('Концовка','','Отличная команда!','титры=да'),('Сцена','finish','До встречи',''),('Концовка','','Продолжим тренировку завтра!','титры=да')]
    if project:
        c=next(iter(project.get('characters',[])),None)
        bg=next((e.get('asset') for scene in project.get('scenes',[]) for e in scene.get('events',[]) if e.get('type')=='background' and e.get('asset')), 'court.png')
        mini=next(iter(project.get('minigames',[])),None)
        award=next(iter(project.get('achievements',[])),None)
        customized=[]
        for cmd,obj,text,params in rows:
            if cmd=='Персонаж':
                if not c:continue
                obj=c['id'];text=c['name'];params='цвет=%s; спрайт=%s; рост=%s'%(c['color'],c.get('sprite',''),c['height'])
            if obj=='anna':
                if not c and cmd=='Показать':continue
                obj=c['id'] if c else ''
            if cmd=='Фон':text=bg
            if cmd=='Мини-игра':
                if mini:obj=mini['id']
                else:cmd='Реплика';obj='';text='Ваша история продолжается';params=''
            if cmd=='Достижение':
                if not award:continue
                obj=award['id']
            customized.append((cmd,obj,text,params))
        rows=customized
    return make_docx(rows,'Шаблон сценария NovelForge',friendly=True)

def import_docx(data,base):
    p=copy.deepcopy(base); scenes=[]; current=None; errors=[]; count=0
    for rownum,row in enumerate(docx_rows(data),1):
        if len(row)<2: continue
        if len(row)>=4 and row[0].strip().lower() not in ('команда','command',''):
            try: row=friendly_row(row)
            except Exception as ex:
                errors.append('Строка %s: %s'%(rownum,ex));continue
        command=row[0].strip().lower(); raw=row[1].strip()
        if command in ('команда','command','') or command.startswith('#'): continue
        try:
            d=json.loads(raw)
            if not isinstance(d,dict): raise ValueError('Параметры должны быть JSON объектом')
            if command=='project':
                for k in ('title','start','target'):
                    if k in d: p[k]=d[k]
            elif command in ('character','variable') or (current is None and command in ('minigame','cutscene','achievement','python')):
                key={'character':'characters','variable':'variables','minigame':'minigames','cutscene':'cutscenes','achievement':'achievements','python':'python'}[command]
                p[key]=[x for x in p.get(key,[]) if x['id']!=d['id']]+[d]
            elif command=='scene':
                current={'id':d['id'],'name':d.get('name',d['id']),'events':[]}; scenes.append(current)
            elif command in EVENTS:
                if current is None: raise ValueError('Сначала добавьте scene')
                current['events'].append(dict(d,type=command)); count+=1
            else: raise ValueError('Неизвестная команда '+command)
        except Exception as ex: errors.append('Строка %s: %s'%(rownum,ex))
    if errors: raise ValueError('\n'.join(errors))
    if not scenes: raise ValueError('В документе не найдены строки scene')
    p['scenes']=scenes
    if p.get('start') not in [s['id'] for s in scenes]: p['start']=scenes[0]['id']
    return p,count

def make_docx(rows,title='Шаблон сценария NovelForge',friendly=False):
    def para(s,style=None): return '<w:p>'+('<w:pPr><w:pStyle w:val="%s"/></w:pPr>'%style if style else '')+'<w:r><w:t xml:space="preserve">'+escape(s)+'</w:t></w:r></w:p>'
    body=para(title,'Title')+para('Заполняйте таблицу по порядку. Один ряд — одна команда. Параметры — JSON в двойных кавычках. Файлы предварительно добавьте в ресурсы проекта. Импорт заменяет сцены, обновляет объекты по ID. Перед импортом сохраняется резервная копия.')+para('Удобный режим без JSON — визуальный редактор событий в программе. Этот документ предназначен для пакетного импорта и обмена сценариями.')
    if friendly:
        body=para(title,'Title')+para('Заполните таблицу сверху вниз. В строке Сцена укажите ID латиницей, затем добавляйте реплики и действия. В колонке Текст или файл пишите обычный текст или имя загруженного ресурса. Параметры задаются через точку с запятой. В выборе каждый вариант пишется на новой строке: текст -> ID сцены.')+para('Шаблон использует демонстрационные ресурсы anna.png и court.png, мини игру volley и достижение FIRST_WIN. Их можно изменить в программе. Для своих персонажей используйте строку Персонаж. Условия и значения могут содержать простые выражения вроде trust >= 3 и trust + 1. Перед импортом создается резервная копия.')
    widths=[1700,1500,4100,2600] if friendly else [1800,8100]
    body+='<w:tbl><w:tblPr><w:tblW w:w="9900" w:type="dxa"/><w:tblBorders>'+''.join('<w:%s w:val="single" w:sz="4" w:color="D9D9D9"/>'%x for x in ('top','left','bottom','right','insideH','insideV'))+'</w:tblBorders><w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="90" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'+''.join('<w:gridCol w:w="%s"/>'%x for x in widths)+'</w:tblGrid>'
    header=['Команда','Объект ID','Текст или файл','Параметры'] if friendly else ['Команда','Параметры']
    for rownum,row in enumerate([header]+rows):
        body+='<w:tr>'+('<w:trPr><w:tblHeader/></w:trPr>' if rownum==0 else '')+''.join('<w:tc><w:tcPr><w:tcW w:w="%s" w:type="dxa"/><w:vAlign w:val="center"/>%s</w:tcPr>%s</w:tc>'%(width,'<w:shd w:fill="E8EDF4"/>' if rownum==0 else '', ''.join(para(line) for line in str(cell).split('\n'))) for cell,width in zip(row,widths))+'</w:tr>'
    body+='</w:tbl><w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="900" w:right="900" w:bottom="900" w:left="900"/></w:sectPr>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('word/styles.xml','<w:styles xmlns:w="%s"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="20"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style></w:styles>'%W)
        z.writestr('word/document.xml','<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s"><w:body>%s</w:body></w:document>'%(W,body))
    return out.getvalue()

def project_rows(p):
    rows=[('project',json.dumps({k:p[k] for k in ('title','start','target')},ensure_ascii=False))]
    for singular,plural in [('character','characters'),('variable','variables'),('minigame','minigames'),('cutscene','cutscenes'),('achievement','achievements'),('python','python')]:
        for obj in p.get(plural,[]): rows.append((singular,json.dumps(obj,ensure_ascii=False)))
    for s in p['scenes']:
        rows.append(('scene',json.dumps({'id':s['id'],'name':s['name']},ensure_ascii=False)))
        for e in s['events']: rows.append((e['type'],json.dumps({k:v for k,v in e.items() if k!='type'},ensure_ascii=False)))
    return rows

def compile_project(p,assets,dest):
    report=validate(p,assets)
    if report['errors']: raise ValueError('\n'.join(report['errors']))
    dest=Path(dest); game=dest/'game'; game.mkdir(parents=True,exist_ok=True)
    (game/'assets').mkdir(exist_ok=True)
    if Path(assets).exists():
        for a in Path(assets).iterdir():
            if a.is_file() and a.suffix.lower() not in ('.py','.rpy') and not p.get('_sourceOnly'): shutil.copy2(a,game/'assets'/a.name)
    (game/'plugins').mkdir(exist_ok=True)
    script=['# Generated by NovelForge 1.0 — UTF-8', '']
    for v in p['variables']: script.append('default %s = %s'%(v['id'],repr(v['value'])))
    for c in p['characters']:
        script.append('define %s = Character(%s, color=%s)'%(c['id'],textq(c['name']),q(c['color'])))
        if c.get('sprite'): script.append('image nfchar_%s = %s'%(c['id'],q('assets/'+c['sprite'])))
    script+=['','init python:', '    import importlib', '    nf_modules = {}']
    for plug in p.get('python',[]):
        if not plug.get('asset'): continue
        source=Path(assets)/plug['asset']
        if plug['mode']=='label': shutil.copy2(source,game/'plugins'/('nf_'+plug['id']+'.rpy'))
        else:
            # Module basename is generated, never evaluated from a path.
            shutil.copy2(source,game/('nfplugin_'+plug['id']+'.py'))
            script.append('    nf_modules[%s] = importlib.import_module(%s)'%(q(plug['id']),q('nfplugin_'+plug['id'])))
    for a in p['achievements']:
        script.append('    achievement.register(%s, steam=%s)'%(q(a['id']),q(a.get('steam') or a['id'])))
    script+=['','label splashscreen:']
    intro=p.get('intro',{})
    if intro.get('video'): script.append('    $ renpy.movie_cutscene(%s)'%q('assets/'+intro['video']))
    else: script.extend(card_script(intro.get('cards',[])))
    script+=['    return','','label start:','    jump nfscene_'+p['start']]
    for s in p['scenes']:
        script+=['','label nfscene_'+s['id']+':']
        for e in s['events']: script.extend(event_script(e,p))
        script.append('    return')
    for c in p['cutscenes']:
        script+=['','label nfcut_'+c['id']+':']+card_script(c.get('cards',[]))+['    return']
    script+=['','label nf_credits:', '    call screen nf_credits_screen', '    return']
    (game/'script.rpy').write_text('\n'.join(script)+'\n',encoding='utf-8')
    (game/'screens.rpy').write_text(screen_script(p),encoding='utf-8')
    (game/'runtime.rpy').write_text(RUNTIME,encoding='utf-8')
    options='''# UTF-8
init -10 python:
    config.screen_width = 1280
    config.screen_height = 720
    config.name = %s
    config.version = "1.0"
    config.save_directory = %s
    config.window_title = %s
    config.has_sound = True
    config.has_music = True
    config.has_voice = True
    config.rollback_enabled = True
    config.overlay_screens.append("nf_hud")
    config.enter_transition = dissolve
    config.exit_transition = dissolve
    config.main_game_transition = fade
    config.end_game_transition = fade
    config.default_text_cps = 35
    config.default_afm_time = 15
    config.game_menu_action = ShowMenu("preferences")
'''%(q(p['title']),q('NovelForge-'+re.sub('[^a-zA-Z0-9]','',p['start'])+'-'+__import__('hashlib').sha256(p['title'].encode()).hexdigest()[:10]),q(p['title']))
    if p['steam'].get('enabled') and p['steam'].get('appid'):
        options += '\ndefine config.steam_appid = '+str(int(p['steam']['appid']))+'\n'
    (game/'options.rpy').write_text(options,encoding='utf-8')
    if p['steam'].get('enabled') and p['steam'].get('appid'):
        (dest/'steam_appid.txt').write_text(str(p['steam']['appid']),encoding='ascii')
    (dest/'NovelForge-project.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'README.txt').write_text('Откройте эту папку как проект в Ren\'Py Launcher. Нажмите Проверить сценарий, затем Запустить. Для дистрибутива используйте Build Distributions. Внутри нет самого движка. Python-плагины исполняются игрой: подключайте только доверенный код. Steam требует Steam support из Launcher и настройки Steamworks. MP4 поддерживается не на всех платформах, используйте WebM VP9/Opus или OGV.\n',encoding='utf-8')
    return report

def card_script(cards):
    lines=[]
    for c in cards:
        bg='assets/'+c['asset'] if c.get('asset') else c.get('background','#111126')
        lines+=['    scene expression '+q(bg) if c.get('asset') else '    scene expression Solid('+q(bg)+')','    with dissolve','    show screen nf_card('+textq(c.get('text',''))+')','    $ renpy.pause(%s, hard=True)'%float(c.get('seconds',2)), '    hide screen nf_card']
    return lines

def event_script(e,p):
    t=e['type']; l=[]
    if t=='say': l=[('    '+e['character']+' ' if e.get('character') else '    ')+textq(e.get('text',''))]
    elif t=='background': l=['    scene expression '+q('assets/'+e['asset'])]
    elif t=='show':
        c=next(c for c in p['characters'] if c['id']==e['character'])
        if not c.get('sprite'): return ['    # Character has no sprite']
        pos={'left':.2,'center':.5,'right':.8}[e.get('position','center')]
        h={'small':370,'medium':490,'large':590}[c['height']]
        l=['    show nfchar_%s at Transform(xalign=%s, yalign=1.0, ysize=%d, fit="contain")'%(c['id'],pos,h)]
    elif t=='hide': l=['    hide nfchar_'+e['character']]
    elif t in ('music','sound'): l=['    play %s %s'%(t,q('assets/'+e['asset']))]
    elif t=='stop_music': l=['    stop music fadeout 1.0']
    elif t=='choice':
        l=['    menu:']
        for o in e['options']:
            cond=' if '+o['condition'] if o.get('condition') else ''
            l+=['        '+textq(o['text'])+cond+':','            jump nfscene_'+o['target']]
        # All conditional choices can be unavailable; don't fall through into next label.
        l+=['    return']
    elif t=='jump': l=['    jump nfscene_'+e['target']]
    elif t=='condition': l=['    if '+e['expression']+':','        jump nfscene_'+e['yes'],'    else:','        jump nfscene_'+e['no']]
    elif t=='set': l=['    $ '+e['variable']+' = '+str(e['value'])]
    elif t=='day': l=['    $ day = '+str(int(float(e.get('value',1)))),'    '+textq('День '+str(e.get('value',1)))]
    elif t=='ending':
        l=['    '+textq(e.get('text','Конец'))]
        if e.get('credits'): l+=['    call nf_credits']
        l+=['    return']
    elif t=='video': l=['    $ renpy.movie_cutscene('+q('assets/'+e['asset'])+')']
    elif t=='cutscene': l=['    call nfcut_'+e['id']]
    elif t=='credits': l=['    call nf_credits']
    elif t=='pause': l=['    $ renpy.pause('+str(float(e.get('value',1)))+')']
    elif t=='effect': l=['    with '+e.get('effect','dissolve')] if e.get('effect')!='none' else []
    elif t=='achievement': l=['    $ achievement.grant('+q(e['id'])+')','    $ achievement.sync()','    $ renpy.notify('+textq(next(a['name'] for a in p['achievements'] if a['id']==e['id']))+')']
    elif t=='minigame':
        g=next(g for g in p['minigames'] if g['id']==e['game'])
        if g['kind']=='quiz':
            l=['    call screen nf_quiz('+textq(g.get('question',''))+', '+repr([(a['text'].replace('[','[[').replace('{','{{'),bool(a.get('correct'))) for a in g['answers']])+', '+str(float(g.get('seconds',30)))+')']
        else: l=['    call screen nf_mini('+textq(g['title'])+', '+q(g['kind'])+', '+str(int(g.get('target',5)))+', '+str(float(g.get('seconds',30)))+')']
        if e.get('variable'): l+=['    $ '+e['variable']+' = _return']
    elif t=='python':
        plug=next(x for x in p['python'] if x['id']==e['plugin'])
        if not plug.get('asset'): raise ValueError('Для Python события выберите файл модуля')
        if plug['mode']=='label': l=['    call '+plug['function']]
        else: l=['    $ nf_result = nf_modules[%s].%s()'%(q(plug['id']),plug['function'])]
        if e.get('variable'): l+=['    $ '+e['variable']+' = '+('_return' if plug['mode']=='label' else 'nf_result')]
    if t in ('background','show','hide') and e.get('effect','dissolve')!='none': l+=['    with '+e.get('effect','dissolve')]
    return l

def screen_script(p):
    ui=p['interface']; panel=ui['panel']; accent=ui['accent']; text=ui['text']; bg=ui['background']
    code='''# NovelForge custom interface; no default gui assets required.
style default:
    font "DejaVuSans.ttf"
    size %(fontSize)s
    color %(text)s
style button:
    background Solid(%(panel)s)
    hover_background Solid(%(accent)s)
    padding (24, 14)
style button_text:
    color %(text)s
    hover_color "#111126"
    size 26
style input:
    color %(text)s
style bar:
    left_bar Solid(%(accent)s)
    right_bar Solid("#49475e")
    ysize 16
screen say(who, what):
    window:
        id "window"
        background Solid(%(panel)s + "ed")
        xpos 0.03
        ypos %(textboxY)s
        xsize 1203
        ysize %(boxPixels)s
        padding (30, 20)
        vbox:
            spacing 10
            if who:
                text who id "who" color %(accent)s size %(nameSize)s
            text what id "what"
    use nf_quick
screen choice(items):
    vbox:
        xalign 0.5
        yalign 0.45
        spacing 12
        for item in items:
            textbutton item.caption action item.action xsize 750
screen main_menu():
    tag menu
    add Solid(%(background)s)
    frame:
        background Solid(%(panel)s)
        xpos 0.08
        ypos 0.12
        xsize 1070
        ysize 550
        padding (50, 45)
        vbox:
            spacing 18
            text %(title)s size 48 color %(accent)s
            null height 15
            textbutton "Начать историю" action Start()
            textbutton "Продолжить" action ShowMenu("load")
            textbutton "Настройки" action ShowMenu("preferences")
            textbutton "Титры" action ShowMenu("nf_credits_menu")
            textbutton "Выйти" action Quit(confirm=False)
screen nf_quick():
    hbox:
        xalign 0.97
        yalign 0.995
        spacing 8
        textbutton "Назад" action Rollback() text_size 16
        textbutton "Сохранить" action ShowMenu("save") text_size 16
        textbutton "Загрузить" action ShowMenu("load") text_size 16
        textbutton "Авто" action Preference("auto-forward", "toggle") text_size 16
        textbutton "Пропуск" action Skip() text_size 16
        textbutton "Меню" action ShowMenu("preferences") text_size 16
screen nf_slots(mode):
    tag menu
    add Solid(%(background)s)
    vbox:
        xalign 0.5
        ypos 0.07
        spacing 20
        text ("Сохранения" if mode == "save" else "Загрузка") size 38
        grid 3 2:
            spacing 15
            for slot in range(1, 7):
                button:
                    xsize 350
                    ysize 190
                    action (FileSave(slot) if mode == "save" else FileLoad(slot))
                    vbox:
                        add FileScreenshot(slot) xsize 300 ysize 135
                        text FileTime(slot, format="%%d.%%m %%H:%%M", empty="Пустой слот") size 18
        hbox:
            spacing 10
            textbutton "Предыдущая" action FilePagePrevious()
            textbutton "Следующая" action FilePageNext()
            textbutton "Назад" action Return()
screen save():
    use nf_slots("save")
screen load():
    use nf_slots("load")
screen preferences():
    tag menu
    add Solid(%(background)s)
    vbox:
        xalign 0.5
        yalign 0.5
        spacing 24
        text "Настройки" size 42
        text "Музыка"
        bar value Preference("music volume") xsize 600
        text "Звук"
        bar value Preference("sound volume") xsize 600
        text "Скорость текста"
        bar value Preference("text speed") xsize 600
        textbutton "Полный экран" action Preference("display", "toggle")
        textbutton "Главное меню" action MainMenu(confirm=False)
        textbutton "Назад" action Return()
screen confirm(message, yes_action, no_action):
    modal True
    add Solid("#000000bb")
    frame:
        xalign 0.5
        yalign 0.5
        padding (35, 35)
        vbox:
            spacing 20
            text message
            hbox:
                textbutton "Да" action yes_action
                textbutton "Нет" action no_action
screen notify(message):
    zorder 100
    frame:
        xalign 0.98
        yalign 0.08
        text message
    timer 3.0 action Hide("notify")
screen nf_card(caption):
    text caption:
        xalign 0.5
        yalign 0.45
        xmaximum 1100
        text_align 0.5
        size 48
        color "#ffffff"
        outlines [(2, "#000000", 0, 0)]
screen nf_credits_screen():
    modal True
    add Solid(%(background)s)
    viewport:
        xalign 0.5
        yalign 0.4
        xsize 1000
        ysize 480
        mousewheel True
        draggable True
        vbox:
            spacing 30
            text %(creditsTitle)s size 42 xalign 0.5
            text %(creditsLines)s text_align 0.5 xalign 0.5
    textbutton "Продолжить" xalign 0.5 yalign 0.94 action Return()
    timer %(creditsSeconds)s action Return()
screen nf_credits_menu():
    tag menu
    use nf_credits_screen
screen nf_hud():
    if not main_menu:
'''%dict(ui,title=textq(p['title']),accent=q(accent),panel=q(panel),text=q(text),background=q(bg),boxPixels=int(float(ui['textboxH'])*720),creditsTitle=textq(p['credits']['title']),creditsLines=textq(p['credits']['lines']),creditsSeconds=max(1,float(p['credits'].get('seconds',10))))
    elements=ui.get('elements',[])
    if not elements: code+='        null\n'
    for el in elements:
        x=float(el.get('x',0)); y=float(el.get('y',0)); width=int(el.get('width',200))
        if el['type']=='text': code+='        text %s xpos %s ypos %s xmaximum %d size 22\n'%(textq(el.get('label','')),x,y,width)
        elif el['type']=='bar':
            code+='        vbox:\n            xpos %s\n            ypos %s\n            spacing 8\n            text %s size 20\n            bar value VariableValue(%s, %s) xsize %d\n'%(x,y,textq(el.get('label','')),q(el['variable']),float(el.get('max',10)),width)
        elif el['type']=='button': code+='        textbutton %s xpos %s ypos %s xsize %d action Jump(%s)\n'%(textq(el.get('label','Кнопка')),x,y,width,q('nfscene_'+el['target']))
    return code

RUNTIME='''# Common Python 2.7/3 syntax for Ren'Py 7.4+ and 8.x.
init python:
    class NFState(renpy.python.RevertableObject):
        def __init__(self):
            self.score = 0
            self.elapsed = 0.0
            self.phase = 0.0
            self.player = 0.5
            self.ball = 0.5
            self.ball_y = 0.1
            self.seed = 17
        def tick(self, kind):
            self.elapsed += 0.05
            self.phase = (self.phase + 0.025) % 1.0
            if kind == "volleyball":
                self.ball_y += 0.018
                if self.ball_y >= 0.84:
                    if abs(self.player - self.ball) < 0.15:
                        self.score += 1
                    self.seed = (self.seed * 1103515245 + 12345) % 2147483648
                    self.ball = 0.06 + (self.seed % 880) / 1000.0
                    self.ball_y = 0.08
        def hit(self, kind):
            if kind == "clicker":
                self.score += 1
            elif kind == "timing" and 0.36 <= self.phase <= 0.64:
                self.score += 1
                self.phase = 0.0
        def move(self, delta):
            self.player = min(0.94, max(0.06, self.player + delta))
screen nf_quiz(question, answers, seconds):
    modal True
    add Solid("#111126")
    timer seconds action Return(0)
    vbox:
        xalign 0.5
        yalign 0.5
        spacing 20
        text question xmaximum 1000 text_align 0.5
        for caption, correct in answers:
            textbutton caption action Return(1 if correct else 0) xsize 800
        textbutton "Пропустить" action Return(0)
screen nf_mini(title, kind, target, seconds):
    modal True
    default state = NFState()
    add Solid("#111126")
    timer 0.05 repeat True action Function(state.tick, kind)
    if state.score >= target or state.elapsed >= seconds:
        timer 0.01 action Return(state.score)
    key "K_LEFT" action Function(state.move, -0.08)
    key "K_RIGHT" action Function(state.move, 0.08)
    key "K_SPACE" action Function(state.hit, kind)
    text title xalign 0.5 ypos 0.04 size 36
    text ("Очки: %d / %d    Время: %d" % (state.score, target, max(0, int(seconds - state.elapsed)))) xalign 0.5 ypos 0.12
    if kind == "volleyball":
        frame:
            xpos 0.15
            ypos 0.23
            xsize 900
            ysize 380
            background Solid("#244a58")
            add Solid("#ffffff44") xpos 0 ypos 190 xsize 900 ysize 3
            add Solid("#ffd875") xpos int(state.ball * 850) ypos int(state.ball_y * 340) xsize 28 ysize 28
            add Solid("#ad93ff") xpos int(state.player * 850) ypos 325 xsize 80 ysize 20
        hbox:
            xalign 0.5
            ypos 0.80
            spacing 20
            textbutton "← Влево" action Function(state.move, -0.08)
            textbutton "Вправо →" action Function(state.move, 0.08)
        text "Ловите мяч платформой. Стрелки или кнопки." xalign 0.5 ypos 0.73 size 22
    elif kind == "timing":
        frame:
            xpos 0.15
            ypos 0.38
            xsize 900
            ysize 70
            background Solid("#37344e")
            add Solid("#4dcdb1") xpos 324 ypos 0 xsize 252 ysize 70
            add Solid("#ffffff") xpos int(state.phase * 880) ypos 0 xsize 10 ysize 70
        textbutton "Удар! · Пробел" xalign 0.5 ypos 0.58 action Function(state.hit, kind)
        text "Попадите в зеленую зону" xalign 0.5 ypos 0.28
    else:
        textbutton "Нажимайте!" xalign 0.5 yalign 0.5 xsize 500 ysize 160 action Function(state.hit, kind)
    textbutton "Завершить" xalign 0.5 ypos 0.91 action Return(state.score)
'''

# Version 1.1 migration keeps existing projects editable without resetting content.
def upgrade_project(project):
    if not isinstance(project,dict) or project.get('format')!=1:raise ValueError('Ожидается проект NovelForge формата 1')
    p=copy.deepcopy(project)
    base=_default_v1()
    for key,value in base.items():p.setdefault(key,copy.deepcopy(value))
    for key in ('interface','intro','credits','steam'):
        if not isinstance(p[key],dict):raise ValueError('Неверный раздел '+key)
        for k,v in base[key].items():p[key].setdefault(k,copy.deepcopy(v))
    ui=p['interface']
    for k,v in {'textboxX':.035,'textboxW':.93,'padding':22,'panelOpacity':.94,'radius':16,'quickY':.945,'backdrop':'aurora','pattern':'orbits','patternOpacity':.18,'menuAlign':'left','menuImage':'','images':[],'hoverText':'#12131b','buttonSize':24,'titleSize':36}.items():ui.setdefault(k,copy.deepcopy(v))
    # Migrate the old bottom panel, which overlapped the quick-menu row.
    if project.get('editorVersion') not in ('1.1','1.2','1.3','1.4') and float(ui.get('textboxY',.7))+float(ui.get('textboxH',.235))>.94:
        ui['textboxY']=.70;ui['textboxH']=.235
    for k,v in {'textOffsetX':0,'textOffsetY':0,'textAlign':'left','textSpeed':35,'textAnimation':'typewriter','lineSpacing':0,'nameOffsetX':0,'nameOffsetY':0}.items():ui.setdefault(k,v)
    for g in p['minigames']:
        g.setdefault('objects',[]);g.setdefault('backgroundImage','');g.setdefault('winTarget','');g.setdefault('loseTarget','');g.setdefault('rewardVariable','');g.setdefault('rewardWin',1);g.setdefault('rewardLose',0)
    p['credits'].setdefault('style','cinema');p['credits'].setdefault('images',[]);p['credits'].setdefault('backgroundImage','');p['credits'].setdefault('textY',.28);p['credits'].setdefault('textH',.55)
    p.setdefault('artboards',[]);p['editorVersion']='1.4'
    p.setdefault('graphicsDocuments',[]);p.setdefault('musicProjects',[])
    for c in p['characters']:c.setdefault('variants',[])
    for cards in [p['intro'].get('cards',[])]+[c.get('cards',[]) for c in p.get('cutscenes',[])]:
        for card in cards:
            for k,v in {'images':[],'textX':.5,'textY':.55,'textWidth':1000,'fontSize':44,'textColor':'#ffffff'}.items():card.setdefault(k,copy.deepcopy(v))
    for scene in p['scenes']:
        for e in scene.get('events',[]):
            if e.get('type')=='show':e.setdefault('variant','')
    layer_sets=[ui.get('images',[]),p['credits'].get('images',[])]+[card.get('images',[]) for cards in [p['intro'].get('cards',[])]+[c.get('cards',[]) for c in p['cutscenes']] for card in cards]
    for items in layer_sets:
        if not isinstance(items,list):continue
        for layer in items:
            if isinstance(layer,dict):
                for key,value in {'x':.5,'y':.2,'width':200,'height':140,'opacity':1,'rotation':0,'z':0}.items():layer.setdefault(key,value)
    if isinstance(p.get('native'),dict):
        for key,value in {'enabled':False,'useStudioUI':False,'labels':[],'files':[],'overview':[]}.items():p['native'].setdefault(key,copy.deepcopy(value))
    return p

_default_v1=default_project
def default_project():
    p=upgrade_project(_default_v1())
    p['scenes'][0]['events'][0]['asset']='court_photo.png'
    p['interface'].update(menuImage='court_photo.png',fontSize=26,nameSize=28,padding=18)
    p['characters'][0]['sprite']='anime_woman.png'
    p['characters'][0]['variants']=[{'id':'stand_'+e,'name':'Стоя · '+e,'asset':'anna_stand_'+e+'.png'} for e in ('neutral','smile','happy','sad','surprise','angry','wink','determined')]
    p['characters'][0]['variants'] += [{'id':'anime_wave','name':'Аниме · Приветствие','asset':'anime_woman_wave.png'}]
    p['credits'].update(seconds=18,images=[{'asset':'novelforge_logo.png','x':.5,'y':.14,'width':230,'height':115,'opacity':1,'rotation':0,'z':0}])
    p['intro']['cards'][0]['images']=[{'asset':'novelforge_logo.png','x':.5,'y':.28,'width':360,'height':180,'opacity':1,'rotation':0,'z':0}]
    return p
_validate_v1=validate
def validate(p,assets=None):
    try:p=upgrade_project(p)
    except (ValueError,TypeError,KeyError) as ex:return {'errors':[str(ex)],'warnings':[]}
    model=copy.deepcopy(p)
    if p.get('native',{}).get('enabled') and not p.get('native',{}).get('bridge'):
        for el in model['interface']['elements']:
            if el.get('type')=='button':el['target']=model['start']
    for g in model['minigames']:
        if g.get('kind')=='hotspot':g['kind']='clicker'
    from story_tree import flat_leaves,validate_controls,walk
    try:
        for scene in model['scenes']:scene['events']=flat_leaves(scene['events'])
    except ValueError as ex:return {'errors':[str(ex)],'warnings':[]}
    result=_validate_v1(model,assets);errors=result['errors'];ui=p['interface']
    errors.extend(validate_controls(p))
    if any(e.get('type') in ('branch','menu_block') for s in p['scenes'] for e in s['events']):result['warnings']=[w for w in result['warnings'] if 'недостижимо' not in w]
    if p.get('native',{}).get('enabled') and not p.get('native',{}).get('bridge'):
        for el in ui['elements']:
            if el.get('type')=='button' and el.get('target') not in p['native'].get('labels',[]):errors.append('Кнопка: неизвестная метка исходного RenPy '+str(el.get('target')))
    from ui_theme import layout
    try:
        l=layout(ui)
        if l['x']<0 or l['y']<0 or l['x']+l['w']>1280 or l['y']+l['h']>l['quickY']-3:errors.append('Окно диалога выходит за безопасную область или перекрывает быстрое меню')
        if l['w']<400 or l['h']<130 or l['h']-2*l['padding']-int(ui['nameSize'])<42 or not 8<=l['padding']<=50:errors.append('Увеличьте окно диалога: минимум 400×130, отступы 8–50')
        if not 0<=float(ui['panelOpacity'])<=1 or not 0<=float(ui['patternOpacity'])<=1:errors.append('Непрозрачность должна быть от 0 до 1')
        if not 0<=int(ui['radius'])<=28:errors.append('Скругление должно быть от 0 до 28')
        if ui['pattern'] not in ('none','orbits','dots','grid','diagonal','waves'):errors.append('Неизвестный узор')
        if ui['backdrop'] not in ('aurora','flat','paper'):errors.append('Неизвестная подложка меню')
        if not COLORS.fullmatch(ui['hoverText']):errors.append('Неверный цвет текста наведения')
    except (ValueError,TypeError,KeyError):errors.append('Неверные настройки интерфейса')
    def image_asset(name):
        if not name:return
        if Path(name).name!=name or '\\' in name or name.startswith('.') or Path(name).suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:errors.append('Некорректное изображение: '+name)
        elif assets is not None and not (Path(assets)/name).is_file():errors.append('Нет изображения: '+name)
    def layers(items):
        if not isinstance(items,list):errors.append('Слои должны быть списком');return
        for im in items:
            try:
                image_asset(im.get('asset',''))
                for k in ('x','y','opacity'):
                    if not 0<=float(im.get(k,.5 if k!='opacity' else 1))<=1:raise ValueError()
                if not 5<=int(im.get('width',200))<=2560 or not 5<=int(im.get('height',140))<=1440:raise ValueError()
                if not -360<=float(im.get('rotation',0))<=360:raise ValueError()
            except (ValueError,TypeError):errors.append('Неверные параметры слоя изображения')
    image_asset(ui['menuImage']);layers(ui['images']);image_asset(p['credits']['backgroundImage']);layers(p['credits']['images'])
    for cards in [p['intro']['cards']]+[c.get('cards',[]) for c in p['cutscenes']]:
        for card in cards:
            layers(card.get('images',[]))
            try:
                if not 12<=int(card['fontSize'])<=100 or not 0<=float(card['textX'])<=1 or not 0<=float(card['textY'])<=1:raise ValueError()
                if not COLORS.fullmatch(card['textColor']):raise ValueError()
            except (ValueError,TypeError):errors.append('Неверные параметры текста карточки')
    for c in p['characters']:
        seen=set()
        for v in c.get('variants',[]):
            if not ident(v.get('id','')) or v['id'] in seen:errors.append('Неверный или повторный ID варианта спрайта')
            seen.add(v.get('id'));image_asset(v.get('asset',''))
    for s in p['scenes']:
        for path,e in walk(s['events']):
            if e.get('type')=='show' and e.get('variant'):
                c=next((c for c in p['characters'] if c['id']==e.get('character')),None)
                if c and e['variant'] not in [v['id'] for v in c['variants']]:errors.append('Не найден вариант спрайта '+e['variant'])
    if p.get('native',{}).get('bridge'):
        result['warnings']=[w for w in result['warnings'] if not w.startswith('Нет пути от старта')]
    if p.get('native',{}).get('bridge'):result['warnings'].append('Нераспознанные конструкции Ren’Py сохраняются как редактируемые блоки исходного кода. Проверяйте результат через SDK.')
    for g in p['minigames']:
        for key in ('winTarget','loseTarget'):
            if g.get(key) and g[key] not in [s['id'] for s in p['scenes']]:errors.append('Мини-игра: неизвестная сцена '+g[key])
        if g.get('rewardVariable') and g['rewardVariable'] not in [v['id'] for v in p['variables']]:errors.append('Мини-игра: неизвестная переменная награды')
        if g.get('kind')=='hotspot':
            if not g.get('objects'):errors.append('Добавьте хотя бы одну область в конструкторе мини-игры')
            for obj in g.get('objects',[]):
                try:
                    if not (0<=float(obj['x'])<=1180 and 0<=float(obj['y'])<=620 and 30<=int(obj['width'])<=1280 and 30<=int(obj['height'])<=720):errors.append('Область мини-игры вне поля')
                except (ValueError,TypeError,KeyError):errors.append('Неверная область мини-игры')
    for scene in p['scenes']:
        for path,e in walk(scene.get('events',[])):
            if e.get('type') in ('music','sound'):
                try:
                    if not 0<=float(e.get('volume',1))<=1 or not 0<=float(e.get('fadein',0))<=30:errors.append('Громкость: 0–1, плавное начало: 0–30 секунд')
                except (ValueError,TypeError):errors.append('Неверные параметры звука')
    try:
        if ui.get('textAnimation') not in ('instant','typewriter','fade'):errors.append('Неизвестная анимация текста')
        if not 0<=float(ui.get('textSpeed',35))<=300:errors.append('Скорость текста: 0–300')
        if ui.get('textAlign') not in ('left','center','right'):errors.append('Неверное выравнивание текста')
        for key in ('textOffsetX','textOffsetY','nameOffsetX','nameOffsetY'):
            if not 0<=float(ui.get(key,0))<=100:errors.append('Отступ текста/имени: 0–100')
        if not -5<=int(ui.get('lineSpacing',0))<=30:errors.append('Межстрочный интервал: -5–30')
    except (ValueError,TypeError):errors.append('Неверные настройки текста')
    scene_ids={s['id'] for s in p['scenes']}
    for scene in p['scenes']:
        for e in scene['events']:
            if e.get('type')=='show':
                try:
                    if any(k in e and not 0<=float(e[k])<=1 for k in ('x','y')) or not .1<=float(e.get('scale',1))<=3:errors.append('Положение персонажа: 0–1, масштаб: 0.1–3')
                except (TypeError,ValueError):errors.append('Неверные параметры персонажа')
            if e.get('type')=='call' and e.get('target') not in scene_ids:errors.append('Вызов: неизвестная label '+str(e.get('target')))
            if e.get('type')=='hide_image' and not ident(e.get('id','')):errors.append('Укажите ID убираемого изображения')
            if e.get('type')=='image':
                image_asset(e.get('asset',''))
                if not ident(e.get('id','')):errors.append('Изображению нужен ID латиницей')
                try:
                    if not all(0<=float(e.get(k,.5 if k!='opacity' else 1))<=1 for k in ('x','y','opacity')) or not 5<=int(e.get('width',300))<=2560 or not 5<=int(e.get('height',300))<=1440:errors.append('Неверные размеры изображения')
                except (TypeError,ValueError):errors.append('Неверное положение изображения')
    if p.get('_forceExport'):
        result['ignoredErrors']=list(errors);result['warnings']+=['Игнорировано: '+e for e in errors];result['errors']=[]
    return result



_screen_v1=screen_script
def screen_script(p):
    from ui_theme import screens,card_screen
    p=upgrade_project(p)
    return screens(p,_screen_v1(p))+card_screen()

_card_v1=card_script
def card_script(cards):
    lines=[]
    for card in cards:
        d=copy.deepcopy(card)
        d['text']=str(d.get('text','')).replace('{','{{')
        # Passed as screen data with substitute False, so punctuation stays literal.
        lines+=['    show screen nf_composition('+repr(d)+')','    with dissolve','    $ renpy.pause(%s, hard=True)'%float(card.get('seconds',2)),'    hide screen nf_composition']
    return lines

_event_v1=event_script
def event_script(e,p):
    if e.get('type') in ('branch','menu_block'):
        from story_tree import compile_control
        return compile_control(e,p,event_script)
    if e.get('type')=='raw':
        import textwrap
        code=e.get('code','').rstrip() or 'pass'
        if p.get('_nativeDestinations'):
            from story_tree import rewrite_statements
            code=rewrite_statements(code,scope=e.get('_source',{}).get('scope') or p.get('_nativeScope',''),destinations=p['_nativeDestinations'])
        return textwrap.indent(code,'    ').splitlines()
    if e.get('type')=='return':return ['    return']
    if e.get('type')=='call':return ['    call nfscene_'+e['target']]
    if e.get('type')=='image':
        native=p.get('native',{}).get('bridge');width=int(e.get('width',300));height=int(e.get('height',300));x=float(e.get('x',.5));y=float(e.get('y',.5))
        w='int(config.screen_width * '+repr(width/1280)+')' if native else str(width);h='int(config.screen_height * '+repr(height/720)+')' if native else str(height)
        xx='int(config.screen_width * '+repr(x)+')' if native else str(round(x*1280));yy='int(config.screen_height * '+repr(y)+')' if native else str(round(y*720))
        return ['    show expression Transform('+q('assets/'+e['asset'])+', xsize='+w+', ysize='+h+', fit="contain", alpha='+str(float(e.get('opacity',1)))+') as nfobj_'+e['id']+' at Transform(xpos='+xx+', ypos='+yy+', xanchor=0.5, yanchor=0.5)']
    if e.get('type')=='hide_image':return ['    hide nfobj_'+e['id']]
    if e.get('type')=='say' and p.get('native',{}).get('bridge'):
        prefix=e.get('character','')+(' '+e['attributes'] if e.get('attributes') else '')
        return ['    '+(prefix+' ' if prefix else '')+q(e.get('text',''))+(' nointeract' if e.get('nointeract') else '')]
    if e.get('type')=='choice' and e.get('prompt'):
        result=_event_v1(e,p);result.insert(1,'        '+(q(e['prompt']) if p.get('native',{}).get('bridge') else textq(e['prompt'])));return result
    if e.get('type')=='background':
        result=['    scene expression Transform('+q('assets/'+e['asset'])+', xysize='+('(config.screen_width, config.screen_height)' if p.get('native',{}).get('bridge') else '(1280, 720)')+', fit="cover")']
        if e.get('effect','dissolve')!='none':result.append('    with '+e.get('effect','dissolve'))
        return result
    if e.get('type')=='show':
        c=next((x for x in p['characters'] if x['id']==e['character']),None)
        if c:
            v=next((v for v in c.get('variants',[]) if v['id']==e.get('variant')),None)
            sprite=v['asset'] if v else c.get('sprite')
            if not sprite:return ['    # Character has no sprite']
            height={'small':370,'medium':490,'large':590}[c['height']];pos={'left':256,'center':640,'right':1024}[e.get('position','center')]
            alias=c.get('_native',{}).get('imageTag',c['id']).split()[0] if p.get('native',{}).get('bridge') else 'nfchar_'+c['id']
            out=['    show expression '+q('assets/'+sprite)+' as '+alias+' at Transform(xpos='+str(pos)+', xanchor=0.5, ypos=720, yanchor=1.0, ysize='+str(height)+', fit="contain")']
            if 'x' in e:out[0]=out[0].replace('xpos='+str(pos)+',','xpos='+str(round(float(e['x'])*1280))+',')
            if 'y' in e:out[0]=out[0].replace('ypos=720,','ypos='+str(round(float(e['y'])*720))+',')
            if 'scale' in e:out[0]=out[0].replace('ysize='+str(height)+',','ysize='+str(round(height*float(e['scale'])))+',')
            if p.get('native',{}).get('bridge'):
                fx=float(e.get('x',pos/1280));fy=float(e.get('y',1));fraction=height/720*float(e.get('scale',1))
                out=['    show expression '+q('assets/'+sprite)+' as '+alias+' at Transform(xpos=int(config.screen_width * '+repr(fx)+'), xanchor=0.5, ypos=int(config.screen_height * '+repr(fy)+'), yanchor=1.0, ysize=int(config.screen_height * '+repr(fraction)+'), fit="contain")']
            if e.get('effect','dissolve')!='none':out+=['    with '+e.get('effect','dissolve')]
            return out
    if e.get('type')=='hide' and p.get('native',{}).get('bridge'):
        c=next(c for c in p['characters'] if c['id']==e['character']);alias=c.get('_native',{}).get('imageTag',c['id']).split()[0];out=['    hide '+alias]
        if e.get('effect','dissolve')!='none':out+=['    with '+e.get('effect','dissolve')]
        return out
    if e.get('type') in ('music','sound'):
        volume=float(e.get('volume',1));fadein=float(e.get('fadein',0))
        return ['    play '+e['type']+' '+q('assets/'+e['asset'])+(' loop' if e.get('loop',e['type']=='music') else ' noloop')+' fadein '+str(fadein)+' volume '+str(volume)]
    if e.get('type')=='minigame':
        g=next(g for g in p['minigames'] if g['id']==e['game'])
        if g['kind']=='hotspot':
            out=['    call screen nf_hotspot('+repr(g)+')']
            if e.get('variable'):out+=['    $ '+e['variable']+' = _return']
        else:out=_event_v1(e,p)
        if g.get('rewardVariable'):
            out+=['    $ '+g['rewardVariable']+' += ('+repr(float(g.get('rewardWin',1)))+' if _return >= '+str(int(g['target']))+' else '+repr(float(g.get('rewardLose',0)))+')']
        if g.get('winTarget'):out+=['    if _return >= '+str(int(g['target']))+':','        jump nfscene_'+g['winTarget']]
        if g.get('loseTarget'):out+=['    if _return < '+str(int(g['target']))+':','        jump nfscene_'+g['loseTarget']]
        return out
    return _event_v1(e,p)

_compile_v1=compile_project
def compile_project(p,assets,dest):
    from ui_theme import assets as build_skins
    p=upgrade_project(p);dest=Path(dest);assetdir=Path(assets)
    if p.get('_forceExport'):
        for plug in p.get('python',[]):
            if plug.get('asset') and (Path(plug['asset']).name!=plug['asset'] or '\\' in plug['asset'] or plug['asset'].startswith('.')):raise ValueError('Пути за пределами ресурсов не допускаются даже при игнорировании ошибок')
            if not IDENT.fullmatch(plug.get('id','')):raise ValueError('ID модуля должен быть идентификатором')
    if p.get('native',{}).get('enabled'):
        original=assetdir.parent/'native'
        if not (original/'game').is_dir():raise ValueError('В проекте нет сохраненных исходников Ren’Py')
        report=validate(p,assets)
        if report['errors']:raise ValueError('\n'.join(report['errors']))
        shutil.copytree(original,dest,dirs_exist_ok=True,ignore=(lambda base,names:[n for n in names if (Path(base)/n).is_file() and Path(n).suffix not in ('.rpy','.py')]) if p.get('_sourceOnly') else None)
        if p['native'].get('bridge'):
            from native_bridge import compile_native
            compile_native(p,original,dest,event_script)
            if not p.get('_sourceOnly'):shutil.copytree(assetdir,dest/'game/assets',dirs_exist_ok=True)
            build_skins(dest/'game',p['interface'])
        if p['native'].get('useStudioUI'):
            game=dest/'game';build_skins(game,p['interface'])
            if not p.get('_sourceOnly'):shutil.copytree(assetdir,game/'assets',dirs_exist_ok=True)
            ui='init offset = 900\n'+screen_script(p)+'\ninit 50 python:\n    config.screen_width = 1280\n    config.screen_height = 720\n    config.game_menu_action = ShowMenu("preferences")\n    config.overlay_screens = [s for s in config.overlay_screens if s != "quick_menu"]\n    if "nf_hud" not in config.overlay_screens:\n        config.overlay_screens.append("nf_hud")\n'
            for scene in p['scenes']:
                label=scene.get('_native',{}).get('originalId',scene['id']) if scene['id']==scene.get('_native',{}).get('baselineId') else scene['id']
                ui=ui.replace(q('nfscene_'+scene['id']),q(label))
            (game/'zz_novelforge_ui.rpy').write_text(ui,encoding='utf-8')
            original_text='\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in original.rglob('*.rpy'))
            defaults='\n'.join('default '+v['id']+' = '+repr(v['value']) for v in p['variables'] if not re.search(r'(?m)^\s*(?:default|define)\s+'+re.escape(v['id'])+r'\s*=',original_text))
            (game/'zz_novelforge_defaults.rpy').write_text(('' if p['native'].get('bridge') else defaults+'\n'+RUNTIME),encoding='utf-8')
        if p['native'].get('bridge'):
            for source in (original/'game').rglob('*.rpy'):
                target=dest/'_original_sources/game'/source.relative_to(original/'game');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        (dest/'NovelForge-project.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
        (dest/'README.txt').write_text('Импортированный проект RenPy. Оригинальные сценарии сохранены. Откройте через Launcher. NovelForge UI: '+str(p['native'].get('useStudioUI',False)),encoding='utf-8')
        _write_debug(dest,p)
        (dest/'NovelForge-diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    report=_compile_v1(p,assets,dest);build_skins(dest/'game',p['interface']);_write_debug(dest,p)
    (dest/'NovelForge-diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

RUNTIME += '''
transform nf_text_fade:
    alpha 0.0
    linear 0.25 alpha 1.0
screen nf_hotspot(game):
    modal True
    default found = []
    default score = 0
    add Solid("#111126")
    if game.get("backgroundImage"):
        add ("assets/" + game["backgroundImage"]) xysize (1280, 720) fit "cover"
    timer float(game.get("seconds", 30)) action Return(score)
    if score >= int(game.get("target", 1)):
        timer 0.1 action Return(score)
    text game.get("title", "Найдите предметы") xalign 0.5 ypos 20 size 32
    text ("Очки: %d" % score) xpos 30 ypos 70
    for i, obj in enumerate(game.get("objects", [])):
        if i not in found:
            button:
                xpos int(obj.get("x", 100))
                ypos int(obj.get("y", 200))
                xsize int(obj.get("width", 120))
                ysize int(obj.get("height", 90))
                background Solid("#ad93ff66")
                hover_background Solid("#ad93ffbb")
                action [SetScreenVariable("found", found + [i]), SetScreenVariable("score", score + int(obj.get("points", 1)))]
                if obj.get("asset"):
                    add ("assets/" + obj["asset"]) xysize (int(obj.get("width", 120)), int(obj.get("height", 90))) fit "contain"
                else:
                    text obj.get("label", "Найти") align (0.5, 0.5)
    textbutton "Завершить" xpos 1080 ypos 665 action Return(score)
'''

def _write_debug(dest,p):
    game=Path(dest)/'game'
    if p.get('_debug'):
        (game/'zz_novelforge_debug.rpy').write_text('init 999 python:\n    config.developer = True\n    config.console = True\n    config.debug = True\n',encoding='utf-8')
    options=game/'options.rpy'
    if options.exists() and not p.get('native',{}).get('enabled'):
        text=options.read_text(encoding='utf-8').replace('config.default_text_cps = 35','config.default_text_cps = '+str(float(p['interface'].get('textSpeed',35))))
        options.write_text(text,encoding='utf-8')
