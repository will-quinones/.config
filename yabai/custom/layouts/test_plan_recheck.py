import unittest
from test_restore_regressions import m
class PlanRecheckTests(unittest.TestCase):
 def setUp(self):
  self.displays=[dict(index=1,uuid='screen',frame=dict(x=0,y=0,w=1000,h=800))]
  self.spaces=[dict(index=i,id=i,uuid=str(i),display=1,type='bsp',tree={'ids':[i]}) for i in (1,2)]
  self.saved=[dict(id=i,pid=i,app=app,space=i,display=1,title_digest=m.digest(app),**{'has-fullscreen-zoom':False,'has-parent-zoom':False}) for i,app in [(1,'A'),(2,'B')]]
  self.doc={'format':1,'state':{'windows':self.saved,'spaces':self.spaces},'displays':self.displays}
 def live(self,i,space=None):
  return {**self.saved[i-1],'title':self.saved[i-1]['app'],'subrole':'AXStandardWindow','space':space or i, 'is-floating':False,'split-child':'first_child','has-ax-reference':True,'root-window':True}
 def test_newly_identified_unselected_space_does_not_change_original_plan(self):
  _,old=m.plan(self.doc,[self.live(1)],self.spaces,self.displays)
  _,fresh=m.plan(self.doc,[self.live(1),self.live(2)],self.spaces,self.displays,allowed_spaces={1})
  self.assertEqual(old['restore'],fresh['restore']);self.assertEqual(fresh['skipped'],[])
 def test_extra_window_still_blocks_selected_destination(self):
  _,fresh=m.plan(self.doc,[self.live(1),self.live(2,space=1)],self.spaces,self.displays,allowed_spaces={1})
  self.assertEqual(fresh['restore'],[]);self.assertTrue(fresh['skipped'])
if __name__=='__main__':unittest.main()
