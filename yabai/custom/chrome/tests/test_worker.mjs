import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
if (!globalThis.crypto) globalThis.crypto=webcrypto;
const profile='a'.repeat(32),local={profile},session={};
let disconnect, sentAlarms=[], listener, sent=[], winId=0,tabId=0,groupId=0,windows=[],groups=[],calls=[];
const event=()=>({addListener(){}});
function area(data){return {async get(k){return {[k]:data[k]};},async set(v){Object.assign(data,structuredClone(v));}};}
function tab(id){return windows.flatMap(w=>w.tabs).find(t=>t.id===id);}
globalThis.chrome={
 storage:{local:area(local),session:area(session)},
 runtime:{onStartup:event(),onInstalled:event(),connectNative(){return {postMessage(m){sent.push(m);},onDisconnect:{addListener(fn){disconnect=fn;}},onMessage:{addListener(fn){listener=fn;}}};}},
 action:{onClicked:event(),async setBadgeText(){},async setTitle(){}},alarms:{onAlarm:event(),create(name,options){sentAlarms.push([name,options]);}},
 windows:{async getAll(){return structuredClone(windows);},async create(options){
  calls.push(['createWindow',options]);const w={id:++winId,incognito:false,left:0,top:0,width:100,height:100,
   tabs:[{id:++tabId,index:0,url:'about:blank',title:'blank',pinned:false,active:true,groupId:-1}]};windows.push(w);return structuredClone(w);}},
 tabs:{async update(id,options){calls.push(['updateTab',id,options]);const t=tab(id);Object.assign(t,options);return structuredClone(t);},
  async create(options){calls.push(['createTab',options]);const w=windows.find(w=>w.id===options.windowId);const t={id:++tabId,index:options.index,url:options.url,pinned:options.pinned,active:options.active,groupId:-1};w.tabs.push(t);return structuredClone(t);},
  async group(options){const id=++groupId;groups.push({id,windowId:options.createProperties.windowId,title:'',color:'grey',collapsed:false});options.tabIds.forEach(t=>tab(t).groupId=id);return id;},
  async query(options){return structuredClone(windows.find(w=>w.id===options.windowId).tabs);}},
 tabGroups:{async query(options){if(!windows.length) throw Error('No current window');assert.ok(Number.isInteger(options.windowId));return structuredClone(groups.filter(g=>g.windowId===options.windowId));},async update(id,options){Object.assign(groups.find(g=>g.id===id),options);}},
};
await import('../extension/worker.js');
await new Promise(r=>setTimeout(r,0));
assert.equal(sent[0].type,'hello');
async function request(action,more={}){const id=String(sent.length);await listener({type:'request',action,id,...more});const result=sent.at(-1);assert.equal(result.id,id);return result;}
session.windows={999:{token:'old',status:'complete'}};
const empty=await request('snapshot');assert.equal(empty.ok,true);assert.deepEqual(empty.result,[]);assert.deepEqual(session.windows,{});assert.equal(calls.length,0);
const source={kind:'chrome-window',profile,token:'b'.repeat(32),active:1,
 tabs:[{url:'https://example.com/a',pinned:true,group:-1},{url:'https://example.com/b',pinned:false,group:0},{url:'https://example.com/c',pinned:false,group:1}],
 groups:[{title:'DEV',color:'blue',collapsed:false},{title:'LOCAL',color:'red',collapsed:true}]};
let result=await request('restore',{source});assert.equal(result.ok,true);assert.equal(windows.length,1);
assert.equal(calls.find(c=>c[0]==='createWindow')[1].focused,false);
assert.equal(calls.filter(c=>c[0]==='createTab').every(c=>c[1].active===false),true);
assert.equal(groups[1].collapsed,true);assert.equal(groups[0].title,'DEV');
result=await request('snapshot',{hints:[source]});assert.equal(result.result[0].source.token,source.token);
assert.equal(result.result[0].source.groups.length,2);
const before=calls.length;result=await request('restore',{source});assert.equal(result.result.reused,true);assert.equal(calls.length,before);
result=await request('restore',{source:{...source,token:'c'.repeat(32),tabs:[...source.tabs,{url:'https://other.com',pinned:false,group:-1}]}});
assert.equal(result.ok,false);assert.equal(windows.length,1);
result=await request('restore',{source:{...source,token:'d'.repeat(32),tabs:[{url:'javascript:alert(1)',pinned:false,group:-1}],groups:[],active:0}});
assert.equal(result.ok,false);assert.equal(windows.length,1);
// Simulated browser reboot: runtime window IDs/tokens change; content hints recover identity.
session.windows={};windows[0].id=91;groups.forEach(g=>g.windowId=91);
result=await request('snapshot',{hints:[source]});assert.equal(result.result[0].source.token,source.token);
// A read-only health check before hints must not prevent subsequent identification.
session.windows={};await request('snapshot');
result=await request('snapshot',{hints:[source]});assert.equal(result.result[0].source.token,source.token);
console.log('Extensión: reapertura, grupos, no foco, no duplicados, URLs seguras y cambio de IDs correctos');

// Reconnect promptly, back off repeated failures, reset only on host ready.
const realTimeout=globalThis.setTimeout, realClear=globalThis.clearTimeout;
let scheduled;
try {
 globalThis.setTimeout=(fn,delay)=>{scheduled={fn,delay};return 123;};
 globalThis.clearTimeout=()=>{};
 disconnect();assert.equal(scheduled.delay,1000);
 assert.equal(sentAlarms.at(-1)[1].delayInMinutes,.5);
 scheduled.fn();await new Promise(r=>realTimeout(r,0));
 disconnect();assert.equal(scheduled.delay,2000);
 scheduled.fn();await new Promise(r=>realTimeout(r,0));
 await listener({type:'ready'});
 disconnect();assert.equal(scheduled.delay,1000);
 console.log('Reconexión rápida, backoff y reinicio tras ready correctos');
} finally {globalThis.setTimeout=realTimeout;globalThis.clearTimeout=realClear;}
