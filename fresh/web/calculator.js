(function(root){
  const cents=value=>Math.floor(Number(value)*100+1e-7);
  function payout(stake,leg,config){
    const net=Math.floor(stake*(1-Number(leg.tax_rate))+1e-7);
    let paid=Math.floor(net*Number(leg.odds)+1e-7);
    if(paid/100>Number(config.winning_tax_threshold??2280))paid=Math.floor(paid*(1-Number(config.winning_tax_rate??.1))+1e-7);
    return paid;
  }
  function allocate(legs,budget,config={}){
    const total=cents(budget);
    if(!Number.isFinite(total)||total<=0||!Array.isArray(legs)||legs.length<2||legs.length>3)return null;
    const inv=legs.map(l=>1/(Number(l.odds)*(1-Number(l.tax_rate))));
    const sum=inv.reduce((a,b)=>a+b,0);
    if(!Number.isFinite(sum)||sum<=0)return null;
    const base=inv.map(x=>Math.floor(total*x/sum));let best=null;
    for(let a=-3;a<=3;a++)for(let b=(legs.length===3?-3:0);b<=(legs.length===3?3:0);b++){
      const stakes=legs.length===3?[base[0]+a,base[1]+b,total-base[0]-a-base[1]-b]:[base[0]+a,total-base[0]-a];
      if(Math.min(...stakes)<100)continue;
      const paid=stakes.map((s,i)=>payout(s,legs[i],config));const floor=Math.min(...paid);
      if(!best||floor>best.floor)best={floor,stakes,paid};
    }
    if(!best)return null;
    return {budget:total/100,payout:best.floor/100,profit:(best.floor-total)/100,profit_pct:(best.floor-total)/total*100,legs:legs.map((l,i)=>({...l,stake:best.stakes[i]/100,payout:best.paid[i]/100}))};
  }
  const api={allocate,payout};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.ArbiMath=api;
})(typeof window!=='undefined'?window:globalThis);
