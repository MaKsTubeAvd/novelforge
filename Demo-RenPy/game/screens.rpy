# NovelForge custom interface; no default gui assets required.
style default:
    font "DejaVuSans.ttf"
    size 24
    color "#f7f4ff"
style button:
    background Frame("nf_ui/panel.png", 24, 24)
    hover_background Frame("nf_ui/hover.png", 24, 24)
    padding (24, 14)
style button_text:
    color "#f7f4ff"
    hover_color "#12131b"
    size 24
style input:
    color "#f7f4ff"
style bar:
    left_bar Solid("#ad93ff")
    right_bar Solid("#49475e")
    ysize 16
screen say(who, what):
    window:
        id "window"
        xanchor 0.0
        yanchor 0.0
        xpos 45
        ypos 504
        xsize 1190
        ysize 169
        padding (18, 18)
        background Frame("nf_ui/panel.png", 24, 24)
        fixed:
            if who:
                text who id "who" size 28 xpos 0 ypos 0
            hbox:
                xpos 0
                ypos 36
                spacing 8
                viewport:
                    id "nf_dialogue_scroll"
                    xsize 1140
                    ysize 96
                    mousewheel True
                    draggable False
                    text what:
                        id "what"
                        size 24
                        xfill True
                        layout "subtitle"
                        text_align 0.0
                        line_spacing 0
                        slow_cps 35.0
                vbar value YScrollValue("nf_dialogue_scroll") xsize 6 ysize 96 top_bar Solid("#ad93ff") bottom_bar Solid("#ffffff18")
    use nf_quick
screen choice(items):
    vbox:
        xalign 0.5
        yalign 0.45
        spacing 12
        for item in items:
            textbutton item.caption action item.action xsize 780
screen main_menu():
    tag menu
    add "nf_ui/backdrop.png"
    add "assets/court_photo.png" xysize (1280, 720) fit "cover"
    add Solid("#00000055")
    add "nf_ui/pattern.png"
    frame:
        xanchor 0.0
        yanchor 0.0
        xpos 80
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
                text "Лето на площадке" size 36 color "#ad93ff" xmaximum 396
                null height 8
                textbutton "Начать историю" action Start() xfill True
                textbutton "Продолжить" action ShowMenu("load") xfill True
                textbutton "Настройки" action ShowMenu("preferences") xfill True
                textbutton "Титры" action ShowMenu("nf_credits_menu") xfill True
                textbutton "Выйти" action Quit(confirm=False) xfill True
screen nf_quick():
    hbox:
        xalign 0.5
        ypos 680
        spacing 6
        textbutton "Назад" action Rollback() text_size 15 padding (12, 6)
        textbutton "Сохранить" action ShowMenu("save") text_size 15 padding (12, 6)
        textbutton "Загрузить" action ShowMenu("load") text_size 15 padding (12, 6)
        textbutton "Авто" action Preference("auto-forward", "toggle") text_size 15 padding (12, 6)
        textbutton "Пропуск" action Skip() text_size 15 padding (12, 6)
        textbutton "Меню" action ShowMenu("preferences") text_size 15 padding (12, 6)
screen nf_slots(mode):
    tag menu
    add "nf_ui/backdrop.png"
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
                        text FileTime(slot, format="%d.%m %H:%M", empty="Пустой слот") size 18
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
    add "nf_ui/backdrop.png"
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
transform nf_credit_roll(seconds=18.0):
    ypos 750
    linear seconds ypos -1000
screen nf_credits_screen():
    modal True
    add "nf_ui/backdrop.png"
    add "assets/novelforge_logo.png":
        xpos 640
        ypos 101
        xanchor 0.5
        yanchor 0.5
        xsize 230
        ysize 115
        fit "contain"
        alpha 1.0
        rotate 0.0
    viewport:
        xpos 240
        ypos 201
        xsize 800
        ysize 396
        mousewheel True
        draggable True
        vbox:
            xfill True
            spacing 26
            text "Над игрой работали" size 42 text_align 0.5 xalign 0.5 color "#ad93ff"
            text "Автор — ваше имя\nМузыка — укажите авторов\nСпасибо за игру!" text_align 0.5 xalign 0.5 size 25
    textbutton "Продолжить" xalign 0.5 ypos 658 action Return() padding (24, 10)
    key "K_ESCAPE" action Return()
    timer 18.0 action Return()
screen nf_credits_menu():
    tag menu
    use nf_credits_screen
screen nf_hud():
    if not main_menu and not any(renpy.get_screen(s) for s in ("nf_credits_screen", "nf_composition", "nf_mini", "nf_quiz", "save", "load", "preferences")):
        vbox:
            xpos 0.78
            ypos 0.04
            spacing 8
            text "Доверие" size 20
            bar value VariableValue("trust", 10.0) xsize 240
        text "Лето на площадке" xpos 0.03 ypos 0.04 xmaximum 400 size 22

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
