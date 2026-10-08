// Read-only, fixed-source bridge. Calculations and notifications stay in the scanner.
const SOURCE = 'https://dobrybuk.pl';
const allowed = /^\/api\/odds\/(?:(?:config|events|bookmakers|sport-tabs)\/|events\/[0-9]+\/)$/;
const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
});
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
    if (request.method !== 'GET') return json({error: 'Tylko GET.'}, 405);
    if (url.pathname === '/' && !url.search) {
      return json({reader: 'arbi-source-reader', configured: typeof env.READER_TOKEN === 'string' && env.READER_TOKEN.length >= 32,
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
