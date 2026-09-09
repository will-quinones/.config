import io,importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
import bridge
spec=importlib.util.spec_from_file_location('native_host',Path(__file__).resolve().parents[1]/'native/host.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
class ProgressTests(unittest.TestCase):
 def test_progress_can_extend_total_past_30s(self):
  frames=[{'id':'x','type':'progress','stage':'tabs.create:done'}]*3+[{'id':'x','ok':True,'result':[]}]
  data=io.BytesIO(b''.join(bridge.pack(f) for f in frames));clock=[0]
  class Pipe:
   def fileno(self):return 42
  def read(fd,size):
   if size==4:clock[0]+=20
   return data.read(size)
  with patch.object(host.time,'monotonic',side_effect=lambda:clock[0]),patch.object(host.select,'select',return_value=([42],[],[])),patch.object(host.os,'read',side_effect=read):
   result=host.wait_response(Pipe(),'x','restore',lambda *args:None)
  self.assertTrue(result['ok']);self.assertGreater(clock[0],30)
 def test_no_progress_reports_last_stage(self):
  with patch.object(host.select,'select',return_value=([],[],[])):
   with self.assertRaisesRegex(TimeoutError,'request-sent'):
    host.wait_response(io.BytesIO(),'x','restore',lambda *args:None)
 def test_total_deadline_not_extended_forever(self):
  clock=iter([0,121])
  with patch.object(host.time,'monotonic',side_effect=lambda:next(clock)):
   with self.assertRaises(TimeoutError):host.wait_response(io.BytesIO(),'x','restore',lambda *args:None)
if __name__=='__main__':unittest.main()
