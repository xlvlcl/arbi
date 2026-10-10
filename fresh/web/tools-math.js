(function(root){
 'use strict';
 const finite=(x,min,max)=>Number.isFinite(Number(x))&&String(x).trim()!==''&&Number(x)>=min&&Number(x)<=max;
 function analyze(legs,stake,tax,winTax,threshold){
  if(!Array.isArray(legs)||!legs.length||legs.length>20||!finite(stake,.01,100000)||!finite(tax,0,99)||!finite(winTax,0,99)||!finite(threshold,0,1e9))return null;
  if(legs.some(x=>!String(x.event||'').trim()||!String(x.market||'').trim()||!String(x.selection||'').trim()||!finite(x.odds,1.01,1000)))return null;
  const odds=legs.reduce((v,x)=>v*Number(x.odds),1);
  if(!Number.isFinite(odds)||odds>1e9)return null;
  let payout=Math.floor(Math.floor(Number(stake)*100*(1-Number(tax)/100)+1e-7)*odds+1e-7)/100;
  if(payout>Number(threshold))payout=Math.floor(payout*100*(1-Number(winTax)/100)+1e-7)/100;
  const names=legs.map(x=>String(x.event).trim().toLocaleLowerCase('pl').replace(/\s+/g,' '));
  const correlated=new Set(names).size!==names.length;
  const complete=legs.every(x=>finite(x.probability,.01,99.99));
  const probability=complete&&!correlated?legs.reduce((v,x)=>v*Number(x.probability)/100,1):null;
  return {odds,payout,profit:payout-Number(stake),breakEven:payout>0?Number(stake)/payout:null,implied:1/odds,probability,correlated,ev:probability===null?null:probability*payout-Number(stake)};
 }
 function totals(entries){return entries.reduce((v,x)=>{const stake=Number(x.stake)||0;if(x.state==='open')v.exposure+=stake;else{v.settled+=stake;v.profit+=(x.state==='won'?Number(x.payout)||0:x.state==='void'?stake:0)-stake;}return v},{exposure:0,settled:0,profit:0})}
 function csv(entries){const cell=x=>'"'+String(x??'').replace(/^([=+@\-\t\r])/,"'$1").replace(/"/g,'""')+'"';return '\uFEFF'+[['Data','Nazwa','Stawka','Wypłata przy wygranej','Status'],...entries.map(x=>[x.created,x.name,x.stake,x.payout,x.state])].map(r=>r.map(cell).join(';')).join('\r\n')}
 const api={analyze,totals,csv};if(typeof module==='object'&&module.exports)module.exports=api;else root.ArbiTools=api;
})(typeof window!=='undefined'?window:globalThis);
