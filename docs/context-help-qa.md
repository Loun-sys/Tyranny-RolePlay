# Context help and wallet icons — 2026-10-04

- Character creation loads the existing Russian mechanical encyclopedia (not lore/location entries), preserving inflected aliases and е/ё spelling variants. All 22 configured skills resolve to localized source descriptions, including «Управление силой» → «Управление силами».
- Attribute help uses the current registration configuration: exact modifiers and primary/secondary skill contributions. Class, specialization, initial ability, point-budget and next-step help includes the relevant configured values.
- Inline glossary terms, explicit controls and profile statistics support both pointer and keyboard focus. Escape dismisses help. Popups stay within the viewport; long content can be scrolled. Automatic scrolling to a focused control does not dismiss its popup, and a short pointer-exit grace period allows crossing into the popup.
- Profile derived statistics have contextual fallback help even when no matching encyclopedia entry exists. Inserted labels and descriptions remain escaped.
- The profile header displays quantities with the existing Imperial iron, bronze and copper ring assets. Each denomination has a localized hover/focus label and an accessible name containing its quantity, including zero balances.

Verification: all 19 JavaScript test scripts passed; modified production JavaScript passed syntax checks and `git diff --check`. Isolated localhost browser QA confirmed a detailed attribute popup, the previously missing stone-magic skill popup with its current value, and all three loaded ring icons with a visible denomination tooltip. No production characters, balances or inventory were changed during QA.
