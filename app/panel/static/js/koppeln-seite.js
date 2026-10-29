'use strict';
// The page of a pairing's „Einmal-Link“ (/koppeln, fernzugang.link_page): no login, no panel, no model. The link's
// key (behind "#", taken from the address at once) asks the panel for the one line for this kind of system; the code
// is never in it. What the panel sends is shown with textContent only.
(()=>{
const EN=!/^de\b/i.test(navigator.language||'de');
const L={titel:['System koppeln','Pair a system'],kopieren:['Kopieren','Copy'],kopiert:['Kopiert','Copied'],
  code:['Die Zeile fragt dann nach dem Einmal-Code, den das Panel zeigt. Er steht nie im Link und nie im Befehl.','The line then asks for the one-time code the panel shows. It is never in the link and never in the command.'],
  nein:['Dieser Link gilt nicht mehr. Einen neuen gibt es im Panel beim Fernzugang über „System koppeln“.','This link is no longer valid. Get a new one in the panel at Remote access with "Pair a system".'],
  linux:['Auf diesem System (Debian, Ubuntu, Raspberry Pi OS mit laufendem sshd) diese eine Zeile im Terminal einfügen:','On this system (Debian, Ubuntu, Raspberry Pi OS with sshd running) paste this one line in the terminal:'],
  mac:['Auf diesem Mac (ab macOS 13) diese eine Zeile im Terminal einfügen:','On this Mac (from macOS 13) paste this one line in the terminal:'],
  bis:['Der Link gilt noch %s Minuten.','The link counts for %s more minutes.']};
const tr=k=>L[k][EN?1:0],$=id=>document.getElementById(id);
document.documentElement.lang=EN?'en':'de';document.title=tr('titel');
document.querySelectorAll('[data-t]').forEach(e=>{e.textContent=tr(e.dataset.t)});
// the key only from the part behind "#", never sent in an address; the address bar forgets it at once
const h=location.hash.slice(1);let key=/^[A-Za-z0-9_-]{20,30}$/.test(h)?h:'';
if(location.hash)history.replaceState(null,'',location.pathname);
const nein=()=>{$('k-nein').hidden=false;$('k-ok').hidden=true};
if(!key){nein();return}
(async()=>{let d=null;
  try{const r=await /*raw: this page loads without base.js*/fetch('/api/fernzugang/koppeln/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({link:key}),credentials:'omit'});
    if(r.ok)d=await r.json()}catch(e){}
  key='';
  if(!d||typeof d.befehl!=='string'){nein();return}
  $('ktext').textContent=tr(d.os==='mac'?'mac':'linux');$('kbefehl').textContent=d.befehl;
  $('kbis').textContent=tr('bis').replace('%s',String(Math.max(1,Math.ceil((+d.gilt_s||0)/60))));
  $('k-ok').hidden=false;
  $('kkopie').onclick=async()=>{try{await navigator.clipboard.writeText(d.befehl);$('kkopie').textContent=tr('kopiert')}catch(e){
    const s=window.getSelection(),rg=document.createRange();rg.selectNodeContents($('kbefehl'));s.removeAllRanges();s.addRange(rg)}};
})();
})();
