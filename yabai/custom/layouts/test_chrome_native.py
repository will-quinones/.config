import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from adapters import chrome


class NativeChromeTests(unittest.TestCase):
 def setUp(self):
  chrome.reset_cache()
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.state=self.root/'state';self.local=self.root/'Local State'
  self.local.write_text(json.dumps({'profile':{'last_used':'Profile 7'}}))
  self.patches=[patch.object(chrome,'STATE',self.state),patch.object(chrome,'LOCAL_STATE',self.local)]
  for item in self.patches:item.start();self.addCleanup(item.stop)
 def source(self, token='b'):
  return {'kind':'chrome-window','profile':'a'*32,'token':token*32,'tabs':[],'groups':[],'active':0}
 def test_old_extension_source_remains_compatible(self):
  self.assertEqual(chrome.key(self.source()),('chrome-window','b'*32))
  self.assertEqual(chrome.last_profile(),'Profile 7')
 def test_marker_assigns_saved_token_and_runtime_map(self):
  window={'id':9,'pid':44,'app':'Google Chrome','title':'YABAI_RESTORE_'+('b'*32)}
  result=chrome.identify([window],[self.source()])
  self.assertEqual(result[9]['token'],'b'*32)
  saved=json.loads(chrome.map_path().read_text())['windows'][0]
  self.assertEqual((saved['id'],saved['pid']),(9,44))
 def test_normal_save_gives_each_window_a_unique_identity(self):
  windows=[{'id':1,'pid':4,'app':'Google Chrome','title':'One'},
           {'id':2,'pid':4,'app':'Google Chrome','title':'Two'}]
  result=chrome.identify(windows)
  self.assertEqual(len({x['token'] for x in result.values()}),2)
 def test_concurrent_remember_keeps_every_window(self):
  threads=[threading.Thread(target=chrome.remember,args=(
   {'id':i,'pid':4,'app':'Google Chrome'},chrome.source_for(('%032x'%i)))) for i in range(1,4)]
  for thread in threads:thread.start()
  for thread in threads:thread.join()
  self.assertEqual(len(json.loads(chrome.map_path().read_text())['windows']),3)
 def test_launch_uses_last_profile_and_waits_for_its_marker(self):
  chrome_bin=self.root/'chrome';yabai=self.root/'yabai';chrome_bin.touch();yabai.touch()
  marker=self.root/'marker.html';marker.write_text('x')
  window={'id':12,'pid':88,'app':'Google Chrome','title':'YABAI_RESTORE_'+('b'*32)}
  with patch.object(chrome,'CHROME',chrome_bin),patch.object(chrome,'YABAI',yabai), \
       patch.object(chrome,'marker_page',return_value=marker),patch.object(chrome.subprocess,'Popen') as popen, \
       patch.object(chrome,'chrome_windows',side_effect=[[],[window]]),patch.object(chrome.time,'sleep'):
   result=chrome.launch(self.source())
  args=popen.call_args.args[0]
  self.assertIn('--profile-directory=Profile 7',args)
  self.assertIn('--new-window',args)
  self.assertEqual(result['window'],12)
  self.assertFalse(marker.exists())


if __name__=='__main__':unittest.main()
