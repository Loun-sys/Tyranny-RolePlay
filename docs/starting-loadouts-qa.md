# Starting loadouts and initiative — 2026-10-04

New weapon kits are granted only by character creation, alongside unchanged class supplies and money. No inventory replacement, backfill or money adjustment is performed for existing characters. `starting_grants` keeps the grant idempotent. Both distinct specializations contribute their kits; paired daggers become two separate equippable inventory entries.

## Specialization weapons

All selected weapons have ordinary quality and original game icons.

| Specialization | Exact catalog item | Quantity |
| --- | --- | --- |
| Меч и щит | Бронзовый меч / Кожаный баклер (вариант 3) | 1 / 1 |
| Двуручный меч | Бронзовый двуручный меч | 1 |
| Короткий лук | Короткий лук | 1 |
| Заклинания молний | Малый посох сердца бури | 1 |
| Заклинания рвения | Малый посох титанов | 1 |
| Дротик | Бронзовый дротик (вариант 3) | 1 |
| Парное оружие | Бронзовый кинжал | 2 |
| Безоружные атаки | — | 0 |
| Заклинания льда | Малый посох северных льдов | 1 |
| Заклинания истощения | Малый посох истощения | 1 |

Книгочей additionally retains Перо Книгочея. Other class-specific weapons were removed, while clothes, crafting materials and class money remain unchanged.

## Compact initiative

The right map toolbar has a native disclosure, initially closed. Its summary contains the original game formation icon and current round. The dropdown preserves turn order, portraits, current actor, defeated rows and roll + bonus tooltips. The HUD initiative button opens the same right dropdown rather than a second drawer. Escape and outside clicks close it.

Browser verification on an isolated temporary database:

- Desktop: opening/closing does not change map viewport geometry; no initiative list remains in the left sidebar.
- HUD button opens the right dropdown; the old information drawer is absent.
- Escape closes it.
- At 390 px viewport width: closed button is 83 × 36 px; the 319 px dropdown stays within the map toolbar. No document overflow or console errors.

## Player terminology

Registration title is «Создание Персонажа», and its command description is «Получить личную ссылку на создание персонажа». Player-facing ability requirements and talent descriptions no longer label players Вершитель Судеб. The prose adaptation is separate from general localization so canonical item names and historical lore are not renamed, and «Вершитель победы» keeps its ability identity.

## Automated verification

- `test_player_possessions.py`: all ten specialization kits, both selections, ordinary quality, icons, exact item counts, two separate daggers, idempotency, existing inventory and wallet preservation.
- `test_character_interface.py`: registration wording and neutralized player references with grammatical cases; item-name and victory-ability preservation.
- `scripts/test_combat_layout.cjs`: collapsed/native disclosure, escaped names, current/defeated rows, right-toolbar placement and shared HUD toggle.
- Capacity smoke test now includes the three specialization weapons before checking free tiny items and remaining bag capacity.
