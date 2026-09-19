"""Stdlib-only safety tests; fixtures here are not hardware evidence."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('ask-pstv')


def response(calls):
    return {'type': 'call', 'success': True, 'error': None, 'error_code': None,
            'function_calls': calls, 'suppressed_calls': [], 'confidence': 1.0}


def call(name='get_system_status', arguments=None):
    return {'name': name, 'arguments': {} if arguments is None else arguments}


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'one-shot wrapper has not been implemented')
        self.mod = runpy.run_path(str(SCRIPT), run_name='test_module')

    def test_accepts_only_three_known_zero_argument_tools(self):
        for name in ('get_system_status', 'get_storage_status', 'get_kernel_info'):
            self.assertEqual(self.mod['select_tool'](json.dumps(response([call(name)]))), (name, {}))

    def test_weather_city_arguments_are_strict(self):
        for city in ['Paris', 'São Paulo', 'Cheshire, Connecticut, USA', '06410']:
            raw = json.dumps(response([call('get_weather', {'city': city})]))
            self.assertEqual(self.mod['select_tool'](raw), ('get_weather', {'city': city}))
        for args in [{}, {'city': ''}, {'city': 'https://evil.example'}, {'city': '../x'},
                     {'city': 'Paris?x=1'}, {'city': 'Paris\n'}, {'city': 'x' * 81},
                     {'city': None}, {'city': 'Paris', 'url': 'https://evil.example'}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mod['select_tool'](json.dumps(response([call('get_weather', args)])))

    def test_cheshire_aliases_are_explicit_not_guessed(self):
        for city in ['Cheshire', '06410']:
            self.assertEqual(self.mod['weather_location'](city), 'Cheshire, Connecticut, USA')
        self.assertEqual(self.mod['weather_location']('Paris'), 'Paris')

    def test_weather_uses_fixed_https_origin_and_resolved_location(self):
        from unittest.mock import MagicMock
        payload = {'nearest_area': [{'areaName': [{'value': 'Cheshire'}],
                    'region': [{'value': 'Connecticut'}],
                    'country': [{'value': 'United States of America'}]}],
                   'current_condition': [{'temp_F': '66', 'temp_C': '19',
                    'weatherDesc': [{'value': 'Sunny'}]}]}
        handle = MagicMock()
        handle.__enter__.return_value = handle
        handle.read.return_value = json.dumps(payload).encode()
        opener = MagicMock()
        opener.open.return_value = handle
        with patch('urllib.request.build_opener', return_value=opener):
            lines = self.mod['get_weather']('06410')
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url,
                'https://wttr.in/Cheshire%2C%20Connecticut%2C%20USA?format=j1&lang=en')
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 15)
            self.assertIn('Cheshire, Connecticut, United States of America', lines[0])
            payload['nearest_area'][0]['country'][0]['value'] = 'France'
            handle.read.return_value = json.dumps(payload).encode()
            with self.assertRaises(OSError):
                self.mod['get_weather']('06410')
            handle.read.return_value = b'x' * 262145
            with self.assertRaises(OSError):
                self.mod['get_weather']('Paris')
        self.assertIsNone(self.mod['NoRedirect']().redirect_request(None, None, 302,
                          'redirect', {}, 'https://evil.example'))

    def test_weather_cannot_send_a_city_not_in_the_prompt(self):
        def forbidden(**_):
            self.fail('invented location must not reach network')
        globals_ = self.mod['main'].__globals__
        raw = json.dumps(response([call('get_weather', {'city': 'Paris'})]))
        with patch.dict(globals_, infer=lambda _: raw, TOOLS={'get_weather': forbidden}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod['main'](['write a poem']), 2)

    def test_pokemon_name_arguments_and_aliases(self):
        for name, slug in [('Gengar', 'gengar'), ('Pikachu', 'pikachu'), ('Mr. Mime', 'mr-mime')]:
            raw = json.dumps(response([call('get_pokemon_info', {'name': name})]))
            self.assertEqual(self.mod['select_tool'](raw), ('get_pokemon_info', {'name': name}))
            self.assertEqual(self.mod['pokemon_slug'](name), slug)
        for name in ['../gengar', 'https://evil.example', 'gengar?x=1', '', 'x'*61, None, '25', 'Gengar\n']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.mod['pokemon_slug'](name)
        with self.assertRaises(ValueError):
            self.mod['select_tool'](json.dumps(response([call('get_pokemon_info', {'name':'Gengar', 'url':'x'})])))

    def test_pokemon_lookup_caches_and_formats_api_data(self):
        import tempfile
        from unittest.mock import MagicMock
        # Synthetic boundary fixture; not a claim about game data.
        payload = {'id': 94, 'name': 'gengar',
                   'types': [{'slot': 1, 'type': {'name': 'ghost'}}],
                   'abilities': [{'is_hidden': False, 'ability': {'name': 'fixture-ability'}}],
                   'stats': [{'base_stat': 10, 'stat': {'name': name}}
                             for name in ['hp','attack','defense','special-attack','special-defense','speed']]}
        handle = MagicMock()
        handle.__enter__.return_value = handle
        handle.read.return_value = json.dumps(payload).encode()
        opener = MagicMock()
        opener.open.return_value = handle
        with tempfile.TemporaryDirectory(dir=SCRIPT.parent) as tmp, \
                patch.dict(self.mod['get_pokemon_info'].__globals__, HERE=Path(tmp)), \
                patch('urllib.request.build_opener', return_value=opener):
            first = self.mod['get_pokemon_info']('Gengar')
            self.assertEqual(opener.open.call_args.args[0].full_url, 'https://pokeapi.co/api/v2/pokemon/gengar/')
            self.assertIn('GENGAR', first[0])
            self.assertTrue(any('HP 10' in line for line in first))
            self.assertTrue(any('fetched' in line for line in first))
            second = self.mod['get_pokemon_info']('Gengar')
            self.assertTrue(any('cached' in line for line in second))
            self.assertEqual(opener.open.call_count, 1)
            cache = Path(tmp)/'.pokemon-cache/gengar.json'
            damaged = json.loads(cache.read_text()); damaged['name'] = 'pikachu'
            cache.write_text(json.dumps(damaged))
            with self.assertRaises(OSError):
                self.mod['get_pokemon_info']('Gengar')
            self.assertEqual(opener.open.call_count, 1)

    def test_pokemon_cannot_send_a_name_not_in_prompt(self):
        def forbidden(**_):
            self.fail('invented name must not reach network')
        raw = json.dumps(response([call('get_pokemon_info', {'name': 'Gengar'})]))
        with patch.dict(self.mod['main'].__globals__, infer=lambda _: raw,
                        TOOLS={'get_pokemon_info': forbidden}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod['main'](['write a poem']), 2)

    def test_dice_arguments_are_strict(self):
        for args in [{'count': 3, 'sides': 20}, {'count': 1, 'sides': 100}, {'count': 20, 'sides': 2}]:
            raw = json.dumps(response([call('roll_dice', args)]))
            self.assertEqual(self.mod['select_tool'](raw), ('roll_dice', args))
        for args in [{}, {'count': 3}, {'sides': 20}, {'count': 0, 'sides': 6}, {'count': 21, 'sides': 6},
                     {'count': 3, 'sides': 1}, {'count': 3, 'sides': 101}, {'count': '3', 'sides': 20},
                     {'count': 3.0, 'sides': 20}, {'count': True, 'sides': 20}, {'count': -1, 'sides': 6},
                     {'count': 3, 'sides': 20, 'modifier': 2}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.mod['select_tool'](json.dumps(response([call('roll_dice', args)])))

    def test_dice_rolls_are_real_random_and_bounded(self):
        seen = set()
        for _ in range(200):
            lines = self.mod['roll_dice'](20, 2)
            self.assertEqual(lines[0], 'rolled 20d2')
            faces = [int(face) for face in lines[1].removeprefix('rolls: ').split(', ')]
            self.assertEqual(len(faces), 20)
            self.assertTrue(all(1 <= face <= 2 for face in faces))
            self.assertEqual(lines[2], f'total: {sum(faces)}')
            seen.update(faces)
        # A constant or model-invented roll would never touch both faces.
        self.assertEqual(seen, {1, 2})

    def test_dice_numbers_must_be_mentioned_in_the_prompt(self):
        mentioned = self.mod['mentioned_arguments']
        for prompt, args in [('roll three twenty-sided dice', {'count': 3, 'sides': 20}),
                             ('roll 3d20', {'count': 3, 'sides': 20}),
                             ('roll two six-sided dice', {'count': 2, 'sides': 6}),
                             ('roll 2 d6 please', {'count': 2, 'sides': 6}),
                             ('ROLL 2D6', {'count': 2, 'sides': 6})]:
            with self.subTest(prompt=prompt):
                self.assertTrue(mentioned('roll_dice', args, prompt))
        for prompt, args in [('roll some dice', {'count': 3, 'sides': 20}),
                             ('roll 3d100', {'count': 3, 'sides': 20}),
                             ('roll three coins', {'count': 3, 'sides': 6}),
                             ('roll 6d6', {'count': 3, 'sides': 6})]:
            with self.subTest(prompt=prompt):
                self.assertFalse(mentioned('roll_dice', args, prompt))
        # String arguments keep the original literal, case-insensitive rule.
        self.assertTrue(mentioned('get_weather', {'city': 'Paris'}, 'weather in paris?'))
        self.assertFalse(mentioned('get_weather', {'city': 'Paris'}, 'weather in Berlin?'))
        self.assertTrue(mentioned('get_pokemon_info', {'name': 'Mr. Mime'}, 'look up mr. mime'))

    def test_dice_notation_must_match_the_roll(self):
        agrees = self.mod['notation_agrees']
        self.assertTrue(agrees('roll_dice', {'count': 2, 'sides': 6}, 'roll 2d6'))
        self.assertTrue(agrees('roll_dice', {'count': 1, 'sides': 20}, 'roll a d20'))
        self.assertTrue(agrees('roll_dice', {'count': 3, 'sides': 20}, 'roll three twenty-sided dice'))
        self.assertTrue(agrees('get_weather', {'city': 'Paris'}, 'weather in Paris'))
        for prompt, args in [('roll 2d6', {'count': 2, 'sides': 2}),
                             ('roll 4d6', {'count': 4, 'sides': 2}),
                             ('roll a d20', {'count': 20, 'sides': 2}),
                             ('roll 2d6 and 1d20', {'count': 2, 'sides': 6})]:
            with self.subTest(prompt=prompt):
                self.assertFalse(agrees('roll_dice', args, prompt))

    def test_misread_dice_notation_is_refused_not_rolled(self):
        def forbidden(**_):
            self.fail('a mismatched notation roll must not happen')
        raw = json.dumps(response([call('roll_dice', {'count': 2, 'sides': 2})]))
        with patch.dict(self.mod['main'].__globals__, infer=lambda _: raw,
                        TOOLS={'roll_dice': forbidden}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod['main'](['roll 2d6']), 2)

    def test_dice_cannot_roll_numbers_not_in_the_prompt(self):
        def forbidden(**_):
            self.fail('invented roll must not happen')
        raw = json.dumps(response([call('roll_dice', {'count': 20, 'sides': 100})]))
        with patch.dict(self.mod['main'].__globals__, infer=lambda _: raw,
                        TOOLS={'roll_dice': forbidden}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod['main'](['roll dice please']), 2)

    def test_empty_calls_refused(self):
        self.assertIsNone(self.mod['select_tool'](json.dumps(response([]))))

    def test_rejects_unknown_names_arguments_and_multiple_calls(self):
        bad = [[call('run_shell')], [call('get_system_status; id')],
               [call(arguments={'path': '/etc/shadow'})], [call(arguments='{}')],
               [call(arguments=[])], [call(), call('get_kernel_info')],
               [{'name': 'get_system_status'}], [dict(call(), command='id')]]
        for calls in bad:
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                self.mod['select_tool'](json.dumps(response(calls)))

    def test_rejects_malformed_error_and_suppressed_responses(self):
        values = ['not json', '[]', 'null', '{}', '{"success":true,"success":false}',
                  json.dumps(response([call()])) + '{}']
        for key, value in [('success', False), ('success', 1), ('error', 'broken'),
                           ('error_code', 'overflow'), ('confidence', 0.01),
                           ('confidence', True), ('confidence', '1'),
                           ('confidence', float('nan')), ('confidence', float('inf')),
                           ('confidence', 10 ** 1000),
                           ('type', 'error'), ('suppressed_calls', [call()])]:
            row = response([call()]); row[key] = value
            values.append(json.dumps(row))
        for raw in values:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.mod['select_tool'](raw)

    def test_no_tool_executes_until_decision_validates(self):
        globals_ = self.mod['main'].__globals__
        fake_tools = {name: lambda: self.fail('tool must not run') for name in self.mod['TOOLS']}
        for raw in [json.dumps(response([])), json.dumps(response([call(), call()]))]:
            with patch.dict(globals_, infer=lambda _: raw, TOOLS=fake_tools):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(self.mod['main'](['irrelevant request']), 2)

    def test_one_model_call_one_readonly_tool(self):
        invocations = []
        def infer(prompt):
            invocations.append(('model', prompt))
            return json.dumps(response([call('get_kernel_info')]))
        def tool():
            invocations.append(('tool',))
            return ['kernel: fixture']
        globals_ = self.mod['main'].__globals__
        with patch.dict(globals_, infer=infer, TOOLS={'get_kernel_info': tool}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(self.mod['main'](['which kernel?']), 0)
        self.assertEqual(invocations, [('model', 'which kernel?'), ('tool',)])
        self.assertEqual(out.getvalue(), 'Needle -> get_kernel_info({})\n\nPSTV:\n  kernel: fixture\n')

    def test_input_boundaries_do_not_run_model(self):
        def forbidden(_):
            self.fail('invalid input must not run model')
        with patch.dict(self.mod['main'].__globals__, infer=forbidden):
            for args in [[], [''], ['one', 'two'], ['x' * 513], ['hi\x00there']]:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(self.mod['main'](args), 2)

    def test_foreground_runtime_session_is_cleaned_up(self):
        from unittest.mock import MagicMock
        import signal
        import subprocess
        globals_ = self.mod['infer'].__globals__
        for outcome in [('{}', ''), subprocess.TimeoutExpired('needle', 180), KeyboardInterrupt()]:
            process = MagicMock(pid=12345, returncode=0)
            process.__enter__.return_value = process
            if isinstance(outcome, BaseException):
                process.communicate.side_effect = outcome
            else:
                process.communicate.return_value = outcome
            with patch.object(Path, 'is_file', return_value=True), \
                    patch('subprocess.Popen', return_value=process) as spawn, \
                    patch('os.killpg') as killpg:
                try:
                    self.mod['infer']('test')
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    pass
                self.assertTrue(spawn.call_args.kwargs.get('start_new_session'))
                killpg.assert_called_once_with(12345, signal.SIGKILL)
                process.wait.assert_called()

    def test_local_tools_return_fixed_readable_fields(self):
        self.assertTrue(self.mod['get_system_status']()[0].startswith('uptime: '))
        self.assertTrue(self.mod['get_storage_status']()[0].startswith('/: '))
        self.assertTrue(self.mod['get_kernel_info']()[0].startswith('kernel: '))


if __name__ == '__main__':
    unittest.main()
