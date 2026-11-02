import test from 'node:test';
import assert from 'node:assert/strict';
import {getAccessToken,setAccessToken,clearAccessToken} from '../src/api/authSession.js';

test('a signed module session works when frame storage is blocked and clears on expiry', () => {
 Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw new Error('Storage blocked');}});
 globalThis.window={dispatchEvent:()=>{}};
 globalThis.CustomEvent=class {constructor(type,options){this.type=type;this.detail=options.detail;}};
 try {
  assert.equal(getAccessToken(),null);
  setAccessToken('test-signed-launch-session');
  assert.equal(getAccessToken(),'test-signed-launch-session');
  clearAccessToken();
  assert.equal(getAccessToken(),null);
 }finally{delete globalThis.localStorage;delete globalThis.window;delete globalThis.CustomEvent;}
});
