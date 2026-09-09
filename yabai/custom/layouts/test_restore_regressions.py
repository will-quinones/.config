"""Pure regression tests: never query/mutate the user's desktop."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('desktop_layout',Path(__file__).with_name('desktop-layout.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class WindowMatchingTests(unittest.TestCase):
    def window(self, wid, title):
        return dict(id=wid, pid=10, app='DBeaver Community', title=title,
                    subrole='AXStandardWindow', **{'root-window':True})
    def test_dbeaver_tip_is_not_main_window(self):
        old=dict(id=1, app='DBeaver Community', title_digest=m.digest('old title'))
        live=[self.window(2,'DBeaver 26.2.0'),self.window(3,'Tip of the day')]
        matches,reasons=m.match([old],live)
        self.assertEqual(matches[1]['id'],2);self.assertFalse(reasons)
    def test_two_real_windows_remain_ambiguous(self):
        old=dict(id=1, app='DBeaver Community', title_digest=m.digest('old title'))
        matches,reasons=m.match([old],[self.window(2,'main1'),self.window(3,'main2')])
        self.assertFalse(matches);self.assertIn(1,reasons)
    def test_other_apps_not_excluded_by_title(self):
        w=self.window(3,'Tip of the day');w['app']='Code'
        self.assertTrue(m.eligible(w))

class FloatingResizeTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(id=197,pid=20,space=7,app='qBittorrent',frame=dict(x=165,y=137,w=1087,h=683))
    def live(self, correct=False, **changes):
        w={**self.saved, 'is-floating':True}
        if not correct:w['frame']=dict(x=165,y=137,w=861,h=539)
        w.update(changes);return {197:w}
    def test_delayed_resize_retried_without_focus(self):
        with patch.object(m.e,'windows',side_effect=[self.live(),self.live(),self.live(True),self.live(True)]),patch.object(m.e,'win') as win,patch.object(m.e.time,'sleep'):
            m.e.restore_float_frame(self.saved)
        self.assertEqual([c.args[1] for c in win.call_args_list],['--move','--resize']*2)
    def test_permanent_mismatch_is_error(self):
        with patch.object(m.e,'windows',return_value=self.live()),patch.object(m.e,'win'),patch.object(m.e.time,'sleep'):
            with self.assertRaisesRegex(m.ERROR,'frame did not settle'):m.e.restore_float_frame(self.saved,attempts=3)
    def test_changed_pid_stops_before_mutation(self):
        with patch.object(m.e,'windows',return_value=self.live(pid=999)),patch.object(m.e,'win') as win:
            with self.assertRaises(m.ERROR):m.e.restore_float_frame(self.saved)
            win.assert_not_called()
    def test_changed_space_stops_before_mutation(self):
        with patch.object(m.e,'windows',return_value=self.live(space=1)),patch.object(m.e,'win') as win:
            with self.assertRaises(m.ERROR):m.e.restore_float_frame(self.saved)
            win.assert_not_called()

class RecoveryNoticeTests(unittest.TestCase):
    def test_geometry_fallback_is_silent_but_saved(self):
        with patch.object(m,'inventory',return_value=([],[],[])), patch.object(m.e,'capture',side_effect=m.ERROR('BSP geometry cannot be reconstructed safely.')), patch.object(m.e,'save') as save, patch('builtins.print') as output:
            m.create_recovery()
            self.assertEqual(save.call_count,2)
            self.assertEqual(save.call_args.args[0]['format'],'diagnostic-only')
            self.assertIn('reason',save.call_args.args[0])
            output.assert_not_called()
    def test_other_errors_still_propagate(self):
        with patch.object(m,'inventory',return_value=([],[],[])), patch.object(m.e,'capture',side_effect=m.ERROR('Window disappeared')), patch.object(m.e,'save'):
            with self.assertRaisesRegex(m.ERROR,'Window disappeared'):
                m.create_recovery()

if __name__=='__main__': unittest.main()
