import assert from 'node:assert/strict';
import {signature,validate,overlaps} from '../extension/model.js';
const p='a'.repeat(32),token='b'.repeat(32);
const s={kind:'chrome-window',profile:p,token,active:0,tabs:[{url:'https://example.com',pinned:false,group:0}],groups:[{title:'DEV',color:'blue',collapsed:false}]};
assert.equal(validate(s,p),s);
assert.equal(signature(s),signature({...s,active:0,token:'c'.repeat(32),groups:[{...s.groups[0],collapsed:true}]}));
for (const url of ['javascript:alert(1)','file:///etc/passwd','data:text/html,hello','chrome://settings/'])
 assert.throws(()=>validate({...s,tabs:[{url,pinned:false,group:0}]},p));
assert.throws(()=>validate(s,'c'.repeat(32)));
assert.throws(()=>validate({...s,tabs:[{...s.tabs[0],pinned:true}]},p));
assert.throws(()=>validate({...s,active:4},p));
assert.throws(()=>validate({...s,groups:[{...s.groups[0],color:'unknown'}]},p));
assert.equal(overlaps(s,s),true);
assert.equal(overlaps({...s,tabs:[{url:'chrome://newtab/'}]}, {...s,tabs:[{url:'chrome://newtab/'}]}),false);
console.log('11 comprobaciones de modelo Chrome correctas');
