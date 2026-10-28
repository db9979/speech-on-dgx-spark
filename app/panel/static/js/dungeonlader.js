// KI-Dungeon-Master: the game's scripts come on first use (Punkt 14 of the review of 2026-10-24, Dominik „alles
// umsetzten“: „Spiel-Skripte erst beim Öffnen laden“). The page always has only this file: the menu entry needs only
// who.dungeon; opening the page (goSec → dmOpen) or a seat link (#spiel=, #weiter=) loads the scripts of DM_SKRIPTE once,
// in this order, with the running version as ?v= (panel._asset), then hands over to their own dmStart, dmOpen, dmHash.
const DM_SKRIPTE=['dungeon.js','dungeonkarte.js','dungeon-ton.js','dungeonfenster.js','dungeonwarten.js','dungeonwappen.js','dungeonbuch.js','dungeonsockel.js'];
const DML={p:null,who:null};
function dmLade(){return DML.p||(DML.p=DM_SKRIPTE.reduce((p,f)=>p.then(()=>new Promise((ok,no)=>{const s=document.createElement('script');
  s.src='/static/js/'+f+'?v='+encodeURIComponent(SPARK_VER);s.onload=ok;s.onerror=()=>{DML.p=null;no(new Error(f))};document.head.appendChild(s)})),Promise.resolve())
  .then(()=>{if(DML.who)window.dmStart(DML.who)}))}
window.dmStart=who=>{DML.who=who;const on=!!(who&&who.profile&&who.dungeon);document.querySelectorAll('nav button[data-s=dungeon]').forEach(b=>b.hidden=!on)};
window.dmOpen=()=>{const root=$('dmroot');if(root&&!root.firstChild)root.innerHTML=`<div class="mut">${esc(t('Lädt …','Loading …'))}</div>`;
  dmLade().then(()=>window.dmOpen()).catch(()=>{if(root)root.innerHTML=`<div class="err">${esc(t('Das Spiel lädt gerade nicht. Seite neu laden.','The game does not load right now. Reload the page.'))}</div>`})};
// „Zum Tisch“ on a tapped „Du bist dran“ (mitteilung.js, mitteilungen.ziel): that round's table
window.dmZumTisch=rid=>{if(!/^r[0-9a-f]{10}$/.test(rid||''))return;dmLade().then(()=>{DM.rid=rid;DM.v=null;goSec('dungeon');dmRound()})};
window.dmHash=()=>{if(!/^#(spiel=[A-Za-z0-9_-]{32}(&app=1)?|weiter=[A-Za-z0-9_-]{43})$/.test(location.hash))return false;dmLade().then(()=>window.dmHash());return true};
