import test from 'node:test';
import assert from 'node:assert/strict';
import { openModuleSwitcher } from '../src/moduleSwitcher.js';

test('popup stays in the module and accepts only its own trusted return', () => {
 const listeners=new Map(), navigations=[]; let opened,closed=false;
 const popup={focus(){},close(){closed=true},get closed(){return closed}};
 global.window={location:{href:'https://attendance.example/',origin:'https://attendance.example',assign:url=>navigations.push(url)},screenX:0,screenY:0,outerWidth:1200,outerHeight:900,open:(url)=>{opened=new URL(url);return popup},addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name),setInterval:()=>1,clearInterval:()=>{}};
 try {
  openModuleSwitcher('https://martinssystem.co.za/profiles?module=attendance');
  assert.equal(opened.searchParams.get('popup'),'1');
  assert.equal(opened.searchParams.get('opener_origin'),'https://attendance.example');
  assert.equal(navigations.length,0);
  const receive=listeners.get('message'), data={type:'martins:branch-switched',path:'/launch/attendance'};
  receive({source:popup,origin:'https://evil.example',data});
  receive({source:{},origin:opened.origin,data});
  receive({source:popup,origin:opened.origin,data:{...data,path:'/admin'}});
  assert.equal(navigations.length,0);
  receive({source:popup,origin:opened.origin,data});
  assert.deepEqual(navigations,['https://martinssystem.co.za/launch/attendance']);
  assert.equal(closed,true);
 } finally {delete global.window}
});

test('a blocked popup leaves the module open', () => {
 let message='';global.window={location:{href:'https://attendance.example/',origin:'https://attendance.example'},screenX:0,screenY:0,outerWidth:1200,outerHeight:900,open:()=>null,alert:value=>message=value};
 try {openModuleSwitcher('https://martinssystem.co.za/profiles?module=attendance');assert.match(message,/Allow popups/)} finally {delete global.window}
});
