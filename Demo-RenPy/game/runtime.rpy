# Common Python 2.7/3 syntax for Ren'Py 7.4+ and 8.x.
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
