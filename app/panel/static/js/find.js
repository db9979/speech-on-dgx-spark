// One search for everything (plan „Bedienung gesamt“, V01.0.265; plaene/suche-gesicht.md: the button in the menu also for
// profiles, the magnifier at the top of the app view, a cross to close): Strg K / Cmd K or "Suchen" in the menu opens a
// box that finds pages, admin switches and settings, the own Ich settings, the checks under Prüfen, the Logs
// areas and the guides. Only what the viewer can open: admins see the admin pages (a Verwalter only his),
// a profile its Ich pages, guests nothing. Runs in the browser over what is already on the page.
const PAL={open:false,hits:[],sel:0};
function palItems(){const out=[],seen=new Set(),add=(grp,label,where,go,more)=>{const k=grp+'|'+label+'|'+where;if(!label||seen.has(k))return;seen.add(k);out.push({grp,label,where,go,more:more||''})};
  const P=t('Seiten','Pages'),F=t('Funktionen','Features'),S=t('Einstellungen','Settings'),M=t('Für dich','For you'),C=t('Prüfen und Logs','Checks and logs'),G=t('Anleitungen','Guides');
  const shown=b=>b&&!b.hidden&&getComputedStyle(b).display!=='none';
  if(ADMIN){
    document.querySelectorAll('nav button[data-s]').forEach(b=>{if(b.hidden)return;const g=b.dataset.s,name=visText(b);
      (GROUPS[g]||[]).forEach(([id,l])=>add(P,l||name,l&&l!==name?name:'',()=>goSec(id)))});
    const cfgOk=shown(document.querySelector('nav button[data-s=cfg]'));
    if(cfgOk){document.querySelectorAll('#cfgnav button[data-p]').forEach(b=>{if(b.dataset.p!=='feat')add(P,visText(b),t('Einstellungen','Settings'),()=>goCfg(b.dataset.p))});
      if(typeof cfgIndex==='function')for(const h of cfgIndex()){if(!h.el)continue;const feat=h.p==='feat';
        add(feat?F:S,h.label,feat?t('Funktionen','Features'):h.page,()=>{goCfg(h.p);setTimeout(()=>cfgGo(h),80)},h.more)}}
    if(!document.body.classList.contains('mgr')){
      document.querySelectorAll('#test h2, #test h3, #test button.b').forEach(e=>{const l=visText(e);if(l&&l.length<=48)add(C,l,t('Zustand → Prüfen','Status → Checks'),()=>{goSec('test');setTimeout(()=>sFlash(e),120)})})}
    document.querySelectorAll('#logs .ptabs button, #logs [data-area], #logs [data-tab]').forEach(e=>{const l=visText(e);if(l&&l.length<=40)add(C,t('Logs: ','Logs: ')+l,t('Zustand → Logs','Status → Logs'),()=>{goSec('logs');setTimeout(()=>{e.click();sFlash(e)},120)})});
    if(cfgOk)(typeof GUIDES!=='undefined'?GUIDES:[]).forEach(g=>add(G,gT(g.t),t('Funktionen → Anleitungen','Features → Guides'),()=>{goSec('int');setTimeout(()=>{const d=document.querySelector(`#guidelist details.guide[data-guide="${g.id}"]`);if(d){d.open=true;sFlash(d)}},120)}))}
  if(PROFILE&&typeof meIndex==='function'){
    if(!ME_ITEMS.length&&typeof meTabs==='function')try{meTabs()}catch{}
    for(const h of meIndex())add(M,h.label,h.el?t('Ich → ','Me → ')+h.page:t('Ich','Me'),()=>{openMe(h.id);setTimeout(()=>meGo(h),120)},h.more)}
  // Probleme melden (melden.js): the window, for admins and profiles alike
  if(typeof RP_ON!=='undefined'&&RP_ON&&(ADMIN||PROFILE))add(P,t('Problem melden','Report a problem'),t('Fenster','Window'),()=>rpOpen());
  return out}
// everyday words for what the pages call otherwise (code check 19.10. D7); a word finds its own spelling or one of these
const PAL_SYN={wecker:['erinnerung','reminder'],alarm:['erinnerung','reminder'],licht:['home assistant','smart home','gerät'],lampe:['home assistant','smart home'],
  heizung:['home assistant','smart home'],backup:['sicherung','backup'],sicherung:['backup'],termin:['kalender','calendar'],termine:['kalender','calendar'],
  pin:['anmeld','sicherheit','login'],passwort:['anmeld','sicherheit','password'],löschen:['entfern','delete','remove'],delete:['löschen','entfern'],
  stimme:['sprachausgabe','sprecher','voice'],mikrofon:['spracherkennung','sprechen','microphone'],lautsprecher:['speaker','esp32'],
  mail:['e-mail','postfach'],email:['e-mail','postfach'],update:['aktualis'],handy:['iphone','android','app'],uhr:['watch','pebble'],
  dokument:['dokumente','wissen','upload'],datei:['dokumente','upload'],musik:['music'],bild:['bilder','image'],foto:['bilder','scan']};
let palSyn=null;
function palRun(q){const w=norm(q).split(' ').filter(Boolean);if(!w.length)return [];
  const syn=palSyn||(palSyn=Object.fromEntries(Object.entries(PAL_SYN).map(([k,v])=>[norm(k),v.map(norm)])));
  const has=(k,p)=>k.includes(p)||(syn[p]||[]).some(s=>k.includes(s));
  // the name, where it lives and its group first; its description too, ranked after them
  const all=palItems().map(x=>{const k=norm(x.label+' '+x.where+' '+x.grp);
    return w.every(p=>has(k,p))?x:w.every(p=>has(k+' '+norm(x.more),p))?{...x,deep:1}:null}).filter(Boolean);
  const nq=norm(q),score=x=>(x.deep?4:norm(x.label)===nq?0:norm(x.label).startsWith(nq)?1:norm(x.label).includes(nq)?2:3);
  const got=all.sort((a,b)=>score(a)-score(b)).slice(0,30);
  // Finden (fund.py): the own data, not only the pages; the last row, it opens the page Finden with these words
  if(PROFILE&&window.FUND_ON&&typeof fundSuche==='function'&&q.trim().length>=2)
    got.push({grp:t('In meinen Daten','In my data'),label:t('In meinen Daten finden: ','Find in my data: ')+q.trim().slice(0,80),where:t('Finden','Find'),go:()=>fundSuche(q.trim())});
  return got}
function palDraw(){const box=$('palres'),q=$('palq').value;box.textContent='';PAL.hits=palRun(q);PAL.sel=Math.min(PAL.sel,Math.max(PAL.hits.length-1,0));
  if(!q.trim()){const p=document.createElement('div');p.className='fnone';p.textContent=t('Seite, Schalter, Einstellung, Prüfung oder Anleitung eingeben.','Type a page, switch, setting, check or guide.');box.appendChild(p);return}
  if(!PAL.hits.length){const p=document.createElement('div');p.className='fnone';p.textContent=t('Nichts gefunden. ','Nothing found. ');
    // nothing on the pages: the assistant knows the Spark (Hilfe zum Spark) and finds the way
    if($('chattext')&&!isGuest()){const a=document.createElement('a');a.href='#';a.className='wayl';a.textContent=t('Frag Spark','Ask Spark');
      a.onclick=e=>{e.preventDefault();palClose();goSec('chat');const c=$('chattext');c.value=q.trim();c.focus()};p.appendChild(a)}
    box.appendChild(p);return}
  const order=[];for(const h of PAL.hits)if(!order.includes(h.grp))order.push(h.grp);
  const sorted=order.flatMap(g=>PAL.hits.filter(h=>h.grp===g));PAL.hits=sorted;
  let last='';sorted.forEach((h,i)=>{if(h.grp!==last){const g=document.createElement('div');g.className='fgrp';g.textContent=h.grp;box.appendChild(g);last=h.grp}
    const b=document.createElement('button');b.type='button';b.className='fit'+(i===PAL.sel?' sel':'');b.dataset.i=i;
    const l=document.createElement('span');l.textContent=h.label;const s=document.createElement('small');s.textContent=h.where;b.append(l,s);
    b.onclick=()=>palGo(i);box.appendChild(b)})}
function palGo(i){const h=PAL.hits[i];if(!h)return;palClose();h.go()}
// The own settings under Ich are only drawn when Ich opens: draw them once quietly so the search finds them too.
let palWarm=null;
function palMe(){if(!PROFILE||palWarm||typeof renderSet!=='function'||GATE||isGuest()||$('setform').children.length)return;
  palWarm=renderSet($('setform'),S,saveSet).catch(()=>{}).then(()=>{if(PAL.open)palDraw()})}
function palOpen(){if(!ADMIN&&!PROFILE)return;const p=$('fpal');p.hidden=false;PAL.open=true;PAL.sel=0;$('palq').value='';palDraw();palMe();setTimeout(()=>$('palq').focus(),0)}
function palClose(){$('fpal').hidden=true;PAL.open=false}
(function(){const p=document.createElement('div');p.id='fpal';p.className='fpal';p.hidden=true;p.setAttribute('role','dialog');p.setAttribute('aria-modal','true');
  p.innerHTML=`<div class="fbox"><div class="fin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="palq" type="search" autocomplete="off"><button type="button" class="fx" id="palx">✕</button></div><div class="fres" id="palres"></div><div class="ffoot"><span></span><span></span><span></span></div></div>`;
  document.body.appendChild(p);const q=$('palq');q.placeholder=t('Suchen …','Search …');q.setAttribute('aria-label',t('Suchen','Search'));
  const f=p.querySelectorAll('.ffoot span');f[0].textContent=t('↑↓ wählen','↑↓ choose');f[1].textContent=t('Enter öffnen','Enter opens');f[2].textContent=t('Esc schließt','Esc closes');
  p.onclick=e=>{if(e.target===p)palClose()};
  // on a phone there is no Esc key: the cross closes the box
  const x=$('palx');x.setAttribute('aria-label',t('Schließen','Close'));x.title=t('Schließen','Close');x.onclick=palClose;
  q.oninput=()=>{PAL.sel=0;palDraw()};
  q.onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();PAL.sel=Math.max(0,Math.min(PAL.hits.length-1,PAL.sel+(e.key==='ArrowDown'?1:-1)));palDraw();
      const s=p.querySelector('.fit.sel');if(s)s.scrollIntoView({block:'nearest'})}
    else if(e.key==='Enter'){e.preventDefault();palGo(PAL.sel)}else if(e.key==='Escape'){palClose()}};
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.altKey&&e.key.toLowerCase()==='k'){e.preventDefault();PAL.open?palClose():palOpen()}
    else if(e.key==='Escape'&&PAL.open)palClose()});
  const b=$('findbtn');if(b){b.onclick=palOpen;b.querySelector('kbd').textContent=/Mac|iPhone|iPad/.test(navigator.platform)?'⌘ K':t('Strg K','Ctrl K')}})();
window.palOpen=palOpen;
