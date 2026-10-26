"""Shared 1280x720 layout and dependency-free PNG skins for editor exports."""
import json,math,struct,zlib
from pathlib import Path

def q(v):return json.dumps(str(v),ensure_ascii=False)
def tq(v):return q(str(v).replace('[','[[').replace('{','{{'))
def rgb(s):return tuple(int(s[i:i+2],16) for i in (1,3,5))
def png(path,w,h,pixel):
    data=b''.join(b'\0'+b''.join(bytes(pixel(x,y)) for x in range(w)) for y in range(h))
    def chunk(tag,data):return struct.pack('!I',len(data))+tag+data+struct.pack('!I',zlib.crc32(tag+data)&0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(data,6))+chunk(b'IEND',b''))

def layout(ui):
    x=round(float(ui.get('textboxX',.035))*1280); y=round(float(ui.get('textboxY',.70))*720)
    w=round(float(ui.get('textboxW',.93))*1280); h=round(float(ui.get('textboxH',.235))*720)
    return {'x':x,'y':y,'w':w,'h':h,'padding':int(ui.get('padding',24)),'quickY':max(0,min(690,round(float(ui.get('quickY',.945))*720)))}

def assets(game,ui):
    d=Path(game)/'nf_ui';d.mkdir(exist_ok=True)
    bg=rgb(ui['background']);accent=rgb(ui['accent']);pattern=ui.get('pattern','orbits');strength=float(ui.get('patternOpacity',.13));style=ui.get('backdrop','aurora')
    def pixel(x,y):
        t=y/720;glow=max(0,1-math.hypot((x-970)/900,(y-150)/700))**2
        if style=='flat':glow=0;t=0
        elif style=='paper':glow=.15; t=.1
        col=[min(255,max(0,int(c*(1-.24*t)+accent[i]*glow*.23))) for i,c in enumerate(bg)]
        hit=False
        if pattern=='grid':hit=(x%64<1 or y%64<1)
        elif pattern=='dots':hit=((x%42-21)**2+(y%42-21)**2<3)
        elif pattern=='diagonal':hit=(x+y)%82<2
        elif pattern=='orbits':hit=any(abs(math.hypot(x-1000,y-160)-r)<1.2 for r in (180,260,340,420,500,580))
        elif pattern=='waves':hit=(y+int(math.sin(x/105)*20))%65<2
        if hit:col=[int(c*(1-strength)+accent[i]*strength) for i,c in enumerate(col)]
        return (*col,255)
    png(d/'backdrop.png',1280,720,pixel)
    def mask(x,y):
        hit=False
        if pattern=='grid':hit=(x%64<1 or y%64<1)
        elif pattern=='dots':hit=((x%42-21)**2+(y%42-21)**2<3)
        elif pattern=='diagonal':hit=(x+y)%82<2
        elif pattern=='orbits':hit=any(abs(math.hypot(x-1000,y-160)-r)<1.2 for r in (180,260,340,420,500,580))
        elif pattern=='waves':hit=(y+int(math.sin(x/105)*20))%65<2
        return (*accent,int(strength*255) if hit else 0)
    png(d/'pattern.png',1280,720,mask)
    # Small nine-slice rounded panels: corners remain sharp and alpha is real.
    for name,color,alpha,border in [('panel',ui['panel'],float(ui.get('panelOpacity',.94)),True),('button',ui['panel'],.92,True),('hover',ui['accent'],1,False)]:
        radius=int(ui.get('radius',16));b=rgb(color);edge=rgb(ui['accent'])
        def pp(x,y,b=b,alpha=alpha,border=border):
            dx=max(radius-x,0,x-(63-radius));dy=max(radius-y,0,y-(63-radius));dist=math.hypot(dx,dy)
            if dist>radius:return (0,0,0,0)
            isedge=x<1 or y<1 or x>62 or y>62 or (dx and dy and dist>radius-1.4)
            return (*(edge if isedge and border else b),int(alpha*255))
        png(d/(name+'.png'),64,64,pp)

def images_code(items,indent='    '):
    code=''
    for im in sorted(items,key=lambda x:float(x.get('z',0))):
        if not im.get('asset'):continue
        code+=indent+'add '+q('assets/'+im['asset'])+':\n'+indent+'    xpos '+str(round(float(im.get('x',.5))*1280))+'\n'+indent+'    ypos '+str(round(float(im.get('y',.2))*720))+'\n'+indent+'    xanchor 0.5\n'+indent+'    yanchor 0.5\n'+indent+'    xsize '+str(int(im.get('width',200)))+'\n'+indent+'    ysize '+str(int(im.get('height',140)))+'\n'+indent+'    fit "contain"\n'+indent+'    alpha '+str(float(im.get('opacity',1)))+'\n'+indent+'    rotate '+str(float(im.get('rotation',0)))+'\n'
    return code

def screens(p,legacy):
    ui=p['interface'];l=layout(ui);a=q(ui['accent']);text=q(ui['text']);hover=q(ui.get('hoverText','#10131b'))
    # Replace only shared menu surfaces; all screens use the same generated texture.
    legacy=legacy.replace('add Solid('+q(ui['background'])+')','add "nf_ui/backdrop.png"')
    legacy=legacy.replace('background Solid('+q(ui['panel'])+')','background Frame("nf_ui/panel.png", 24, 24)')
    start=legacy.index('screen say(');end=legacy.index('screen choice(',start)
    tx=int(ui.get('textOffsetX',0));ty=int(ui.get('textOffsetY',0));nx=int(ui.get('nameOffsetX',0));ny=int(ui.get('nameOffsetY',0))
    nameH=int(ui['nameSize'])+8+ny
    textW=max(40,l['w']-l['padding']*2-14-tx);lineH=math.ceil(int(ui['fontSize'])*1.2)+int(ui.get('lineSpacing',0));textH=max(32,(l['h']-l['padding']*2-nameH-ty)//lineH*lineH)
    animation=ui.get('textAnimation','typewriter');cps=0 if animation!='typewriter' else float(ui.get('textSpeed',35))
    say='''screen say(who, what):
    window:
        id "window"
        xanchor 0.0
        yanchor 0.0
        xpos %(x)d
        ypos %(y)d
        xsize %(w)d
        ysize %(h)d
        padding (%(padding)d, %(padding)d)
        background Frame("nf_ui/panel.png", 24, 24)
        fixed:
            if who:
                text who id "who" size %(nameSize)d xpos %(nx)d ypos %(ny)d
            hbox:
                xpos %(tx)d
                ypos %(textY)d
                spacing 8
                viewport:
                    id "nf_dialogue_scroll"
                    xsize %(textW)d
                    ysize %(innerH)d
                    mousewheel True
                    draggable False
                    text what:
                        id "what"
                        size %(fontSize)d
                        xfill True
                        layout "subtitle"
                        text_align %(align)s
                        line_spacing %(lineSpacing)d
                        slow_cps %(cps)s
%(fade)s                vbar value YScrollValue("nf_dialogue_scroll") xsize 6 ysize %(innerH)d top_bar Solid(%(accent)s) bottom_bar Solid("#ffffff18")
    use nf_quick
'''%dict(l,accent=a,nameSize=int(ui['nameSize']),textW=textW,fontSize=int(ui['fontSize']),innerH=textH,tx=tx,textY=nameH+ty,nx=nx,ny=ny,align={'left':0.0,'center':0.5,'right':1.0}.get(ui.get('textAlign'),0.0),lineSpacing=int(ui.get('lineSpacing',0)),cps=cps,fade='                        at nf_text_fade\n' if animation=='fade' else '')
    legacy=legacy[:start]+say+legacy[end:]
    start=legacy.index('screen main_menu(');end=legacy.index('screen nf_quick(',start)
    x={'left':80,'center':410,'right':740}.get(ui.get('menuAlign','left'),80)
    menu='''screen main_menu():
    tag menu
    add "nf_ui/backdrop.png"
'''
    if ui.get('menuImage'):menu+='    add '+q('assets/'+ui['menuImage'])+' xysize (1280, 720) fit "cover"\n    add Solid("#00000055")\n    add "nf_ui/pattern.png"\n'
    menu+=images_code(ui.get('images',[]))
    menu+='''    frame:
        xanchor 0.0
        yanchor 0.0
        xpos %(x)d
        ypos 70
        xsize 460
        ysize 580
        padding (32, 30)
        background Frame("nf_ui/panel.png", 24, 24)
        viewport:
            xfill True
            ysize 520
            mousewheel True
            draggable True
            vbox:
                spacing 13
                text %(title)s size %(titleSize)d color %(accent)s xmaximum 396
                null height 8
                textbutton "Начать историю" action Start() xfill True
                textbutton "Продолжить" action ShowMenu("load") xfill True
                textbutton "Настройки" action ShowMenu("preferences") xfill True
                textbutton "Титры" action ShowMenu("nf_credits_menu") xfill True
                textbutton "Выйти" action Quit(confirm=False) xfill True
'''%dict(x=x,title=tq(p['title']),titleSize=int(ui.get('titleSize',36)),accent=a)
    legacy=legacy[:start]+menu+legacy[end:]
    start=legacy.index('screen nf_quick(');end=legacy.index('screen nf_slots(',start)
    legacy=legacy[:start]+'''screen nf_quick():
    hbox:
        xalign 0.5
        ypos %d
        spacing 6
        textbutton "Назад" action Rollback() text_size 15 padding (12, 6)
        textbutton "Сохранить" action ShowMenu("save") text_size 15 padding (12, 6)
        textbutton "Загрузить" action ShowMenu("load") text_size 15 padding (12, 6)
        textbutton "Авто" action Preference("auto-forward", "toggle") text_size 15 padding (12, 6)
        textbutton "Пропуск" action Skip() text_size 15 padding (12, 6)
        textbutton "Меню" action ShowMenu("preferences") text_size 15 padding (12, 6)
'''%l['quickY']+legacy[end:]
    # Choose buttons and fonts with explicit bounded widths, prevent overflow.
    legacy=legacy.replace('xsize 750','xsize 780').replace('size 26','size '+str(int(ui.get('buttonSize',24))))
    legacy=legacy.replace('background Solid('+q(ui['accent'])+')','background Frame("nf_ui/hover.png", 24, 24)')
    legacy=legacy.replace('hover_color "#111126"','hover_color '+hover)
    legacy=legacy.replace('hover_background Solid('+q(ui['accent'])+')','hover_background Frame("nf_ui/hover.png", 24, 24)')
    start=legacy.index('screen nf_credits_screen(');end=legacy.index('screen nf_credits_menu(',start)
    cr=p['credits'];duration=float(cr.get('seconds',18));style=cr.get('style','cinema')
    credit='''transform nf_credit_roll(seconds=18.0):
    ypos 750
    linear seconds ypos -1000
screen nf_credits_screen():
    modal True
    add "nf_ui/backdrop.png"
'''
    if cr.get('backgroundImage'):credit+='    add '+q('assets/'+cr['backgroundImage'])+' xysize (1280, 720) fit "cover"\n    add Solid("#00000077")\n'
    credit+=images_code(cr.get('images',[]))
    if style=='scroll':
        credit+='    vbox at nf_credit_roll('+str(duration)+'):\n        xalign 0.5\n        xsize 820\n        spacing 28\n        text '+tq(cr['title'])+' xalign 0.5 text_align 0.5 size 42 color '+a+'\n        text '+tq(cr['lines'])+' xalign 0.5 text_align 0.5 size 26\n'
    else:
        credit+='''    viewport:
        xpos 240
        ypos %(textY)d
        xsize 800
        ysize %(textH)d
        mousewheel True
        draggable True
        vbox:
            xfill True
            spacing 26
            text %(title)s size 42 text_align 0.5 xalign 0.5 color %(accent)s
            text %(lines)s text_align 0.5 xalign 0.5 size 25
'''%dict(textY=int(cr.get('textY',.28)*720),textH=int(cr.get('textH',.55)*720),title=tq(cr['title']),lines=tq(cr['lines']),accent=a)
    credit+='    textbutton "Продолжить" xalign 0.5 ypos 658 action Return() padding (24, 10)\n    key "K_ESCAPE" action Return()\n    timer '+str(duration)+' action Return()\n'
    legacy=legacy[:start]+credit+legacy[end:]
    # Show custom widgets inside the 1280x720 safe frame with explicit sizes.
    legacy=legacy.replace('font "DejaVuSans.ttf"','font "DejaVuSans.ttf"')
    legacy=legacy.replace('screen nf_hud():\n    if not main_menu:', 'screen nf_hud():\n    if not main_menu and not any(renpy.get_screen(s) for s in ("nf_credits_screen", "nf_composition", "nf_mini", "nf_quiz", "save", "load", "preferences")):')
    return legacy

def card_screen():
    return '''
transform nf_card_appear:
    alpha 0.0
    linear 0.5 alpha 1.0
screen nf_composition(data):
    add Solid(data.get("background", "#111126"))
    if data.get("asset"):
        add ("assets/" + data["asset"]) xysize (1280, 720) fit "cover"
    for layer in sorted(data.get("images", []), key=lambda x: x.get("z", 0)):
        if layer.get("asset"):
            add ("assets/" + layer["asset"]):
                xpos int(layer.get("x", 0.5) * 1280)
                ypos int(layer.get("y", 0.2) * 720)
                xanchor 0.5
                yanchor 0.5
                xsize int(layer.get("width", 200))
                ysize int(layer.get("height", 140))
                fit "contain"
                alpha layer.get("opacity", 1.0)
                rotate layer.get("rotation", 0.0)
    text data.get("text", "") at nf_card_appear:
        xpos int(data.get("textX", 0.5) * 1280)
        ypos int(data.get("textY", 0.55) * 720)
        xanchor 0.5
        yanchor 0.5
        xmaximum int(data.get("textWidth", 1000))
        size int(data.get("fontSize", 44))
        color data.get("textColor", "#ffffff")
        text_align 0.5
        outlines [(1, "#00000088", 0, 1)]
        substitute False
'''
