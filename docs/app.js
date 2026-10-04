const BOOK_META={
  Betclic:{abbr:"BC",url:"https://www.betclic.pl/"},
  Fortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},eFortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},
  Superbet:{abbr:"SB",url:"https://superbet.pl/"},STS:{abbr:"STS",url:"https://www.sts.pl/"},
  Forbet:{abbr:"FB",url:"https://www.iforbet.pl/"},LVBet:{abbr:"LV",url:"https://lvbet.pl/"},
  ETOTO:{abbr:"ET",url:"https://www.etoto.pl/"},eToto:{abbr:"ET",url:"https://www.etoto.pl/"},Etoto:{abbr:"ET",url:"https://www.etoto.pl/"},
  Betfan:{abbr:"BF",url:"https://betfan.pl/"},Fuksiarz:{abbr:"FU",url:"https://fuksiarz.pl/"},
  TotalBet:{abbr:"TB",url:"https://totalbet.pl/"},Totalbet:{abbr:"TB",url:"https://totalbet.pl/"},"Total Bet":{abbr:"TB",url:"https://totalbet.pl/"},
  Betters:{abbr:"BE",url:"https://betters.pl/"},LeBull:{abbr:"LB",url:"https://lebull.pl/"},
  AdmiralBet:{abbr:"AB",url:"https://admiralbet.pl/"},BetSport:{abbr:"BS",url:"https://betsport.pl/"},Betsport:{abbr:"BS",url:"https://betsport.pl/"},
  ComeOn:{abbr:"CO",url:"https://www.comeon.com/pl"},PZBuk:{abbr:"PZ",url:"https://pzbuk.pl/"}
};

const fmt=n=>new Intl.NumberFormat("pl-PL",{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n)||0);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const meta=b=>BOOK_META[b]||{abbr:String(b||"?").slice(0,3).toUpperCase(),url:"#"};
const linkFor=o=>o?.bookmaker_url||o?.source_url||meta(o?.bookmaker).url||"#";

let data={latest:[],stats:{},scan_preview:[],coupon_catalog:[]};
let budget=50;
let coupon=loadCoupon();

const DATA_ENDPOINTS=[
  "data/latest.json",
  "https://raw.githubusercontent.com/xlvlcl/arbi/main/docs/data/latest.json"
];

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
  if(!expected)return true;
  try{
    const saved=JSON.parse(localStorage.getItem(AUTH_KEY)||"null");
    if(!saved||saved.hash!==expected)return false;
    if(saved.forever)return true;
    return Number(saved.expires||0)>Date.now();
  }catch{return false}
}
function showGate(){document.getElementById("authGate").hidden=false;document.body.classList.add("locked");setTimeout(()=>document.getElementById("authPassword")?.focus(),80)}
function hideGate(){document.getElementById("authGate").hidden=true;document.body.classList.remove("locked")}
function lockNow(){localStorage.removeItem(AUTH_KEY);sessionStorage.removeItem(AUTH_KEY);showGate()}
async function initAuth(){
  const expected=authHash();
  if(!expected){hideGate();return}
  if(sessionStorage.getItem(AUTH_KEY)===expected||rememberedAccessValid()){hideGate();return}
  showGate();
}
document.getElementById("authForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const expected=authHash(),value=document.getElementById("authPassword").value;
  const actual=await sha256(value);
  const error=document.getElementById("authError");
  if(actual!==expected){error.textContent="Nieprawidłowe hasło.";return}
  error.textContent="";
  const mode=document.querySelector('input[name="remember"]:checked')?.value||"30";
  if(mode==="session")sessionStorage.setItem(AUTH_KEY,expected);
  else if(mode==="forever")localStorage.setItem(AUTH_KEY,JSON.stringify({hash:expected,forever:true}));
  else localStorage.setItem(AUTH_KEY,JSON.stringify({hash:expected,expires:Date.now()+30*24*60*60*1000}));
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
      data=next;
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
      <div class="odds-badge"><div class="odds-stack"><div class="odds">${Number(l.odds).toFixed(2)}</div><div class="stake">${fmt(l.stake)} zł</div></div>${link&&link!=="#"?`<a class="btn btn-small open-btn" href="${esc(link)}" target="_blank" rel="noopener">Otwórz mecz ↗</a>`:""}</div>
      </div>${alternativesHtml(l)}</div>`;
  }).join("");
}
function card(a,bankroll){
  const s=scale(a,bankroll);
  return `<article class="arb glass"><div class="arb-top"><div class="arb-left"><div class="arb-line"><span class="sport-tag">${esc(a.sport)}</span><span class="profit">+${Number(a.profit_pct||0).toFixed(2)}%</span><span class="market">${esc(a.market||"Rynek")}</span></div><h2 class="event">${esc(a.event)}</h2></div><div class="status-pill status-compact"><span class="dot"></span> potwierdzony</div></div>
  <div class="arb-body"><div class="legs">${legsHtml(a,bankroll)}</div><aside class="calc"><div class="calc-title">Budżet</div><div class="calc-input"><input class="budget" type="number" min="1" step="1" value="${Number(bankroll)}"><span>PLN</span></div><div class="calc-grid"><div class="calc-stat"><span>Wkład</span><strong>${fmt(bankroll)} zł</strong></div><div class="calc-stat"><span>Wypłata min.</span><strong>${fmt(s.payout)} zł</strong></div><div class="calc-stat full"><span>Zysk min.</span><strong class="green">+${fmt(s.profit)} zł</strong></div></div>${s.legs.map(l=>`<div class="leg-mini"><span>${esc(l.bookmaker)} · ${esc(l.selection)}</span><strong>${fmt(l.stake)} zł</strong></div>`).join("")}<div class="warning">Sprawdź kursy bezpośrednio przed postawieniem obu stron.</div></aside></div></article>`;
}

function addToCouponByPreview(rowIndex,selection){
  const row=(data.scan_preview||[])[rowIndex];if(!row)return;
  const catalog=(data.coupon_catalog||[]).find(x=>x.event===row.event&&x.market===row.market);
  if(catalog)addCoupon(catalog.id,selection);
}
function previewHtml(){
  const sport=document.getElementById("sportFilter").value;
  const rows=(data.scan_preview||[]).filter(x=>!sport||x.sport===sport).slice(0,36);
  if(!rows.length)return "";
  return `<section class="scan-preview"><div class="scan-preview-head"><div><strong>Ostatnio zeskanowane rynki</strong><span>Kliknij kurs, żeby przejść do buka, albo dodaj typ do kuponu.</span></div><span>${rows.length} pokazanych</span></div><div class="scan-preview-grid">${rows.map((x,i)=>{
    const originalIndex=(data.scan_preview||[]).indexOf(x);
    return `<div class="scan-row glass"><div class="scan-row-top"><span class="sport-tag">${esc(x.sport||"Sport")}</span><span class="market">${esc(x.market||"Rynek")}</span></div><div class="scan-event">${esc(x.event||"Zdarzenie")}</div><div class="scan-outcomes">${(x.best||[]).map(q=>{
      const link=linkFor(q),m=meta(q.bookmaker);
      return `<div class="scan-outcome"><div><b>${esc(q.selection)}</b><span>${esc(q.bookmaker)} · ${Number(q.odds||0).toFixed(2)}</span></div><div class="scan-outcome-actions">${link&&link!=="#"?`<a class="mini-link" href="${esc(link)}" target="_blank" rel="noopener">${esc(m.abbr)} ↗</a>`:""}<button class="mini-add" onclick='addToCouponByPreview(${originalIndex},${JSON.stringify(String(q.selection))})'>+ kupon</button></div></div>`;
    }).join("")}</div></div>`;
  }).join("")}</div></section>`;
}

function renderSources(){
  const sources=data.stats?.sources||{};
  const el=document.getElementById("sourceStrip");
  const entries=Object.entries(sources);
  if(!entries.length){el.innerHTML="";return}
  el.innerHTML=entries.map(([name,s])=>`<span class="source-chip"><b>${esc(name)}</b> ${Number(s.markets||0)} ryn.</span>`).join("");
}
function repaintSurebets(){
  const sport=document.getElementById("sportFilter").value;
  const min=Number(document.getElementById("minFilter").value)||0;
  const items=(data.latest||[]).filter(a=>(Number(a.profit_pct)||0)>=min&&(!sport||a.sport===sport)).sort((a,b)=>(Number(b.profit_pct)||0)-(Number(a.profit_pct)||0));
  document.getElementById("count").textContent=items.length;
  document.getElementById("best").textContent=items.length?`+${Number(items[0].profit_pct).toFixed(2)}%`:"—";
  const ev=Number(data.stats?.events||0),mk=Number(data.stats?.markets_scanned??data.stats?.markets??0);
  document.getElementById("markets").textContent=`${ev} / ${mk}`;
  const ts=data.last_scan||data.generated_at;
  document.getElementById("last").textContent=ts?new Date(Number(ts)*1000).toLocaleString("pl-PL"):"—";
  const errs=data.errors||[],age=ts?Date.now()/1000-Number(ts):Infinity,complete=data.stats?.exhaustive_complete;
  let status="monitoring aktywny",dot="var(--green)";
  if(age>15*60){status="skan opóźniony";dot="#fb7185"}else if(age>7*60){status="czekam na nowy skan";dot="#fbbf24"}else if(complete===false){status="skan częściowy";dot="#fbbf24"}else if(errs.length){status="monitoring aktywny · część źródeł niedostępna";dot="#fbbf24"}
  document.getElementById("statusText").textContent=status;document.getElementById("statusDot").style.background=dot;
  renderSources();
  const sports=[...new Set([...(data.stats?.sports||[]),...(data.latest||[]).map(x=>x.sport),...(data.scan_preview||[]).map(x=>x.sport),...(data.coupon_catalog||[]).map(x=>x.sport)].filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("sportFilter"),current=sel.value;sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");sel.value=sports.includes(current)?current:"";
  const empty=`<div class="empty glass"><div class="icon">⌁</div><h3>Brak potwierdzonych surebetów w tym skanie</h3><p>Skaner odczytał ${ev} zdarzeń i ${mk} rynków. Poniżej widać rynki i najlepsze kursy, które faktycznie znalazł.</p></div>`;
  document.getElementById("list").innerHTML=(items.length?items.slice(0,200).map(a=>card(a,budget)).join(""):empty)+previewHtml();
}

// ---------- COUPON ----------
function loadCoupon(){try{return JSON.parse(localStorage.getItem("arbi_coupon_v1")||"[]")||[]}catch{return []}}
function saveCoupon(){localStorage.setItem("arbi_coupon_v1",JSON.stringify(coupon));document.getElementById("couponCount").textContent=coupon.length}
function catalogById(id){return (data.coupon_catalog||[]).find(x=>x.id===id)}
function addCoupon(id,selection){
  const item=catalogById(id);if(!item)return;
  const sel=(item.selections||[]).find(x=>x.selection===selection);if(!sel)return;
  const key=`${id}|${selection}`;
  if(coupon.some(x=>x.key===key))return;
  coupon.push({key,id,selection,event:item.event,sport:item.sport,market:item.market});saveCoupon();renderCoupon();switchView("coupon");
}
function removeCoupon(key){coupon=coupon.filter(x=>x.key!==key);saveCoupon();renderCoupon()}
function clearCoupon(){coupon=[];saveCoupon();renderCoupon()}
function currentLegs(){
  return coupon.map(c=>{
    const item=catalogById(c.id);if(!item)return null;
    const selection=(item.selections||[]).find(x=>x.selection===c.selection);if(!selection)return null;
    return {...c,item,offers:selection.offers||[],best_odds:selection.best_odds,best_bookmaker:selection.best_bookmaker};
  }).filter(Boolean);
}
function commonBookRanking(legs){
  if(!legs.length)return [];
  let common=new Set((legs[0].offers||[]).map(o=>o.bookmaker));
  for(const leg of legs.slice(1)){const books=new Set((leg.offers||[]).map(o=>o.bookmaker));common=new Set([...common].filter(x=>books.has(x)))}
  const rows=[];
  for(const book of common){
    const offers=legs.map(leg=>(leg.offers||[]).find(o=>o.bookmaker===book));
    if(offers.some(x=>!x))continue;
    const total=offers.reduce((a,o)=>a*Number(o.odds||1),1);
    rows.push({book,total,offers});
  }
  return rows.sort((a,b)=>b.total-a.total);
}
function independentBest(legs){
  const offers=legs.map(leg=>(leg.offers||[]).slice().sort((a,b)=>Number(b.odds)-Number(a.odds))[0]).filter(Boolean);
  return {offers,total:offers.length===legs.length?offers.reduce((a,o)=>a*Number(o.odds||1),1):0};
}
function eventLinksHtml(row,legs){
  return `<div class="rank-links">${row.offers.map((o,i)=>{const u=linkFor(o);return u&&u!=="#"?`<a href="${esc(u)}" target="_blank" rel="noopener">${i+1}. mecz ↗</a>`:`<span>${i+1}. brak linku</span>`}).join("")}</div>`;
}
function renderCouponRanking(legs){
  const wrap=document.getElementById("couponRanking"),stake=Math.max(1,Number(document.getElementById("couponStake").value)||1),chosen=document.getElementById("couponBookFilter").value;
  if(!legs.length){wrap.innerHTML='<div class="coupon-empty">Dodaj co najmniej jeden typ.</div>';return}
  const rankings=commonBookRanking(legs),bestEach=independentBest(legs);
  const books=[...new Set(legs.flatMap(l=>(l.offers||[]).map(o=>o.bookmaker)))].sort();
  const select=document.getElementById("couponBookFilter"),prev=select.value;select.innerHTML='<option value="">Automatycznie — ranking</option>'+books.map(b=>`<option value="${esc(b)}">${esc(b)}</option>`).join("");select.value=books.includes(prev)?prev:"";
  let html="";
  if(chosen){
    const row=rankings.find(r=>r.book===chosen);
    html+=`<div class="rank-section"><div class="rank-section-title">Wybrany bukmacher</div>${row?`<div class="rank-card best"><div><span>${esc(row.book)}</span><strong>${row.total.toFixed(2)}</strong></div><small>Potencjalna wypłata przy ${fmt(stake)} zł: ${fmt(stake*row.total)} zł</small>${eventLinksHtml(row,legs)}</div>`:`<div class="coupon-empty">${esc(chosen)} nie ma obecnie wszystkich zaznaczonych typów.</div>`}</div>`;
  }else{
    html+=`<div class="rank-section"><div class="rank-section-title">Najlepszy jeden buk dla całego kuponu</div>${rankings.length?rankings.slice(0,6).map((r,i)=>`<div class="rank-card ${i===0?'best':''}"><div><span>${i+1}. ${esc(r.book)}</span><strong>${r.total.toFixed(2)}</strong></div><small>${fmt(stake)} zł → ${fmt(stake*r.total)} zł brutto</small>${eventLinksHtml(r,legs)}</div>`).join(""):'<div class="coupon-empty">Żaden pojedynczy bukmacher nie ma wszystkich tych typów w aktualnym skanie.</div>'}</div>`;
  }
  html+=`<div class="rank-section"><div class="rank-section-title">Najlepszy kurs każdej nogi osobno</div><div class="rank-card split"><div><span>Łączny iloczyn najlepszych kursów</span><strong>${bestEach.total?bestEach.total.toFixed(2):'—'}</strong></div>${bestEach.offers.map((o,i)=>{const u=linkFor(o),leg=legs[i];return `<div class="split-leg"><span>${i+1}. ${esc(leg?.event||'')} · ${esc(leg?.selection||'')}</span><b>${esc(o.bookmaker)} ${Number(o.odds).toFixed(2)}</b>${u&&u!=="#"?`<a href="${esc(u)}" target="_blank" rel="noopener">Otwórz ↗</a>`:''}</div>`}).join("")}</div></div>`;
  wrap.innerHTML=html;
}
function renderCouponLegs(legs){
  document.getElementById("couponTitle").textContent=`${legs.length} ${legs.length===1?'typ':'typy'}`;
  document.getElementById("couponLegs").innerHTML=legs.length?legs.map(l=>`<div class="coupon-leg"><div><span class="sport-tag">${esc(l.sport)}</span><strong>${esc(l.event)}</strong><small>${esc(l.market)} → ${esc(l.selection)}</small></div><button onclick='removeCoupon(${JSON.stringify(l.key)})'>×</button></div>`).join(""):'<div class="coupon-empty">Jeszcze nic nie zaznaczyłeś.</div>';
}
function renderCouponCatalog(){
  const q=document.getElementById("couponSearch").value.trim().toLowerCase(),sport=document.getElementById("couponSport").value;
  const catalog=(data.coupon_catalog||[]).filter(x=>(!sport||x.sport===sport)&&(!q||`${x.event} ${x.market} ${x.sport}`.toLowerCase().includes(q))).slice(0,100);
  const sports=[...new Set((data.coupon_catalog||[]).map(x=>x.sport).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("couponSport"),prev=sel.value;sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");sel.value=sports.includes(prev)?prev:"";
  document.getElementById("couponCatalog").innerHTML=catalog.length?catalog.map(item=>`<div class="catalog-card"><div class="catalog-head"><div><span class="sport-tag">${esc(item.sport)}</span><strong>${esc(item.event)}</strong><small>${esc(item.market)}</small></div><span class="source-mini">${esc((item.sources||[]).join(' + '))}</span></div><div class="catalog-selections">${(item.selections||[]).map(s=>`<button class="selection-btn" onclick='addCoupon(${JSON.stringify(item.id)},${JSON.stringify(String(s.selection))})'><span>${esc(s.selection)}</span><b>${Number(s.best_odds||0).toFixed(2)}</b><small>${esc(s.best_bookmaker||'')}</small><em>+ dodaj</em></button>`).join("")}</div></div>`).join(""):'<div class="coupon-empty">Brak pasujących rynków w ostatnim skanie.</div>';
}
function renderCoupon(){const legs=currentLegs();renderCouponLegs(legs);renderCouponCatalog();renderCouponRanking(legs);saveCoupon()}

// ---------- VIEWS / EVENTS ----------
function switchView(name){
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  document.querySelectorAll(".view").forEach(v=>{const on=v.id===`${name}View`;v.classList.toggle("active",on);v.hidden=!on});
  if(name==="coupon")renderCoupon();
}
function repaint(){repaintSurebets();renderCoupon();document.getElementById("couponCount").textContent=coupon.length}

document.querySelectorAll(".tab-btn").forEach(b=>b.addEventListener("click",()=>switchView(b.dataset.view)));
document.getElementById("globalBudget").addEventListener("input",e=>{budget=Math.max(1,Number(e.target.value)||1);repaintSurebets()});
document.getElementById("sportFilter").addEventListener("change",repaintSurebets);
document.getElementById("minFilter").addEventListener("input",repaintSurebets);
document.getElementById("couponSearch").addEventListener("input",renderCouponCatalog);
document.getElementById("couponSport").addEventListener("change",renderCouponCatalog);
document.getElementById("couponStake").addEventListener("input",()=>renderCouponRanking(currentLegs()));
document.getElementById("couponBookFilter").addEventListener("change",()=>renderCouponRanking(currentLegs()));
document.getElementById("clearCouponBtn").addEventListener("click",clearCoupon);
document.getElementById("refreshBtn").addEventListener("click",async()=>{const b=document.getElementById("refreshBtn");b.disabled=true;b.textContent="↻ odświeżam…";try{await load()}catch{document.getElementById("statusText").textContent="brak danych"}b.disabled=false;b.textContent="↻ Odśwież"});
document.addEventListener("input",e=>{if(e.target.classList.contains("budget")){budget=Math.max(1,Number(e.target.value)||1);document.getElementById("globalBudget").value=budget;repaintSurebets()}});

window.addCoupon=addCoupon;window.removeCoupon=removeCoupon;window.addToCouponByPreview=addToCouponByPreview;

initAuth();saveCoupon();
load().catch(()=>{document.getElementById("statusText").textContent="brak danych";document.getElementById("statusDot").style.background="#fb7185"});
setInterval(()=>load().catch(()=>{}),3000);
