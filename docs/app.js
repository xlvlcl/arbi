const BOOK_META={
  Betclic:{abbr:"BC",url:"https://www.betclic.pl/"},
  Fortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},
  eFortuna:{abbr:"FO",url:"https://www.efortuna.pl/"},
  Superbet:{abbr:"SB",url:"https://superbet.pl/"},
  STS:{abbr:"STS",url:"https://www.sts.pl/"},
  Forbet:{abbr:"FB",url:"https://www.iforbet.pl/"},
  LVBet:{abbr:"LV",url:"https://lvbet.pl/"},
  ETOTO:{abbr:"ET",url:"https://www.etoto.pl/"},
  eToto:{abbr:"ET",url:"https://www.etoto.pl/"},
  Etoto:{abbr:"ET",url:"https://www.etoto.pl/"},
  Betfan:{abbr:"BF",url:"https://betfan.pl/"},
  Fuksiarz:{abbr:"FU",url:"https://fuksiarz.pl/"},
  TotalBet:{abbr:"TB",url:"https://totalbet.pl/"},
  Totalbet:{abbr:"TB",url:"https://totalbet.pl/"},
  "Total Bet":{abbr:"TB",url:"https://totalbet.pl/"},
  Betters:{abbr:"BE",url:"https://betters.pl/"},
  LeBull:{abbr:"LB",url:"https://lebull.pl/"},
  AdmiralBet:{abbr:"AB",url:"https://admiralbet.pl/"},
  BetSport:{abbr:"BS",url:"https://betsport.pl/"},
  Betsport:{abbr:"BS",url:"https://betsport.pl/"},
  ComeOn:{abbr:"CO",url:"https://www.comeon.com/pl"},
  PZBuk:{abbr:"PZ",url:"https://pzbuk.pl/"}
};

const fmt=n=>new Intl.NumberFormat("pl-PL",{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n)||0);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const meta=b=>BOOK_META[b]||{abbr:String(b||"?").slice(0,3).toUpperCase(),url:"#"};

function scale(a,budget){
  const base=Number(a.bankroll)||50, ratio=budget/base;
  const legs=(a.legs||[]).map(l=>({...l,stake:(Number(l.stake)||0)*ratio,payout:(Number(l.payout)||0)*ratio}));
  const payout=(Number(a.guaranteed_payout)||0)*ratio;
  return {legs,payout,profit:payout-budget};
}

function alternativesHtml(l){
  const alts=(l.alternatives||[]).slice(0,5);
  if(!alts.length)return "";
  return `<div class="alternatives"><span class="alt-title">Inni:</span>${alts.map(a=>{
    const m=meta(a.bookmaker), link=a.bookmaker_url||a.source_url||m.url;
    const chip=`<span class="alt-logo">${esc(m.abbr)}</span><span>${esc(a.bookmaker)}</span><b>${Number(a.odds).toFixed(2)}</b>`;
    return link&&link!=="#"?`<a class="alt-chip" href="${esc(link)}" target="_blank" rel="noopener">${chip}</a>`:`<span class="alt-chip">${chip}</span>`;
  }).join("")}</div>`;
}

function legsHtml(a,budget){
  const s=scale(a,budget);
  return s.legs.map(l=>{
    const m=meta(l.bookmaker), link=l.bookmaker_url||l.source_url||m.url;
    return `<div class="leg">
      <div class="leg-main">
        <div class="book"><div class="book-logo">${esc(m.abbr)}</div><div class="book-info"><div class="book-name">${esc(l.bookmaker)}</div><div class="book-sub">najlepszy kurs</div></div></div>
        <div class="pick"><div class="pick-label">Wybór</div><div class="pick-value">${esc(l.selection)}</div></div>
        <div class="odds-badge"><div class="odds-stack"><div class="odds">${Number(l.odds).toFixed(2)}</div><div class="stake">${fmt(l.stake)} zł</div></div>${link&&link!=="#"?`<a class="btn btn-small open-btn" href="${esc(link)}" target="_blank" rel="noopener">Otwórz ↗</a>`:""}</div>
      </div>
      ${alternativesHtml(l)}
    </div>`;
  }).join("");
}

function card(a,budget){
  const s=scale(a,budget);
  return `<article class="arb glass" data-profit="${Number(a.profit_pct)||0}" data-sport="${esc(a.sport)}">
    <div class="arb-top">
      <div class="arb-left"><div class="arb-line"><span class="sport-tag">${esc(a.sport)}</span><span class="profit">+${Number(a.profit_pct||0).toFixed(2)}%</span><span class="market">${esc(a.market||"Rynek")}</span></div><h2 class="event">${esc(a.event)}</h2></div>
      <div class="status-pill status-compact"><span class="dot"></span> potwierdzony</div>
    </div>
    <div class="arb-body"><div class="legs">${legsHtml(a,budget)}</div>
      <aside class="calc"><div class="calc-title">Budżet</div>
        <div class="calc-input"><input class="budget" data-key="${esc(a.event+"|"+a.market)}" type="number" min="1" step="1" value="${fmt(budget).replace(",",".")}"><span>PLN</span></div>
        <div class="calc-grid"><div class="calc-stat"><span>Wkład</span><strong>${fmt(budget)} zł</strong></div><div class="calc-stat"><span>Wypłata min.</span><strong>${fmt(s.payout)} zł</strong></div><div class="calc-stat full"><span>Zysk min.</span><strong style="color:var(--green)">+${fmt(s.profit)} zł</strong></div></div>
        ${s.legs.map(l=>`<div class="leg-mini"><span>${esc(l.bookmaker)} · ${esc(l.selection)}</span><strong>${fmt(l.stake)} zł</strong></div>`).join("")}
        <div class="warning">Sprawdź kursy bezpośrednio przed postawieniem obu stron.</div>
      </aside>
    </div>
  </article>`;
}

let data={latest:[],stats:{}}, budget=50;

const DATA_ENDPOINTS=[
  "https://raw.githubusercontent.com/xlvlcl/arbi/main/docs/data/latest.json",
  "data/latest.json"
];

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
    }catch(err){lastError=err;}
  }
  throw lastError||new Error("data");
}

function repaint(){
  const sport=document.getElementById("sportFilter").value;
  const min=Number(document.getElementById("minFilter").value)||0;
  const items=(data.latest||[])
    .filter(a=>(Number(a.profit_pct)||0)>=min&&(!sport||a.sport===sport))
    .sort((a,b)=>(Number(b.profit_pct)||0)-(Number(a.profit_pct)||0));

  document.getElementById("count").textContent=items.length;
  document.getElementById("best").textContent=items.length?`+${Number(items[0].profit_pct).toFixed(2)}%`:"—";
  document.getElementById("markets").textContent=data.stats?.markets_scanned??data.stats?.markets??0;
  const ts=data.last_scan||data.generated_at;
  document.getElementById("last").textContent=ts?new Date(Number(ts)*1000).toLocaleString("pl-PL"):"—";

  const errs=data.errors||[];
  const age=ts?Date.now()/1000-Number(ts):Infinity;
  const complete=data.stats?.exhaustive_complete;
  let status="monitoring aktywny", dot="var(--green)";
  if(age>15*60){status="skan opóźniony";dot="#fb7185";}
  else if(age>8*60){status="czekam na nowy skan";dot="#fbbf24";}
  else if(complete===false){status="skan częściowy";dot="#fbbf24";}
  else if(errs.length){status="uwaga";dot="#fbbf24";}
  document.getElementById("statusText").textContent=status;
  document.getElementById("statusDot").style.background=dot;

  const sports=[...new Set((data.latest||[]).map(x=>x.sport).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pl"));
  const sel=document.getElementById("sportFilter"), current=sel.value;
  sel.innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(s=>`<option>${esc(s)}</option>`).join("");
  sel.value=sports.includes(current)?current:"";

  document.getElementById("list").innerHTML=items.length?items.slice(0,200).map(a=>card(a,budget)).join(""):`<div class="empty glass"><div class="icon">⌁</div><h3>Brak potwierdzonych surebetów</h3><p>System pokaże tylko kompletne rynki, gdzie wszystkie możliwe wyniki są pokryte.</p></div>`;
}

document.getElementById("globalBudget").addEventListener("input",e=>{budget=Math.max(1,Number(e.target.value)||1);repaint()});
document.getElementById("sportFilter").addEventListener("change",repaint);
document.getElementById("minFilter").addEventListener("input",repaint);
document.getElementById("refreshBtn").addEventListener("click",async()=>{
  const b=document.getElementById("refreshBtn"); b.disabled=true; b.textContent="↻ odświeżam…";
  try{await load()}catch(e){document.getElementById("statusText").textContent="brak danych"}
  b.disabled=false; b.textContent="↻ Odśwież";
});
document.addEventListener("input",e=>{if(e.target.classList.contains("budget")){budget=Math.max(1,Number(e.target.value)||1);document.getElementById("globalBudget").value=budget;repaint()}});

load().catch(()=>{document.getElementById("statusText").textContent="brak danych";document.getElementById("statusDot").style.background="#fb7185"});
setInterval(()=>load().catch(()=>{}),3000);
