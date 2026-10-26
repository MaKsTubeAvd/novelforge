"""Structured story events, conservative control parsing and source-aware rewrites."""
import ast,copy,re

CONTROL={'branch','menu_block'}

def children(event):
    return event.get('branches',[]) if event.get('type')=='branch' else event.get('options',[]) if event.get('type')=='menu_block' else []

def walk(events,path=(),depth=0):
    if depth>24:raise ValueError('Вложенность событий превышает 24 уровня')
    for i,event in enumerate(events):
        if not isinstance(event,dict):raise ValueError('Событие должно быть объектом')
        at=path+(i,);yield at,event
        for j,arm in enumerate(children(event)):
            if not isinstance(arm,dict) or not isinstance(arm.get('events',[]),list):raise ValueError('Ветка должна содержать список событий')
            yield from walk(arm.get('events',[]),at+('branches' if event['type']=='branch' else 'options',j,'events'),depth+1)

def flat_leaves(events):return [copy.deepcopy(e) for path,e in walk(events) if e.get('type') not in CONTROL]

def validate_controls(p):
    from core import expression
    errors=[];variables={v['id'] for v in p['variables']};count=0
    try:
        for scene in p['scenes']:
            for path,e in walk(scene['events']):
                count+=1
                if count>20000:raise ValueError('В проекте больше 20 000 событий')
                if e.get('type') not in CONTROL:continue
                arms=children(e);where=scene['id']+' / '+'.'.join(str(x) for x in path)
                if not arms:errors.append(where+': добавьте ветку')
                for i,arm in enumerate(arms):
                    condition=arm.get('condition','')
                    if e['type']=='branch' and not condition and (i==0 or i!=len(arms)-1):errors.append(where+': «иначе» может быть только последней веткой')
                    if e['type']=='menu_block' and not str(arm.get('text','')).strip():errors.append(where+': у варианта выбора нет текста')
                    if condition:
                        try:expression(condition,variables)
                        except (ValueError,SyntaxError) as ex:errors.append(where+': '+str(ex))
    except (ValueError,TypeError,KeyError) as ex:errors.append(str(ex))
    return errors

def parse_control(code,parse_children,variables,logical_lines,string_pattern,depth=0):
    if depth>=24:return None
    lines=code.splitlines(keepends=True)
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith('#')):lines.pop(0)
    if not lines:return None
    source=''.join(lines);offsets=[];at=0
    for line in lines:offsets.append(at);at+=len(line)
    logical={pos:indent for pos,indent in logical_lines(source)}
    from core import expression
    if re.match(r'^if\s+',lines[0]):
        headers=[]
        for i,line in enumerate(lines):
            if logical.get(offsets[i])!=0:continue
            m=re.fullmatch(r'(if|elif)\s+(.+):\s*(?:#.*)?',line.rstrip('\r\n'))
            if m:
                if headers and m[1]=='if':return None
                try:expression(m[2],variables)
                except (ValueError,SyntaxError):return None
                headers.append((i,m[2]));continue
            if re.fullmatch(r'else\s*:\s*(?:#.*)?',line.rstrip('\r\n')):headers.append((i,''));continue
            if line.strip() and not line.lstrip().startswith('#'):return None
        if not headers or headers[0][0]!=0:return None
        arms=[]
        for j,(line,condition) in enumerate(headers):
            end=headers[j+1][0] if j+1<len(headers) else len(lines)
            arms.append({'condition':condition,'events':parse_children(''.join(lines[line+1:end]))})
        return {'type':'branch','branches':arms}
    if re.fullmatch(r'menu\s*:\s*(?:#.*)?',lines[0].rstrip('\r\n')):
        logical_inner=[(i,logical.get(offsets[i])) for i in range(1,len(lines)) if offsets[i] in logical]
        if not logical_inner:return None
        base=min(indent for i,indent in logical_inner);headers=[];prompt=''
        for i,indent in logical_inner:
            if indent!=base:continue
            text=lines[i].strip();m=re.fullmatch('('+string_pattern+r')(?:\s+if\s+(.+))?:\s*(?:#.*)?',text)
            if m:
                try:
                    caption=ast.literal_eval(m[1]);condition=m[2] or ''
                    if condition:expression(condition,variables)
                except (ValueError,SyntaxError):return None
                headers.append((i,caption,condition));continue
            if not headers:
                try:prompt=ast.literal_eval(text);continue
                except (ValueError,SyntaxError):pass
            return None
        if not headers:return None
        options=[]
        for j,(i,caption,condition) in enumerate(headers):
            end=headers[j+1][0] if j+1<len(headers) else len(lines)
            options.append({'text':caption,'condition':condition,'events':parse_children(''.join(lines[i+1:end]))})
        return {'type':'menu_block','prompt':prompt,'options':options}
    return None

def compile_control(event,p,compile_event):
    from core import q,textq
    quote=q if p.get('native',{}).get('bridge') else textq
    lines=[]
    if event['type']=='branch':
        for i,arm in enumerate(event['branches']):
            condition=arm.get('condition','');lines.append('    '+(('if ' if i==0 else 'elif ')+condition+':' if condition else 'else:'))
            body=[line for e in arm.get('events',[]) for line in compile_event(e,p)] or ['    pass']
            lines.extend('    '+line for line in body)
    else:
        lines=['    menu:']
        if event.get('prompt'):lines.append('        '+quote(event['prompt']))
        for option in event['options']:
            lines.append('        '+quote(option['text'])+(' if '+option['condition'] if option.get('condition') else '')+':')
            body=[line for e in option.get('events',[]) for line in compile_event(e,p)] or ['    pass']
            lines.extend('        '+line for line in body)
    return lines

def rewrite_statements(text,targets=None,speakers=None,scope='',destinations=None):
    """Change only logical command lines, never string/comment contents."""
    from native_bridge import logical_lines
    starts={offset for offset,indent in logical_lines(text)};out=[];offset=0;targets=targets or {};speakers=speakers or {};destinations=destinations or {}
    for line in text.splitlines(keepends=True):
        original=line
        if offset in starts:
            m=re.match(r'^(\s*)(jump|call)\s+([\w.]+)\b',line)
            if m:
                value=m[3];replacement=value
                if value.startswith('.') and scope:
                    canonical=scope+value;replacement=destinations.get(canonical,canonical)
                else:
                    for old,new in sorted(targets.items(),key=lambda x:-len(x[0])):
                        if value==old or value.startswith(old+'.'):replacement=new+value[len(old):];break
                if replacement!=value:line=line[:m.start(3)]+replacement+line[m.end(3):]
            m=re.match(r'^(\s*)([A-Za-z_]\w*)(?=(?:\s+\w+)*\s+["\'])',line)
            if m and m[2] in speakers:line=line[:m.start(2)]+speakers[m[2]]+line[m.end(2):]
        out.append(line);offset+=len(original)
    return ''.join(out)
