import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'layouts'))
from adapters import chrome

class BootstrapTests(unittest.TestCase):
 def source(self, directory='Profile 1'):
  return {'kind':'chrome-window','profile':'a'*32,'token':'b'*32,'profile_directory':directory}
 def test_disconnected_starts_profile_without_window(self):
  with patch.object(chrome.bridge,'request',side_effect=[FileNotFoundError(),[],{'reused':False}]) as request,patch.object(chrome.subprocess,'Popen') as launch:
   chrome.launch(self.source())
   args=launch.call_args.args[0]
   self.assertIn('--no-startup-window',args)
   self.assertIn('--profile-directory=Profile 1',args)
   self.assertEqual(request.call_args.args[1]['action'],'restore')
   self.assertEqual(launch.call_count,1)
 def test_connected_never_starts_browser(self):
  with patch.object(chrome.bridge,'request',side_effect=[[],{}]),patch.object(chrome.subprocess,'Popen') as launch:
   chrome.launch(self.source());launch.assert_not_called()
 def test_unknown_profile_fails_without_opening_default(self):
  for directory in (None,'../../Default','Profile 1 --new-window'):
   with patch.object(chrome.bridge,'request',side_effect=FileNotFoundError()),patch.object(chrome.subprocess,'Popen') as launch,patch.object(chrome.subprocess,'run') as run:
    with self.assertRaises(RuntimeError):chrome.launch(self.source(directory))
    launch.assert_not_called();run.assert_not_called()
 def test_restore_timeout_not_retried(self):
  with patch.object(chrome.bridge,'request',side_effect=[FileNotFoundError(),[],TimeoutError()]) as request,patch.object(chrome.subprocess,'Popen') as launch:
   with self.assertRaises(TimeoutError): chrome.launch(self.source())
   self.assertEqual(request.call_count,3);self.assertEqual(launch.call_count,1)
if __name__=='__main__':unittest.main()
