// Sprung-Links (Dominik 12.10.2026: „bei solchen Meldungen immer direkt Link anbieten“): every hint that names a
// place in the panel ("unter Einstellungen → Spark → Betrieb → Logs „Live-Seite“", "Ich → Dokumente",
// "Funktionen → Websuche", "Zustand → Logs → Anfragen") becomes a link that opens that place, unfolds what hides
// it and marks it. It works on whatever the page shows (fixed texts, messages from the panel, the assistant's
// answers), so a new hint links itself. The way is matched against the names on the page, step by step: only what
// the viewer can open is linked (admin pages for an admin, Ich for a profile, nothing for guests and the monitor).
// A link only moves to the place; it never switches, saves or sends anything.
const WAY_ROOTS=[['Personen und Geräte','prof'],['People and devices','prof'],['Einstellungen','cfg'],['Settings','cfg'],
  ['Funktionen','feat'],['Features','feat'],['Zustand','mon'],['Status','mon'],['Ich','me'],['Me','me'],['Kalender','o:calbox'],['Calendar','o:calbox'],
  ['E-Mail','o:mailbox'],['E-mail','o:mailbox'],['Listen','o:taskbox'],['Lists','o:taskbox'],['Offen','o:vgbox'],['Open','o:vgbox'],['Kontakte','o:conbox'],['Contacts','o:conbox'],['Wissensbuch','o:wbbox'],['Knowledge book','o:wbbox'],['Krisenspiel','o:ksbox'],['Crisis game','o:ksbox']];   // the pages of their own (kalender.js OWN_PAGES), both languages
const WAY_RX=/(Personen und Geräte|People and devices|Einstellungen|Settings|Funktionen|Features|Zustand|Status|Ich|Me|Kalender|Calendar|E-Mail|E-mail|Listen|Lists|Offen|Open|Kontakte|Contacts|Wissensbuch|Knowledge book|Krisenspiel|Crisis game)\s*→/g;
const WAY_ARROW=/^\s*→\s*/;
// the names a step can match inside a page: rows, headings, folded parts, tabs
const WAY_SEL='.setrow .lbl>b, label, summary, h2, h3, .ptabs button, .ltabs button, .lchips button, [data-tab], [data-area], .mgrp, .fgrp>summary b, .zk';
const WAY_TAB='.ptabs button,.ltabs button,.lchips button,[data-tab],[data-area]';
const wayMark=e=>e.closest('.setrow,.zcard')||e;
// where a hint is not turned into a link: controls, typed text, code, the search box, the menus themselves
const WAY_SKIP='[role=log],a,button,label,summary,select,option,textarea,input,[contenteditable],script,style,code,pre,svg,nav,#fpal,.sres,#ptabs,#cfgnav,#subnav,[data-nolink]';
const wayLow=s=>(s||'').toLocaleLowerCase('de');
const wayVis=e=>!!e&&!e.hidden&&getComputedStyle(e).display!=='none';
const wayWait=ms=>new Promise(r=>setTimeout(r,ms));
let WAY_MEMO=null;   // the names per step and which menus are seen, kept for one frame (a page can hold many hints)
const wayFrame=()=>{if(!WAY_MEMO){WAY_MEMO=new Map();requestAnimationFrame(()=>{WAY_MEMO=null})}return WAY_MEMO};
function wayRootOk(k,all){
  // Ich and the pages of their own (kalender.js OWN_PAGES) for a signed-in profile, the rest for an admin
  const own=k.startsWith('o:');
  if(own||k==='me'){if(all)return true;if(typeof PROFILE==='undefined'||!PROFILE||typeof GATE!=='undefined'&&GATE)return false;
    if(!own)return true;k=OWN_PAGES[k.slice(2)][0]}   // a page of its own: only while its menu entry shows
  else{if(typeof ADMIN==='undefined'||!ADMIN||typeof KIOSK!=='undefined'&&KIOSK)return false;if(all)return true}
  // once per frame: getComputedStyle after each link put in recalculated the whole page (8 s at an admin's start
  // on a slow phone, V01.0.749)
  const M=wayFrame(),key='vis:'+k;if(!M.has(key))M.set(key,wayVis(document.querySelector(`nav button[data-s=${k}]`)));return M.get(key)}
// the open parts of a page around an element: folded boxes, the function's detail
function wayOpen(el){for(let d=el.closest('details');d;d=d.parentElement.closest('details'))d.open=true;
  if(typeof featShow==='function')featShow(el)}
async function wayMe(id){if(typeof openMe!=='function')return;
  if($('profmodal').style.display==='grid'&&$(id)&&typeof ptab==='function'){meLast=id;ptab(id);return}
  await openMe(id)}
function wayKids(c,all){const key=JSON.stringify(c)+(all?'+':'');
  if(wayFrame().has(key))return WAY_MEMO.get(key);
  const out=[],seen=new Set(),add=(label,go,ctx,el)=>{label=(label||'').replace(/\s+/g,' ').trim().replace(/[:：]$/,'');
    const low=wayLow(label);if(!label||label.length>90||seen.has(low))return;seen.add(low);out.push({label,low,go,ctx:ctx||c,el})};
  // not inside guides, not a tab that is off (Logs → Anfragen without the recording)
  const inside=(root,go)=>{if(root)root.querySelectorAll(WAY_SEL).forEach(e=>{if(e.closest('details.guide')||e.hidden&&e.matches(WAY_TAB))return;add(visText(e),()=>go(e),c,e)})};
  if(c.k==='cfg'){
    document.querySelectorAll('#cfgnav button[data-p]').forEach(b=>add(visText(b),()=>goCfg(b.dataset.p),b.dataset.p==='feat'?{k:'feat'}:{k:'p',p:b.dataset.p}));
    document.querySelectorAll('#cfgnav .cgrp').forEach(e=>add(e.textContent,()=>goSec('cfg'),c))}   // Assistent, Sprache, Spark
  else if(c.k==='p'||c.k==='feat'){const p=c.k==='feat'?'feat':c.p;
    if(c.k==='feat')for(const [id,l] of GROUPS.feat)if(id!=='feat')add(l,()=>goSec(id),{k:'s',s:id});
    if(typeof cfgIndex==='function')for(const h of cfgIndex())if(h.p===p&&h.el)add(h.label,async()=>{goCfg(p);await wayWait(80);cfgGo(h)},c,h.el);
    inside($('pane-'+p),async e=>{goCfg(p);await wayWait(80);if(e.matches(WAY_TAB))e.click();wayOpen(e);sFlash(wayMark(e))})}
  else if(c.k==='mon'||c.k==='prof'){for(const [id,l] of GROUPS[c.k])add(l,()=>goSec(id),{k:'s',s:id});
    return wayKeep(key,out.concat(wayKids({k:'s',s:c.k},all)))}   // and what the first page shows (cards, lists)
  else if(c.k.startsWith('o:')){const [sec]=OWN_PAGES[c.k.slice(2)],go=k=>()=>{icTabSet(sec,k);goSec(sec)};
    add(t('Einstellungen','Settings'),go('set'),{k:'os',id:c.k.slice(2)});add(OWN_PAGES[c.k.slice(2)][2],go('show'),c);
    for(const [k,l,on] of OWN_PAGES[c.k.slice(2)][3]||[])if(all||on())add(l,go(k),{k:'ot',id:k})}
  else if(c.k==='os'){const [sec]=OWN_PAGES[c.id];inside($(c.id),async e=>{icTabSet(sec,'set');goSec(sec);await wayWait(120);wayOpen(e);sFlash(wayMark(e))})}
  else if(c.k==='s')inside($(c.s),async e=>{goSec(c.s);await wayWait(120);if(e.matches(WAY_TAB))e.click();wayOpen(e);sFlash(wayMark(e))});
  else if(c.k==='me'){const items=typeof meAll==='function'?meAll():[];
    for(const [id,l,on] of items)if(on||all)add(l,()=>wayMe(id),{k:'mp',id})}
  else if(c.k==='mp')inside($(c.id),async e=>{await wayMe(c.id);if(e.matches('.ptabs button'))e.click();else if(typeof meGo==='function')meGo({id:c.id,el:e.closest('.setrow')||e})});
  return wayKeep(key,out)}
function wayKeep(key,out){WAY_MEMO.set(key,out);return out}
// the longest name that the text continues with at i, ending at a word border; else a name the text shortens
// („Spark-Begleiter“ for „Spark-Begleiter am PC und Mac“, „Eigene Lautsprecher“ for „… (ESP32)“)
const WAY_END=/[\p{L}\p{N}]/u;
function wayStep(text,i,kids){const rest=wayLow(text.slice(i,i+120));let best=null,part=null,pl=0;
  for(const k of kids){const l=k.low;   // lowered once per frame (wayKids), not per hint
    if(l.length>(best?best.label.length:0)&&rest.startsWith(l)&&!WAY_END.test(rest.charAt(l.length)))best=k;
    else if(!best){const n=wayShort(rest,l);if(n>pl){pl=n;part=k}}}
  return best||(part&&{...part,label:text.slice(i,i+pl)})}
// how much of the name l the text starts with, when that is whole words of it (at least 8 letters)
function wayShort(rest,l){let n=0;
  for(let j=8;j<l.length;j++){if(l[j]!==' '&&l[j]!=='(')continue;const pre=l.slice(0,j).trimEnd();
    if(pre.length>=8&&rest.startsWith(pre)&&!WAY_END.test(rest.charAt(pre.length)))n=pre.length}
  return n}
// The way that starts at `at` in text: {start, end, hit (the last step that matched), steps, want (arrows seen)}.
// all=true knows the hidden Ich pages too (for the self-test), it never links.
function wayParse(text,at=0,all=false){
  // „Mein Zustand →“ is a page of Ich; „Uhr → Einstellungen →“, „Admin-Panel → Einstellungen →“ is another program
  if(/((Mein|My) |→\s*)$/.test(text.slice(Math.max(0,at-5),at)))return null;
  for(const [name,k] of WAY_ROOTS){if(!text.startsWith(name,at)||at>0&&/[\p{L}\p{N}-]/u.test(text.charAt(at-1)))continue;
    let pos=at+name.length,m=WAY_ARROW.exec(text.slice(pos));if(!m)continue;if(!wayRootOk(k,all))return null;
    let ctx={k},hit=null,steps=0,want=0,end=pos,quoted=false;
    // a step that starts small is what to do there („→ einschalten“, „→ switch on“), not a place
    while(m){let s=pos+m[0].length;const qo=/^[„“"]/.test(text.charAt(s))?1:0;s+=qo;   // a step in quotes: → „Probleme melden“
      if(/^[\p{Lu}\p{N}]/u.test(text.charAt(s)))want++;const kid=wayStep(text,s,wayKids(ctx,all));if(!kid)break;
      let e=s+kid.label.length;if(qo){if(!/^[“”"]/.test(text.charAt(e)))break;e++}
      hit=kid;steps++;pos=end=e;ctx=kid.ctx;m=WAY_ARROW.exec(text.slice(pos))}
    // the quoted name of a setting after the way: „Live-Seite“, “Live page”
    const q=/^\s*[„“"]([^“”"„]{1,80})[“”"]/.exec(text.slice(end));
    if(hit&&q){const kid=wayKids(ctx,all).find(x=>x.low===wayLow(q[1].trim()));if(kid){hit=kid;end+=q[0].length;quoted=true}}
    return hit?{start:at,end,hit,steps,want,quoted:q?quoted:null}:null}
  return null}
// Opens the place step by step: Ich and some pages draw their rows only once they open, so after a jump the way
// is looked up again until every step was found (at most 4 times).
async function wayGo(text){let last=null;
  for(let round=0;round<4;round++){const r=wayParse(text,0);if(!r)return;
    if(last&&r.end<=last.end&&r.steps<=last.steps)return;
    await r.hit.go();last=r;if(r.steps>=r.want&&r.quoted!==false)return;
    await wayWait(400)}}
// one link: text that opens the way (way.js turns hints into it, a tile under Zustand holds it)
function wayEl(text,way){const l=document.createElement('a');l.href='#';l.className='wayl';l.dataset.way=way;l.textContent=text;
  l.title=t('Dorthin springen','Go there');return l}
// a count that stands for a place (Zustand → Überblick „Heute“ tiles): the first way the viewer can open (the own
// page first, then the switch), else '' (the tile is no link then)
function wayFirst(...ways){return ways.find(x=>x&&wayParse(x,0))||''}
// Zahlen und Zeilen, die für einen Ort stehen (Dominik 14.10.2026: „sollte klickbar sein und direkt hinbringen“):
// a row (.zrow, .znrow, a count .kn-tn on a Technik page) with data-way, or in a card of WAY_CARDS, opens that place. A click on a control in the row
// stays the control's; a row without controls is a link for the keyboard too. Only counts and names move, never content.
const WAY_ROWS='.zrow,.znrow,.kn-tn',WAY_CTRL='a,button,input,select,textarea,label,summary';
const WAY_CARDS={zbg:['Funktionen → Mein Zustand','Features → My status'],zsvc:['Funktionen → Dienst-Wächter','Features → Service watch'],zwart:['Funktionen → Wartungspause','Features → Maintenance pause'],
  znas:['Ich → Speicher','Me → Storage'],znaszustand:['Funktionen → Zustand der NAS','Features → NAS status'],
  znasquelle:['Ich → Speicher','Me → Storage'],zstore:['Ich → Speicher','Me → Storage'],
  zdev:['Funktionen → Geräte-Updates','Features → Device updates'],zdocs:['Funktionen → Eigene Dokumente','Features → Own documents'],
  zverbrauch:['Zustand → Verbrauch','Status → Usage']};
function wayRowWay(r){if(r.dataset.way)return r.dataset.way;for(let c=r.parentElement;c;c=c.parentElement)if(WAY_CARDS[c.id])return t(...WAY_CARDS[c.id]);return ''}
function wayRows(root){if(!root||root.nodeType!==1)return;const l=root.matches(WAY_ROWS)?[root]:root.querySelectorAll(WAY_ROWS);
  for(const r of l){const w=wayRowWay(r),on=!!w&&!!wayParse(w,0);r.classList.toggle('wayrow',on);
    if(on&&!r.querySelector(WAY_CTRL)){r.setAttribute('role','link');r.tabIndex=0;r.title=t('Dorthin springen','Go there')}
    else if(r.getAttribute('role')==='link'){r.removeAttribute('role');r.removeAttribute('tabindex');r.removeAttribute('title')}}}
// turns the hints in one text node into links
function wayText(node){const s=node.nodeValue;if(!s||s.indexOf('→')<0)return;const p=node.parentElement;if(!p||p.closest(WAY_SKIP))return;
  const parts=[];let last=0,m;WAY_RX.lastIndex=0;
  while((m=WAY_RX.exec(s))){if(m.index<last)continue;const r=wayParse(s,m.index);if(!r)continue;
    parts.push([r.start,r.end]);last=r.end;WAY_RX.lastIndex=r.end}
  if(!parts.length)return;const f=document.createDocumentFragment();let at=0;
  for(const [a,b] of parts){if(a>at)f.appendChild(document.createTextNode(s.slice(at,a)));
    f.appendChild(wayEl(s.slice(a,b),s.slice(a,b)));at=b}
  if(at<s.length)f.appendChild(document.createTextNode(s.slice(at)));node.replaceWith(f)}
function wayScan(root){if(!root)return;if(root.nodeType===3){wayText(root);return}if(root.nodeType!==1||root.closest&&root.closest(WAY_SKIP))return;
  if(root.textContent.indexOf('→')<0)return;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),list=[];
  for(let n=w.nextNode();n;n=w.nextNode())if(n.nodeValue.indexOf('→')>=0)list.push(n);list.forEach(wayText)}
// #weg=Ich%20→%20Sicherheit: the apps, mails and messages link a way into the panel; only a known way opens
function wayHash(){const m=/^#weg=(.{3,600})$/.exec(location.hash);if(!m)return;history.replaceState(null,'',location.pathname+location.search);
  let w='';try{w=decodeURIComponent(m[1]).slice(0,200)}catch{return}if(wayParse(w,0))wayGo(w)}
// a way from outside while the page is open: the Android app loads #weg=… into it, a tapped notification sends it (sw.js)
addEventListener('hashchange',()=>{if(typeof PROFILE!=='undefined'&&location.hash.startsWith('#weg='))wayHash()});
if(navigator.serviceWorker)navigator.serviceWorker.addEventListener('message',e=>{const w=e.data&&e.data.weg;
  if(typeof PROFILE!=='undefined'&&typeof w==='string'&&w.length>=3&&w.length<=200&&wayParse(w,0))wayGo(w)});
document.addEventListener('click',e=>{if(!e.target.closest)return;const a=e.target.closest('a.wayl[data-way]');if(a){e.preventDefault();wayGo(a.dataset.way);return}
  const r=e.target.closest('.wayrow');if(r&&!e.target.closest(WAY_CTRL)&&!String(getSelection()||''))wayGo(wayRowWay(r))});
document.addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==' '||!e.target.matches||!e.target.matches('.wayrow[role=link]'))return;e.preventDefault();wayGo(wayRowWay(e.target))});
{let q=0;const todo=new Set();const later=()=>{if(!q)q=requestAnimationFrame(()=>{q=0;const l=[...todo];todo.clear();l.forEach(n=>{if(n.isConnected){wayScan(n);wayRows(n)}})})};
 // the version under the page is written once the page knows who signs in: then the whole page again (admin, Ich pages)
 new MutationObserver(ms=>{for(const m of ms){if(m.target.id==='ver')todo.add(document.body);if(m.type==='characterData')todo.add(m.target);else m.addedNodes.forEach(n=>todo.add(n))}later()})
   .observe(document.body,{childList:true,subtree:true,characterData:true});
 // the page as it stands now, after the other scripts drew it
 setTimeout(()=>{todo.add(document.body);later()},0)}
