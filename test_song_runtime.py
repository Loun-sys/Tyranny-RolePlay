import copy
import unittest
from unittest.mock import patch

from ability_rules import library, owned_actions, profile, resolve
from consumables import pulse, virtual_equipment
from registration_api import _derived
from song_rules import advance, breath_limit, phrase_profile
from test_talent_runtime import actor
from training_combat import TrainingSession


SWORD = 'Abl_Comp_Sirin_Song_SwordOfStrengthSwordOfJustice'
DEATH = 'Abl_Comp_Sirin_Song_BringerOfDeath'
DAWN = 'Abl_Comp_Sirin_Song_BloodBringsTheDawn'
FORCE = 'Abl_Comp_Sirin_AriaOfForce'


class SongRuntimeTests(unittest.TestCase):
    def session(self, *keys):
        c = actor(*keys)
        c['skills']['Исполнение'] = {'value': 40}
        s = TrainingSession(1)
        s.player_position = (9, 4)
        return c, s, _derived(c, [])

    def use(self, c, s, d, key):
        return s.act({'kind': 'ability', 'name': key}, c, d, [], 2)

    def test_source_exports_all_nine_songs_with_actual_phrase_effects(self):
        songs = [r for r in library() if r.get('song')]
        self.assertEqual(len(songs), 9)
        self.assertTrue(all(r['phrases'] for r in songs))
        self.assertTrue(all(p['nodes'] for r in songs for p in r['phrases']))
        self.assertTrue(all(r['song']['radius'] == 4 for r in songs))

    def test_source_aria_costs_are_not_cooldowns(self):
        expected = {'Resolve': 5, 'Dissonance': 5, 'Force': 5, 'Resonance': 5,
                    'Pain': 6, 'Respite': 6, 'Confusion': 7, 'Storms': 7,
                    'Winter': 7, 'Memories': 8, 'Nightmares': 8}
        for name, cost in expected.items():
            self.assertEqual(resolve('Abl_Comp_Sirin_AriaOf' + name)['breathCost'], cost)

    def test_level_one_stanza_takes_four_seconds_and_lingers_two(self):
        song = resolve(SWORD)
        p = phrase_profile(song, song['phrases'][0])
        self.assertEqual(p['recitationSeconds'], 4)
        self.assertEqual(p['lingerSeconds'], 2)
        self.assertEqual(p['effects'][0]['Duration'], 6)

    def test_tempo_changes_recitation_not_linger(self):
        song = resolve(SWORD)
        fast = phrase_profile(song, song['phrases'][0], tempo=25)
        slow = phrase_profile(song, song['phrases'][0], tempo=-25)
        self.assertEqual(fast['recitationSeconds'], 3)
        self.assertEqual(slow['recitationSeconds'], 5)
        self.assertEqual(fast['lingerSeconds'], slow['lingerSeconds'])

    def test_resolve_changes_linger_without_changing_recitation(self):
        song = resolve(SWORD)
        p = phrase_profile(song, song['phrases'][0], {'effectiveAttributes': {'Стойкость': 20}})
        self.assertAlmostEqual(p['lingerSeconds'], 2.6)
        self.assertEqual(p['recitationSeconds'], 4)

    def test_advance_preserves_subround_offsets_and_cycles(self):
        active = {'phrase': 0, 'phraseCount': 3, 'remainingSeconds': 4}
        self.assertEqual(advance(active, 10, lambda _: 4), [(1, 4), (2, 8)])
        self.assertEqual(active['remainingSeconds'], 2)
        self.assertEqual(advance(active, 10, lambda _: 4), [(0, 2), (1, 6), (2, 10)])
        self.assertEqual(active['remainingSeconds'], 4)

    def test_song_is_available_as_action_but_not_ordinary_passive(self):
        c, s, d = self.session(SWORD)
        actions = owned_actions(c['talents'], d)
        self.assertTrue(any(a['key'] == SWORD for a in actions))
        self.assertEqual(d['effectiveAttributes']['Сила'], 10)

    def test_start_and_stop_preserve_action_and_apply_real_strength(self):
        c, s, d = self.session(SWORD, FORCE)
        self.use(c, s, d, SWORD)
        self.assertTrue(s.action_available)
        self.assertEqual(s.breath, 0)
        enhanced = _derived(c, virtual_equipment(s.conditions['player'], s.round_number))
        self.assertEqual(enhanced['effectiveAttributes']['Сила'], 14)
        self.use(c, s, d, SWORD)
        self.assertFalse(s.active_songs)
        self.assertTrue(s.action_available)
        s._end_turn()
        self.assertEqual(s.breath, 0)
        self.assertFalse(s.conditions['player'])

    def test_one_round_completes_two_stanzas_and_grants_two_breath(self):
        c, s, d = self.session(SWORD, FORCE)
        self.use(c, s, d, SWORD)
        s._end_turn()
        self.assertEqual(s.breath, 2)
        self.assertEqual(s.active_songs[0]['phrase'], 2)
        self.assertEqual(s.active_songs[0]['remainingSeconds'], 2)

    def test_breath_never_exceeds_highest_owned_aria_cost(self):
        c, s, d = self.session(SWORD, FORCE)
        self.use(c, s, d, SWORD)
        for _ in range(5):
            s._end_turn()
        self.assertEqual(s.breath, 5)
        self.assertEqual(breath_limit(c['talents']), 5)

    def test_without_arias_breath_capacity_is_one(self):
        c, s, d = self.session(SWORD)
        self.use(c, s, d, SWORD)
        s._end_turn()
        self.assertEqual(s.breath, 1)

    def test_starting_breath_bonus_is_applied_once(self):
        c, s, d = self.session(SWORD, FORCE, 'PSV_Comp_Sirin_QuickBreath_2of2')
        self.use(c, s, d, SWORD)
        self.assertEqual(s.breath, 2)
        s.breath = 0
        self.use(c, s, d, SWORD)
        self.assertEqual(s.breath, 0)

    def test_insufficient_breath_does_not_consume_action_or_set_cooldown(self):
        c, s, d = self.session(FORCE)
        with self.assertRaisesRegex(ValueError, 'дыхания'):
            self.use(c, s, d, FORCE)
        self.assertTrue(s.action_available)
        self.assertNotIn(FORCE, s.cooldowns)
        self.assertEqual(s.breath, 0)

    def test_aria_consumes_exact_cost_and_one_action(self):
        c, s, d = self.session(FORCE)
        s.view(c, d, [], 2)
        s.breath = 5
        with patch('training_combat.random.randint', side_effect=lambda lo, hi: hi):
            self.use(c, s, d, FORCE)
        self.assertEqual(s.breath, 0)
        self.assertFalse(s.action_available)

    def test_one_song_limit_is_checked_without_overwriting_old_song(self):
        c, s, d = self.session(SWORD, DEATH)
        self.use(c, s, d, SWORD)
        with self.assertRaisesRegex(ValueError, 'остановите'):
            self.use(c, s, d, DEATH)
        self.assertEqual([a['key'] for a in s.active_songs], [SWORD])
        self.assertTrue(s.action_available)

    def test_dual_vocalization_allows_two_not_three_songs(self):
        c, s, d = self.session(SWORD, DEATH, DAWN, 'PSV_Comp_Sirin_DualVocalization')
        self.use(c, s, d, SWORD)
        self.use(c, s, d, DEATH)
        with self.assertRaisesRegex(ValueError, 'остановите'):
            self.use(c, s, d, DAWN)
        self.assertEqual(len(s.active_songs), 2)

    def test_silence_prevents_start_and_pauses_existing_song(self):
        c, s, d = self.session(SWORD, FORCE)
        s.conditions['player'] = {'silence': {'name': 'Безмолвие', 'until': 9}}
        with self.assertRaises(ValueError):
            self.use(c, s, d, SWORD)
        s.conditions['player'].clear()
        self.use(c, s, d, SWORD)
        original = copy.deepcopy(s.active_songs)
        s.conditions['player']['silence'] = {'name': 'Безмолвие', 'until': 9}
        s._end_turn()
        self.assertEqual(s.active_songs, original)
        self.assertEqual(s.breath, 0)

    def test_hostile_stanza_applies_to_enemy_not_caster(self):
        c, s, d = self.session(DEATH)
        with patch('training_combat.random.randint', side_effect=lambda lo, hi: hi):
            self.use(c, s, d, DEATH)
        self.assertTrue(any(v.get('source', {}).get('AffectsStat') == 56 for v in s.conditions['dummy'].values()))
        self.assertFalse(any(v.get('source', {}).get('AffectsStat') == 56 for v in s.conditions.get('player', {}).values()))

    def test_missed_hostile_stanza_does_not_apply_debuff(self):
        c, s, d = self.session(DEATH)
        d['effectiveSkills']['Исполнение'] = -200
        with patch('training_combat.random.randint', return_value=1):
            self.use(c, s, d, DEATH)
        self.assertFalse(s.conditions.get('dummy', {}))

    def test_out_of_range_enemy_has_no_song_effect(self):
        c, s, d = self.session(DEATH)
        s.player_position = (0, 0)
        self.use(c, s, d, DEATH)
        self.assertFalse(s.conditions.get('dummy', {}))

    def test_partial_round_dot_does_not_tick_before_stanza_started(self):
        source = {'AffectsStat': 25, 'Value': 8, 'Duration': 6, 'IntervalRate': 1}
        states = {'dot': {'consumable': True, 'source': source, 'remainingSeconds': 6,
                          'until': 2, 'pulseDelaySeconds': 8}}
        hp = pulse(states, 2, 100, 100)
        self.assertEqual(hp, 84)
        self.assertEqual(states['dot']['remainingSeconds'], 4)
        self.assertEqual(pulse(states, 3, hp, 100), 52)

    def test_refresh_within_round_ticks_old_dot_before_replacing_it(self):
        c, s, d = self.session(DAWN)
        s.view(c, d, [], 2)
        s.runtime_talents = c['talents']
        s.runtime_derived = d
        before = s.target_healths['dummy']
        with patch('training_combat.random.randint', side_effect=lambda lo, hi: hi):
            s._song_phrase(resolve(DAWN), 1, d)
            s._song_phrase(resolve(DAWN), 1, d, offset=9)
        self.assertEqual(before - s.target_healths['dummy'], 48)
        s._end_turn()
        self.assertEqual(before - s.target_healths['dummy'], 56)

    def test_tempo_modal_can_be_selected_through_actual_stance_action(self):
        key = 'PSV_Comp_Sirin_RapidTempo'
        c, s, d = self.session(SWORD, FORCE, key)
        s.act({'kind': 'stance', 'name': resolve(key)['name']}, c, d, [], 2)
        self.use(c, s, d, SWORD)
        self.assertEqual(s.active_songs[0]['remainingSeconds'], 3)
        s._end_turn()
        self.assertEqual(s.breath, 3)
        self.assertEqual(s.active_songs[0]['remainingSeconds'], 2)

    def test_wall_blocks_hostile_song(self):
        c, s, d = self.session(DEATH)
        with patch.object(s.grid, 'line_of_sight', return_value=False):
            self.use(c, s, d, DEATH)
        self.assertFalse(s.conditions.get('dummy', {}))

    def test_friendly_stanza_affects_ally_but_not_enemy(self):
        c, s, d = self.session(SWORD)
        s.targets['dummy']['team'] = 'ally'
        self.use(c, s, d, SWORD)
        self.assertTrue(any(v.get('source', {}).get('AffectsStat') == 57 for v in s.conditions['dummy'].values()))
        for target in s.targets:
            if target != 'dummy':
                self.assertFalse(any(v.get('source', {}).get('AffectsStat') == 57 for v in s.conditions.get(target, {}).values()))

    def test_view_reports_breath_and_active_stanza_and_blocks_other_song(self):
        c, s, d = self.session(SWORD, DEATH, FORCE)
        self.use(c, s, d, SWORD)
        state = s.view(c, d, [], 2)
        songs = state['songs']
        self.assertTrue(songs['available'])
        self.assertEqual((songs['breath'], songs['limit'], songs['capacity']), (0, 5, 1))
        self.assertEqual(songs['active'][0]['key'], SWORD)
        self.assertEqual(songs['active'][0]['phraseName'], resolve(SWORD)['phrases'][0]['name'])
        self.assertEqual(songs['active'][0]['remainingSeconds'], 4)
        actions = {a.get('key'): a for a in state['actions']}
        self.assertFalse(actions[SWORD]['disabledReason'])
        self.assertIn('остановите', actions[DEATH]['disabledReason'])
        self.assertIn('дыхания', actions[FORCE]['disabledReason'])
        s._end_turn()
        self.assertEqual(s.view(c, d, [], 2)['songs']['breath'], 2)

    def test_active_song_stop_is_available_after_main_action_spent(self):
        c, s, d = self.session(SWORD)
        self.use(c, s, d, SWORD)
        s.action_available = False
        action = next(a for a in s.view(c, d, [], 2)['actions'] if a.get('key') == SWORD)
        self.assertFalse(action['disabledReason'])
        self.use(c, s, d, SWORD)
        self.assertFalse(s.active_songs)
        self.assertFalse(s.action_available)

    def test_actual_round_ticks_only_elapsed_fire_and_bleed_seconds(self):
        c, s, d = self.session(DAWN)
        before = s.target_healths['dummy']
        with patch('training_combat.random.randint', side_effect=lambda lo, hi: hi):
            self.use(c, s, d, DAWN)
            s._end_turn()
        # Fire starts at second 4 (six seconds at 8 damage/second);
        # bleeding starts at second 8 (two seconds at 6 damage/second).
        self.assertEqual(before - s.target_healths['dummy'], 60)


if __name__ == '__main__':
    unittest.main()
