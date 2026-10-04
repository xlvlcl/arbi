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

let data={latest:[],stats:{},scan_preview:[],coupon_catalog:[]};
let budget=50;
let coupon=loadCoupon();
let selectedBook=localStorage.getItem("arbi_coupon_book_v16")||"";
let openEventKey="";
let currentView="surebets";

const DATA_ENDPOINTS=[
  "data/latest.json",
  "https://raw.githubusercontent.com/xlvlcl/arbi/main/docs/data/latest.json"
];

function normalizePayload(payload){
  payload.latest=Array.isArray(payload.latest)?payload.latest:[];
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
async function sha256(value){
  const bytes=new TextEncoder().encode(value);
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
function authHash(){return String(window.ARBI_AUTH_HASH||"").trim().toLowerCase()}
function rememberedAccessValid(){
  const expected=authHash();
  if(!expected)return false;
  try{
    const saved=JSON.parse(localStorage.getItem(AUTH_KEY)||"null");
    return Boolean(saved&&saved.hash===expected&&saved.forever===true);
  }catch{return false}
}
function showGate(message=""){
  const gate=document.getElementById("authGate");
  gate.hidden=false;
  document.body.classList.add("locked");
  const error=document.getElementById("authError");
  if(error&&message)error.textContent=message;
  setTimeout(()=>document.getElementById("authPassword")?.focus(),80);
}
function hideGate(){
  document.getElementById("authGate").hidden=true;
  document.body.classList.remove("locked");
}
function lockNow(){localStorage.removeItem(AUTH_KEY);showGate()}
async function initAuth(){
  const expected=authHash();
  if(!expected){
    showGate("Blokada nie jest skonfigurowana. Dodaj sekret SITE_PASSWORD i uruchom workflow ponownie.");
    return;
  }
  if(rememberedAccessValid()){hideGate();return}
  showGate();
}
document.getElementById("authForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const expected=authHash(),error=document.getElementById("authError");
  if(!expected){error.textContent="Brak skonfigurowanego hasła SITE_PASSWORD.";return}
  const actual=await sha256(document.getElementById("authPassword").value);
  if(actual!==expected){error.textContent="Nieprawidłowe hasło.";return}
  error.textContent="";
  localStorage.setItem(AUTH_KEY,JSON.stringify({hash:expected,forever:true}));
  document.getElementById("authPassword").value="";
  hideGate();
});
document.getElementById("lockBtn").addEventListener("click",lockNow);

// ---------- DATA ----------
async function load(){
  let lastError=null;
  for(const endpoint of DATA_ENDPOINTS){
    try{
      const sep=endpoint.includes("?")?"&":"?";
      const r=await fetch(`${endpoint}${sep}t=${Date.now()}`,{cache:"no-store",mode:"cors"});
      if(!r.ok)throw new Error(`HTTP ${r.status}`);
      const next=await r.json();
      if(!next||typeof next!=="object")throw new Error("invalid data");
      data=normalizePayload(next);
      ensureSelectedBook();
      repaint();
      return;
    }catch(err){lastError=err}
  }
  throw lastError||new Error("data");
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
    const m=meta(l.bookmaker),link=linkFor(l);
    return `<div class="leg"><div class="leg-main">
      <div class="book"><div class="book-logo">${esc(m.abbr)}</div><div class="book-info"><div class="book-name">${esc(l.bookmaker)}</div><div class="book-sub">najlepszy kurs</div></div></div>
      <div class="pick"><div class="pick-label">Wybór</div><div class="pick-value">${esc(l.selection)}</div></div>
      <div class="odds-badge"><div class="odds-stack"><div class="odds">${Number(l.odds).toFixed(2)}</div><div class="stake">${fmt(l.stake)} zł</div></div>${link&&link!=="#"?`<a class="btn btn-small open-btn" href="${esc(link)}" target="_blank" rel="noopener">Otwórz ↗</a>`:""}</div>
      </div>${alternativesHtml(l)}</div>`;
  }).join("");
}
function card(a,bankroll){
  const s=scale(a,bankroll);
  return `<article class="arb glass"><div class="arb-top"><div class="arb-left"><div class="arb-line"><span class="sport-tag">${esc(a.sport)}</span><span class="profit">+${Number(a.profit_pct||0).toFixed(2)}%</span><span class="market">${esc(a.market||"Rynek")}</span></div><h2 class="event">${esc(a.event)}</h2></div><div class="status-pill status-compact"><span class="dot"></span> potwierdzony</div></div>
  <div class="arb-body"><div class="legs">${legsHtml(a,bankroll)}</div><aside class="calc"><div class="calc-title">Budżet</div><div class="calc-input"><input class="budget" type="number" min="1" step="1" value="${Number(bankroll)}"><span>PLN</span></div><div class="calc-grid"><div class="calc-stat"><span>Wkład</span><strong>${fmt(bankroll)} zł</strong></div><div class="calc-stat"><span>Wypłata min.</span><strong>${fmt(s.payout)} zł</strong></div><div class="calc-stat full"><span>Zysk min.</span><strong class="green">+${fmt(s.profit)} zł</strong></div></div>${s.legs.map(l=>`<div class="leg-mini"><span>${esc(l.bookmaker)} · ${esc(l.selection)}</span><strong>${fmt(l.stake)} zł</strong></div>`).join("")}<div class="warning">Sprawdź kursy bezpośrednio przed postawieniem obu stron.</div></aside></div></article>`;
}
function previewHtml(){
  const sport=document.getElementById("sportFilter").value;
  const rows=(data.scan_preview||[]).filter(x=>!sport||x.sport===sport).slice(0,24);
  if(!rows.length)return "";
  return `<section class="scan-preview"><div class="scan-preview-head"><div><strong>Ostatnio zeskanowane rynki</strong><span>Podgląd danych — nie są to surebety.</span></div><span>${rows.length} pokazanych</span></div><div class="scan-preview-grid">${rows.map(x=>`<div class="scan-row glass"><div class="scan-row-top"><span class="sport-tag">${esc(x.sport||"Sport")}</span><span class="market">${esc(x.market||"Rynek")}</span></div><div class="scan-event">${esc(x.event||"Zdarzenie")}</div><div class="scan-best">${(x.best||[]).slice(0,4).map(q=>`<span><b>${esc(q.selection)}</b> ${Number(q.odds||0).toFixed(2)} <small>${esc(q.bookmaker)}</small></span>`).join("")}</div></div>`).join("")}</div></section>`;
}
function renderSources(){
  const sources=data.stats?.sources||{};
  const rows=Object.entries(sources);
  document.getElementById("sourceStrip").innerHTML=rows.map(([name,s])=>`<span class="source-chip"><b>${esc(name)}</b> ${Number(s.markets||0)} rynków</span>`).join("");
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
  const sel=document.getElementById("sportFilter"),current=sel.value;
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

    const key=`${item.sport}|${item.event}`;
    if(!groups.has(key)){
      groups.set(key,{
        key,event:item.event,sport:item.sport,markets:[],eventLink:"",
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
  const sel=document.getElementById("couponSport"),prev=sel.value;
  sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
  sel.value=sports.includes(prev)?prev:"";
}
function toggleEvent(key){
  openEventKey=openEventKey===key?"":key;
  renderEventCatalog();
}
function marketHtml(market,event){
  return `<div class="event-market">
    <div class="event-market-title"><span>${esc(market.market)}</span><small>${market.selections.length} typów</small></div>
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
  let html='<div class="compare-title">Porównanie tego samego kuponu</div>';
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
  currentView=name;
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  document.querySelectorAll(".view").forEach(v=>{
    const on=v.id===`${name}View`;
    v.classList.toggle("active",on);
    v.hidden=!on;
  });
  if(name==="coupon")renderCoupon();
}
function repaint(){
  repaintSurebets();
  if(currentView==="coupon")renderCoupon();
  document.getElementById("couponCount").textContent=coupon.length;
}

// ---------- EVENTS ----------
document.querySelectorAll(".tab-btn").forEach(b=>b.addEventListener("click",()=>switchView(b.dataset.view)));
document.getElementById("globalBudget").addEventListener("input",e=>{budget=Math.max(1,Number(e.target.value)||1);repaintSurebets()});
document.getElementById("sportFilter").addEventListener("change",repaintSurebets);
document.getElementById("minFilter").addEventListener("input",repaintSurebets);
document.getElementById("couponSearch").addEventListener("input",renderEventCatalog);
document.getElementById("couponSport").addEventListener("change",()=>{openEventKey="";renderEventCatalog()});
document.getElementById("couponStake").addEventListener("input",()=>{const legs=currentLegs();renderCouponTotal(legs);renderCouponRanking(legs)});
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
    repaintSurebets();
  }
});

window.selectBook=selectBook;
window.toggleEvent=toggleEvent;
window.addCoupon=addCoupon;
window.removeCoupon=removeCoupon;

initAuth();saveCoupon();
load().catch(()=>{
  document.getElementById("statusText").textContent="brak danych";
  document.getElementById("statusDot").style.background="#ff6b8b";
});
setInterval(()=>load().catch(()=>{}),3000);
