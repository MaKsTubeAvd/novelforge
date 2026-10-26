# UTF-8
init -10 python:
    config.screen_width = 1280
    config.screen_height = 720
    config.name = "Лето на площадке"
    config.version = "1.0"
    config.save_directory = "NovelForge-arrival-35cb6ab03a"
    config.window_title = "Лето на площадке"
    config.has_sound = True
    config.has_music = True
    config.has_voice = True
    config.rollback_enabled = True
    config.overlay_screens.append("nf_hud")
    config.enter_transition = dissolve
    config.exit_transition = dissolve
    config.main_game_transition = fade
    config.end_game_transition = fade
    config.default_text_cps = 35.0
    config.default_afm_time = 15
    config.game_menu_action = ShowMenu("preferences")
