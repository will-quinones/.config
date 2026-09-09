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
 def test_reconnect_after_old_30_second_deadline(self):
  with patch.object(chrome.bridge,'request',side_effect=[FileNotFoundError(),FileNotFoundError(),[],{}]) as request,patch.object(chrome.subprocess,'Popen'),patch.object(chrome.time,'monotonic',side_effect=[0,0,0,40,40,40]),patch.object(chrome.time,'sleep'):
   chrome.launch(self.source())
   self.assertEqual(request.call_args.args[1]['action'],'restore')
   self.assertEqual(sum(c.args[1]['action']=='restore' for c in request.call_args_list),1)
 def test_native_read_timeout_can_reconnect(self):
  err=RuntimeError('Chrome no respondió; no se reintentó la apertura')
  with patch.object(chrome.bridge,'request',side_effect=[err,[],{}]) as request,patch.object(chrome.subprocess,'Popen'):
   chrome.launch(self.source())
   self.assertEqual(request.call_count,3)
 def test_runtime_mutation_error_never_retried(self):
  with patch.object(chrome.bridge,'request',side_effect=[[],RuntimeError('Chrome no respondió; no se reintentó la apertura')]) as request,patch.object(chrome.subprocess,'Popen') as launch:
   with self.assertRaises(RuntimeError):chrome.launch(self.source())
   self.assertEqual(request.call_count,2);launch.assert_not_called()
 def test_shared_profile_ready_once(self):
  with patch.object(chrome,'await_profile') as ready,patch.object(chrome.bridge,'request',return_value={}):
   cache={};chrome.launch(self.source(),readiness=cache);chrome.launch({**self.source(),'token':'c'*32},readiness=cache)
   self.assertEqual(ready.call_count,1)
 def test_failed_profile_not_retried_for_second_window(self):
  with patch.object(chrome,'await_profile',side_effect=TimeoutError('late')) as ready,patch.object(chrome.bridge,'request') as request:
   cache={}
   for token in ('b','c'):
    with self.assertRaises((OSError,RuntimeError)):chrome.launch({**self.source(),'token':token*32},readiness=cache)
   self.assertEqual(ready.call_count,1);request.assert_not_called()
if __name__=='__main__':unittest.main()
