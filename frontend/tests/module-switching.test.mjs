import test from 'node:test';
import assert from 'node:assert/strict';
import { profileSwitchUrl, getProfileSwitchUrl } from '../src/martinsLaunch.js';

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
