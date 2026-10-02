"""Legacy entry point: refresh icons from installed game archives, never the wiki."""
from pathlib import Path

from extract_game_icons import main as extract_icons
from extract_hud_symbols import main as extract_hud


def main():
    if not Path('C:/Games/Tyranny/Data/resources.assets').is_file():
        raise SystemExit('Не найдены файлы Tyranny. Существующие оригинальные иконки сохранены; загрузка с wiki отключена.')
    extract_hud()
    extract_icons()


if __name__ == '__main__':
    main()
