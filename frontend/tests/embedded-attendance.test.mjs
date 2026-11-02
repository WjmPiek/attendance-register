import test from 'node:test';
import assert from 'node:assert/strict';
import {embeddedParentOrigin, notifyAttendanceParent} from '../src/embeddedAttendance.js';

test('integrated mode only communicates with the approved main site', () => {
 const messages=[];
 globalThis.window={parent:{postMessage:(...args)=>messages.push(args)},location:{search:'?embedded=1&parent_origin=https%3A%2F%2Fmartinssystem.co.za'}};
 try {
  assert.equal(embeddedParentOrigin(),'https://martinssystem.co.za');
  notifyAttendanceParent('martins:attendance-height',{height:800});
  assert.deepEqual(messages,[[{type:'martins:attendance-height',height:800},'https://martinssystem.co.za']]);
  for(const query of ['?embedded=1&parent_origin=https://evil.example','?embedded=1&parent_origin=javascript:bad','?parent_origin=https://martinssystem.co.za']){
   window.location.search=query;
   assert.equal(embeddedParentOrigin(),'');
  }
  window.location.search='?embedded=1&parent_origin=https://martinssystem.co.za';
  window.parent=window;
  assert.equal(embeddedParentOrigin(),'');
 } finally {delete globalThis.window;}
});
