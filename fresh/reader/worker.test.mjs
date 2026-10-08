import assert from 'node:assert/strict';
import {test} from 'node:test';
import worker from './worker.mjs';
const token = 'x'.repeat(32);
const env = {READER_TOKEN: token};
const request = (path, auth = true, method = 'GET') => new Request('https://reader.example' + path, {
  method, headers: auth ? {Authorization: 'Bearer ' + token} : {},
});
test('rate limiting preserves status and Retry-After for scanner backoff', async () => {
  const old=globalThis.fetch;
  globalThis.fetch=async()=>new Response('',{status:429,headers:{'Retry-After':'600'}});
  try {
    const response=await worker.fetch(request('/api/odds/config/'),env);
    assert.equal(response.status,429);assert.equal(response.headers.get('Retry-After'),'600');
    assert.equal((await response.json()).upstream_status,429);
  } finally {globalThis.fetch=old;}
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
test('feed is public with CORS, ETag and no HTTP cache; unchanged values return 304', async () => {
  let cancelled=false;
  const data={getWithMetadata:async(key,options)=>{
    assert.equal(key,'latest');assert.equal(options.type,'stream');assert.equal(options.cacheTtl,30);
    return {value:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('{"version":"NEW-1"}'));c.close();},cancel(){cancelled=true;}}),metadata:{attempt_at:123}};
  }};
  const response=await worker.fetch(request('/feed/latest?t=123',false),{...env,DATA:data});
  assert.equal(response.status,200);assert.equal(response.headers.get('Access-Control-Allow-Origin'),'https://xlvlcl.github.io');
  assert.equal(response.headers.get('Cache-Control'),'no-store');assert.equal(response.headers.get('ETag'),'"123"');
  assert.deepEqual(await response.json(),{version:'NEW-1'});
  const conditional=new Request('https://reader.example/feed/latest',{headers:{'If-None-Match':'"123"'}});
  assert.equal((await worker.fetch(conditional,{...env,DATA:data})).status,304);assert(cancelled);
  assert.equal((await worker.fetch(new Request('https://reader.example/feed/latest',{method:'OPTIONS'}),env)).status,204);
});
test('feed upload requires token, a bounded JSON stream and KV binding', async () => {
  let body='',metadata;
  const data={put:async(key,value,options)=>{assert.equal(key,'latest');body=await new Response(value).text();metadata=options.metadata;}};
  const upload=(auth=token,headers={})=>new Request('https://reader.example/feed/latest',{method:'PUT',body:'{}',headers:{
    Authorization:'Bearer '+auth,'Content-Type':'application/json','Content-Length':'2','X-Arbi-Attempt':'123',...headers}});
  assert.equal((await worker.fetch(upload('wrong'),{...env,DATA:data})).status,401);
  assert.equal((await worker.fetch(upload(),env)).status,503);
  assert.equal((await worker.fetch(upload(token,{'Content-Length':String(9*1024*1024)}),{...env,DATA:data})).status,400);
  assert.equal((await worker.fetch(upload(token,{'X-Arbi-Attempt':'NaN'}),{...env,DATA:data})).status,400);
  const response=await worker.fetch(upload(),{...env,DATA:data});
  assert.equal(response.status,200);assert.deepEqual(await response.json(),{ok:true});assert.equal(body,'{}');assert.equal(metadata.attempt_at,123);
});
test('missing feed and KV failures remain visible errors', async () => {
  assert.equal((await worker.fetch(request('/feed/latest',false),env)).status,503);
  assert.equal((await worker.fetch(request('/feed/latest',false),{...env,DATA:{getWithMetadata:async()=>({value:null})}})).status,404);
  assert.equal((await worker.fetch(request('/feed/latest',false),{...env,DATA:{getWithMetadata:async()=>{throw Error('quota');}}})).status,503);
});
