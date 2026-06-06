/* ===========================================================================
 * Ancestry DNA – SideView-Spion (mütterlich / väterlich pro Match)
 * ===========================================================================
 *
 * ZWECK
 *   Findet, woran Ancestry die Eltern-Seite (Parent 1 / Parent 2 bzw.
 *   mütterlich/väterlich, "SideView") eines Matches festmacht – im matchList
 *   und/oder in den cluster-Endpunkten (paternalCluster / subject /
 *   matchClusterCodes). Speichert volle Antworten in
 *   "ancestry_spy_sideview.json".
 *
 * ANLEITUNG
 *   1. Match-LISTE öffnen (nicht Compare):
 *      https://www.ancestry.com/discoveryui-matches/list/BEC4AE66-352E-406F-B2DA-6BC5D4DED923
 *      → falls vorhanden, links auf "By parent / Nach Elternteil" / SideView
 *        umschalten und beide Seiten kurz anzeigen lassen.
 *   2. F12 → "Console" → diesen GESAMTEN Text einfügen → Enter.
 *   3. Nach ~20 Sek. lädt "ancestry_spy_sideview.json" → hier einfügen.
 *
 * Liest nur – ändert nichts.
 * ========================================================================= */

(async () => {
  "use strict";
  const HINT = /matchlist|cluster|paternal|maternal|sideview|side|parent|subject|relationship/i;
  const API  = /\/api\/|discoveryui|matchesservice/i;
  const IGNORE = ["ube-torrent","/events","newrelic","nr-data","/log","telemetry",
    "google","doubleclick","adobe","/akam/","qualtrics","hotjar","/metrics","/beacon",
    "fonts.",".css",".js",".png",".jpg",".svg",".woff","/ping","optimizely","/static/","/media/"];
  const isApi  = (u)=>!!u && API.test(u) && !IGNORE.some(s=>u.toLowerCase().includes(s));
  const isHot  = (u)=>isApi(u) && HINT.test(u);

  const caps=[]; const seen=new Set();
  function keys(t){ try{const j=JSON.parse(t);return Array.isArray(j)?["<array "+j.length+">"]:Object.keys(j||{});}catch(e){return null;} }
  function add(m,u,b,t,src){
    const rec={method:m,url:u,source:src,topKeys:keys(t),
               requestBody:b?String(b).slice(0,600):null};
    if(isHot(u)) rec.responseFull=String(t).slice(0,120000);
    else rec.sample=String(t).slice(0,300);
    caps.push(rec);
  }
  const _f=window.fetch;
  window.fetch=async function(i,init){
    const u=(typeof i==="string")?i:(i&&i.url); const m=(init&&init.method)||"GET"; const b=init&&init.body;
    const r=await _f.apply(this,arguments);
    if(isApi(u)&&!seen.has("L:"+u)){seen.add("L:"+u);try{r.clone().text().then(t=>add(m,u,b,t,"live"));}catch(e){}}
    return r;
  };
  const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;return _o.apply(this,arguments);};
  XMLHttpRequest.prototype.send=function(b){
    this.addEventListener("load",function(){
      if(isApi(this.__u)&&!seen.has("L:"+this.__u)){seen.add("L:"+this.__u);try{add(this.__m,this.__u,b,this.responseText,"live");}catch(e){}}
    });return _s.apply(this,arguments);
  };

  const box=document.createElement("div");
  box.style.cssText="position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#2b1b3a;color:#fff;font:14px/1.4 system-ui;padding:14px 18px;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.4);max-width:380px;";
  document.body.appendChild(box); const msg=h=>box.innerHTML=h; const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  msg("<b>SideView-Spion</b><br>Schalte jetzt auf 'Nach Elternteil/SideView' und zeig beide Seiten …");

  for(let n=0;n<16;n++){
    const urls=performance.getEntriesByType("resource").map(e=>e.name).filter(isApi);
    for(const u of [...new Set(urls)]){
      if(!seen.has("R:"+u)){seen.add("R:"+u);
        try{const r=await _f(u,{credentials:"include",headers:{Accept:"application/json"}});add("GET",u,null,await r.text(),"replay");}catch(e){}}
    }
    msg("<b>SideView-Spion</b><br>warte auf Klicks … ("+(16-n)+"s)<br>erfasst: "+caps.length);
    await sleep(1000);
  }
  window.fetch=_f;XMLHttpRequest.prototype.open=_o;XMLHttpRequest.prototype.send=_s;
  const blob=new Blob([JSON.stringify(caps,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="ancestry_spy_sideview.json";
  document.body.appendChild(a);a.click();a.remove();
  msg("✅ <b>Fertig.</b> "+caps.length+" Anfragen → <b>ancestry_spy_sideview.json</b> im Chat einfügen.");
})();
