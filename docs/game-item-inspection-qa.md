# Game-style item inspections (2026-10-11)

## Sources and display

The inventory, public catalogue, merchant detail, admin catalogue and forge use
one renderer. Its inspection payload is built from the original imported item
components, not Wiki text or a generic description. All 1,233 source items can
be inspected; all 383 modifier records have effect text or a source description.

`scripts/extract_item_inspection.py` exports the missing inspection-only Russian
localization from the installed game. `NoEffect.Value` references **gui**, not
abilities: the snapshot restores 16 GUI strings and resolves the affected
abilities for ability modifiers. Assembly-CSharp enum values distinguish armor
category and material. Existing source weapon stats remain unchanged.

Stat labels use the orange game palette; named modifiers are green; real lore
is gold. Rings use the original denomination icons. Empty descriptions/lore,
irrelevant zero stats, weight and duplicate generated property rows are omitted.
Meaningful zero resistance to particular damage types remains visible. Comparing
items is read-only and uses the actual equipment slot and active weapon set.

## Adaptation and limitations

Durations retain the project's 10 seconds = 1 round conversion. Recovery shows
the source equipment modifier in seconds and its round equivalent. No fictional
real-time DPS or base recovery is inferred for the turn-based engine. Damage and
bonuses shown here are source item values, not a simulated attack against a target.

Unsupported conditional equipment effects, triggered attacks and ability
modifiers are described, but **not newly automated by this display change**.
Their cards explicitly say they require manual application by the master.

## Context help

`game-help.js` shares the imported mechanical encyclopedia across creation,
personal files, admin and combat. Existing specific control help takes priority;
game glossary links and mechanical terms open the same keyboard/touch-accessible
popover. Popovers use the browser top layer so item dialogs cannot cover them.
Their contents scroll and remain within the viewport. Escape first dismisses
the help, without closing the underlying item dialog.

## Verification

- All 31 JavaScript regression scripts passed, including shop, forge, combat,
  creation help, mobile layout and item comparison.
- 39 Python tests passed: item presentations, merchant balance/API and source
  weapon readouts. The broader 94-test equipment/combat/item/encyclopedia suite
  also passed before the final inspection-only additions.
- Browser QA used `scripts/preview_combat.py 8774 shops craft` with a temporary
  database, without opening the production database or Discord.
- Verified forge before/after typed armor, original modifier text, inventory
  comparison, cloth material, Phalanster's +5 Parry/1 round/2.5 m crit effect,
  source glossary above a modal, and Escape behavior.
- At a 390×844 phone viewport: page and document width 375 px, no horizontal
  overflow; help width 351 px, entirely inside the viewport. Long item cards
  remain independently scrollable.
