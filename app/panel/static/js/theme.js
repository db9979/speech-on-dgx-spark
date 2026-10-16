// The chosen light or dark look before the page is drawn (no flash). Its own file since the strict CSP (V01.0.286).
try{const th=localStorage.getItem("theme");if(th==="light"||th==="dark")document.documentElement.dataset.theme=th}catch{}
// Start-Wächter (Dominik 16.10.2026: „nach Updates funktioniert der Seitenrefresh nicht richtig“): a page loaded while
// the Spark restarts (an update) can miss one of its scripts (the proxy answers 502) or get no answer to its first
// /api/whoami. The start (start.js startPage) then never finished and the page stood at „Zustand wird geladen …“ for
// good, also after a reload in the wrong moment. Here, first of all scripts: a script of the page that did not load or a
// start that failed shows a band, asks the Spark again after 3, 6, 12 … at most 60 s and loads the page anew once it
// answers; after 5 such loads the band only offers the button. Kept in this tab: the number of tries, never contents.
(()=>{const de=(()=>{try{const l=localStorage.getItem("lang");if(l)return l!=="en"}catch{}return /^de/i.test(navigator.language)})(),
  say=(d,e)=>de?d:e,B={failed:false,missing:0,band:null,next:0,tick:0},MOST=5;
  const tries=()=>{try{return Math.max(0,parseInt(sessionStorage.getItem("boottry")||"0",10)||0)}catch{return 0}};
  addEventListener("error",e=>{const s=e.target;if(s&&s.tagName==="SCRIPT"&&/\/static\/js\//.test(s.src||""))B.missing++},true);
  function band(text){let b=B.band;if(!b){b=B.band=document.createElement("div");b.id="bootband";b.className="lzband";b.setAttribute("role","alert");
      const s=document.createElement("b");s.textContent=say("Die Seite ist nicht vollständig geladen.","The page did not load completely.");
      const m=document.createElement("span");m.id="bootmsg";
      const go=document.createElement("button");go.type="button";go.className="b";go.textContent=say("Jetzt neu laden","Reload now");
      go.addEventListener("click",()=>{try{sessionStorage.setItem("boottry",String(tries()+1))}catch{}location.reload()});
      b.append(s,m,go);document.body.prepend(b)}
    b.hidden=false;$m(text)}
  const $m=text=>{const m=document.getElementById("bootmsg");if(m)m.textContent=text};
  function count(){const left=Math.ceil((B.next-Date.now())/1000);
    if(left<=0){clearInterval(B.tick);B.tick=0;return ping()}
    $m(say(`Der Spark startet vielleicht gerade neu. Neuer Versuch in ${left} s …`,`The Spark may be restarting right now. Trying again in ${left} s …`))}
  function wait(){const n=tries();if(n>=MOST)return $m(say("Bitte gleich noch einmal neu laden.","Please reload again in a moment."));
    B.next=Date.now()+Math.min(60,3*2**n)*1000;clearInterval(B.tick);B.tick=setInterval(count,1000);count()}
  // the Spark answers with its own JSON again (not a proxy's error page): load the page anew
  async function ping(){$m(say("Versuche …","Trying …"));
    try{const r=await /*raw: the Start-Wächter's probe, before base.js and api() exist*/fetch("/api/whoami",{cache:"no-store"});
      if(r.ok&&typeof await r.json()==="object"){try{sessionStorage.setItem("boottry",String(tries()+1))}catch{}return location.reload()}}catch{}
    wait()}
  function fail(){if(B.failed)return;B.failed=true;band("");wait()}
  // start.js: the start went through (with every script there) or failed
  window.sparkBootDone=()=>{if(B.missing)return fail();try{sessionStorage.removeItem("boottry")}catch{}};
  window.sparkBootFail=()=>fail();
  // a script that did not load also when start.js itself is missing (then nobody else says so)
  addEventListener("load",()=>{if(B.missing)fail()});
})();
