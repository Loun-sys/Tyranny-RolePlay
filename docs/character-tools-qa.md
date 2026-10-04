# Character tools, forge and inventory QA — 2026-10-04

## Changes

- Self-deletion command and administrator deletion require explicit confirmation. Deletion is atomic, audited, guild/owner scoped, revokes access links and removes only the deleted player's saved map placements.
- Forge accepts equipped single-instance gear, compares current/next quality, shows original material and ring costs, completes immediately and preserves the equipment slot.
- Portrait upload uses owner authentication, validates PNG/JPEG/WEBP and dimensions, and changes its content-addressed URL to avoid stale images. Inventory and Discord snapshots cover the equipment rectangle through the quick slots.
- Removed letter fallback layers from item, talent and sigil icons. Empty equipment slots and inventory category icons are extracted from the game's Fallen_UI atlas; the extraction manifest records original sprite rectangles.
- All 318 source weapon records were checked for grip labels. Two Scroll bow prefabs incorrectly categorized as one-handed are repaired from their two-hand source flag. Existing/crafted source-backed catalogue entries get the canonical hand and native slot metadata at initialization.
- Two-handed gear occupies both displayed hands; shield is left-only, native armor slots are enforced. Equipped items, including inactive weapon sets, do not consume bag slots.

## Verification

- Full Python discovery: 297 tests, 296 passed; one stale assertion expected the legacy stance name. Updated that assertion to the existing canonical Russian name and reran the complete test successfully. Combat implementation was unchanged.
- Reran all 33 focused character tools, inventory, forge and character-interface tests after the final renderer change: passed.
- All JavaScript `scripts/test*.cjs` suites: passed.
- Local browser QA uses a temporary database, never the production database. Verified instant upgrade, equipped slot retention, inventory filtering, loaded original icons, portrait upload/save, and the named deletion confirmation (cancelled; no production character was deleted).
- Visually inspected full inventory and generated Discord snapshot. Portrait covers the full equipment/quickbar background and slot labels retain their small black backplates.
- Browser viewport override did not resize the existing in-app tab; it was reset. Narrow-screen CSS rules are covered by the layout test, but this run does not claim a live mobile viewport check.

No new talent mechanics or unrelated combat changes are included.
