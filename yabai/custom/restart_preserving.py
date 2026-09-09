#!/opt/homebrew/bin/python3
"""Conservative yabai restart. Never closes apps or creates/destroys Spaces.

Usage: restart_preserving.py inspect|capture|restart|restore [--state PATH]
Unknown/ambiguous layouts abort before restart. A checkpoint survives failure.
Only the same window ID + process ID may be restored. Native fullscreen and
minimized/hidden app windows are not rearranged. Capture briefly visits Spaces.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

YABAI = '/opt/homebrew/bin/yabai'
DEFAULT_STATE = Path.home() / '.local/state/yabai-preserving-restart/session.json'
TOL = 3.0

class RestoreError(RuntimeError):
    pass


def cmd(*args, timeout=12):
    r = subprocess.run([YABAI, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RestoreError(f"yabai {' '.join(map(str,args))}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def query(what):
    for attempt in range(8):
        try:
            return json.loads(cmd('-m', 'query', '--' + what))
        except json.JSONDecodeError:
            if attempt == 7: raise RestoreError('yabai repeatedly returned invalid JSON; operation stopped.')
            time.sleep(.2)


def windows():
    return {w['id']: w for w in query('windows')}


def win(wid, *args):
    return cmd('-m', 'window', wid, *args)


def bounds(items):
    frames = [x['frame'] for x in items]
    x = min(f['x'] for f in frames); y = min(f['y'] for f in frames)
    return dict(x=x, y=y, w=max(f['x']+f['w'] for f in frames)-x,
                h=max(f['y']+f['h'] for f in frames)-y)


def near(a, b, tolerance=TOL):
    return all(abs(a[k]-b[k]) <= tolerance for k in ('x','y','w','h'))


def managed(w, space):
    return (not w.get('is-floating') and not w.get('scratchpad')
            and not w.get('is-minimized') and not w.get('is-hidden')
            and not w.get('is-native-fullscreen')
            and (w.get('split-child','none') != 'none' or w.get('stack-index',0) > 0
                 or w['id'] in (space.get('first-window'),space.get('last-window'))))


def infer_tree(ws, layout='bsp'):
    """Infer a slicing tree, refusing overlaps not explicitly identified as stacks."""
    groups = []
    for w in sorted(ws, key=lambda x:x['id']):
        same = next((g for g in groups if near(g['frame'],w['frame'])),None)
        if same:
            if layout != 'stack' and not (w.get('stack-index',0)>0 and all(x.get('stack-index',0)>0 for x in same['members'])):
                raise RestoreError('Overlapping non-stack windows; cannot safely infer the BSP tree.')
            same['members'].append(w)
        else:
            groups.append({'frame':w['frame'], 'members':[w]})
    for g in groups:
        g['members'].sort(key=lambda w:(w.get('stack-index',0),w['id']))
        g['ids']=[w['id'] for w in g['members']]
    if layout == 'stack':
        if len(groups)>1:
            raise RestoreError('Stack layout reports inconsistent frames.')
    def leaf_hint(g,axis,side):
        w=g['members'][0]
        return (w.get('split-type','none') in ('none',axis)
                and w.get('split-child','none') in ('none',side))
    def build(gs):
        if len(gs)==1:
            return {'ids':gs[0]['ids'], 'frame':gs[0]['frame']}
        box=bounds(gs)
        for axis,pos,size in [('vertical','x','w'),('horizontal','y','h')]:
            ordered=sorted(gs,key=lambda g:g['frame'][pos])
            for k in range(1,len(ordered)):
                a,b=ordered[:k],ordered[k:]
                end=max(g['frame'][pos]+g['frame'][size] for g in a)
                start=min(g['frame'][pos] for g in b)
                if end>start+TOL: continue
                if len(a)==1 and not leaf_hint(a[0],axis,'first_child'): continue
                if len(b)==1 and not leaf_hint(b[0],axis,'second_child'): continue
                try:
                    left,right=build(a),build(b)
                except RestoreError:
                    continue
                ratio=((end+start)/2-box[pos])/box[size]
                if not 0.02 < ratio < 0.98: continue
                return dict(axis=axis,ratio=ratio,left=left,right=right,frame=box)
        raise RestoreError('BSP geometry cannot be reconstructed safely.')
    return build(groups) if groups else None


def leaves(tree):
    if not tree: return []
    if 'ids' in tree: return [tree]
    return leaves(tree['left'])+leaves(tree['right'])


def rep(tree):
    return leaves(tree)[0]['ids'][0]


def show_space(index):
    current=next((s for s in query('spaces') if s['index']==index),None)
    if not current: raise RestoreError(f'Space {index} disappeared.')
    if not current.get('has-focus'):
        cmd('-m','space','--focus',index)
    time.sleep(0.18)


def zoom_to(wid, saved):
    current=windows().get(wid)
    if not current or current['pid']!=saved['pid']: return
    for flag,toggle in [('has-fullscreen-zoom','zoom-fullscreen'),('has-parent-zoom','zoom-parent')]:
        current=windows()[wid]
        if current.get(flag,False)!=saved.get(flag,False):
            win(wid,'--toggle',toggle)


def restore_focus(state):
    for index in state.get('visible_spaces',[]):
        try: show_space(index)
        except RestoreError: pass
    if state.get('focused_space'):
        show_space(state['focused_space'])
    focus=state.get('focus')
    current=windows() if focus else {}
    if focus and focus in current:
        try:
            if not current[focus].get('has-focus'): win(focus,'--focus')
        except RestoreError: pass
    elif state.get('focused_space'):
        show_space(state['focused_space'])


def capture(only_space=None, only_spaces=None):
    spaces=query('spaces'); initial=windows()
    state={'version':1,'created':time.time(),'display_ids':[d['uuid'] for d in query('displays')],
           'visible_spaces':[s['index'] for s in spaces if s.get('is-visible')],
           'focused_space':next((s['index'] for s in spaces if s.get('has-focus')),None),
           'focus':next((w['id'] for w in initial.values() if w.get('has-focus')),None),
           'spaces':[], 'windows':[]}
    original_mouse=cmd('-m','config','mouse_follows_focus')
    cmd('-m','config','mouse_follows_focus','off')
    try:
        for space in spaces:
            if space.get('is-native-fullscreen') or not space['windows']: continue
            if only_space is not None and space['index'] != only_space: continue
            if only_spaces is not None and space['index'] not in only_spaces: continue
            show_space(space['index'])
            # A visible Space has fresh AX geometry, unlike inactive Space queries.
            fresh=windows()
            ws=[w for w in fresh.values() if w['space']==space['index']
                and w.get('root-window',True) and not w.get('is-native-fullscreen')]
            if any(not w.get('has-ax-reference',True) and managed(w,space) for w in ws):
                raise RestoreError(f"Space {space['index']} has inaccessible tiled windows.")
            ws=[w for w in ws if w.get('has-ax-reference',True)
                and (w.get('subrole')=='AXStandardWindow' or managed(w,space) or w.get('scratchpad'))]
            normal=[w for w in ws if managed(w,space)]
            try:
                for w in normal:
                    cleared={**w,'has-fullscreen-zoom':False,'has-parent-zoom':False}
                    zoom_to(w['id'],cleared)
                time.sleep(0.15)
                base=windows()
                tree=infer_tree([base[w['id']] for w in normal],space['type']) if space['type']!='float' else None
                entry={k:space[k] for k in ('index','id','uuid','display','type')}
                entry['tree']=tree
                entry['auto_balance']=cmd('-m','config','--space',space['index'],'auto_balance')
                state['spaces'].append(entry)
                for w in ws:
                    keys=('id','pid','app','space','display','frame','scratchpad','is-floating','is-minimized',
                          'is-hidden','is-visible','is-sticky','sub-layer','has-fullscreen-zoom','has-parent-zoom')
                    saved={k:w.get(k) for k in keys}
                    saved['kind']='tiled' if w in normal else 'free'
                    saved['base_frame']=base[w['id']]['frame']
                    state['windows'].append(saved)
            finally:
                for w in normal: zoom_to(w['id'],w)
    finally:
        restore_focus(state)
        cmd('-m','config','mouse_follows_focus',original_mouse)
    ids = [w['id'] for w in state['windows']]
    if len(ids) != len(set(ids)):
        raise RestoreError('A window moved during capture; please keep windows still and retry.')
    return state


def save(state,path):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_suffix('.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: json.dump(state,f,indent=2)
    os.replace(tmp,path)


def validate_identity(state, only_space=None, check_windows=True):
    if state.get('version')!=1: raise RestoreError('Unsupported checkpoint version.')
    if state['display_ids']!=[d['uuid'] for d in query('displays')]:
        raise RestoreError('Displays changed; restore aborted.')
    live=windows(); spaces={s['index']:s for s in query('spaces')}
    for s in state['spaces']:
        now=spaces.get(s['index'])
        if not now or (now['id'],now['uuid'],now['display'])!=(s['id'],s['uuid'],s['display']):
            raise RestoreError('Spaces changed; restore aborted.')
    for w in state['windows'] if check_windows else []:
        if only_space is not None and w['space']!=only_space: continue
        now=live.get(w['id'])
        # App display names can change (DBeaver Community -> DBeaver).
        # This checkpoint requires the same window ID and owning process ID.
        if not now or now['id']!=w['id'] or now['pid']!=w['pid']:
            raise RestoreError(f"Window {w['id']} ({w['app']}) closed or changed; checkpoint kept.")
    return live


def wait_ready():
    for _ in range(100):
        try:
            rs=json.loads(cmd('-m','rule','--list'))
            if any(r.get('label')=='native-stacking' for r in rs):
                # native-stacking is the last registered rule; --apply follows it.
                time.sleep(0.8)
                return
        except (RestoreError,json.JSONDecodeError): pass
        time.sleep(0.3)
    raise RestoreError('yabai configuration did not finish loading.')


def set_float(wid,yes):
    w=windows()[wid]
    if bool(w.get('is-floating'))!=yes: win(wid,'--toggle','float')


def build_tree(tree):
    if not tree or 'ids' in tree: return
    a,b=rep(tree['left']),rep(tree['right'])
    win(a,'--insert','east' if tree['axis']=='vertical' else 'south')
    set_float(b,False)
    win(b,'--ratio',f"abs:{tree['ratio']:.8f}")
    build_tree(tree['left']); build_tree(tree['right'])


def restore(state, verify_result=False):
    validate_identity(state, check_windows=False)
    mouse=cmd('-m','config','mouse_follows_focus')
    cmd('-m','config','mouse_follows_focus','off')
    try:
        saved_by_id={w['id']:w for w in state['windows']}
        # Reconcile scratchpad ownership before layout rules can pick another window.
        live=windows()
        owners={w.get('scratchpad'):w['id'] for w in state['windows'] if w.get('scratchpad')}
        for wid,w in live.items():
            label=w.get('scratchpad')
            if label in owners and owners[label]!=wid: win(wid,'--scratchpad')
        for label,wid in owners.items():
            if windows()[wid].get('scratchpad')!=label: win(wid,'--scratchpad',label)
        for space in state['spaces']:
            index=space['index']; show_space(index)
            for attempt in range(20):
                try:
                    live=validate_identity(state, only_space=index)
                    break
                except RestoreError:
                    if attempt==19: raise
                    time.sleep(.2)
            recorded=[w for w in state['windows'] if w['space']==index]
            active=[w for w in recorded if not w['is-minimized'] and not w['is-hidden']]
            target_ids={w['id'] for w in recorded}
            now_space=next(s for s in query('spaces') if s['index']==index)
            unknown=[w['id'] for w in live.values() if w['space']==index and w['id'] not in target_ids and managed(w,now_space)]
            if unknown: raise RestoreError(f'New tiled windows in Space {index}; will not rearrange them: {unknown}')
            # Scratchpads may follow the active Space during focus restoration.
            for w in active:
                if w.get('scratchpad') and live[w['id']]['space'] != index:
                    win(w['id'], '--space', index)
            live = windows()
            # Never silently move a normal window the user has moved meanwhile.
            if any(live[w['id']]['space']!=index for w in active):
                raise RestoreError(f'Windows moved between Spaces; restore stopped at Space {index}.')
            for w in active:
                if w['kind']=='tiled': zoom_to(w['id'],{**w,'has-fullscreen-zoom':False,'has-parent-zoom':False})
                if w['kind']=='tiled' or w['is-floating']: set_float(w['id'],True)
            cmd('-m','config','--space',index,'auto_balance','off')
            try:
                cmd('-m','space',index,'--layout',space['type'])
                tree=space['tree']
                if tree:
                    set_float(rep(tree),False)
                    build_tree(tree)
                    for group in leaves(tree):
                        for wid in group['ids'][1:]:
                            win(group['ids'][0],'--stack',wid)
                for w in active:
                    if w['kind']=='free' and w['is-floating']:
                        f=w['frame']
                        win(w['id'],'--resize',f"abs:{round(f['w'])}:{round(f['h'])}")
                        win(w['id'],'--move',f"abs:{round(f['x'])}:{round(f['y'])}")
                    if w.get('sub-layer') in ('normal','above','below'):
                        win(w['id'],'--sub-layer',w['sub-layer'])
                for w in active:
                    if w['kind']=='tiled': zoom_to(w['id'],w)
                # Restore scratchpad shown/hidden state only while its Space is visible.
                for w in active:
                    if w.get('scratchpad'):
                        current=windows()[w['id']]
                        if bool(current.get('is-visible'))!=bool(w['is-visible']):
                            win(w['id'],'--toggle',w['scratchpad'])
            finally:
                cmd('-m','config','--space',index,'auto_balance',space['auto_balance'])
            if verify_result:
                verify_current_space(state, space)
    finally:
        restore_focus(state)
        cmd('-m','config','mouse_follows_focus',mouse)


def summary(state):
    return {'spaces':len(state['spaces']),'windows':len(state['windows']),
            'stacks':[g['ids'] for s in state['spaces'] for g in leaves(s['tree']) if len(g['ids'])>1],
            'zoomed':[w['id'] for w in state['windows'] if w.get('has-fullscreen-zoom') or w.get('has-parent-zoom')],
            'scratchpads':[w['scratchpad'] for w in state['windows'] if w.get('scratchpad')]}


def verify_current_space(state, space):
    """Verify while the restored Space is already visible; do not change focus."""
    live=validate_identity(state, only_space=space['index'])
    failures=[]
    for w in state['windows']:
        if w['space']!=space['index'] or w['is-minimized'] or w['is-hidden']: continue
        now=live[w['id']]
        for flag in ('has-fullscreen-zoom','has-parent-zoom','scratchpad'):
            if now.get(flag)!=w.get(flag): failures.append(f"{w['app']} {w['id']}: {flag}")
        if (w['kind']=='tiled' or w['is-floating']) and not near(now['frame'],w['frame'],6):
            failures.append(f"{w['app']} {w['id']}: frame")
    for g in leaves(space['tree']):
        if len(g['ids'])>1:
            members=[live[i] for i in g['ids']]
            if not all(w.get('stack-index',0)>0 for w in members) or not all(near(members[0]['frame'],w['frame']) for w in members):
                failures.append(f"Stack {g['ids']}")
    if failures: raise RestoreError('Restore differs from checkpoint: '+', '.join(failures))


def verify(state):
    # Standalone verification remains available for diagnostics/tests.
    validate_identity(state, check_windows=False)
    try:
        for space in state['spaces']:
            show_space(space['index'])
            verify_current_space(state, space)
    finally:
        restore_focus(state)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['inspect','capture','restart','restore'])
    p.add_argument('--state',type=Path,default=DEFAULT_STATE)
    args=p.parse_args()
    args.state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(args.state.with_suffix('.lock'),'w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RestoreError('Another preserving restart is already running.')
        if args.action=='inspect':
            print(json.dumps({'spaces':query('spaces'),'windows':len(windows())},indent=2)); return
        if args.action=='restart' and args.state.exists():
            previous=json.loads(args.state.read_text())
            if previous.get('phase') in ('restarting','restoring'):
                raise RestoreError('An earlier restore is pending. Run restore first; checkpoint will not be overwritten.')
        if args.action=='restore':
            state=json.loads(args.state.read_text()); restore(state, verify_result=True)
            state['phase']='complete'; save(state,args.state)
        else:
            state=capture(); save(state,args.state)
            print(json.dumps(summary(state),indent=2),flush=True)
            if args.action=='restart':
                state['phase']='restarting'; save(state,args.state)
                cmd('--restart-service',timeout=45)
                wait_ready()
                state['phase']='restoring'; save(state,args.state)
                restore(state, verify_result=True)
                state['phase']='complete'; save(state,args.state)
        print('OK: '+args.action,flush=True)

if __name__=='__main__':
    try: main()
    except (RestoreError,subprocess.TimeoutExpired,OSError,ValueError) as e:
        print('ERROR: '+str(e),file=sys.stderr)
        sys.exit(1)
