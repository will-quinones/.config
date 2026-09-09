import unittest
from unittest.mock import patch, call
from test_restore_regressions import m


def saved(app='Docker Desktop', ident=1, space=2, bundle='com.electron.dockerdesktop'):
    return dict(id=ident, pid=10, app=app, bundle_id=bundle, space=space,
                title_digest=m.digest('Docker Desktop'),
                frame={'x': 0, 'y': 0, 'w': 1700, 'h': 1000})


def live(title='Docker Desktop', width=1700, height=1000):
    return dict(id=20, pid=30, app='Docker Desktop', bundle_id='com.electron.dockerdesktop',
                title=title, frame={'x': 0, 'y': 0, 'w': width, 'h': height},
                subrole='AXStandardWindow', **{'has-ax-reference': True, 'root-window': True})


class DockerReadinessTests(unittest.TestCase):
    def test_open_success_is_not_readiness_without_engine(self):
        old = saved()
        with patch.object(m.e, 'windows', return_value={20: live()}), \
             patch.object(m, 'with_bundles', side_effect=lambda ws: ws), \
             patch.object(m, 'docker_window_role', return_value='dashboard'), \
             patch.object(m, 'docker_engine_ready', return_value=False), \
             patch.object(m.time, 'monotonic', side_effect=[0, 0, 0, 2]), \
             patch.object(m.time, 'sleep'):
            result = m.wait_docker_ready(old, 1)
        self.assertFalse(result['ready'])
        self.assertIn('no terminó de iniciar', result['warnings'][0])

    def test_ready_requires_engine_and_main_window(self):
        old = saved()
        dashboard = live('Volumes - Docker Desktop', 856, 1083)
        with patch.object(m.e, 'windows', return_value={20: dashboard}), \
             patch.object(m, 'with_bundles', side_effect=lambda ws: ws), \
             patch.object(m, 'docker_window_role', return_value='dashboard'), \
             patch.object(m, 'docker_engine_ready', return_value=True), \
             patch.object(m.time, 'monotonic', side_effect=[0, 0]):
            result = m.wait_docker_ready(old, 10)
        self.assertTrue(result['ready'])

    def test_error_process_is_reported_without_restart(self):
        old = saved()
        # Title and geometry are deliberately indistinguishable from normal content.
        dialog = live('Docker Desktop', 800, 450)
        with patch.object(m.e, 'windows', return_value={20: dialog}), \
             patch.object(m, 'with_bundles', side_effect=lambda ws: ws), \
             patch.object(m, 'docker_window_role', return_value='error-dialog'), \
             patch.object(m, 'docker_engine_ready', return_value=False), \
             patch.object(m.time, 'monotonic', side_effect=[0, 0, 0, 1]), \
             patch.object(m.time, 'sleep'), \
             patch.object(m.subprocess, 'run') as run:
            result = m.wait_docker_ready(old, 10)
        self.assertFalse(result['ready'])
        self.assertIn('No se pulsó Reiniciar', result['warnings'][0])
        run.assert_not_called()

    def test_process_role_uses_explicit_docker_name(self):
        response = type('Result', (), {
            'returncode': 0,
            'stdout': '/Applications/Docker Desktop --reason=open-tray --name=dashboard\n'
        })()
        with patch.object(m.subprocess, 'run', return_value=response) as run:
            self.assertEqual(m.docker_window_role(live()), 'dashboard')
        self.assertEqual(run.call_args.args[0],
                         ['/bin/ps', '-p', '30', '-o', 'command='])

    def test_process_role_rejects_unnamed_docker_process(self):
        response = type('Result', (), {'returncode': 0, 'stdout': '/Applications/Docker Desktop\n'})()
        with patch.object(m.subprocess, 'run', return_value=response):
            self.assertIsNone(m.docker_window_role(live()))

    def test_dependents_open_only_after_docker_ready(self):
        docker, dbeaver = saved(), saved('DBeaver Community', 2, 2, 'org.jkiss.dbeaver.core.product')
        document = {'format': 1, 'state': {'windows': [docker, dbeaver]}}
        results = [
            {'opened': ['Docker Desktop'], 'warnings': []},
            {'opened': ['DBeaver Community'], 'warnings': []},
        ]
        with patch.object(m, 'open_missing_apps', side_effect=results) as opening, \
             patch.object(m, 'wait_docker_ready', return_value={'ready': True, 'warnings': []}), \
             patch.object(m.e, 'windows', return_value={}), \
             patch.object(m, 'with_bundles', side_effect=lambda ws: ws):
            result = m.open_docker_workspace(document, [], {}, 30)
        self.assertEqual(result['opened'], ['Docker Desktop', 'DBeaver Community'])
        self.assertEqual(opening.call_count, 2)
        self.assertEqual(opening.call_args_list[0].args[0]['state']['windows'], [docker])
        self.assertEqual(opening.call_args_list[1].args[0]['state']['windows'], [dbeaver])

    def test_dependents_are_not_opened_when_docker_fails(self):
        docker, dbeaver = saved(), saved('DBeaver Community', 2, 2, 'org.jkiss.dbeaver.core.product')
        document = {'format': 1, 'state': {'windows': [docker, dbeaver]}}
        with patch.object(m, 'open_missing_apps', return_value={'opened': ['Docker Desktop'], 'warnings': []}) as opening, \
             patch.object(m, 'wait_docker_ready', return_value={'ready': False, 'warnings': ['Docker failed']}):
            result = m.open_docker_workspace(document, [], {}, 30)
        self.assertEqual(opening.call_count, 1)
        self.assertEqual(result['blocked_window_ids'], [1, 2])
        self.assertEqual(result['warnings'], ['Docker failed'])

    def test_existing_dependent_is_reused(self):
        docker, dbeaver = saved(), saved('DBeaver Community', 2, 2, 'org.jkiss.dbeaver.core.product')
        existing = {**dbeaver, 'id': 22, 'pid': 32, 'title': 'DBeaver'}
        document = {'format': 1, 'state': {'windows': [docker, dbeaver]}}
        with patch.object(m, 'open_missing_apps', return_value={'opened': [], 'warnings': []}) as opening, \
             patch.object(m, 'wait_docker_ready', return_value={'ready': True, 'warnings': []}), \
             patch.object(m.e, 'windows', return_value={22: existing}), \
             patch.object(m, 'with_bundles', side_effect=lambda ws: ws):
            result = m.open_docker_workspace(document, [live(), existing], {}, 30)
        opening.assert_called_once()
        self.assertEqual(opening.call_args.args[0]['state']['windows'], [dbeaver])
        self.assertEqual(result['opened'], [])


if __name__ == '__main__':
    unittest.main()
