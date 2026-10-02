"""Общие правила клеточного боя для сайта и Discord.

Одна клетка всегда равна одному метру.  Диагональный шаг также расходует одну
клетку: это намеренное настольное упрощение, благодаря которому игроку не нужно
считать корни и половинные метры.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


CELL_METERS = 1
BASE_MOVEMENT = 6
DEFAULT_WIDTH = 13
DEFAULT_HEIGHT = 9


# Локальные копии карт взяты из Tyranny Wiki; ссылка на источник сохранена рядом.
# Сетка и препятствия хранятся отдельно, поэтому фон можно заменить без миграции боя.
TACTICAL_MAPS = {
    "training_grounds": {
        "name": "Тренировочная площадка Небесной Тверди",
        "image": "assets/maps/training-grounds.png",
        "source": "https://tyranny.fandom.com/wiki/Category:Location_images",
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "blocked": ((6, 0), (6, 1), (6, 7), (6, 8)),
    },
    "burning_library": {
        "name": "Руины Горящей библиотеки",
        "image": "assets/maps/burning-library.png",
        "source": "https://tyranny.fandom.com/wiki/Category:Location_images",
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "blocked": (),
    },
    "plainsgate": {
        "name": "Равнинные врата",
        "image": "assets/maps/plainsgate.png",
        "source": "https://tyranny.fandom.com/wiki/Category:Location_images",
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "blocked": (),
    },
}


@dataclass
class TacticalGrid:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    blocked: set[tuple[int, int]] = field(default_factory=set)

    def inside(self, point: tuple[int, int]) -> bool:
        x, y = point
        return 0 <= x < self.width and 0 <= y < self.height

    @staticmethod
    def distance(a: tuple[int, int], b: tuple[int, int]) -> int:
        """Игровая дальность в метрах (шахматное расстояние)."""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def neighbors(self, point: tuple[int, int]) -> Iterable[tuple[int, int]]:
        x, y = point
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                candidate = (x + dx, y + dy)
                if (dx or dy) and self.inside(candidate) and candidate not in self.blocked:
                    yield candidate

    def reachable(
        self, origin: tuple[int, int], movement: int, occupied: set[tuple[int, int]] | None = None,
    ) -> dict[tuple[int, int], int]:
        """Клетки, достижимые без прыжков сквозь препятствия и другие токены."""
        occupied = set(occupied or ()) - {origin}
        distance = {origin: 0}
        queue = deque([origin])
        while queue:
            point = queue.popleft()
            if distance[point] >= movement:
                continue
            for candidate in self.neighbors(point):
                if candidate in occupied or candidate in distance:
                    continue
                distance[candidate] = distance[point] + 1
                queue.append(candidate)
        return distance

    def line_of_sight(self, start: tuple[int, int], end: tuple[int, int]) -> bool:
        """Проверка прямой видимости по клеткам алгоритмом Брезенхэма."""
        x0, y0 = start
        x1, y1 = end
        dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
        error = dx + dy
        while (x0, y0) != (x1, y1):
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += sx
            if doubled <= dx:
                error += dx
                y0 += sy
            if (x0, y0) != end and (x0, y0) in self.blocked:
                return False
        return True

    def payload(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "cellMeters": CELL_METERS,
            "blocked": [{"x": x, "y": y} for x, y in sorted(self.blocked, key=lambda p: (p[1], p[0]))],
        }


def initiative_bonus(quickness: int) -> int:
    """Быстрота 10 даёт +0; каждые две единицы дают ±1."""
    return (int(quickness) - 10) // 2
