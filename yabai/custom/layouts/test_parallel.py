import unittest, threading, time, tempfile
from pathlib import Path
from unittest.mock import patch
from test_restore_regressions import m

class ParallelTests(unittest.TestCase):
 def test_three_concurrent_never_more(self):
  lock=threading.Lock();active=0;peak=0
  barrier=threading.Barrier(3)
  def job():
   nonlocal active,peak
   with lock:active+=1;peak=max(peak,active)
   barrier.wait(timeout=3)
   with lock:active-=1
   return {'opened':['app']}
  result=m.run_open_jobs([(str(i),job) for i in range(6)],3,lambda *args:None)
  self.assertEqual(peak,3);self.assertEqual(len(result),6)
 def test_failed_job_does_not_stop_other_jobs(self):
  def failed():raise RuntimeError('failed')
  results=m.run_open_jobs([('bad',failed),('good',lambda:{'opened':['good']})],2,lambda *args:None)
  self.assertTrue(any(x.get('opened')==['good'] for x in results))
  self.assertTrue(any(x.get('warnings') for x in results))
 def test_groups_chrome_profile_serially_and_launches_generic_apps(self):
  src=lambda token:dict(kind='chrome-window',profile='a'*32,token=token*32)
  ws=[dict(id=1,app='Google Chrome',space=4,reopen=src('b')),dict(id=2,app='Google Chrome',space=10,reopen=src('c')),dict(id=3,app='Docker Desktop',space=2)]
  document={'format':1,'state':{'windows':ws}}
  def jobs(items, limit, report):
   self.assertEqual(limit,3);self.assertEqual([x[0] for x in items],['Docker Desktop','Chrome'])
   return [operation() for _,operation in items]
  with patch.object(m,'run_open_jobs',side_effect=jobs),patch.object(m,'progress'),patch.object(m,'open_docker_workspace',return_value={'opened':['Docker Desktop'],'blocked_window_ids':[]}),patch.object(m,'open_missing_apps') as generic,patch.object(m,'reopen_windows',return_value={'reopened_windows':['Chrome']}) as reopen,patch.object(m.e,'windows',return_value={}),patch.object(m,'with_bundles',return_value=[]),patch.object(m.adapters,'annotate',return_value=([],[])),patch.object(m,'match',return_value=({1:1,2:2,3:3},{})),patch.object(m.time,'sleep'):
   result=m.open_parallel(document,[],{},1)
   generic.assert_not_called()
   self.assertFalse(reopen.call_args.kwargs['wait_ready'])
   self.assertEqual(len(reopen.call_args.args[0]['state']['windows']),2)
   self.assertEqual(result['opened'],['Docker Desktop'])
 def test_progress_written_immediately(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'DATA',Path(tmp)):
   m.progress('Esperando Chrome',time.monotonic())
   self.assertIn('Esperando Chrome',(Path(tmp)/'run.log').read_text())
if __name__=='__main__':unittest.main()
