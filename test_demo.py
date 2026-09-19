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
            self.assertEqual(self.mod['select_tool'](json.dumps(response([call(name)]))), name)

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
