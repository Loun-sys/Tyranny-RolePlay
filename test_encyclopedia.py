"""Glossary coverage and correct article identity, including game-source checks."""
import json
from pathlib import Path
import unittest

from scripts.extract_game_encyclopedia import (
    GLOSSARY_SCRIPT, REMOVED_ASSETS, REMOVED_CATEGORIES,
    entry_aliases, load_locale, normalize, resolve,
)


ROOT = Path(__file__).parent
GAME = Path('C:/Games/Tyranny/Data')


class EncyclopediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'web/data/encyclopedia.json').read_text(encoding='utf-8'))
        cls.entries = cls.catalog['entries']

    def test_canonical_title_always_opens_its_own_article(self):
        lookup = {}
        for entry in self.entries:
            for alias in [entry['key'], entry['asset'], entry['title'], entry['titleEn'], *entry['aliases']]:
                lookup.setdefault(normalize(alias), entry['key'])
        for entry in self.entries:
            with self.subTest(title=entry['title']):
                self.assertEqual(lookup[normalize(entry['title'])], entry['key'])
                self.assertEqual(lookup[normalize(entry['titleEn'])], entry['key'])

    def test_aliases_contain_only_article_identity(self):
        aliases = entry_aliases('Точность', 'Accuracy', 'GL_Accuracy',
                                '[url=glossary:точность]Точность[/url]',
                                '[url=glossary:accuracy]Accuracy[/url]')
        self.assertIn('точность', aliases)
        self.assertNotIn('Волшебный посох', aliases)
        for entry in self.entries:
            own = {normalize(entry['title']), normalize(entry['titleEn']), normalize(entry['asset'])}
            self.assertTrue(all(normalize(alias) in own for alias in entry['aliases']), entry['key'])

    def test_no_duplicates_or_unintended_exclusions(self):
        self.assertEqual(len({e['key'] for e in self.entries}), len(self.entries))
        self.assertEqual(len({e['asset'] for e in self.entries}), len(self.entries))
        for entry in self.entries:
            self.assertNotIn(entry['asset'], REMOVED_ASSETS)
            self.assertNotIn(entry['category'], REMOVED_CATEGORIES)
            self.assertTrue(entry['body'].strip(), entry['key'])

    def test_role_play_overrides_survive_regeneration(self):
        by_asset = {entry['asset']: entry for entry in self.entries}
        self.assertIn('Певчий', by_asset['GL_GameMechanics_Breath']['body'])
        self.assertNotIn('Сирин', by_asset['GL_GameMechanics_Breath']['body'])
        self.assertIn('Персонажу игрока', by_asset['GL_GameMechanics_Favor']['body'])
        self.assertNotIn('одноручным', by_asset['GL_Boon_Quality_Alone_Time']['body'])
        self.assertNotIn('Таймер перезарядки работает', by_asset['GL_GameMechanics_Cooldown']['body'])

    @unittest.skipUnless((GAME / 'bundles/lists.unity3d').exists(), 'Installed game not available')
    def test_all_allowed_game_articles_and_full_affliction_lore_copy(self):
        import UnityPy
        environment = UnityPy.load(str(GAME / 'bundles/lists.unity3d'))
        source = []
        for obj in environment.objects:
            if obj.type.name == 'MonoBehaviour':
                row = obj.read_typetree()
                if row.get('m_Script', {}).get('m_PathID') == GLOSSARY_SCRIPT:
                    source.append(row)
        allowed = {row['m_Name']: row for row in source
                   if row['m_Name'] not in REMOVED_ASSETS and row['Category'] not in REMOVED_CATEGORIES}
        by_asset = {entry['asset']: entry for entry in self.entries}
        self.assertEqual(set(allowed), set(by_asset))
        self.assertEqual(sum(row['Category'] == 2 for row in allowed.values()), 39)
        ru = load_locale(GAME / 'data/exported/localized/ru')
        for asset, row in allowed.items():
            if row['Category'] == 2 or asset.casefold() == 'gl_skills_noncombat_lore':
                with self.subTest(asset=asset):
                    self.assertEqual(by_asset[asset]['body'], resolve(row['Body'], ru))


if __name__ == '__main__':
    unittest.main()
