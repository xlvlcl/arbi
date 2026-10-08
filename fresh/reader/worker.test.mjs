import assert from 'node:assert/strict';
import {test} from 'node:test';
import worker from './worker.mjs';
const token = 'x'.repeat(32);
const env = {READER_TOKEN: token};
const request = (path, auth = true, method = 'GET') => new Request('https://reader.example' + path, {
  method, headers: auth ? {Authorization: 'Bearer ' + token} : {},
});
test('fixed routes and authentication gate all source reads', async () => {
  const old = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {calls++; return new Response('{}', {headers: {'Content-Type': 'application/json'}});};
  try {
    for (const path of ['/api/odds/events/1/?url=https://evil.example', '/api/odds/other/', '/unknown/']) {
      assert.equal((await worker.fetch(request(path), env)).status, 404);
    }
    assert.equal((await worker.fetch(request('/api/odds/config/', false), env)).status, 401);
    assert.equal((await worker.fetch(request('/api/odds/config/'), {})).status, 503);
    assert.equal((await worker.fetch(request('/api/odds/config/', true, 'POST'), env)).status, 405);
    assert.equal(calls, 0);
  } finally {globalThis.fetch = old;}
});
test('streams JSON from fixed source and never forwards reader credentials', async () => {
  const old = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'https://dobrybuk.pl/api/odds/events/12/');
    assert.equal(options.redirect, 'manual');
    assert.equal(options.headers.Authorization, undefined);
    return new Response('{"id":12}', {headers: {'Content-Type': 'application/json'}});
  };
  try {
    const response = await worker.fetch(request('/api/odds/events/12/'), env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.deepEqual(await response.json(), {id: 12});
  } finally {globalThis.fetch = old;}
});
test('blocked source, redirects, HTML and transport failure remain errors', async () => {
  const old = globalThis.fetch;
  try {
    for (const [response, expected] of [
      [new Response('blocked', {status: 403}), 403],
      [new Response('', {status: 302, headers: {Location: 'https://elsewhere.example'}}), 502],
      [new Response('<html>challenge</html>', {headers: {'Content-Type': 'text/html'}}), 502],
    ]) {
      globalThis.fetch = async () => response;
      assert.equal((await worker.fetch(request('/api/odds/config/'), env)).status, expected);
    }
    globalThis.fetch = async () => {throw new Error('timeout');};
    assert.equal((await worker.fetch(request('/api/odds/config/'), env)).status, 502);
  } finally {globalThis.fetch = old;}
});
test('root confirms only configuration and does not request source', async () => {
  const old = globalThis.fetch;
  globalThis.fetch = async () => {throw new Error('unexpected source request');};
  try {
    const data = await (await worker.fetch(request('/', false), env)).json();
    assert.equal(data.configured, true);
    assert.equal(data.source_available, undefined);
  } finally {globalThis.fetch = old;}
});
