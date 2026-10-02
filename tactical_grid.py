"""Общие правила клеточного боя для сайта и Discord.

Одна клетка всегда равна одному метру.  Диагональный шаг также расходует одну
клетку: это намеренное настольное упрощение, благодаря которому игроку не нужно
считать корни и половинные метры.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Iterable


CELL_METERS = 1
BASE_MOVEMENT = 5
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
        "blocked": ((6, 0), (6, 1), (6, 7), (6, 8), (7, 3), (7, 5)),
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
    sight_blocked: set[tuple[int, int]] | None = None
    cover_cells: set[tuple[int,int]] = field(default_factory=set)

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
                if dx and dy and ((x + dx,y) in self.blocked or (x,y + dy) in self.blocked):
                    continue
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

    def path(self, origin, destination, occupied=None):
        parents = {origin: None}
        queue = deque([origin])
        occupied = set(occupied or ()) - {origin}
        while queue:
            point = queue.popleft()
            if point == destination:
                result = []
                while point is not None:
                    result.append(point)
                    point = parents[point]
                return result[::-1]
            for neighbor in sorted(self.neighbors(point),key=lambda p:abs(p[0]-destination[0])+abs(p[1]-destination[1])):
                if neighbor not in occupied and neighbor not in parents:
                    parents[neighbor] = point
                    queue.append(neighbor)
        return []

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
            if (x0, y0) != end and (x0, y0) in (self.blocked if self.sight_blocked is None else self.sight_blocked):
                return False
        return True

    def line_cells(
        self, start: tuple[int, int], end: tuple[int, int], maximum: int | None = None,
    ) -> list[tuple[int, int]]:
        """Клетки луча от источника к цели, без клетки источника."""
        x0, y0 = start
        x1, y1 = end
        dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
        error, cells = dx + dy, []
        while (x0, y0) != (x1, y1):
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += sx
            if doubled <= dx:
                error += dx
                y0 += sy
            point = (x0, y0)
            if not self.inside(point) or point in (self.blocked if self.sight_blocked is None else self.sight_blocked):
                break
            cells.append(point)
            if maximum is not None and len(cells) >= maximum:
                break
        return cells

    def radius_cells(self, center: tuple[int, int], radius: int) -> set[tuple[int, int]]:
        radius=max(0,radius)
        return {
            (x,y) for y in range(max(0,center[1]-radius),min(self.height,center[1]+radius+1))
            for x in range(max(0,center[0]-radius),min(self.width,center[0]+radius+1))
        }

    def cone_cells(
        self, origin: tuple[int, int], toward: tuple[int, int], length: int, angle: float = 90,
    ) -> set[tuple[int, int]]:
        """Конус задан направлением на выбранную клетку и углом в градусах."""
        ox, oy = origin
        vx, vy = toward[0] - ox, toward[1] - oy
        magnitude = math.hypot(vx, vy)
        if not magnitude:
            return set()
        threshold = math.cos(math.radians(angle / 2))
        result: set[tuple[int, int]] = set()
        for y in range(self.height):
            for x in range(self.width):
                dx, dy = x - ox, y - oy
                distance = math.hypot(dx, dy)
                if not distance or distance > length:
                    continue
                cosine = (dx * vx + dy * vy) / (distance * magnitude)
                if cosine >= threshold and self.line_of_sight(origin, (x, y)):
                    result.add((x, y))
        return result

    def control_zone(self, positions: Iterable[tuple[int, int]]) -> set[tuple[int, int]]:
        """Все свободные соседние клетки, контролируемые в ближнем бою."""
        occupied = set(positions)
        return {cell for point in occupied for cell in self.neighbors(point) if cell not in occupied}

    def cover(self, start: tuple[int, int], end: tuple[int, int]) -> tuple[str, int]:
        """Вернуть вид укрытия и бонус защиты дальнего боя."""
        if not self.line_of_sight(start, end):
            return "полное", 10_000
        ray = self.line_cells(start, end)
        if end in self.cover_cells or any(point in self.cover_cells for point in ray):
            return 'частичное', 15
        adjacent = 0
        for x, y in ray[:-1]:
            adjacent += sum((x + dx, y + dy) in self.blocked for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        return ("частичное", 15) if adjacent else ("нет", 0)

    def displace(
        self, source: tuple[int, int], target: tuple[int, int], meters: int,
        occupied: set[tuple[int, int]] | None = None, *, pull: bool = False,
    ) -> tuple[int, int]:
        """Оттолкнуть цель от источника либо притянуть к нему до препятствия."""
        occupied = set(occupied or ()) - {target}
        dx = (source[0] > target[0]) - (source[0] < target[0]) if pull else (target[0] > source[0]) - (target[0] < source[0])
        dy = (source[1] > target[1]) - (source[1] < target[1]) if pull else (target[1] > source[1]) - (target[1] < source[1])
        current = target
        for _ in range(max(0, meters)):
            candidate = (current[0] + dx, current[1] + dy)
            if not self.inside(candidate) or candidate in self.blocked or candidate in occupied or candidate == source:
                break
            current = candidate
        return current

    def can_teleport(
        self, origin: tuple[int, int], destination: tuple[int, int], maximum: int,
        occupied: set[tuple[int, int]] | None = None,
    ) -> bool:
        return (
            self.inside(destination) and destination not in self.blocked
            and destination not in set(occupied or ()) and self.distance(origin, destination) <= maximum
        )

    def payload(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "cellMeters": CELL_METERS,
            "blocked": [{"x": x, "y": y} for x, y in sorted(self.blocked, key=lambda p: (p[1], p[0]))],
            "sightBlocked": [{"x": x, "y": y} for x,y in sorted(self.blocked if self.sight_blocked is None else self.sight_blocked)],
            "cover": [{'x':x,'y':y} for x,y in sorted(self.cover_cells)],
        }


def initiative_bonus(quickness: int) -> int:
    """Быстрота 10 даёт +0; каждые две единицы дают ±1."""
    return (int(quickness) - 10) // 2
