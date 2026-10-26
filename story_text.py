"""Plain text or ordinary Word paragraphs, without tables or JSON."""
import copy,io,json,re,zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
SAMPLE='''# Простой сценарий NovelForge
# Замените текст после двоеточия. Для выбора добавьте строки Вариант.
Проект: Моя новелла
Персонаж: anna | Анна | anna.png | #b7a4ff
Сцена: intro | Знакомство
Фон: court.png
Показать: anna | справа
Анна: Привет! Какой путь выберем?
Выбор:
Вариант: Пойти на тренировку -> training
Вариант: Остаться поговорить -> talk
Сцена: training | Тренировка
Анна: Начнем с простой подачи.
Концовка: Продолжение следует
Сцена: talk | Разговор
Рассказчик: Вечер обещал быть интересным.
Концовка: До встречи!
'''

def word_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist())>64*1024*1024:raise ValueError('Документ слишком большой')
        root=ET.fromstring(z.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    return '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:body/w:p',ns))

def import_text(text,base):
    p=copy.deepcopy(base);p.pop('native',None);scenes=[];current=None;count=0
    characters={c['name'].lower():c['id'] for c in p['characters']};characters.update({c['id'].lower():c['id'] for c in p['characters']})
    def event(e):
        nonlocal current,count
        if current is None:current={'id':'intro','name':'Начало','events':[]};scenes.append(current)
        current['events'].append(e);count+=1
    for n,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#') or line=='Простой сценарий NovelForge':continue
        command,sep,value=line.partition(':');key=command.strip().lower();value=value.strip();args=[s.strip() for s in value.split('|')]
        try:
            if not sep:event({'type':'say','character':'','text':line});continue
            if key=='проект':p['title']=value
            elif key=='персонаж':
                if len(args)<2:raise ValueError('Персонаж: id | Имя | спрайт.png | #цвет')
                c={'id':args[0],'name':args[1],'sprite':args[2] if len(args)>2 else '', 'color':args[3] if len(args)>3 else '#b7a4ff','height':'medium','variants':[]}
                p['characters']=[x for x in p['characters'] if x['id']!=c['id']]+[c];characters[c['name'].lower()]=c['id'];characters[c['id'].lower()]=c['id']
            elif key=='переменная':
                if len(args)!=2:raise ValueError('Переменная: trust | 0')
                try:v=json.loads(args[1])
                except ValueError:v=args[1]
                p['variables']=[v for v in p['variables'] if v['id']!=args[0]]+[{'id':args[0],'value':v}]
            elif key=='сцена':current={'id':args[0],'name':args[1] if len(args)>1 else args[0],'events':[]};scenes.append(current)
            elif key in ('фон','музыка','звук','видео'):event({'type':{'фон':'background','музыка':'music','звук':'sound','видео':'video'}[key],'asset':value,'effect':'dissolve'})
            elif key=='показать':event({'type':'show','character':characters.get(args[0].lower(),args[0]),'position':{'слева':'left','справа':'right','центр':'center','по центру':'center'}.get(args[1].lower() if len(args)>1 else 'центр',args[1] if len(args)>1 else 'center'),'variant':args[2] if len(args)>2 else '', 'effect':'dissolve'})
            elif key=='скрыть':event({'type':'hide','character':characters.get(value.lower(),value),'effect':'dissolve'})
            elif key=='выбор':event({'type':'choice','options':[]})
            elif key=='вариант':
                caption,separator,target=value.rpartition('->')
                if not separator:raise ValueError('Вариант: Текст -> ID сцены')
                if not current or not current['events'] or current['events'][-1]['type']!='choice':event({'type':'choice','options':[]})
                current['events'][-1]['options'].append({'text':caption.strip(),'target':target.strip()})
            elif key=='переход':event({'type':'jump','target':value})
            elif key=='условие':
                if len(args)!=3:raise ValueError('Условие: trust >= 3 | win | finish')
                event({'type':'condition','expression':args[0],'yes':args[1],'no':args[2]})
            elif key=='значение':
                if len(args)!=2:raise ValueError('Значение: trust | trust + 1')
                event({'type':'set','variable':args[0],'value':args[1]})
            elif key in ('пауза','день'):event({'type':'pause' if key=='пауза' else 'day','value':float(value)})
            elif key=='концовка':event({'type':'ending','text':value,'credits':True})
            elif key=='титры':event({'type':'credits'})
            elif key=='мини-игра':event({'type':'minigame','game':args[0],'variable':args[1] if len(args)>1 else ''})
            elif key=='катсцена':event({'type':'cutscene','id':value})
            elif key in ('рассказчик','текст','автор'):event({'type':'say','character':'','text':value})
            else:
                if key not in characters:
                    cid='hero'+str(len(p['characters'])+1)
                    while any(c['id']==cid for c in p['characters']):cid+='x'
                    p['characters'].append({'id':cid,'name':command.strip(),'sprite':'','color':'#b7a4ff','height':'medium','variants':[]});characters[key]=cid
                event({'type':'say','character':characters[key],'text':value})
        except (ValueError,KeyError) as ex:raise ValueError('Строка %d: %s'%(n,ex))
    if not scenes:raise ValueError('В сценарии нет событий')
    p['scenes']=scenes;p['start']=scenes[0]['id'];return p,count

def simple_docx():
    from core import make_docx
    source=io.BytesIO(make_docx([]));out=io.BytesIO()
    body=''
    for i,line in enumerate(SAMPLE.splitlines()):
        title=i==0
        body+='<w:p>'+('<w:pPr><w:pStyle w:val="Title"/></w:pPr>' if title else '')+'<w:r><w:t xml:space="preserve">'+escape(line.lstrip('# ') if title else line)+'</w:t></w:r></w:p>'
    body+='<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1100" w:right="1100" w:bottom="1100" w:left="1100"/></w:sectPr>'
    with zipfile.ZipFile(source) as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in src.infolist():z.writestr(f,src.read(f.filename) if f.filename!='word/document.xml' else ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>').encode('utf-8'))
    return out.getvalue()
