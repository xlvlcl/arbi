'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>new Intl.NumberFormat('pl-PL',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n)||0);
const date=n=>n?new Date(typeof n==='number'?n*1000:n).toLocaleString('pl-PL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
const safeURL=value=>{try{const url=new URL(value,location.href);return url.protocol==='https:'||url.protocol==='http:'?url.href:'#'}catch{return '#'}};
let config={},payload={status:{},opportunities:[],events:[],stats:{}},view='surebets',page=0,inFlight=null,pushReady=null;
const responseCache=new Map();
function pref(key,fallback){try{return localStorage.getItem('arbi_new_'+key)??fallback}catch{return fallback}}
function save(key,value){try{localStorage.setItem('arbi_new_'+key,String(value))}catch{}}
$('budget').value=pref('budget',50);$('minimum').value=pref('minimum',.35);
function budget(){return Math.min(100000,Math.max(3,Number($('budget').value)||50))}
async function getJSON(url,conditional=false){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),conditional?6000:20000);const saved=responseCache.get(url);try{const response=await fetch(url+(url.includes('?')?'&':'?')+'t='+Date.now(),{cache:'no-store',signal:controller.signal,headers:conditional&&saved?.etag?{'If-None-Match':saved.etag}:{}});if(response.status===304&&saved)return saved.data;if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();if(conditional)responseCache.set(url,{data,etag:response.headers?.get('ETag')||''});return data}finally{clearTimeout(timer)}}
async function digest(value){const buffer=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));return [...new Uint8Array(buffer)].map(n=>n.toString(16).padStart(2,'0')).join('')}
function unlock(){ $('gate').hidden=true;$('app').hidden=false;load().catch(showLoadError);initPush() }
$('login').addEventListener('submit',async event=>{event.preventDefault();if(!config.password_hash){$('authError').textContent='Brak konfiguracji dostępu. Sprawdź publikację strony.';return}try{if(await digest($('password').value)!==config.password_hash){$('authError').textContent='Nieprawidłowe hasło.';return}save('access',config.password_hash);$('password').value='';unlock()}catch{$('authError').textContent='Nie udało się sprawdzić hasła. Otwórz stronę przez HTTPS.'}});
$('lock').addEventListener('click',()=>{save('access','');location.reload()});
async function boot(){try{config=await getJSON('config.json');if(!config.password_hash)throw new Error('config');if(pref('access','')===config.password_hash)unlock()}catch{$('authError').textContent='Nie można pobrać konfiguracji strony. Odśwież za chwilę.'}}
function showLoadError(){ $('status').textContent='Nie można pobrać danych';$('statusDot').style.background='var(--red)';$('diagnostic').hidden=false;$('diagnostic').textContent='Nie udało się odczytać wyniku. Ostatnie dane mogą być nieaktualne.';renderCards();renderInsights() }
function validData(data){return data?.version==='NEW-1'&&data.status&&Array.isArray(data.events)&&Array.isArray(data.opportunities)}
function applyData(data){if(!validData(data))throw new Error('format');if(Number(data.status.attempt_at||0)<Number(payload.status.attempt_at||0))return;payload=data;render()}
function load(){
 if(inFlight)return inFlight;
 inFlight=(async()=>{
  let successes=0;
  if(config.data_url){
   try{
    const data=await getJSON(config.data_url,true);applyData(data);successes++;
    const stamp=data.status.state==='error'?data.status.attempt_at:data.status.last_success_at;
    if(Date.now()/1000-Number(stamp||0)<=300&&Number(data.status.attempt_at||0)>=Number(payload.status.attempt_at||0))return;
   }catch{}
  }
  const urls=['data/latest.json'];if(config.repository)urls.push('https://raw.githubusercontent.com/'+config.repository+'/main/fresh/web/data/latest.json');
  await Promise.allSettled(urls.map(async url=>{const data=await getJSON(url);applyData(data);successes++}));
  if(!successes)throw new Error('data');
 })().finally(()=>{inFlight=null});
 return inFlight;
}
function filteredEvents(){const sport=$('sport').value,search=$('search').value.trim().toLocaleLowerCase('pl');return (payload.events||[]).filter(e=>(!sport||e.sport===sport)&&(!search||(e.name+' '+e.league).toLocaleLowerCase('pl').includes(search)))}
function currentOpportunities(){if(['error'].includes(payload.status.state)||Date.now()/1000-Number(payload.status.last_success_at||0)>300)return [];return (payload.opportunities||[]).map(op=>{const calculation=ArbiMath.allocate(op.legs,budget(),op.config||payload.config);return calculation?{...op,...calculation}:null}).filter(Boolean).filter(op=>new Date(op.starts_at).getTime()>Date.now()).filter(op=>op.profit_pct>=Math.max(0,Number($('minimum').value)||0)&&(!$('sport').value||op.sport===$('sport').value)&&(!$('search').value||op.event.toLocaleLowerCase('pl').includes($('search').value.toLocaleLowerCase('pl')))).sort((a,b)=>b.profit_pct-a.profit_pct)}
function render(){const s=payload.status,stats=payload.stats||{},old=$('sport').value;const sports=[...new Set((payload.events||[]).map(e=>e.sport))].sort((a,b)=>a.localeCompare(b,'pl'));$('sport').innerHTML='<option value="">Wszystkie sporty</option>'+sports.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');$('sport').value=sports.includes(old)?old:'';const age=Date.now()/1000-Number(s.last_success_at||0);const good=s.state==='ok'&&age<300;const partial=s.state==='partial'&&age<300;$('status').textContent=good?'Monitoring aktywny':partial?'Skan częściowy':s.state==='error'?'Błąd odczytu':'Dane opóźnione';$('statusDot').style.background=good?'var(--green)':partial?'#e7bd6a':'var(--red)';$('diagnostic').hidden=good&&!(s.errors||[]).length;$('diagnostic').textContent=`Ostatnia próba: ${date(s.attempt_at)} · ${sourceMessage(s.message)} ${(s.errors||[]).slice(0,2).join(' ')}`;$('coverage').textContent=`${stats.upcoming_events??'—'} / ${stats.market_groups??'—'}`;$('last').textContent=date(s.last_success_at);$('sourceNote').textContent=payload.source_note||'Dane oczekują na pierwszy skan.';$('runLink').href=safeURL(s.run_url);$('telegramStatus').textContent=payload.notifications?.channels?.telegram?'Telegram skonfigurowany. Alerty są wysyłane po potwierdzeniu okazji.':'Telegram nie jest skonfigurowany w skanerze.';$('alertsCount').textContent='Usługi przyjęły alerty w ostatnim skanie: '+Number(payload.notifications?.accepted||0);renderCards();renderEvents();renderInsights()}
function book(leg){const image=leg.logo?`<img src="${esc(safeURL('https://dobrybuk.pl'+leg.logo))}" loading="lazy" alt="">`:'';return `<a class="book" href="${esc(safeURL(leg.url))}" target="_blank" rel="noopener">${image}${esc(leg.bookmaker)} ↗</a>`}
function renderCards(){const items=currentOpportunities();$('count').textContent=items.length;$('navCount').textContent=items.length;$('best').textContent=items.length?'+'+money(items[0].profit_pct)+'%':'—';const state=payload.status.state;let message='W aktualnym skanie nie ma potwierdzonej okazji spełniającej wybrane filtry.';if(state==='error')message='Skaner zgłosił błąd. Szczegóły znajdują się w komunikacie u góry.';else if(!payload.status.last_success_at)message='Czekam na pierwszy wynik nowego skanera.';else if(Date.now()/1000-Number(payload.status.last_success_at)>300)message='Ostatni wynik ma ponad 5 minut. Czekam na świeży skan.';$('opportunities').innerHTML=items.length?items.map(op=>`<article class="card"><div class="card-top"><span class="sport-tag">${esc(op.sport)}</span><span class="profit-tag">+${money(op.profit_pct)}%</span></div><h2>${esc(op.event)}</h2><div class="market">${esc(op.market)} · ${date(op.starts_at)}</div>${op.legs.map(leg=>`<div class="leg"><div class="leg-top">${book(leg)}<b>${esc(leg.selection)} @ ${money(leg.odds)}</b></div><div class="leg-bottom"><span>Stawka</span><span class="stake">${money(leg.stake)} zł</span></div><div class="cost">Podatek od stawki: ${money(Number(leg.tax_rate)*100)}% · wyliczona wypłata ${money(leg.payout)} zł</div>${leg.alternatives?.length?`<div class="alternatives">Inne oferty: ${leg.alternatives.slice(0,3).map(a=>`${esc(a.bookmaker)} ${money(a.odds)}`).join(' · ')}</div>`:''}</div>`).join('')}<div class="card-footer"><span>Budżet ${money(op.budget)} zł</span><b>Zysk ${money(op.profit)} zł</b></div><div class="confirmed">Ponowny odczyt źródła: ${date(op.confirmed_at)} · <a href="${esc(safeURL(op.source_url))}" target="_blank" rel="noopener">Porównaj kursy ↗</a></div></article>`).join(''):`<div class="empty"><h2>Brak okazji do wyświetlenia</h2><p>${esc(message)}</p></div>`}

function sourceMessage(message){return /(?:HTTP.*403|403.*Forbidden)/i.test(message||'')?'DobryBuk odrzuca odczyt kursów (HTTP 403). Brak aktualnych danych dla Surebetów, Radaru i Valuebetów.':message||''}
function freshInsights(){return payload.status.state!=='error'&&Date.now()/1000-Number(payload.status.last_success_at||0)<=300}
function matchesInsight(item){return new Date(item.starts_at).getTime()>Date.now()&&(!$('sport').value||item.sport===$('sport').value)&&(!$('search').value||item.event.toLocaleLowerCase('pl').includes($('search').value.toLocaleLowerCase('pl')))}
function emptyInsight(label){let text='W ostatnim skanie nie ma pozycji spełniających filtry.';if(payload.status.state==='error')text=sourceMessage(payload.status.message)||'Źródło nie zwróciło aktualnych danych.';else if(!payload.status.last_success_at)text='Czekam na pierwszy poprawny odczyt źródła.';else if(!freshInsights())text='Ostatni wynik ma ponad 5 minut. Czekam na świeże dane.';return `<div class="empty"><h2>${esc(label)}</h2><p>${esc(text)}</p></div>`}
function renderInsights(){
 const watch=freshInsights()?(payload.radar||[]).filter(matchesInsight).filter(x=>Number(x.gap_pct)<=Math.min(35,Math.max(0,Number($('radarGap').value)||0))).sort((a,b)=>a.gap_pct-b.gap_pct):[];
 const values=freshInsights()?(payload.valuebets||[]).filter(matchesInsight).map(item=>{const stake=Math.floor(budget()*100+1e-7);const paid=ArbiMath.payout(stake,item.leg,item.config||payload.config)/100;const expected=paid*Number(item.probability)-stake/100;return {...item,budget:stake/100,payout:paid,expected_profit:expected,edge_pct:expected/(stake/100)*100}}).filter(x=>x.edge_pct>=Math.max(5,Number($('valueMinimum').value)||5)).sort((a,b)=>b.edge_pct-a.edge_pct):[];
 $('radarCount').textContent=watch.length;$('valueCount').textContent=values.length;
 $('radarSummary').textContent=`${watch.length} rynków do obserwacji`;$('valueSummary').textContent=`${values.length} potwierdzonych odczytem pozycji`;
 $('radarList').innerHTML=watch.length?watch.map(item=>`<article class="card"><div class="card-top"><span class="sport-tag">${esc(item.sport)}</span><span class="watch-tag">Brak ${money(item.gap_pct)}%</span></div><h2>${esc(item.event)}</h2><div class="market">${esc(item.market)} · ${date(item.starts_at)}</div>${item.legs.map(leg=>`<div class="leg"><div class="leg-top">${book(leg)}<b>${esc(leg.selection)} @ ${money(leg.odds)}</b></div><div class="cost">Podatek ${money(Number(leg.tax_rate)*100)}% · kurs po kosztach ${money(leg.effective_odds)}</div></div>`).join('')}<div class="card-footer"><span>${Number(item.bookmakers)} bukmacherów w odczycie</span><span>${item.tier==='market'?'Jeden bukmacher':item.tier==='near'?'Blisko arbitrażu':'Obserwacja'}</span></div><div class="confirmed">Odczyt źródła: ${date(item.observed_at)} · <a href="${esc(safeURL(item.source_url))}" target="_blank" rel="noopener">Porównaj kursy ↗</a></div></article>`).join(''):emptyInsight('Brak aktualnych pozycji radaru');
 $('valueList').innerHTML=values.length?values.map(item=>`<article class="card"><div class="card-top"><span class="sport-tag">${esc(item.sport)}</span><span class="profit-tag">Szacowana przewaga +${money(item.edge_pct)}%</span></div><h2>${esc(item.event)}</h2><div class="market">${esc(item.market)} · ${date(item.starts_at)}</div><div class="leg"><div class="leg-top">${book(item.leg)}<b>${esc(item.leg.selection)} @ ${money(item.leg.odds)}</b></div><div class="cost">Podatek ${money(Number(item.leg.tax_rate)*100)}% · budżet ${money(item.budget)} zł</div></div><dl class="value-details"><div><dt>Szacowana szansa</dt><dd>${money(Number(item.probability)*100)}%</dd></div><div><dt>Kurs modelowy</dt><dd>${money(item.fair_odds)}</dd></div><div><dt>Inni bukmacherzy</dt><dd>${Number(item.reference_books)}</dd></div><div><dt>Rozbieżność odniesień</dt><dd>${money(item.dispersion_pct)}%</dd></div><div><dt>Wypłata przy wygranej</dt><dd>${money(item.payout)} zł</dd></div><div><dt>Szacowane EV</dt><dd>+${money(item.expected_profit)} zł</dd></div></dl><div class="value-note">Przy przegranej tracisz stawkę. Szacunek rynku nie gwarantuje zysku.</div><div class="confirmed">Ponowny odczyt: ${date(item.confirmed_at)} · <a href="${esc(safeURL(item.source_url))}" target="_blank" rel="noopener">Porównaj kursy ↗</a></div></article>`).join(''):emptyInsight('Brak aktualnych valuebetów');
}

const labels={'1':'1','X':'X','2':'2','bts_yes':'Obie strzelą: tak','bts_no':'Obie strzelą: nie'};
function renderEvents(){const rows=filteredEvents().sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at));const size=24;const pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(page,pages-1);$('catalogueCount').textContent=rows.length+' wydarzeń';$('events').innerHTML=rows.slice(page*size,(page+1)*size).map(e=>`<article class="event"><small>${esc(e.sport)} · ${date(e.starts_at)}</small><h2>${esc(e.name)}</h2><small>${esc(e.league)} · ${e.market_count} rynków</small><div class="odds-row">${e.odds.filter(x=>['1','X','2'].includes(x.code)).map(x=>`<span class="odd">${labels[x.code]||esc(x.code)}<b>${money(x.value)}</b>${esc(x.bookmaker)}</span>`).join('')}</div><a class="event-link" href="${esc(safeURL(e.url))}" target="_blank" rel="noopener">Wszystkie kursy ↗</a></article>`).join('')||'<div class="empty"><h2>Brak pasujących wydarzeń</h2></div>';$('page').textContent=`${page+1} / ${pages}`;$('previous').disabled=page===0;$('next').disabled=page>=pages-1}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{view=button.dataset.view;for(const id of ['surebets','radar','valuebets','catalogue','notifications'])$(id).hidden=id!==view;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===button))}));
for(const id of ['budget','minimum','sport','search','radarGap','valueMinimum'])$(id).addEventListener(id==='sport'?'change':'input',()=>{if(id==='budget'||id==='minimum')save(id,$(id).value);page=0;renderCards();renderEvents();renderInsights()});
$('previous').addEventListener('click',()=>{page=Math.max(0,page-1);renderEvents()});$('next').addEventListener('click',()=>{page++;renderEvents()});$('refresh').addEventListener('click',async()=>{$('refresh').disabled=true;try{await load()}catch{showLoadError()}finally{$('refresh').disabled=false}});
const help={radar:['Jak działa radar?','Łączymy najlepsze kursy po podatku dla rozłącznych stron tego samego rynku. Brak do arbitrażu to nadwyżka sumy odwrotności kursów po kosztach ponad 1, wyrażona w procentach. Radar pokazuje ostatni odczyt źródła; pozycje z jednym widocznym bukmacherem są oznaczone. To nie są potwierdzone surebety.'],value:['Jak szacujemy value?','Z kompletnych ofert co najmniej 5 innych bukmacherów wyliczamy prawdopodobieństwa po proporcjonalnym usunięciu marży, a następnie ich medianę. Wykluczamy porównywanego bukmachera z grupy odniesienia i filtrujemy rozbieżne lub skrajne kursy. Szacowana przewaga uwzględnia koszty i zaokrąglenia dla podanego budżetu. To oszacowanie rynku, a nie pewność wygranej. Valuebet musi przejść drugi odczyt źródła. Alerty skanera dotyczą surebetów.'],calculation:['Jak liczymy zysk?','Wybieramy najlepszy kurs po kosztach dla każdej strony tego samego rynku. Rozdzielamy budżet tak, aby najniższa wyliczona wypłata była możliwie równa. Stawki są zaokrąglone do groszy. Okazja trafia do panelu po drugim odczycie porównywarki. Przed postawieniem sprawdź dostępny kurs i zasady rozliczenia u bukmachera.'],coverage:['Co oznacza pokrycie?','Pierwsza liczba to nadchodzące wydarzenia odczytane ze źródła. Druga to rozpoznane, kompletne grupy rynków. Skaner pobiera pełne oferty dla wydarzeń z możliwą okazją, a następnie ponownie odczytuje kursy kandydatów. Nie wszystkie rynki i bukmacherzy są dostępni w źródle.'],tax:['Podatki i obliczenia','Koszty pochodzą z konfiguracji źródła i danych bukmachera. Na każdej stronie rynku widzisz zastosowany podatek. Promocja bez podatku musi być dostępna na Twoim koncie. Jeżeli korzystasz z takiej promocji, jej stawkę można ustawić w BOOKMAKER_TAX_OVERRIDES w workflow.']};
document.querySelectorAll('[data-help]').forEach(b=>b.addEventListener('click',()=>{const [title,text]=help[b.dataset.help];$('helpTitle').textContent=title;$('helpText').textContent=text;$('helpDialog').showModal()}));$('closeHelp').addEventListener('click',()=>$('helpDialog').close());
let pushStarted=false,pushPhase='idle';
function pushStatus(text,disabled=true,label='Włącz powiadomienia'){$('pushStatus').textContent=text;$('push').disabled=disabled;$('push').textContent=label}
function pushError(text){pushPhase='error';pushStatus(text,false,'Odśwież obsługę push')}
function updatePushSubscription(){
 if(!pushReady)return;
 const subscription=pushReady.User.PushSubscription;
 if(pushReady.Notifications.permission&&subscription.optedIn&&subscription.id){pushStatus('Powiadomienia włączone. To urządzenie jest zarejestrowane do odbierania alertów.',true,'Powiadomienia włączone');return}
 if(typeof Notification!=='undefined'&&Notification.permission==='denied'){pushStatus('Powiadomienia są zablokowane. Zmień zgodę w ustawieniach tej aplikacji lub witryny, potem otwórz ją ponownie.');return}
 pushStatus(pushReady.Notifications.permission?'Zgoda przyznana. Czekam na rejestrację urządzenia w OneSignal.':'Push gotowy. Włącz powiadomienia na tym urządzeniu.',false);
}
function initPush(){
 if(pushStarted)return;pushStarted=true;
 if(!config.onesignal_app_id){pushStatus('Push nie jest skonfigurowany. Telegram może działać niezależnie.');return}
 const device=typeof navigator==='undefined'?{}:navigator;
 const ios=/iPad|iPhone|iPod/.test(device.userAgent||'')||(device.platform==='MacIntel'&&device.maxTouchPoints>1);
 const installed=device.standalone===true||window.matchMedia?.('(display-mode: standalone)').matches===true;
 if(ios&&!installed){pushPhase='install';pushStatus('Na iPhonie: Safari → Udostępnij → Dodaj do ekranu początkowego. Następnie otwórz stronę z dodanej ikony i tutaj włącz powiadomienia.',true,'Otwórz z ikony na ekranie');return}
 pushPhase='loading';pushStatus('Ładuję obsługę powiadomień…',true,'Ładowanie…');
 const timer=setTimeout(()=>{if(pushPhase==='loading')pushError('Obsługa powiadomień nie uruchomiła się. Sprawdź połączenie i czy przeglądarka nie blokuje OneSignal, następnie odśwież obsługę.')},25000);
 window.OneSignalDeferred=window.OneSignalDeferred||[];
 window.OneSignalDeferred.push(async OneSignal=>{
  try{
   await OneSignal.init({appId:config.onesignal_app_id,serviceWorkerPath:'OneSignalSDKWorker.js',serviceWorkerParam:{scope:new URL(config.public_url||location.href).pathname}});
   clearTimeout(timer);
   if(!OneSignal.Notifications.isPushSupported()){pushPhase='unsupported';pushStatus('Ta przeglądarka nie obsługuje powiadomień push. Na iPhonie wymagany jest iOS 16.4 lub nowszy i otwarcie strony z ikony na ekranie początkowym.');return}
   pushReady=OneSignal;pushPhase='ready';
   OneSignal.User.PushSubscription.addEventListener('change',updatePushSubscription);
   OneSignal.Notifications.addEventListener('permissionChange',updatePushSubscription);
   updatePushSubscription();
  }catch(error){clearTimeout(timer);pushError('Nie udało się uruchomić push: '+String(error?.message||'błąd konfiguracji OneSignal').slice(0,220))}
 });
 const script=document.createElement('script');script.src='https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js';script.defer=true;
 script.onerror=()=>{clearTimeout(timer);pushError('Nie udało się pobrać OneSignal. Sprawdź połączenie i blokowanie skryptów, następnie odśwież obsługę.')};document.head.appendChild(script);
}
$('push').addEventListener('click',async()=>{
 if(pushPhase==='error'){location.reload();return}
 if(!pushReady)return;
 try{
  pushStatus('Czekam na zgodę na powiadomienia…',true,'Włączanie…');
  await pushReady.Notifications.requestPermission();
  if(pushReady.Notifications.permission)await pushReady.User.PushSubscription.optIn();
  updatePushSubscription();
 }catch(error){pushStatus('Nie udało się włączyć push: '+String(error?.message||'sprawdź zgodę na powiadomienia').slice(0,220),false)}
});
setInterval(()=>{if(!$('app').hidden)load().catch(showLoadError)},10000);
boot();
