// Fixed-source bridge and latest scan storage. Calculations and alerts stay in Actions.
const SOURCE = 'https://dobrybuk.pl';
const allowed = /^\/api\/odds\/(?:(?:config|events|bookmakers|sport-tabs)\/|events\/[0-9]+\/)$/;
const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
});
const cors = {'Access-Control-Allow-Origin': 'https://xlvlcl.github.io', 'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'If-None-Match', 'Access-Control-Expose-Headers': 'ETag', 'Access-Control-Max-Age': '86400', 'Cache-Control': 'no-store'};
const feedError = (data, status) => {const response = json(data, status);for (const [key, value] of Object.entries(cors)) response.headers.set(key, value);return response;};
function matches(actual, expected) {
  if (actual.length !== expected.length) return false;
  let difference = 0;
  for (let i = 0; i < expected.length; i++) difference |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  return difference === 0;
}
async function upstream(path) {
  return fetch(SOURCE + path, {
    method: 'GET', redirect: 'manual', signal: AbortSignal.timeout(9000),
    headers: {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'},
  });
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/feed/latest' && [...url.searchParams].every(([key, value]) => key === 't' && /^\d+$/.test(value))) {
      if (request.method === 'OPTIONS') return new Response(null, {status: 204, headers: cors});
      if (request.method === 'GET') {
        if (!env.DATA) return feedError({error: 'Dodaj binding KV o nazwie DATA.'}, 503);
        try {
          const {value, metadata} = await env.DATA.getWithMetadata('latest', {type: 'stream', cacheTtl: 30});
          if (!value) return feedError({error: 'Czekam na pierwszy zapis skanera.'}, 404);
          const etag = '"' + String(metadata?.attempt_at || 0) + '"';
          const headers = {...cors, 'Content-Type': 'application/json; charset=utf-8', 'ETag': etag};
          if (request.headers.get('If-None-Match') === etag) {
            await value.cancel();
            return new Response(null, {status: 304, headers});
          }
          return new Response(value, {headers});
        } catch {return feedError({error: 'Nie można odczytać wyniku skanera.'}, 503);}
      }
      if (request.method !== 'PUT') return feedError({error: 'Tylko GET lub PUT.'}, 405);
      if (typeof env.READER_TOKEN !== 'string' || env.READER_TOKEN.length < 32) return json({error: 'Brak sekretu czytnika.'}, 503);
      if (!matches(request.headers.get('Authorization') || '', 'Bearer ' + env.READER_TOKEN)) return json({error: 'Brak dostępu.'}, 401);
      if (!env.DATA) return json({error: 'Dodaj binding KV o nazwie DATA.'}, 503);
      const attempt = Number(request.headers.get('X-Arbi-Attempt'));
      const length = Number(request.headers.get('Content-Length'));
      if (!request.body || !Number.isFinite(attempt) || attempt <= 0 || attempt > Date.now()/1000 + 300 || !Number.isFinite(length) || length <= 0 || length > 8*1024*1024 || !request.headers.get('Content-Type')?.startsWith('application/json')) return json({error: 'Nieprawidłowy zapis wyniku.'}, 400);
      try {
        await env.DATA.put('latest', request.body, {expirationTtl: 86400, metadata: {attempt_at: attempt}});
        return json({ok: true});
      } catch {return json({error: 'Nie można zapisać wyniku skanera.'}, 503);}
    }
    if (request.method !== 'GET') return json({error: 'Tylko GET.'}, 405);
    if (url.pathname === '/' && !url.search) {
      return json({reader: 'arbi-source-reader', configured: typeof env.READER_TOKEN === 'string' && env.READER_TOKEN.length >= 32,
        feed_configured: Boolean(env.DATA),
        next: 'Dodaj URL i token do sekretów GitHub Actions, następnie uruchom skaner.'});
    }
    if (!allowed.test(url.pathname) || url.search) return json({error: 'Nieznana ścieżka.'}, 404);
    if (typeof env.READER_TOKEN !== 'string' || env.READER_TOKEN.length < 32) return json({error: 'Czytnik wymaga sekretu READER_TOKEN (minimum 32 znaki).'}, 503);
    if (!matches(request.headers.get('Authorization') || '', 'Bearer ' + env.READER_TOKEN)) return json({error: 'Brak dostępu.'}, 401);
    try {
      const response = await upstream(url.pathname);
      if (response.status !== 200) {
        await response.body?.cancel();
        return json({error: 'Źródło odrzuciło odczyt.', upstream_status: response.status}, response.status === 403 ? 403 : 502);
      }
      if (!(response.headers.get('Content-Type') || '').toLowerCase().includes('application/json')) {
        await response.body?.cancel();
        return json({error: 'Źródło nie zwróciło JSON.'}, 502);
      }
      // Stream the catalogue instead of parsing several MB on a free Worker.
      return new Response(response.body, {headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
    } catch {
      return json({error: 'Nie udało się połączyć ze źródłem w limicie czasu.'}, 502);
    }
  },
};
