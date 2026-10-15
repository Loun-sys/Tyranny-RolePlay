import copy
import json
import unittest
from pathlib import Path

from gameplay_copy import REVIEWED, COMPANION_REFERENCE, adapt_gameplay_description
from localization import localize_player_text, neutralize_companion_names


class NeutralGameplayCopyTests(unittest.TestCase):
    def test_all_reviewed_keys_exist_and_have_neutral_prose(self):
        from ability_rules import library
        source = {r['key']: r for r in library()}
        self.assertFalse(set(REVIEWED)-source.keys())
        for key, text in REVIEWED.items():
            self.assertEqual(source[key]['description'], localize_player_text(text), key)
            self.assertIsNone(COMPANION_REFERENCE.search(text), key)

    def test_song_biographies_are_not_just_name_substitution(self):
        from ability_rules import library
        songs = [r for r in library() if r['key'].startswith('Abl_Comp_Sirin_Song_')]
        self.assertEqual(len(songs), 9)
        for row in songs:
            for phrase in ['вынуждена', 'заставил', 'Алому Хору', 'своего отца', 'шлем']:
                self.assertNotIn(phrase, row['description'], row['key'])

    def test_cached_neutralized_originals_use_reviewed_text(self):
        raw = json.loads(Path('catalog/ability_rules.json').read_text(encoding='utf-8'))
        for row in raw['abilities']:
            if row['key'] in REVIEWED:
                self.assertEqual(localize_player_text(neutralize_companion_names(row['description'])),
                                 localize_player_text(REVIEWED[row['key']]), row['key'])

    def test_numeric_rules_and_graphs_are_unchanged(self):
        from ability_rules import library
        raw = json.loads(Path('catalog/ability_rules.json').read_text(encoding='utf-8'))['abilities']
        def mechanical(value):
            if isinstance(value, dict):
                return {k: mechanical(v) for k, v in value.items() if k not in {'description','localizedDescription'}}
            if isinstance(value, list):return [mechanical(v) for v in value]
            return value
        self.assertEqual(mechanical(raw), mechanical(library()))

    def test_npc_saved_copy_and_custom_description(self):
        from npc_store import refresh_ability
        raw = json.loads(Path('catalog/ability_rules.json').read_text(encoding='utf-8'))['abilities']
        row = next(r for r in raw if r['key']=='Abl_Comp_Sirin_Song_BloodBringsTheDawn')
        saved = refresh_ability({'key': row['key'], 'sourceVersion': 1, 'description': row['description']})
        self.assertEqual(saved['description'], REVIEWED[row['key']])
        self.assertEqual(refresh_ability({'key':row['key'],'sourceVersion':1,'description':'Песня моего отряда.'})['description'], 'Песня моего отряда.')

    def test_item_lore_overrides_preserve_item_stats_and_raw_source(self):
        from item_copy import NEUTRAL_ITEM_LORE
        from item_texts import catalog_texts, normalize_item_text
        catalog = catalog_texts()[0]
        self.assertFalse(set(NEUTRAL_ITEM_LORE)-catalog.keys())
        for key, text in NEUTRAL_ITEM_LORE.items():
            item = copy.deepcopy(catalog[key])
            original = copy.deepcopy(item['properties']['gameData'])
            normalized = normalize_item_text(item)
            self.assertEqual(normalized['lore'], text)
            self.assertEqual(normalized['properties']['gameData'], original)
            self.assertIsNone(COMPANION_REFERENCE.search(text), key)

    def test_custom_and_world_prose_is_not_removed_by_keyword(self):
        text = 'Снимает контроль и страх. Тяжёлая броня препятствует применению.'
        self.assertEqual(adapt_gameplay_description(text), text)


if __name__ == '__main__':unittest.main()
