const BOOK_META={
  Betclic:{abbr:"BC",url:"https://www.betclic.pl/"},
  Fortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},eFortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},
  Superbet:{abbr:"SB",url:"https://superbet.pl/"},STS:{abbr:"STS",url:"https://www.sts.pl/"},
  Forbet:{abbr:"FB",url:"https://www.iforbet.pl/"},LVBet:{abbr:"LV",url:"https://lvbet.pl/"},
  ETOTO:{abbr:"ET",url:"https://www.etoto.pl/"},eToto:{abbr:"ET",url:"https://www.etoto.pl/"},Etoto:{abbr:"ET",url:"https://www.etoto.pl/"},
  Betfan:{abbr:"BF",url:"https://betfan.pl/"},BETFAN:{abbr:"BF",url:"https://betfan.pl/"},
  Fuksiarz:{abbr:"FU",url:"https://fuksiarz.pl/"},
  TotalBet:{abbr:"TB",url:"https://totalbet.pl/"},Totalbet:{abbr:"TB",url:"https://totalbet.pl/"},"Total Bet":{abbr:"TB",url:"https://totalbet.pl/"},
  Betters:{abbr:"BE",url:"https://betters.pl/"},LeBull:{abbr:"LB",url:"https://lebull.pl/"},
  AdmiralBet:{abbr:"AB",url:"https://admiralbet.pl/"},BetSport:{abbr:"BS",url:"https://betsport.pl/"},Betsport:{abbr:"BS",url:"https://betsport.pl/"},
  ComeOn:{abbr:"CO",url:"https://www.comeon.com/pl"},PZBuk:{abbr:"PZ",url:"https://pzbuk.pl/"}
};

const fmt=n=>new Intl.NumberFormat("pl-PL",{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n)||0);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const meta=b=>BOOK_META[b]||{abbr:String(b||"?").slice(0,3).toUpperCase(),url:"#"};
const linkFor=o=>o?.bookmaker_url||o?.source_url||meta(o?.bookmaker).url||"#";
const safeId=s=>String(s||"").replace(/[^a-z0-9_-]+/gi,"-");

const DATA_ENDPOINTS=[
  "data/latest.json",
  "https://raw.githubusercontent.com/xlvlcl/arbi/main/docs/data/latest.json"
];

const UI_PREF_KEY="arbi_ui_prefs_v24";

const INFO_COPY={
  scanner:{
    title:"Skaner — co właściwie robi?",
    body:"Skaner cyklicznie zbiera publicznie dostępne kursy, grupuje je po tym samym wydarzeniu i rynku, sprawdza kompletność wyników, a potem liczy arbitraże, value bety i pozycje do obserwacji.",
    example:"Jeżeli dla rynku 1X2 mamy komplet kursów na 1, X i 2, dopiero wtedy można uczciwie sprawdzić, czy powstał surebet.",
    note:"Liczba zeskanowanych wydarzeń nie oznacza pełnej oferty każdego bukmachera."
  },
  surebet:{
    title:"Surebet / arbitraż",
    body:"Surebet to zestaw zakładów na wszystkie wzajemnie wykluczające się wyniki tego samego rynku, w którym suma odwrotności efektywnych kursów jest mniejsza niż 1.",
    formula:"1/kurs₁ + 1/kurs₂ + … < 1",
    example:"Dla rynku dwudrogowego kursy 2.10 i 2.10 dają 1/2.10 + 1/2.10 ≈ 0.952, czyli matematyczną przestrzeń na arbitraż.",
    note:"W praktyce kurs może się zmienić, buk może ograniczyć stawkę albo inaczej rozliczyć rynek."
  },
  bestFound:{
    title:"Najlepszy znaleziony",
    body:"Największy procentowy zysk spośród potwierdzonych surebetów w najnowszym skanie.",
    note:"To nie jest prognoza meczu — dotyczy wyłącznie matematyki kursów."
  },
  surebetCount:{
    title:"Liczba surebetów",
    body:"Ile potwierdzonych arbitraży przeszło aktualny filtr i ponowny recheck w ostatnim skanie."
  },
  eventMarkets:{
    title:"Zdarzenia / rynki",
    body:"Pierwsza liczba to liczba znalezionych wydarzeń, druga to liczba zeskanowanych rynków. Jedno wydarzenie może mieć wiele rynków.",
    example:"Jeden mecz może zawierać 1X2, over/under, BTS, handicapy, kartki, rożne i inne rynki."
  },
  lastScan:{
    title:"Ostatni skan",
    body:"Moment, z którego pochodzą najnowsze dane. Aplikacja porównuje dane z GitHub Pages i RAW repozytorium i wybiera nowsze."
  },
  bankroll:{
    title:"Budżet surebeta",
    body:"Łączna kwota, którą chcesz rozdzielić pomiędzy wszystkie nogi arbitrażu.",
    example:"Przy budżecie 100 zł aplikacja dobiera stawki tak, aby wypłata była możliwie równa niezależnie od wyniku."
  },
  surebetProfit:{
    title:"Minimalny zysk surebeta",
    body:"Filtr pokazuje tylko arbitraże o matematycznej marży co najmniej tej wartości.",
    formula:"zysk % ≈ (1 / suma odwrotności efektywnych kursów − 1) × 100%",
    note:"To jest wartość modelowa przy założeniu, że kursy są nadal dostępne i rynki mają zgodne zasady rozliczenia."
  },
  sportFilter:{
    title:"Filtr sportu",
    body:"Ogranicza widok do wybranego sportu. Nie zmienia działania samego skanera — tylko to, co widzisz na ekranie."
  },
  market:{
    title:"Rynek",
    body:"Dokładny rodzaj zakładu, którego dotyczą kursy.",
    example:"1X2, U/O 2.5, BTS, wynik setów, kartki albo strzały to różne rynki i nie wolno mieszać ich kursów."
  },
  selection:{
    title:"Typ / wybór",
    body:"Konkretny wynik w obrębie danego rynku, który trzeba postawić.",
    example:"W U/O 2.5 wyborem może być „Powyżej 2.5” albo „Poniżej 2.5”."
  },
  odds:{
    title:"Kurs",
    body:"Mnożnik wypłaty oferowany przez bukmachera przed uwzględnieniem szczegółowych zasad, podatków lub limitów.",
    example:"Kurs 2.00 oznacza nominalnie 200 zł wypłaty z 100 zł stawki."
  },
  stake:{
    title:"Stawka",
    body:"Kwota przypisana do konkretnej nogi arbitrażu. Skaner rozdziela budżet proporcjonalnie do odwrotności efektywnych kursów."
  },
  guaranteedPayout:{
    title:"Minimalna wypłata",
    body:"Najniższa modelowa wypłata spośród wszystkich możliwych wyników po rozdzieleniu stawek."
  },
  guaranteedProfit:{
    title:"Minimalny zysk",
    body:"Różnica pomiędzy minimalną modelową wypłatą a całym budżetem surebeta."
  },
  recheck:{
    title:"Ponownie potwierdzony",
    body:"Po znalezieniu kandydata skaner otwiera ten rynek jeszcze raz i dopiero na świeżych danych decyduje, czy nadal spełnia warunki.",
    note:"Recheck zmniejsza ryzyko użycia starego kursu, ale nie zatrzymuje zmian kursów po zakończeniu skanu."
  },
  radar:{
    title:"Radar",
    body:"Radar pokazuje kompletne rynki, które są najbliżej matematycznego arbitrażu. To watchlista, a nie gotowe surebety.",
    note:"Pozycja w Radarze nie oznacza, że należy ją obstawić."
  },
  radarGap:{
    title:"Brak do arbitrażu",
    body:"Pokazuje, jak daleko aktualna suma odwrotności kursów znajduje się od granicy surebeta.",
    formula:"brak % ≈ (suma odwrotności efektywnych kursów − 1) × 100%",
    example:"0.25% oznacza dużo bliższy rynek niż 6%."
  },
  scanMode:{
    title:"Tryb skanu FAST / DEEP",
    body:"FAST priorytetowo sprawdza watchlistę i część katalogu, żeby szybciej reagować. DEEP okresowo robi szersze przejście po katalogu i źródłach."
  },
  watchlist:{
    title:"Watchlista",
    body:"Rynki, które poprzednio były blisko arbitrażu albo miały interesujący sygnał value. Są sprawdzane wcześniej w kolejnych cyklach."
  },
  nearestArb:{
    title:"Najbliższy arb",
    body:"Najmniejszy aktualny procent brakujący do granicy matematycznego surebeta w Radarze."
  },
  value:{
    title:"Value bet",
    body:"Zakład, którego oferowany kurs jest wyższy niż oszacowany kurs fair. Value nie gwarantuje wygranej — chodzi o dodatnią oczekiwaną wartość w długim okresie.",
    example:"Jeżeli fair kurs to 2.00, a buk oferuje 2.15, cena może być korzystna mimo że pojedynczy zakład nadal może przegrać."
  },
  edge:{
    title:"Edge — przewaga kursu",
    body:"Edge mówi, o ile korzystniejszy jest efektywny kurs buka względem ceny fair wyliczonej z konsensusu innych bukmacherów.",
    formula:"edge ≈ efektywny kurs × fair prawdopodobieństwo − 1",
    example:"+6% edge nie oznacza 6% szansy na wygraną. Oznacza około 6% przewagi ceny względem modelowej ceny fair.",
    note:"To estymacja oparta na rynku, nie gwarancja dodatniego wyniku."
  },
  fairOdds:{
    title:"Fair kurs",
    body:"Modelowy kurs bez marży, oszacowany z wielu innych kompletnych ofert na ten sam rynek.",
    formula:"fair kurs = 1 / fair prawdopodobieństwo",
    example:"Fair kurs 5.08 odpowiada około 19.7% prawdopodobieństwa."
  },
  fairChance:{
    title:"Fair szansa",
    body:"Oszacowane prawdopodobieństwo wyniku po usunięciu marży z kursów bukmacherów referencyjnych.",
    formula:"fair szansa = 1 / fair kurs",
    example:"1 / 5.08 ≈ 19.7%."
  },
  outcomeRisk:{
    title:"Ryzyko wyniku",
    body:"Przybliżone ryzyko, że konkretny typ nie wejdzie, liczone jako 100% minus fair szansa.",
    formula:"ryzyko wyniku ≈ 100% − fair szansa",
    example:"Fair szansa 19.7% daje około 80.3% ryzyka niewejścia pojedynczego typu.",
    note:"Wysokie ryzyko wyniku może występować jednocześnie z dobrym value."
  },
  signalRisk:{
    title:"Ryzyko sygnału",
    body:"Wewnętrzny wskaźnik niepewności jakości samego sygnału value. Bierze pod uwagę zgodność bukmacherów, liczbę źródeł, odstęp kursu, edge i ponowne potwierdzenia.",
    note:"To NIE jest prawdopodobieństwo przegrania meczu."
  },
  referenceBooks:{
    title:"Bukmacherzy referencyjni",
    body:"Inni bukmacherzy z kompletnym tym samym rynkiem, których kursy służą do zbudowania konsensusu ceny fair."
  },
  dispersion:{
    title:"Rozbieżność rynku",
    body:"Mierzy, jak mocno bukmacherzy referencyjni różnią się w ocenie prawdopodobieństwa. Niższa wartość oznacza bardziej zgodny rynek."
  },
  confidence:{
    title:"HIGH / ELITE",
    body:"HIGH oznacza, że sygnał przeszedł restrykcyjne filtry i pełny recheck. ELITE wymaga jeszcze mocniejszego edge, większej liczby referencji i niskiej rozbieżności.",
    note:"Ani HIGH, ani ELITE nie gwarantuje wygranej."
  },
  coverage:{
    title:"Rzeczywiste pokrycie",
    body:"Pokazuje ile zdarzeń, rynków i kursów skaner naprawdę znalazł dla poszczególnych źródeł. Nie jest to deklaracja 100% całej oferty bukmachera."
  },
  directSource:{
    title:"Direct source",
    body:"Próba odczytania publicznej strony bukmachera bezpośrednio. Jeżeli źródło blokuje automatyczny dostęp, aplikacja pokazuje błąd zamiast udawać, że dane zostały pobrane."
  },
  coupon:{
    title:"Kupon",
    body:"Narzędzie do zebrania własnych typów i porównania, u którego bukmachera cały zestaw ma najwyższy łączny kurs."
  },
  couponStake:{
    title:"Stawka kuponu",
    body:"Kwota, którą chcesz postawić na cały kupon. Służy do wyliczenia potencjalnej wypłaty."
  },
  totalOdds:{
    title:"Łączny kurs",
    body:"Iloczyn kursów wszystkich typów w kuponie.",
    formula:"łączny kurs = kurs₁ × kurs₂ × …"
  },
  payout:{
    title:"Potencjalna wypłata",
    body:"Stawka pomnożona przez łączny kurs. To wartość nominalna przed ewentualnymi różnicami w rozliczeniu.",
    formula:"wypłata = stawka × łączny kurs"
  },
  bestBook:{
    title:"Najlepszy buk dla kuponu",
    body:"Bukmacher, u którego skaner znalazł wszystkie zaznaczone typy i najwyższy iloczyn ich aktualnie widzianych kursów."
  },
  push:{
    title:"Powiadomienia Push",
    body:"Po aktywnej subskrypcji OneSignal urządzenie może dostać alert po potwierdzeniu nowego surebeta lub mocnego value betu.",
    note:"Sama zgoda Android/iOS nie wystarczy — status w zakładce Aplikacja powinien pokazywać aktywną subskrypcję."
  },
  sourceHealth:{
    title:"Zdrowie źródeł",
    body:"Pokazuje czy dane źródło odpowiadało w ostatnich skanach oraz ile razy z rzędu działało lub zgłaszało problem."
  },
  scanQuality:{
    title:"Jakość skanu",
    body:"Podsumowanie liczby rynków, bukmacherów i średniej liczby ofert przypadających na rynek. Im bogatszy rynek, tym więcej danych do porównania."
  }
};

function readPrefs(){
  try{return JSON.parse(localStorage.getItem(UI_PREF_KEY)||"{}")||{}}
  catch{return {}}
}
let uiPrefs=readPrefs();
function pref(id,fallback=""){
  return Object.prototype.hasOwnProperty.call(uiPrefs,id)?uiPrefs[id]:fallback;
}
function savePref(id,value){
  uiPrefs[id]=value;
  try{localStorage.setItem(UI_PREF_KEY,JSON.stringify(uiPrefs))}catch{}
}
function restoreStaticPrefs(){
  for(const id of ["globalBudget","minFilter","radarGap","valueMinEdge","couponStake","couponSearch"]){
    const el=document.getElementById(id);
    if(el&&Object.prototype.hasOwnProperty.call(uiPrefs,id))el.value=uiPrefs[id];
  }
}
function infoIcon(key){
  return `<button type="button" class="info-i" data-info="${esc(key)}" aria-label="Wyjaśnij pojęcie" title="Kliknij, żeby wyjaśnić">i</button>`;
}
function setOptionalText(id,value){
  const el=document.getElementById(id);
  if(!el)return;
  const text=String(value||"").trim();
  el.textContent=text;
  el.parentElement.hidden=!text;
}
function openInfo(key){
  const info=INFO_COPY[key];
  if(!info)return;
  document.getElementById("infoModalTitle").textContent=info.title;
  document.getElementById("infoModalBody").textContent=info.body||"";
  setOptionalText("infoModalFormula",info.formula);
  setOptionalText("infoModalExample",info.example);
  setOptionalText("infoModalNote",info.note);
  document.getElementById("infoModal").hidden=false;
  document.body.classList.add("modal-open");
}
function closeInfo(){
  const modal=document.getElementById("infoModal");
  if(modal)modal.hidden=true;
  document.body.classList.remove("modal-open");
}
function riskLabel(level){
  return ({low:"małe",medium:"średnie",high:"duże"}[String(level||"").toLowerCase()]||"—");
}
function humanPick(selection,market){
  const s=String(selection||"").trim();
  let m=s.match(/^(?:O|Over)\s*([0-9.,]+)/i);
  if(m)return `Powyżej ${m[1].replace(",",".")}`;
  m=s.match(/^(?:U|Under)\s*([0-9.,]+)/i);
  if(m)return `Poniżej ${m[1].replace(",",".")}`;
  if(/^BTS\+$/i.test(s)||(/^(tak|yes)$/i.test(s)&&/bts/i.test(String(market))))return "Obie drużyny strzelą — TAK";
  if(/^BTS-$/i.test(s)||(/^(nie|no)$/i.test(s)&&/bts/i.test(String(market))))return "Obie drużyny strzelą — NIE";
  if(s==="1")return "Wygrana pierwszej drużyny / zawodnika (1)";
  if(/^x$/i.test(s))return "Remis (X)";
  if(s==="2")return "Wygrana drugiej drużyny / zawodnika (2)";
  return s;
}
function exactBookUrl(v){return String(v?.exact_bookmaker_url||"").trim()}
function comparisonUrl(v){
  const u=String(v?.event_url||v?.source_url||"").trim();
  return u.includes("dobrybuk.pl")?u:"";
}

let data={latest:[],valuebets:[],near_arbs:[],coverage:{},intelligence:{},stats:{},scan_preview:[],coupon_catalog:[]};
let budget=Math.max(1,Number(pref("globalBudget",50))||50);
let coupon=loadCoupon();
let selectedBook=localStorage.getItem("arbi_coupon_book_v16")||"";
let openEventKey="";
let currentView="surebets";

function normalizePayload(payload){
  payload.latest=Array.isArray(payload.latest)?payload.latest:[];
  payload.valuebets=Array.isArray(payload.valuebets)?payload.valuebets:[];
  payload.near_arbs=Array.isArray(payload.near_arbs)?payload.near_arbs:[];
  payload.intelligence=payload.intelligence&&typeof payload.intelligence==="object"?payload.intelligence:{};
  payload.coverage=payload.coverage&&typeof payload.coverage==="object"?payload.coverage:{};
  payload.scan_preview=Array.isArray(payload.scan_preview)?payload.scan_preview:[];
  payload.coupon_catalog=Array.isArray(payload.coupon_catalog)?payload.coupon_catalog:[];
  payload.stats=payload.stats&&typeof payload.stats==="object"?payload.stats:{};

  if(!payload.coupon_catalog.length&&payload.scan_preview.length){
    payload.coupon_catalog=payload.scan_preview.map((row,i)=>({
      id:`compat-${i}-${safeId(row.event)}-${safeId(row.market)}`,
      event:row.event||"",
      sport:row.sport||"",
      market:row.market||"Rynek",
      event_url:row.event_url||"",
      sources:row.sources||["starszy skan"],
      selections:(row.best||[]).map(q=>({
        selection:q.selection||"",
        best_odds:Number(q.odds||0),
        best_bookmaker:q.bookmaker||"",
        offers:[
          {
            bookmaker:q.bookmaker||"",
            odds:Number(q.odds||0),
            bookmaker_url:q.bookmaker_url||q.source_url||"",
            source_url:q.source_url||"",
            source_name:"compat"
          },
          ...((q.alternatives||[]).map(a=>({
            bookmaker:a.bookmaker||"",
            odds:Number(a.odds||0),
            bookmaker_url:a.bookmaker_url||a.source_url||"",
            source_url:a.source_url||"",
            source_name:"compat"
          })))
        ].filter(x=>x.bookmaker&&x.odds>1)
      })).filter(x=>x.offers.length)
    })).filter(x=>x.selections.length);
  }
  return payload;
}

// ---------- ACCESS GATE ----------
const AUTH_KEY="arbi_access_v1";
const AUTH_COOKIE="arbi_access_forever";

async function sha256(value){
  const bytes=new TextEncoder().encode(value);
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
function authHash(){
  return String(window.ARBI_AUTH_HASH||"").trim().toLowerCase();
}
function authCookieValue(){
  const row=document.cookie.split("; ").find(x=>x.startsWith(`${AUTH_COOKIE}=`));
  return row?decodeURIComponent(row.split("=").slice(1).join("=")):"";
}
function rememberAccess(expected){
  try{
    localStorage.setItem(AUTH_KEY,JSON.stringify({
      hash:expected,
      forever:true,
      savedAt:Date.now()
    }));
  }catch{}
  try{
    document.cookie=`${AUTH_COOKIE}=${encodeURIComponent(expected)}; Max-Age=315360000; Path=/; SameSite=Lax; Secure`;
  }catch{}
}
function clearRememberedAccess(){
  try{localStorage.removeItem(AUTH_KEY)}catch{}
  try{document.cookie=`${AUTH_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax; Secure`}catch{}
}
function rememberedAccessValid(){
  const expected=authHash();
  if(!expected)return false;
  try{
    const saved=JSON.parse(localStorage.getItem(AUTH_KEY)||"null");
    if(saved&&saved.hash===expected&&saved.forever===true)return true;
  }catch{}
  return authCookieValue()===expected;
}
async function refreshAuthConfig(){
  return new Promise(resolve=>{
    const script=document.createElement("script");
    script.src=`./auth-config.js?t=${Date.now()}`;
    script.async=true;
    script.onload=()=>{script.remove();resolve(true)};
    script.onerror=()=>{script.remove();resolve(false)};
    document.head.appendChild(script);
  });
}
function showGate(message=""){
  const gate=document.getElementById("authGate");
  if(!gate)return;
  gate.hidden=false;
  document.body.classList.add("locked");
  const error=document.getElementById("authError");
  if(error)error.textContent=message;
  setTimeout(()=>document.getElementById("authPassword")?.focus(),80);
}
function hideGate(){
  const gate=document.getElementById("authGate");
  if(gate)gate.hidden=true;
  document.body.classList.remove("locked");
}
function lockNow(){
  clearRememberedAccess();
  showGate("Dostęp został zablokowany na tym urządzeniu.");
}
async function initAuth(){
  const status=document.getElementById("authStatus");
  if(status)status.textContent="Sprawdzam aktualną konfigurację…";
  await refreshAuthConfig();

  const expected=authHash();
  if(!expected){
    if(status)status.textContent="Brak konfiguracji hasła";
    showGate("Brak aktualnego hasha SITE_PASSWORD w opublikowanej stronie. Uruchom workflow po zapisaniu sekretu SITE_PASSWORD.");
    return false;
  }

  if(rememberedAccessValid()){
    if(status)status.textContent="Dostęp zapamiętany";
    hideGate();
    return true;
  }

  if(status)status.textContent="Wymagane hasło";
  showGate();
  return false;
}

document.getElementById("authForm")?.addEventListener("submit",async e=>{
  e.preventDefault();
  const error=document.getElementById("authError");
  const input=document.getElementById("authPassword");
  const submit=e.submitter||e.currentTarget.querySelector('button[type="submit"]');

  if(submit){submit.disabled=true;submit.textContent="Sprawdzam…"}
  if(error)error.textContent="";

  await refreshAuthConfig();
  const expected=authHash();
  if(!expected){
    if(error)error.textContent="Nie udało się pobrać aktualnej konfiguracji hasła. Odśwież stronę lub uruchom workflow.";
    if(submit){submit.disabled=false;submit.textContent="Wejdź"}
    return;
  }

  const raw=String(input?.value||"");
  if(!raw){
    if(error)error.textContent="Wpisz hasło.";
    if(submit){submit.disabled=false;submit.textContent="Wejdź"}
    return;
  }

  const exact=await sha256(raw);
  const trimmed=raw.trim()!==raw?await sha256(raw.trim()):exact;
  if(exact!==expected&&trimmed!==expected){
    if(error)error.textContent="To hasło nie pasuje do aktualnej konfiguracji strony. Jeśli SITE_PASSWORD było zmieniane, zapisz właściwą wartość w GitHub Secrets i uruchom workflow.";
    if(submit){submit.disabled=false;submit.textContent="Wejdź"}
    return;
  }

  rememberAccess(expected);
  if(error)error.textContent="";
  if(input)input.value="";
  if(submit){submit.disabled=false;submit.textContent="Wejdź"}
  const status=document.getElementById("authStatus");
  if(status)status.textContent="Zapamiętane na tym urządzeniu";
  hideGate();
});

document.getElementById("authToggle")?.addEventListener("click",()=>{
  const input=document.getElementById("authPassword");
  const btn=document.getElementById("authToggle");
  if(!input||!btn)return;
  const show=input.type==="password";
  input.type=show?"text":"password";
  btn.textContent=show?"Ukryj":"Pokaż";
  btn.setAttribute("aria-pressed",show?"true":"false");
});

document.getElementById("lockBtn")?.addEventListener("click",lockNow);

// ---------- DATA ----------
async function load(){
  const attempts=await Promise.all(DATA_ENDPOINTS.map(async endpoint=>{
    try{
      const sep=endpoint.includes("?")?"&":"?";
      const r=await fetch(`${endpoint}${sep}t=${Date.now()}`,{cache:"no-store",mode:"cors"});
      if(!r.ok)throw new Error(`HTTP ${r.status}`);
      const payload=await r.json();
      if(!payload||typeof payload!=="object")throw new Error("invalid data");
      return {endpoint,payload:normalizePayload(payload),ok:true};
    }catch(error){
      return {endpoint,error,ok:false};
    }
  }));

  const good=attempts.filter(x=>x.ok);
  if(!good.length)throw attempts.find(x=>x.error)?.error||new Error("data");

  good.sort((a,b)=>Number(b.payload.last_scan||0)-Number(a.payload.last_scan||0));
  data=good[0].payload;
  data._loaded_from=good[0].endpoint.includes("raw.githubusercontent")?"repo RAW":"GitHub Pages";
  ensureSelectedBook();
  repaint();
}

// ---------- SUREBETS ----------
function scale(a,bankroll){
  const base=Number(a.bankroll)||50,ratio=bankroll/base;
  const legs=(a.legs||[]).map(l=>({...l,stake:(Number(l.stake)||0)*ratio,payout:(Number(l.payout)||0)*ratio}));
  const payout=(Number(a.guaranteed_payout)||0)*ratio;
  return {legs,payout,profit:payout-bankroll};
}
function alternativesHtml(l){
  const alts=(l.alternatives||[]).slice(0,5);
  if(!alts.length)return "";
  return `<div class="alternatives"><span class="alt-title">Inni:</span>${alts.map(a=>{
    const m=meta(a.bookmaker),link=linkFor(a);
    const chip=`<span class="alt-logo">${esc(m.abbr)}</span><span>${esc(a.bookmaker)}</span><b>${Number(a.odds).toFixed(2)}</b>`;
    return link&&link!=="#"?`<a class="alt-chip" href="${esc(link)}" target="_blank" rel="noopener">${chip}</a>`:`<span class="alt-chip">${chip}</span>`;
  }).join("")}</div>`;
}
function legsHtml(a,bankroll){
  const s=scale(a,bankroll);
  return s.legs.map(l=>{
    const m=meta(l.bookmaker),link=linkFor(l),exact=Boolean(l.link_exact||l.bookmaker_link_exact);
    return `<div class="leg"><div class="leg-main">
      <div class="book"><div class="book-logo">${esc(m.abbr)}</div><div class="book-info"><div class="book-name">${esc(l.bookmaker)}</div><div class="book-sub">najlepszy kurs</div></div></div>
      <div class="pick"><div class="pick-label">Wybór ${infoIcon("selection")}</div><div class="pick-value">${esc(l.selection)}</div></div>
      <div class="odds-badge"><div class="odds-stack"><div class="odds">${Number(l.odds).toFixed(2)}</div><div class="stake">${fmt(l.stake)} zł</div></div>${exact&&link&&link!=="#"?`<a class="btn btn-small open-btn" href="${esc(link)}" target="_blank" rel="noopener">Otwórz wydarzenie ↗</a>`:""}</div>
      </div>${alternativesHtml(l)}</div>`;
  }).join("");
}
function card(a,bankroll){
  const s=scale(a,bankroll);
  return `<article class="arb glass"><div class="arb-top"><div class="arb-left"><div class="arb-line"><span class="sport-tag">${esc(a.sport)}</span><span class="profit">+${Number(a.profit_pct||0).toFixed(2)}% ${infoIcon("surebetProfit")}</span><span class="market">${esc(a.market||"Rynek")} ${infoIcon("market")}</span></div><h2 class="event">${esc(a.event)}</h2></div><div class="status-pill status-compact"><span class="dot"></span> potwierdzony ${infoIcon("recheck")}</div></div>
  <div class="arb-body"><div class="legs">${legsHtml(a,bankroll)}</div><aside class="calc"><div class="calc-title">Budżet ${infoIcon("bankroll")}</div><div class="calc-input"><input class="budget" type="number" min="1" step="1" value="${Number(bankroll)}"><span>PLN</span></div><div class="calc-grid"><div class="calc-stat"><span>Wkład ${infoIcon("bankroll")}</span><strong>${fmt(bankroll)} zł</strong></div><div class="calc-stat"><span>Wypłata min. ${infoIcon("guaranteedPayout")}</span><strong>${fmt(s.payout)} zł</strong></div><div class="calc-stat full"><span>Zysk min. ${infoIcon("guaranteedProfit")}</span><strong class="green">+${fmt(s.profit)} zł</strong></div></div>${s.legs.map(l=>`<div class="leg-mini"><span>${esc(l.bookmaker)} · ${esc(l.selection)}</span><strong>${fmt(l.stake)} zł</strong></div>`).join("")}<div class="warning">Sprawdź kursy bezpośrednio przed postawieniem obu stron.</div></aside></div></article>`;
}
function cleanPreviewEvent(value){
  return String(value||"")
    .replace(/\s+(?:RYNEK|KURS|ŚREDNIA|SREDNIA|DO\s+KUPONU|IDŹ\s+DO|IDZ\s+DO)\b.*$/i,"")
    .replace(/\s+/g," ")
    .trim()
    .replace(/[·|\-\s]+$/,"");
}
function previewEventKey(row){
  const url=String(row?.event_url||"").split("#")[0].split("?")[0].replace(/\/+$/,"");
  if(url)return url.toLowerCase();
  return `${String(row?.sport||"").toLowerCase()}|${cleanPreviewEvent(row?.event).toLowerCase()}`;
}
function groupPreviewEvents(rows){
  const groups=new Map();
  for(const row of rows||[]){
    const key=previewEventKey(row);
    if(!key)continue;

    if(!groups.has(key)){
      groups.set(key,{
        key,
        event:cleanPreviewEvent(row.event)||"Zdarzenie",
        sport:row.sport||"Inne",
        event_url:row.event_url||"",
        markets:new Map(),
        sources:new Set()
      });
    }

    const g=groups.get(key);
    const cleaned=cleanPreviewEvent(row.event);
    if(cleaned && cleaned.length<g.event.length)g.event=cleaned;
    if((!g.sport||g.sport==="Inne")&&row.sport&&row.sport!=="Inne")g.sport=row.sport;
    if(!g.event_url&&row.event_url)g.event_url=row.event_url;
    for(const src of row.sources||[])g.sources.add(src);

    const market=String(row.market||"Rynek").trim();
    const mkey=market.toLowerCase().replace(/\s+/g," ");
    const best=(row.best||[]).slice().sort((a,b)=>Number(b.odds||0)-Number(a.odds||0));
    const old=g.markets.get(mkey);

    // Same event+market can come from detail scan and broad scan.
    // Keep only one copy, preferring the row with more useful quotes.
    if(!old||best.length>(old.best||[]).length){
      g.markets.set(mkey,{market,best,sources:row.sources||[]});
    }
  }

  return [...groups.values()].map(g=>({
    ...g,
    markets:[...g.markets.values()],
    sources:[...g.sources]
  }));
}
function previewHtml(){
  const sport=document.getElementById("sportFilter").value;
  const filtered=(data.scan_preview||[]).filter(x=>!sport||x.sport===sport);
  const events=groupPreviewEvents(filtered).slice(0,100);
  if(!events.length)return "";

  return `<section class="scan-preview">
    <div class="scan-preview-head">
      <div>
        <strong>Ostatnio zeskanowane zdarzenia</strong>
        <span>Jedno wydarzenie = jeden kafelek. Kliknij, aby rozwinąć jego rynki.</span>
      </div>
      <span>${events.length} zdarzeń</span>
    </div>

    <div class="scan-event-grid">
      ${events.map(g=>{
        const markets=g.markets||[];
        const chips=markets.slice(0,6).map(m=>`<span>${esc(m.market)}</span>`).join("");
        const more=markets.length>6?`<span class="scan-more">+${markets.length-6}</span>`:"";
        const link=g.event_url?String(g.event_url).split("#")[0]:"";

        return `<details class="scan-event-card glass">
          <summary>
            <div class="scan-event-summary">
              <div class="scan-event-summary-top">
                <span class="sport-tag">${esc(g.sport||"Sport")}</span>
                <span class="scan-market-count">${markets.length} ${markets.length===1?"rynek":"rynków"}</span>
              </div>
              <div class="scan-event-title">${esc(g.event||"Zdarzenie")}</div>
              <div class="scan-market-chips">${chips}${more}</div>
            </div>
            <span class="scan-expand">+</span>
          </summary>

          <div class="scan-event-markets">
            ${markets.map(m=>`<div class="scan-market-row">
              <div class="scan-market-name">${esc(m.market)}</div>
              <div class="scan-best">
                ${(m.best||[]).slice(0,6).map(q=>`<span><b>${esc(q.selection)}</b> ${Number(q.odds||0).toFixed(2)} <small>${esc(q.bookmaker)}</small></span>`).join("")}
              </div>
            </div>`).join("")}
            ${link?`<a class="btn btn-small scan-event-open" href="${esc(link)}" target="_blank" rel="noopener">Otwórz wydarzenie ↗</a>`:""}
          </div>
        </details>`;
      }).join("")}
    </div>
  </section>`;
}
function renderSources(){
  const sources=data.stats?.sources||{};
  const rows=Object.entries(sources);
  document.getElementById("sourceStrip").innerHTML=rows.map(([name,s])=>{
    const broad=Number(s.broad_candidate_markets||0);
    return `<span class="source-chip"><b>${esc(name)}</b> ${Number(s.markets||0)} pełnych${broad?` + ${broad} candidate`:""}</span>`;
  }).join("");
}
function repaintSurebets(){
  const sport=document.getElementById("sportFilter").value,min=Number(document.getElementById("minFilter").value)||0;
  const items=(data.latest||[]).filter(a=>(Number(a.profit_pct)||0)>=min&&(!sport||a.sport===sport)).sort((a,b)=>(Number(b.profit_pct)||0)-(Number(a.profit_pct)||0));
  document.getElementById("count").textContent=items.length;
  document.getElementById("best").textContent=items.length?`+${Number(items[0].profit_pct).toFixed(2)}%`:"—";
  const ev=Number(data.stats?.events||0),mk=Number(data.stats?.markets_scanned??data.stats?.markets??0);
  document.getElementById("markets").textContent=`${ev} / ${mk}`;
  const ts=data.last_scan||data.generated_at;
  document.getElementById("last").textContent=ts?new Date(Number(ts)*1000).toLocaleString("pl-PL"):"—";
  const age=ts?Date.now()/1000-Number(ts):Infinity,errs=data.errors||[];
  let status="monitoring aktywny",dot="var(--green)";
  if(age>15*60){status="skan opóźniony";dot="#ff6b8b"}
  else if(age>7*60){status="czekam na nowy skan";dot="#ffd166"}
  else if(data.stats?.exhaustive_complete===false){status="skan częściowy";dot="#ffd166"}
  else if(errs.length){status="uwaga";dot="#ffd166"}
  document.getElementById("statusText").textContent=status;
  document.getElementById("statusDot").style.background=dot;
  renderSources();
  const sports=[...new Set([...(data.stats?.sports||[]),...(data.latest||[]).map(x=>x.sport),...(data.scan_preview||[]).map(x=>x.sport),...(data.coupon_catalog||[]).map(x=>x.sport)].filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("sportFilter"),current=sel.value||String(pref("sportFilter",""));
  sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
  sel.value=sports.includes(current)?current:"";
  const oldPayload=!data.scan_preview?.length&&!data.coupon_catalog?.length&&ev>0;
  const empty=`<div class="empty glass ${oldPayload?"data-warning":""}">
    <div class="icon">${oldPayload?"↻":"⌁"}</div>
    <h3>${oldPayload?"Czekam na świeży katalog zdarzeń":"Brak potwierdzonych surebetów w tym skanie"}</h3>
    <p>${oldPayload
      ?`Aktualny plik ma jeszcze starszy format (${ev} zdarzeń / ${mk} rynków). V17 uzupełni katalog po następnym poprawnym skanie.`
      :`Skaner odczytał ${ev} zdarzeń i ${mk} rynków. Poniżej widać część zeskanowanych rynków.`}</p>
  </div>`;
  document.getElementById("list").innerHTML=(items.length?items.slice(0,200).map(a=>card(a,budget)).join(""):empty)+previewHtml();
}


// ---------- OPPORTUNITY RADAR ----------
function radarLink(x){
  return x.event_url||(x.legs||[]).map(l=>l.bookmaker_url||l.source_url).find(Boolean)||"#";
}
function radarCard(x){
  const link=radarLink(x);
  return `<article class="radar-card glass">
    <div class="radar-card-head">
      <div>
        <div class="arb-line"><span class="sport-tag">${esc(x.sport)}</span><span class="radar-gap">${x.radar_tier==="near"?"BLISKO ARBU":"OBSERWUJ"} · brakuje ${Number(x.gap_pct||0).toFixed(2)}% ${infoIcon("radarGap")}</span><span class="market">${esc(x.market)}</span></div>
        <h3>${esc(x.event)}</h3>
      </div>
      <div class="radar-seen">${Number(x.seen_scans||1)}× obserwowany ${infoIcon("watchlist")}</div>
    </div>
    <div class="radar-legs">${(x.legs||[]).map(l=>`<div class="radar-leg"><span>${esc(l.selection)}</span><b>${Number(l.odds||0).toFixed(2)}</b><small>${esc(l.bookmaker)}</small></div>`).join("")}</div>
    <div class="radar-foot">
      <span>${Number(x.bookmakers||0)} buków • najlepszy historyczny brak ${Number(x.best_gap_pct??x.gap_pct??0).toFixed(2)}%</span>
      ${link&&link!=="#"?`<a class="btn btn-small" href="${esc(link)}" target="_blank" rel="noopener">Otwórz rynek ↗</a>`:""}
    </div>
  </article>`;
}
function renderSourceHealth(){
  const grid=document.getElementById("sourceHealthGrid");
  if(!grid)return;
  const health=data.intelligence?.source_health||{};
  const rows=Object.entries(health);
  grid.innerHTML=rows.length?rows.map(([name,x])=>{
    const ok=Boolean(x.ok),fail=Number(x.consecutive_failures||0),succ=Number(x.consecutive_success||0);
    return `<div class="source-health ${ok?"ok":"bad"}"><div><b>${esc(name)}</b><span>${ok?"działa":"problem"}</span>${infoIcon("sourceHealth")}</div><small>${ok?`${succ} udanych z rzędu`:`${fail} błędów z rzędu`}</small></div>`;
  }).join(""):'<div class="coupon-empty">Brak historii źródeł.</div>';
}
function renderRadar(){
  const all=(data.near_arbs||[]).slice().sort((a,b)=>Number(a.gap_pct||99)-Number(b.gap_pct||99));
  const sports=[...new Set(all.map(x=>x.sport).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("radarSport");
  const prev=sel?.value||String(pref("radarSport",""));
  if(sel){
    sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
    sel.value=sports.includes(prev)?prev:"";
  }
  const sport=sel?.value||"";
  const maxGap=Number(document.getElementById("radarGap")?.value||8);
  let items=all.filter(x=>(!sport||x.sport===sport)&&Number(x.gap_pct||99)<=maxGap);
  const fallbackUsed=!items.length&&all.length>0;
  if(fallbackUsed){
    items=all.filter(x=>!sport||x.sport===sport).slice(0,24);
  }
  document.getElementById("radarCount").textContent=all.length;
  const plan=data.intelligence?.scan_plan||{};
  document.getElementById("radarMode").textContent=(plan.mode||data.stats?.scan_mode||"—").toString().toUpperCase();
  document.getElementById("radarWatch").textContent=Number(data.intelligence?.watchlist_size||0);
  document.getElementById("radarBest").textContent=items.length?`${Number(items[0].gap_pct).toFixed(2)}%`:"—";
  const list=document.getElementById("radarList");
  if(list)list.innerHTML=items.length?items.map(radarCard).join(""):`<div class="empty glass"><div class="icon">📡</div><h3>Brak rynków bardzo blisko arbitrażu</h3><p>Radar nadal je śledzi. Zwiększ próg, jeśli chcesz zobaczyć dalsze kandydaty.</p></div>`;
  const q=data.intelligence?.quality||data.stats?.quality||{};
  const quality=document.getElementById("intelQuality");
  if(quality)quality.innerHTML=`<b>${Number(q.markets||0)} rynków</b><span>${Number(q.bookmakers||0)} buków • ${Number(q.offers_per_market||0).toFixed(1)} kursów/rynek</span>`;
  renderSourceHealth();
}

// ---------- HIGH-CONFIDENCE VALUE BETS ----------
function valueCard(v){
  const p=Number(v.fair_probability||0)*100;
  const outcomeRisk=Number(v.outcome_risk_pct ?? (100-p));
  const signalRisk=Number(v.signal_risk_pct||0);
  const exact=exactBookUrl(v);
  const compare=comparisonUrl(v);
  const home=meta(v.bookmaker).url||"#";
  const event=cleanPreviewEvent(v.event)||String(v.event||"Zdarzenie");
  const pick=humanPick(v.selection,v.market);
  const outcomeLevel=String(v.outcome_risk_level||(outcomeRisk<=40?"low":outcomeRisk<=65?"medium":"high"));
  const signalLevel=String(v.signal_risk_level||(signalRisk<=40?"low":signalRisk<=65?"medium":"high"));

  return `<article class="value-card glass">
    <div class="value-card-head">
      <div>
        <div class="arb-line">
          <span class="sport-tag">${esc(v.sport||"Sport")}</span>
          <span class="value-edge">+${Number(v.edge_pct||0).toFixed(1)}% edge ${infoIcon("edge")}</span>
          <span class="market">${esc(v.market||"Rynek")} ${infoIcon("market")}</span>
        </div>
        <h3>${esc(event)}</h3>
      </div>
      <div class="value-confidence">${v.elite_signal?"ELITE":"HIGH"} ${infoIcon("confidence")}</div>
    </div>

    <div class="bet-instruction">
      <div class="bet-instruction-icon">🎯</div>
      <div class="bet-instruction-main">
        <span>CO DOKŁADNIE POSTAWIĆ</span>
        <strong>${esc(pick)}</strong>
        <small>${esc(v.bookmaker)} • kurs <b>${Number(v.odds||0).toFixed(2)}</b> ${infoIcon("odds")} • rynek: ${esc(v.market||"Rynek")}</small>
      </div>
    </div>

    <div class="value-card-grid value-card-grid-v22">
      <div class="value-number"><span>Fair kurs ${infoIcon("fairOdds")}</span><strong>${Number(v.fair_odds||0).toFixed(2)}</strong></div>
      <div class="value-number"><span>Fair szansa ${infoIcon("fairChance")}</span><strong>${p.toFixed(1)}%</strong></div>
      <div class="risk-tile risk-${esc(outcomeLevel)}"><span>Ryzyko wyniku ${infoIcon("outcomeRisk")}</span><strong>${outcomeRisk.toFixed(1)}%</strong><small>${riskLabel(outcomeLevel)} ryzyko</small></div>
      <div class="risk-tile risk-${esc(signalLevel)}"><span>Ryzyko sygnału ${infoIcon("signalRisk")}</span><strong>${signalRisk.toFixed(1)}%</strong><small>${riskLabel(signalLevel)} ryzyko danych</small></div>
    </div>

    <div class="value-evidence">
      <span>✓ ${Number(v.reference_books||0)} buków referencyjnych ${infoIcon("referenceBooks")}</span>
      <span>✓ rozbieżność ${Number(v.dispersion_pct||0).toFixed(2)}% ${infoIcon("dispersion")}</span>
      <span>✓ pełny recheck ${infoIcon("recheck")}</span>
      <span>✓ ${Number(v.stability_scans||1)}× potwierdzenie</span>
    </div>

    <div class="value-actions">
      ${exact?`<a class="btn btn-primary value-open" href="${esc(exact)}" target="_blank" rel="noopener">🎯 Otwórz dokładnie wydarzenie w ${esc(v.bookmaker)} ↗</a>`:""}
      ${!exact&&compare?`<a class="btn value-open" href="${esc(compare)}" target="_blank" rel="noopener">📊 Otwórz wydarzenie w porównywarce ↗</a>`:""}
      ${!exact&&home&&home!=="#"?`<a class="btn value-home" href="${esc(home)}" target="_blank" rel="noopener">Strona ${esc(v.bookmaker)} ↗</a>`:""}
    </div>
    ${!exact?`<div class="link-warning">Brak potwierdzonego deep-linku do tego wydarzenia u ${esc(v.bookmaker)}. Nie oznaczam strony głównej jako „Otwórz wydarzenie”. Gdy direct-source zwróci prawdziwy link do meczu/rynku, pojawi się dokładny przycisk.</div>`:""}
  </article>`;
}
function renderCoverage(){
  const cov=data.coverage||{},books=cov.books||{};
  const completion=Number(cov.detail_completion_pct||0);
  const c=document.getElementById("coverageCompletion");
  if(c)c.innerHTML=`<b>${completion.toFixed(1)}%</b><span>odkrytych zdarzeń przeszło detail scan</span>`;
  const grid=document.getElementById("coverageGrid");
  if(!grid)return;
  const statusLabel=s=>({
    "working":"direct ✓",
    "reachable-no-markets":"direct: brak rynków",
    "blocked-or-failed":"direct: blokada/błąd",
    "not-configured":"tylko porównywarka",
    "unknown":"status nieznany"
  }[s]||s);
  const rows=Object.entries(books).sort((a,b)=>(Number(b[1].markets||0)-Number(a[1].markets||0))||a[0].localeCompare(b[0],"pl"));
  grid.innerHTML=rows.length?rows.map(([book,x])=>`<div class="coverage-book">
    <div class="coverage-book-top"><b>${esc(book)}</b><span class="${x.direct_status==="working"?"ok":"warn"}">${esc(statusLabel(x.direct_status))}</span></div>
    <div class="coverage-book-stats"><span>${Number(x.events||0)} zdarzeń</span><span>${Number(x.markets||0)} rynków</span><span>${Number(x.offers||0)} kursów</span></div>
  </div>`).join(""):`<div class="coupon-empty">Brak danych o pokryciu w tym skanie.</div>`;
}
function renderValuebets(){
  const sport=document.getElementById("valueSport")?.value||"";
  const min=Number(document.getElementById("valueMinEdge")?.value||5);
  const all=(data.valuebets||[]).slice().sort((a,b)=>Number(b.edge_pct||0)-Number(a.edge_pct||0));
  const sports=[...new Set(all.map(x=>x.sport).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("valueSport");
  if(sel){
    const prev=sel.value||String(pref("valueSport",""));
    sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
    sel.value=sports.includes(prev)?prev:"";
  }
  const items=all.filter(v=>(!sport||v.sport===sport)&&Number(v.edge_pct||0)>=min);
  document.getElementById("valueCount").textContent=all.length;
  document.getElementById("valueKpiCount").textContent=items.length;
  document.getElementById("valueKpiBest").textContent=items.length?`+${Number(items[0].edge_pct).toFixed(1)}%`:"—";
  const list=document.getElementById("valueList");
  if(list)list.innerHTML=items.length?items.map(valueCard).join(""):`<div class="empty glass"><div class="icon">💎</div><h3>Brak mocnych value betów</h3><p>To dobrze — filtr jest celowo restrykcyjny i nie pokazuje słabych ani niepewnych sygnałów.</p></div>`;
  renderCoverage();
}

// ---------- COUPON DATA MODEL ----------
function loadCoupon(){try{return JSON.parse(localStorage.getItem("arbi_coupon_v2")||"[]")||[]}catch{return []}}
function saveCoupon(){
  localStorage.setItem("arbi_coupon_v2",JSON.stringify(coupon));
  document.getElementById("couponCount").textContent=coupon.length;
}
function catalogById(id){return (data.coupon_catalog||[]).find(x=>x.id===id)}
function allBookmakers(){
  const books=new Set();
  for(const item of data.coupon_catalog||[]){
    for(const selection of item.selections||[]){
      for(const offer of selection.offers||[])if(offer.bookmaker)books.add(offer.bookmaker);
    }
  }
  return [...books].sort((a,b)=>a.localeCompare(b,"pl"));
}
function bookStats(book){
  const events=new Set(),sports=new Set(),markets=new Set();
  for(const item of data.coupon_catalog||[]){
    let has=false;
    for(const selection of item.selections||[]){
      if((selection.offers||[]).some(o=>o.bookmaker===book)){has=true;break}
    }
    if(has){
      events.add(`${item.sport}|${item.event}`);
      if(item.sport)sports.add(item.sport);
      markets.add(item.id);
    }
  }
  return {events:events.size,sports:sports.size,markets:markets.size};
}
function ensureSelectedBook(){
  const books=allBookmakers();
  if(selectedBook&&!books.includes(selectedBook))selectedBook="";
  if(!selectedBook&&books.length)selectedBook=books[0];
  if(selectedBook)localStorage.setItem("arbi_coupon_book_v16",selectedBook);
}
function selectBook(book){
  selectedBook=book;
  localStorage.setItem("arbi_coupon_book_v16",book);
  openEventKey="";
  renderCoupon();
}
function offerForBook(selection,book){
  return (selection?.offers||[]).find(o=>o.bookmaker===book)||null;
}
function addCoupon(id,selection){
  const item=catalogById(id);if(!item)return;
  const sel=(item.selections||[]).find(x=>x.selection===selection);if(!sel)return;
  const key=`${id}|${selection}`;
  if(coupon.some(x=>x.key===key))return;
  coupon.push({key,id,selection,event:item.event,sport:item.sport,market:item.market});
  saveCoupon();renderCoupon();
}
function removeCoupon(key){coupon=coupon.filter(x=>x.key!==key);saveCoupon();renderCoupon()}
function clearCoupon(){coupon=[];saveCoupon();renderCoupon()}
function currentLegs(){
  return coupon.map(c=>{
    const item=catalogById(c.id);if(!item)return null;
    const selection=(item.selections||[]).find(x=>x.selection===c.selection);if(!selection)return null;
    return {...c,item,offers:selection.offers||[],selectedOffer:offerForBook(selection,selectedBook),bestOffer:(selection.offers||[]).slice().sort((a,b)=>Number(b.odds)-Number(a.odds))[0]||null};
  }).filter(Boolean);
}
function commonBookRanking(legs){
  if(!legs.length)return [];
  let common=new Set((legs[0].offers||[]).map(o=>o.bookmaker));
  for(const leg of legs.slice(1)){
    const books=new Set((leg.offers||[]).map(o=>o.bookmaker));
    common=new Set([...common].filter(x=>books.has(x)));
  }
  return [...common].map(book=>{
    const offers=legs.map(leg=>(leg.offers||[]).find(o=>o.bookmaker===book));
    return {book,offers,total:offers.reduce((a,o)=>a*Number(o.odds||1),1)};
  }).sort((a,b)=>b.total-a.total);
}
function selectedBookEvents(){
  if(!selectedBook)return [];
  const q=document.getElementById("couponSearch")?.value.trim().toLowerCase()||"";
  const sport=document.getElementById("couponSport")?.value||"";
  const groups=new Map();

  for(const item of data.coupon_catalog||[]){
    if(sport&&item.sport!==sport)continue;

    const marketSelections=[];
    for(const selection of item.selections||[]){
      const offer=offerForBook(selection,selectedBook);
      if(offer)marketSelections.push({selection:selection.selection,offer,bestOdds:selection.best_odds,bestBookmaker:selection.best_bookmaker});
    }
    if(!marketSelections.length)continue;

    const hay=`${item.event} ${item.market} ${item.sport} ${marketSelections.map(x=>x.selection).join(" ")}`.toLowerCase();
    if(q&&!hay.includes(q))continue;

    const baseUrl=String(item.event_url||"").split("#")[0].split("?")[0].replace(/\/+$/,"");
    const cleanEvent=cleanPreviewEvent(item.event);
    const key=baseUrl.toLowerCase()||`${item.sport}|${cleanEvent}`;
    if(!groups.has(key)){
      groups.set(key,{
        key,event:cleanEvent,sport:item.sport,markets:[],eventLink:"",
        sources:new Set()
      });
    }
    const group=groups.get(key);
    const deep=marketSelections.find(x=>linkFor(x.offer)!=="#");
    if(!group.eventLink&&deep)group.eventLink=linkFor(deep.offer);
    for(const source of item.sources||[])group.sources.add(source);
    group.markets.push({id:item.id,market:item.market,selections:marketSelections,sources:item.sources||[]});
  }

  return [...groups.values()]
    .map(g=>({...g,sources:[...g.sources]}))
    .sort((a,b)=>a.sport.localeCompare(b.sport,"pl")||a.event.localeCompare(b.event,"pl"));
}
function couponSportsForBook(book){
  const sports=new Set();
  for(const item of data.coupon_catalog||[]){
    if((item.selections||[]).some(s=>(s.offers||[]).some(o=>o.bookmaker===book)))sports.add(item.sport);
  }
  return [...sports].filter(Boolean).sort((a,b)=>a.localeCompare(b,"pl"));
}

// ---------- COUPON RENDER ----------
function renderBookmakerPicker(){
  const books=allBookmakers();
  const wrap=document.getElementById("bookmakerPicker");
  wrap.innerHTML=books.length?books.map(book=>{
    const st=bookStats(book),m=meta(book),active=book===selectedBook;
    return `<button class="bookmaker-card ${active?"active":""}" onclick='selectBook(${JSON.stringify(book)})'>
      <span class="bookmaker-card-logo">${esc(m.abbr)}</span>
      <span class="bookmaker-card-name">${esc(book)}</span>
      <span class="bookmaker-card-stats">${st.sports} sportów · ${st.events} zdarzeń</span>
      <span class="bookmaker-card-markets">${st.markets} rynków</span>
    </button>`;
  }).join(""):'<div class="coupon-empty">Brak bukmacherów w ostatnim skanie.</div>';

  const st=selectedBook?bookStats(selectedBook):{sports:0,events:0,markets:0};
  document.getElementById("selectedBookSummary").innerHTML=selectedBook?`<b>${esc(selectedBook)}</b><span>${st.sports} sportów • ${st.events} zdarzeń • ${st.markets} rynków</span>`:"Wybierz bukmachera";
  document.getElementById("couponBookBadge").textContent=selectedBook||"—";
}
function renderSportSelect(){
  const sports=selectedBook?couponSportsForBook(selectedBook):[];
  const sel=document.getElementById("couponSport"),prev=sel.value||String(pref("couponSport",""));
  sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
  sel.value=sports.includes(prev)?prev:"";
}
function toggleEvent(key){
  openEventKey=openEventKey===key?"":key;
  renderEventCatalog();
}
function marketHtml(market,event){
  return `<div class="event-market">
    <div class="event-market-title"><span>${esc(market.market)} ${infoIcon("market")}</span><small>${market.selections.length} typów</small></div>
    <div class="market-selections">
      ${market.selections.map(s=>{
        const o=s.offer,u=linkFor(o),inCoupon=coupon.some(x=>x.key===`${market.id}|${s.selection}`);
        const bestDifferent=s.bestBookmaker&&s.bestBookmaker!==selectedBook;
        return `<div class="market-pick ${inCoupon?"picked":""}">
          <div class="market-pick-main"><span>${esc(s.selection)}</span><strong>${Number(o.odds||0).toFixed(2)}</strong></div>
          <div class="market-pick-sub">
            <span>${esc(selectedBook)}</span>
            ${bestDifferent?`<em>najlepiej: ${esc(s.bestBookmaker)} ${Number(s.bestOdds||0).toFixed(2)}</em>`:"<em>najlepszy lub równy</em>"}
          </div>
          <div class="market-pick-actions">
            <button class="pick-add" onclick='event.stopPropagation();addCoupon(${JSON.stringify(market.id)},${JSON.stringify(String(s.selection))})'>${inCoupon?"✓ w kuponie":"+ do kuponu"}</button>
            ${u&&u!=="#"?`<a class="pick-open" href="${esc(u)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Otwórz ↗</a>`:""}
          </div>
        </div>`;
      }).join("")}
    </div>
  </div>`;
}
function renderEventCatalog(){
  const events=selectedBookEvents(),wrap=document.getElementById("couponCatalog");
  const marketCount=events.reduce((a,e)=>a+e.markets.length,0);
  document.getElementById("catalogStats").textContent=`${events.length} zdarzeń • ${marketCount} rynków`;
  document.getElementById("eventBrowserTitle").textContent=selectedBook?`Oferta: ${selectedBook}`:"Wybierz bukmachera powyżej";

  if(!selectedBook){
    wrap.innerHTML='<div class="coupon-empty big-empty">Wybierz bukmachera, a pokażę jego zeskanowaną ofertę.</div>';
    return;
  }
  if(!events.length){
    wrap.innerHTML=`<div class="coupon-empty big-empty">Brak pasujących zdarzeń dla ${esc(selectedBook)} w ostatnim skanie. Zmień sport lub wyszukiwanie.</div>`;
    return;
  }

  wrap.innerHTML=events.slice(0,260).map(event=>{
    const opened=openEventKey===event.key;
    const link=event.eventLink;
    return `<article class="event-card ${opened?"open":""}">
      <button class="event-card-head" onclick='toggleEvent(${JSON.stringify(event.key)})'>
        <div class="event-card-left">
          <div class="event-meta"><span class="sport-tag">${esc(event.sport)}</span><span>${event.markets.length} rynków</span></div>
          <h4>${esc(event.event)}</h4>
          <small>${esc((event.sources||[]).slice(0,3).join(" + "))}</small>
        </div>
        <div class="event-card-right">
          ${link&&link!=="#"?`<a class="event-deeplink" href="${esc(link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Otwórz u buka ↗</a>`:""}
          <span class="event-chevron">${opened?"−":"+"}</span>
        </div>
      </button>
      ${opened?`<div class="event-card-body">${event.markets.map(m=>marketHtml(m,event)).join("")}</div>`:""}
    </article>`;
  }).join("");
}
function renderCouponLegs(legs){
  document.getElementById("couponTitle").textContent=`${legs.length} ${legs.length===1?"typ":"typy"}`;
  document.getElementById("couponLegs").innerHTML=legs.length?legs.map(l=>{
    const o=l.selectedOffer,u=o?linkFor(o):"#";
    return `<div class="coupon-leg-v16 ${o?"":"unavailable"}">
      <div class="coupon-leg-top"><span class="sport-tag">${esc(l.sport)}</span><button onclick='removeCoupon(${JSON.stringify(l.key)})'>×</button></div>
      <strong>${esc(l.event)}</strong>
      <small>${esc(l.market)} → ${esc(l.selection)}</small>
      <div class="coupon-leg-offer">
        ${o?`<span>${esc(selectedBook)} <b>${Number(o.odds).toFixed(2)}</b></span>${u&&u!=="#"?`<a href="${esc(u)}" target="_blank" rel="noopener">Otwórz ↗</a>`:""}`:`<span class="missing">Brak tego typu u ${esc(selectedBook)}</span>`}
      </div>
    </div>`;
  }).join(""):'<div class="coupon-empty">Dodaj typy z listy zdarzeń.</div>';
}
function renderCouponTotal(legs){
  const stake=Math.max(1,Number(document.getElementById("couponStake").value)||1);
  const offers=legs.map(l=>l.selectedOffer);
  const complete=legs.length>0&&offers.every(Boolean);
  const total=complete?offers.reduce((a,o)=>a*Number(o.odds||1),1):0;
  document.getElementById("couponTotalOdds").textContent=complete?total.toFixed(2):"—";
  document.getElementById("couponPayout").textContent=complete?`${fmt(stake*total)} zł`:"—";
  const card=document.getElementById("couponTotalCard");
  card.classList.toggle("incomplete",legs.length>0&&!complete);
}
function renderCouponRanking(legs){
  const wrap=document.getElementById("couponRanking");
  if(!legs.length){wrap.innerHTML="";return}
  const rankings=commonBookRanking(legs),current=rankings.find(r=>r.book===selectedBook),best=rankings[0];
  let html='<div class="compare-title">Porównanie tego samego kuponu ${infoIcon("bestBook")}</div>';
  if(current){
    html+=`<div class="compare-row current"><span>${esc(selectedBook)}</span><strong>${current.total.toFixed(2)}</strong><small>Twój wybrany buk</small></div>`;
  }
  if(best&&best.book!==selectedBook){
    html+=`<div class="compare-row best"><span>${esc(best.book)}</span><strong>${best.total.toFixed(2)}</strong><small>najwyższy łączny kurs</small></div>`;
  }
  const rest=rankings.filter(r=>r.book!==selectedBook&&(!best||r.book!==best.book)).slice(0,4);
  html+=rest.map(r=>`<div class="compare-row"><span>${esc(r.book)}</span><strong>${r.total.toFixed(2)}</strong></div>`).join("");
  if(!rankings.length)html+='<div class="coupon-empty">Żaden buk nie ma wszystkich zaznaczonych typów.</div>';
  wrap.innerHTML=html;
}
function renderCoupon(){
  ensureSelectedBook();
  renderBookmakerPicker();
  renderSportSelect();
  renderEventCatalog();
  const legs=currentLegs();
  renderCouponLegs(legs);
  renderCouponTotal(legs);
  renderCouponRanking(legs);
  saveCoupon();
}

// ---------- VIEWS ----------
function switchView(name){
  if(!["surebets","radar","value","coupon","app"].includes(name))name="surebets";
  currentView=name;
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  document.querySelectorAll(".view").forEach(v=>{
    const on=v.id===`${name}View`;
    v.classList.toggle("active",on);
    v.hidden=!on;
  });
  if(name==="radar")renderRadar();
  if(name==="value")renderValuebets();
  if(name==="coupon")renderCoupon();
  try{history.replaceState(null,"",`#${name}`)}catch{}
}
function repaint(){
  repaintSurebets();
  if(currentView==="radar")renderRadar();
  if(currentView==="value")renderValuebets();
  if(currentView==="coupon")renderCoupon();
  document.getElementById("couponCount").textContent=coupon.length;
  document.getElementById("radarCount").textContent=(data.near_arbs||[]).length;
  document.getElementById("valueCount").textContent=(data.valuebets||[]).length;
  const lastPush=document.getElementById("lastPushStats");
  if(lastPush){
    const s=data.stats||{};
    lastPush.textContent=`Ostatni skan: ${Number(s.push_alerts_sent||0)} push surebet • ${Number(s.value_push_alerts_sent||0)} push value`;
  }
}

function addInfoTo(selector,key){
  document.querySelectorAll(selector).forEach(el=>{
    if(el.querySelector?.(`[data-info="${key}"]`))return;
    el.insertAdjacentHTML("beforeend",` ${infoIcon(key)}`);
  });
}
function decorateStaticHelp(){
  addInfoTo(".hero-card .eyebrow","scanner");
  addInfoTo(".kpi:nth-child(1) .kpi-label","bestFound");
  addInfoTo(".kpi:nth-child(2) .kpi-label","surebetCount");
  addInfoTo(".kpi:nth-child(3) .kpi-label","eventMarkets");
  addInfoTo(".kpi:nth-child(4) .kpi-label","lastScan");
  addInfoTo(".budget-wrap label","bankroll");
  addInfoTo("#surebetsView .controls .input-wrap:first-child label","sportFilter");

  addInfoTo("#radarView .radar-hero .eyebrow","radar");
  addInfoTo("#radarView .radar-plan>div:nth-child(1) span","scanMode");
  addInfoTo("#radarView .radar-plan>div:nth-child(2) span","watchlist");
  addInfoTo("#radarView .radar-plan>div:nth-child(3) span","nearestArb");
  addInfoTo("#radarView .intel-panel h3","scanQuality");

  addInfoTo("#valueView .value-hero .eyebrow","value");
  addInfoTo("#valueView .value-kpis>div:nth-child(1) span","confidence");
  addInfoTo("#valueView .value-kpis>div:nth-child(2) span","edge");
  addInfoTo("#valueView .coverage-panel h3","coverage");

  addInfoTo("#couponView .coupon-dashboard .eyebrow","coupon");
  addInfoTo("#couponView label[for='couponStake'], #couponView .compact-input label","couponStake");
  addInfoTo("#couponTotalOddsLabel","totalOdds");
  addInfoTo("#couponPayoutLabel","payout");

  addInfoTo("#appView .app-hero .eyebrow, #appView .push-panel .eyebrow","push");
}

// ---------- EVENTS ----------
document.querySelectorAll(".tab-btn").forEach(b=>b.addEventListener("click",()=>switchView(b.dataset.view)));
const initialView=(location.hash||"").replace("#","");
if(["surebets","radar","value","coupon","app"].includes(initialView))switchView(initialView);
document.getElementById("globalBudget").addEventListener("input",e=>{budget=Math.max(1,Number(e.target.value)||1);savePref("globalBudget",e.target.value);repaintSurebets()});
document.getElementById("sportFilter").addEventListener("change",e=>{savePref("sportFilter",e.target.value);repaintSurebets()});
document.getElementById("radarSport")?.addEventListener("change",e=>{savePref("radarSport",e.target.value);renderRadar()});
document.getElementById("radarGap")?.addEventListener("input",e=>{savePref("radarGap",e.target.value);renderRadar()});
document.getElementById("valueSport")?.addEventListener("change",e=>{savePref("valueSport",e.target.value);renderValuebets()});
document.getElementById("valueMinEdge")?.addEventListener("input",e=>{savePref("valueMinEdge",e.target.value);renderValuebets()});
document.getElementById("minFilter").addEventListener("input",e=>{savePref("minFilter",e.target.value);repaintSurebets()});
document.getElementById("couponSearch").addEventListener("input",e=>{savePref("couponSearch",e.target.value);renderEventCatalog()});
document.getElementById("couponSport").addEventListener("change",e=>{savePref("couponSport",e.target.value);openEventKey="";renderEventCatalog()});
document.getElementById("couponStake").addEventListener("input",e=>{savePref("couponStake",e.target.value);const legs=currentLegs();renderCouponTotal(legs);renderCouponRanking(legs)});
document.getElementById("clearCouponBtn").addEventListener("click",clearCoupon);
document.getElementById("refreshBtn").addEventListener("click",async()=>{
  const b=document.getElementById("refreshBtn");b.disabled=true;b.textContent="↻ odświeżam…";
  try{await load()}catch{document.getElementById("statusText").textContent="brak danych"}
  b.disabled=false;b.textContent="↻ Odśwież";
});
document.addEventListener("input",e=>{
  if(e.target.classList.contains("budget")){
    budget=Math.max(1,Number(e.target.value)||1);
    document.getElementById("globalBudget").value=budget;
    savePref("globalBudget",budget);
    repaintSurebets();
  }
});

document.addEventListener("click",e=>{
  const target=e.target instanceof Element?e.target:null;
  const btn=target?.closest("[data-info]");
  if(!btn)return;
  e.preventDefault();
  e.stopPropagation();
  e.stopImmediatePropagation?.();
  openInfo(btn.dataset.info);
},true);
document.getElementById("infoModalClose")?.addEventListener("click",closeInfo);
document.getElementById("infoModalBackdrop")?.addEventListener("click",closeInfo);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeInfo()});

window.selectBook=selectBook;
window.toggleEvent=toggleEvent;
window.addCoupon=addCoupon;
window.removeCoupon=removeCoupon;

restoreStaticPrefs();
decorateStaticHelp();
budget=Math.max(1,Number(document.getElementById("globalBudget")?.value||budget)||budget);
initAuth();
saveCoupon();
load().catch(()=>{
  document.getElementById("statusText").textContent="brak danych";
  document.getElementById("statusDot").style.background="#ff6b8b";
});
setInterval(()=>load().catch(()=>{}),3000);
