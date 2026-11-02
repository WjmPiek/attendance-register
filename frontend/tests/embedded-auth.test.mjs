import test from 'node:test';
import assert from 'node:assert/strict';
import {getAccessToken,setAccessToken,clearAccessToken} from '../src/api/authSession.js';
import {getStaffBranchId,setStaffBranchId} from '../src/api/branchContext.js';
import {getSessionValue,setSessionValue,removeSessionValue} from '../src/api/sessionContext.js';

test('a signed module session works when frame storage is blocked and clears on expiry', () => {
 Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw new Error('Storage blocked');}});
 Object.defineProperty(globalThis,'sessionStorage',{configurable:true,get(){throw new Error('Storage blocked');}});
 globalThis.window={dispatchEvent:()=>{}};
 globalThis.CustomEvent=class {constructor(type,options){this.type=type;this.detail=options.detail;}};
 try {
  assert.equal(getAccessToken(),null);
  setAccessToken('test-signed-launch-session');
  setStaffBranchId(27);
  setSessionValue('commissionFocusId',135);
  assert.equal(getAccessToken(),'test-signed-launch-session');
  assert.equal(getStaffBranchId(),'27');
  assert.equal(getSessionValue('commissionFocusId'),'135');
  removeSessionValue('commissionFocusId');
  assert.equal(getSessionValue('commissionFocusId'),null);
  clearAccessToken();
  assert.equal(getAccessToken(),null);
  assert.equal(getStaffBranchId(),'');
 }finally{delete globalThis.localStorage;delete globalThis.sessionStorage;delete globalThis.window;delete globalThis.CustomEvent;}
});

test('integrated sessions stay in their own frame instead of overwriting another branch tab', () => {
 const stored=new Map([['token','independent-standalone-session']]);
 globalThis.localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
 globalThis.window={parent:{},location:{search:'?embedded=1&parent_origin=https://martinssystem.co.za'}};
 try {
  setAccessToken('signed-branch-session');
  assert.equal(getAccessToken(),'signed-branch-session');
  assert.equal(stored.get('token'),'independent-standalone-session');
  setAccessToken(null);assert.equal(getAccessToken(),null);
 }finally{delete globalThis.localStorage;delete globalThis.window;}
});
