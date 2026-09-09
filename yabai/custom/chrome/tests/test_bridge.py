import base64
import hashlib
import io
import json
from pathlib import Path
import select
import subprocess
import sys
import threading
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
import bridge
ROOT=Path(__file__).resolve().parents[1]
class BridgeTests(unittest.TestCase):
 def test_roundtrip(self):
  value={'groups':['Clínica'],'tabs':[]}
  self.assertEqual(bridge.receive(io.BytesIO(bridge.pack(value)).read),value)
 def test_size_limit(self):
  with self.assertRaises(ValueError):bridge.pack('a'*bridge.LIMIT)
 def test_truncated(self):
  with self.assertRaises(EOFError):bridge.receive(io.BytesIO(b'\x01').read)
 def test_profile_path_traversal(self):
  with self.assertRaises(ValueError):bridge.address('../../other')
 def test_real_native_process_socket_roundtrip(self):
  manifest=json.loads((ROOT/'extension/manifest.json').read_text())
  digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
  ext=''.join(chr(ord('a')+int(c,16)) for c in digest)
  profile=uuid.uuid4().hex
  proc=subprocess.Popen([sys.executable,str(ROOT/'native/host.py'),'chrome-extension://'+ext+'/'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  def response():
   self.assertTrue(select.select([proc.stdout],[],[],5)[0]);return bridge.receive(proc.stdout.read)
  try:
   proc.stdin.write(bridge.pack({'type':'hello','profile':profile}));proc.stdin.flush()
   self.assertEqual(response(),{'type':'ready'})
   result=[]
   t=threading.Thread(target=lambda:result.append(bridge.request(profile,{'action':'snapshot'},timeout=5)))
   t.start();command=response();self.assertEqual(command['action'],'snapshot')
   proc.stdin.write(bridge.pack({'id':command['id'],'ok':True,'result':[]}));proc.stdin.flush()
   t.join(6);self.assertEqual(result,[[]])
   with self.assertRaises(RuntimeError): bridge.request(profile,{'action':'shell','command':'anything'},timeout=5)
  finally:
   proc.stdin.close();proc.wait(timeout=5)
   proc.stdout.close();err=proc.stderr.read().decode();proc.stderr.close()
   if proc.returncode: print('host diagnostic:',err)
   bridge.address(profile).unlink(missing_ok=True)
   bridge.address(profile).with_suffix('.lock').unlink(missing_ok=True)
if __name__=='__main__':unittest.main()
