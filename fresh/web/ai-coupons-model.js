(function(root){
 'use strict';
 const stamp=x=>typeof x==='number'?x:new Date(x).getTime()/1000;
 const eventKey=x=>String(x.event_id??x.event).trim().toLocaleLowerCase('pl').replace(/\s+/g,' ');
 const bookKey=x=>String(x.leg?.slug||x.leg?.bookmaker||'').trim().toLowerCase();
 function generate(payload,options={},now=Date.now()/1000){
  const minimum=Number(options.minimum??2),maximum=Number(options.maximum??15),outside=Number(options.outside??50)/100;
  if(!Number.isFinite(minimum)||!Number.isFinite(maximum)||minimum<1.01||maximum>100||minimum>maximum||!Number.isFinite(outside)||outside<0||outside>1)return {coupons:[],reason:'Podaj poprawny zakres kursu i próg szacunku od 0 do 100%.'};
  const age=now-Number(payload.status?.last_success_at||0);
  if(!['ok','partial'].includes(payload.status?.state)||!Number.isFinite(age)||age<0||age>300)return {coupons:[],reason:'Brak świeżego skanu. Generator czeka na aktualne kursy.'};
  const seen=new Set();
  const candidates=(payload.valuebets||[]).filter(x=>{
   const odds=Number(x.leg?.odds),prob=Number(x.probability),observed=Number(x.confirmed_at),tax=Number(x.leg?.tax_rate);
   if(!x.id||!x.event||!x.market||!x.leg?.selection||!bookKey(x)||seen.has(x.id)||!Number.isFinite(odds)||odds<1.01||odds>maximum||!Number.isFinite(prob)||prob<=0||prob>=1||!Number.isFinite(observed)||now-observed<0||now-observed>300||stamp(x.starts_at)<=now||!Number.isFinite(stamp(x.starts_at))||!Number.isFinite(Number(x.reference_books))||Number(x.reference_books)<5||!Number.isFinite(Number(x.dispersion_pct))||Number(x.dispersion_pct)<0||Number(x.dispersion_pct)>8||!Number.isFinite(tax)||tax<0||tax>=1)return false;
   seen.add(x.id);return true;
  }).sort((a,b)=>Number(b.probability)-Number(a.probability)).slice(0,40);
  const result=[];
  function walk(legs,start,odds,prob){
   if(legs.length&&odds>=minimum&&odds<=maximum){
    const preferred=odds>=3&&odds<=6;
    if(preferred||prob>=outside){
     const signature=legs.map(x=>String(x.id)).sort().join('|');
     result.push({id:signature,created_at:now,odds,probability:prob,preferred,bookmaker:legs[0].leg.bookmaker||legs[0].leg.slug,legs:legs.map(x=>JSON.parse(JSON.stringify(x))),state:'open',evidence:'',settled_at:null});
    }
   }
   if(legs.length>=3)return;
   for(let i=start;i<candidates.length;i++){
    const c=candidates[i];if(odds*Number(c.leg.odds)>maximum)continue;
    if(legs.some(x=>eventKey(x)===eventKey(c)||bookKey(x)!==bookKey(c)||Number(x.leg.tax_rate)!==Number(c.leg.tax_rate)))continue;
    walk([...legs,c],i+1,odds*Number(c.leg.odds),prob*Number(c.probability));
   }
  }
  walk([],0,1,1);
  result.sort((a,b)=>Number(b.preferred)-Number(a.preferred)||b.probability-a.probability||a.legs.length-b.legs.length||a.id.localeCompare(b.id));
  const chosen=[],used=new Set();
  for(const c of result){if(c.legs.some(x=>used.has(eventKey(x))))continue;chosen.push(c);c.legs.forEach(x=>used.add(eventKey(x)));if(chosen.length===3)break;}
  return {coupons:chosen,reason:chosen.length?'':'Nie ma kuponów spełniających warunki. Potrzebne są świeże pozycje Valuebet u tego samego bukmachera; generator nie wymyśla typów.'};
 }
 function counters(coupons){return coupons.reduce((a,c)=>{a.total++;if(c.state==='won')a.won++;else if(c.state==='lost')a.lost++;else if(c.state==='void')a.void++;else a.open++;return a},{total:0,won:0,lost:0,open:0,void:0})}
 function settle(coupon,state,evidence,now=Date.now()/1000){
  if(!['won','lost','void'].includes(state))throw new Error('Wybierz wynik kuponu.');
  if(!coupon.legs?.length||coupon.legs.some(x=>!Number.isFinite(stamp(x.starts_at))||stamp(x.starts_at)>now))throw new Error('Nie rozliczaj kuponu, zanim rozpoczną się wszystkie jego wydarzenia.');
  let url;try{url=new URL(evidence)}catch{throw new Error('Dodaj link HTTPS do wyniku lub rozliczenia kuponu.');}
  if(url.protocol!=='https:'||url.username||url.password)throw new Error('Wymagany jest poprawny link HTTPS bez danych logowania.');
  return {...coupon,state,evidence:url.href,settled_at:now,settlement_method:'manual',corrections:[...(coupon.corrections||[]),...(coupon.state!=='open'?[{state:coupon.state,evidence:coupon.evidence,settled_at:coupon.settled_at}]:[])]};
 }
 const api={generate,counters,settle};if(typeof module==='object'&&module.exports)module.exports=api;else root.AiCoupons=api;
})(typeof window!=='undefined'?window:globalThis);
