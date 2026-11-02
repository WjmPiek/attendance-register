import test from 'node:test';
import assert from 'node:assert/strict';
import { profileSwitchUrl, getProfileSwitchUrl, getMartinsReturnUrl } from '../src/martinsLaunch.js';

test('switch uses the signed main-system origin and returns to Attendance', () => {
 assert.equal(profileSwitchUrl('https://martinssystem.co.za/some/path?old=1'), 'https://martinssystem.co.za/profiles?module=attendance');
 assert.equal(profileSwitchUrl('http://localhost:5000/'), 'http://localhost:5000/profiles?module=attendance');
});
test('missing, malformed and unsafe origins use the production switcher', () => {
 for (const value of [undefined, '', 'broken', 'javascript:alert(1)', 'http://untrusted.example', 'https://[']) {
  assert.equal(profileSwitchUrl(value), 'https://martinssystem.co.za/profiles?module=attendance');
 }
 assert.equal(getProfileSwitchUrl(), 'https://martinssystem.co.za/profiles?module=attendance');
});

test('return link preserves the launched franchise destination and session context', () => {
 const values = new Map([['martins_attendance_return_url', 'https://martinssystem.co.za/performance/graphs?branch=7']]);
 globalThis.window = {sessionStorage: {getItem: key => values.get(key)}};
 try {
  assert.equal(getMartinsReturnUrl(), 'https://martinssystem.co.za/performance/graphs?branch=7');
  assert.equal(values.size, 1);
  for (const value of ['', 'broken', 'javascript:alert(1)', 'http://untrusted.example']) {
   values.set('martins_attendance_return_url', value);
   assert.equal(getMartinsReturnUrl(), 'https://martinssystem.co.za/');
  }
 } finally { delete globalThis.window; }
 assert.equal(getMartinsReturnUrl(), 'https://martinssystem.co.za/');
});
