// Wissensbuch (wissensbuch.py, plan plaene/wissensbuch.md; a page of its own in the menu since the Wissenskarte, plan
// wissensgraph/plan.md „2a“): pages the language model wrote from the own documents, every sentence with its source.
// „Seiten“: the pages by kind on the left, the one tapped on the right with its sentences, „Stimmt nicht“ per sentence,
// „Neu schreiben“ and „Löschen“; on top what the nightly check left for the owner (contradictions: „Stimmt“ keeps one
// value; „veraltet?“: „Stimmt noch“). „Karte“ (wissenskarte.py, own switch): the pages as points and their connections,
// drawn here from the panel's JSON with own code; titles, details and sources come from documents and are only ever
// text (textContent, esc), never markup. Drag a point to place it, drag a document onto the map to see its part.
// With „Personen, Firmen und Fristen“ (Stufe 2, own switch) the points from documents ("k" and their number) come along,
// each kind with its colour and a filter above the map; renaming, merging and deleting only by the owner's click.
const WBART={Thema:['Themen','Topics'],Person:['Personen','People'],Firma:['Firmen','Companies'],Ding:['Dinge','Things'],Ort:['Orte','Places'],Antwort:['Abgelegte Antworten','Filed answers']};
const WBWORD={eingearbeitet:['eingearbeitet','worked in'],nichts:['nichts Neues','nothing new'],fehler:['nicht eingearbeitet','not worked in'],
  geloescht:['Seite gelöscht','page deleted'],neu:['Seite neu geschrieben','page written again'],falsch:['Satz entfernt','sentence removed'],
  quelle:['Dokumente weg','documents gone'],geprueft:['nachts geprüft','checked at night'],probe:['Stichprobe: Satz entfernt','sample: sentence removed'],
  stimmt:['Widerspruch geklärt','contradiction settled'],noch:['stimmt noch','still right'],abgelegt:['Antwort abgelegt','answer filed'],
  nas:['auf den NAS kopiert','copied to the NAS']};
// the colour of a kind (app.css), named here in full so every class is found
const WKACLS={Thema:'wk-Thema',Person:'wk-Person',Firma:'wk-Firma',Ding:'wk-Ding',Ort:'wk-Ort',Antwort:'wk-Antwort'};
const WKKCLS={person:'wk-k-person',firma:'wk-k-firma',ort:'wk-k-ort',vertrag:'wk-k-vertrag',konto:'wk-k-konto',frist:'wk-k-frist'};
const WKKPL={person:['Personen','People'],firma:['Firmen','Companies'],ort:['Orte','Places'],vertrag:['Verträge','Contracts'],konto:['Konten','Accounts'],frist:['Fristen','Deadlines']};
const wkaCls=a=>WKACLS[a]||WKACLS.Thema;
const wkaNodeCls=n=>n.ent?(WKKCLS[n.ent]||WKKCLS.person):wkaCls(n.art);
const WB={data:null,sel:'',page:null,q:'',msg:'',err:false,seq:0};
let WB_ON=false,WK_ON=false;
const wbWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
// the menu entry only for a signed-in profile the admin released the Wissensbuch for (start.js, like Listen)
window.wbStart=who=>{WB_ON=!!(who&&who.profile&&who.knowledge_book);WK_ON=WB_ON&&!!who.knowledge_map;
  document.querySelectorAll('nav button[data-s=wbuch]').forEach(b=>b.hidden=!WB_ON)};
function wbOpen(){if(!PROFILE)return;const root=$('wbroot'),box=$('wbbox');if(box){box.hidden=true;$('wbuch').appendChild(box)}root.textContent='';
  const tabs=[{k:'show',label:OWN_PAGES.wbbox[2],body:wbBody}];
  if(WK_ON)tabs.push({k:'karte',label:t('Karte','Map'),body:wkaBody});
  root.appendChild(icTabs('wbuch',tabs));wbLoad()}
window.wbOpen=wbOpen;
async function wbLoad(){if(!WB_ON)return;const seq=++WB.seq;const {r,d}=await apiTry('/api/profile/wissensbuch');if(seq!==WB.seq)return;
  if(r.ok){WB.data=d;WB.err=false}else{WB.msg=errSay(r.status,d.detail,'');WB.err=true}
  wbDraw();if(WB.sel&&WB.sel!=='offen')wbPick(WB.sel,true)}
// kept for the button under an answer and older callers: draws the page again if it is open
async function wbShow(){if($('wbview'))await wbLoad()}
function wbBody(){const w=document.createElement('div');w.className='ld-box ld-frame wb';w.id='wbview';wbPaint(w);return w}
function wbDraw(){const w=$('wbview');if(w)wbPaint(w)}
function wbSay(x,err){WB.msg=String(x||'').slice(0,300);WB.err=!!err;const m=document.querySelector('#wbview .wbmsg');if(m){m.className='wbmsg '+(err?'err':'mut');m.textContent=WB.msg}}
function wbPaint(w){const W=WB.data;w.classList.toggle('ld-sel',!!WB.sel);
  if(!w.querySelector('.ld-split'))w.innerHTML=`<div class="ld-split"><div class="ld-list"></div><div class="ld-detail wbdet" hidden></div></div>`;
  const list=w.querySelector('.ld-list');
  if(!W){list.innerHTML=`<div class="ld-empty mut">${esc(WB.err?WB.msg:t('Lade das Wissensbuch …','Loading the knowledge book …'))}</div>`;return}
  const pages=(W.seiten||[]).filter(p=>p.n),q=WB.q.trim().toLowerCase(),shown=q?pages.filter(p=>p.title.toLowerCase().includes(q)):pages;
  const open=(W.widersprueche||[]).length+(W.veraltet||[]).length;
  const groups=Object.keys(WBART).map(a=>[a,shown.filter(p=>p.art===a)]).filter(([,l])=>l.length);
  list.innerHTML=`<div class="ld-tools"><input type="search" class="wbq" placeholder="${esc(t('Seiten suchen','Search pages'))}" aria-label="${esc(t('Seiten suchen','Search pages'))}" value="${esc(WB.q)}"></div>
    <div class="mut wbsum">${esc(t(`${pages.length} Seiten · ${W.saetze} Sätze · ${W.done} Dokumente eingearbeitet`,`${pages.length} pages · ${W.saetze} sentences · ${W.done} documents worked in`))}${W.wait?esc(t(` · ${W.wait} warten`,` · ${W.wait} waiting`)):''}${W.running?esc(t(' · arbeitet gerade',' · working')):''}</div>
    ${open?`<div class="ld-row${WB.sel==='offen'?' on':''}" role="button" tabindex="0" data-wbsel="offen"><span class="ld-ico wbico warn" aria-hidden="true">!</span><span class="ld-mid"><b>${esc(t('Braucht dich','Needs you'))}</b><small>${esc(t(`${(W.widersprueche||[]).length} Widersprüche · ${(W.veraltet||[]).length} veraltet?`,`${(W.widersprueche||[]).length} contradictions · ${(W.veraltet||[]).length} out of date?`))}</small></span><span class="ld-right"><b>${open}</b></span></div>`:''}
    ${pages.length?'':`<div class="ld-empty mut">${esc(t('Noch keine Seiten. Sie entstehen, während niemand mit dem Spark spricht, höchstens '+W.day+' Dokumente am Tag.','No pages yet. They are made while nobody talks to the Spark, at most '+W.day+' documents a day.'))}</div>`}
    ${groups.map(([a,l])=>`<div class="ld-grp"><span>${esc(t(...WBART[a]))}</span><span>${l.length}</span></div>`+l.map(p=>`<div class="ld-row${p.id===WB.sel?' on':''}" role="button" tabindex="0" data-wbsel="${esc(p.id)}"><span class="ld-ico wbico ${wkaCls(p.art)}" aria-hidden="true">${esc((p.title||'?').slice(0,1).toUpperCase())}</span><span class="ld-mid"><b>${esc(p.title)}</b><small>${esc(t(`${p.n} Sätze aus ${p.docs} Dokumenten`,`${p.n} sentences from ${p.docs} documents`))}</small></span><span class="ld-right">${p.widerspruch?`<span class="ld-badge err">${esc(t('Widerspruch','Contradiction'))}</span>`:''}</span></div>`).join('')).join('')}
    ${(W.verlauf||[]).length?`<details class="mkmore"><summary>${esc(t('Verlauf','History'))}</summary><ul class="facts small">${W.verlauf.map(v=>`<li><span>${esc(wbWhen(v.at))} · ${esc(t(...(WBWORD[v.word]||[v.word,v.word])))}</span><b>${v.word==='eingearbeitet'?esc(t(`${v.n} Seiten, ${v.m} Sätze`,`${v.n} pages, ${v.m} sentences`)):''}</b></li>`).join('')}</ul></details>`:''}
    ${pages.length?`<div class="row"><a class="b" href="/api/profile/wissensbuch/export" download="Wissensbuch.zip">${esc(t('Als Obsidian-Ordner herunterladen','Download as an Obsidian folder'))}</a></div>`:''}
    <div class="wbmsg ${WB.err?'err':'mut'}" role="status">${esc(WB.msg)}</div>`;
  const qi=list.querySelector('.wbq');qi.oninput=()=>{WB.q=qi.value;const pos=qi.selectionStart;wbDraw();const n=document.querySelector('#wbview .wbq');if(n){n.focus();n.setSelectionRange(pos,pos)}};
  list.querySelectorAll('[data-wbsel]').forEach(r=>{const go=()=>wbPick(r.dataset.wbsel);r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  wbDetail(w)}
async function wbPick(id,quiet){WB.sel=id;if(id&&id!=='offen'){const r=await apiTry('/api/profile/wissensbuch/'+encodeURIComponent(id));
    if(!r.r.ok){WB.page=null;WB.sel='';if(!quiet)wbSay(r.d.detail,true);wbDraw();return}WB.page=r.d}else WB.page=null;wbDraw()}
function wbSrcIn(s){const n=esc(s.name+(s.page?t(' · S. ',' · p. ')+s.page:''));return s.kiwix?n:`<a href="#" data-wbdoc="${esc(s.doc)}">${n}</a>`}
function wbDetail(w){const det=w.querySelector('.wbdet'),W=WB.data;if(!WB.sel||!W){det.hidden=true;det.textContent='';return}
  det.hidden=false;const back=`<button class="b ld-back" type="button" data-wbback="1">‹ ${esc(OWN_PAGES.wbbox[1])}</button>`;
  if(WB.sel==='offen'){const c=W.widersprueche||[],v=W.veraltet||[];
    det.innerHTML=back+`<h3>${esc(t('Braucht dich','Needs you'))}</h3>`+
      (c.length?`<h4>${esc(t(`Widersprüche (${c.length})`,`Contradictions (${c.length})`))}</h4><div class="mut">${esc(t('Zwei Dokumente sagen verschiedene Werte. Welcher stimmt? Die anderen fallen weg.','Two documents say different values. Which is right? The others go.'))}</div>
      <ul class="facts">${c.map(g=>`<li><span><b>${esc(g.seite)}</b>${g.werte.map(s=>`<br>${esc(s.text)} <small class="mut">${wbSrcIn(s)}</small> <button type="button" class="b" data-wbright="${esc(String(s.id))}">${esc(t('Stimmt','Right'))}</button>`).join('')}</span></li>`).join('')}</ul>`:'')+
      (v.length?`<h4>${esc(t(`Veraltet? (${v.length})`,`Out of date? (${v.length})`))}</h4><div class="mut">${esc(t('Ein Datum ist vorbei oder ein Wort wie „derzeit“ ist alt.','A date has passed or a word like "currently" is old.'))}</div>
      <ul class="facts">${v.map(s=>`<li><span>${esc(s.text)}<br><b>${esc(s.seite)}</b> · <small class="mut">${wbSrcIn(s)}</small></span><span><button type="button" class="b" data-wbstill="${esc(String(s.id))}">${esc(t('Stimmt noch','Still right'))}</button> <button type="button" class="b" data-wbbad="${esc(String(s.id))}">${esc(t('Stimmt nicht','Wrong'))}</button></span></li>`).join('')}</ul>`:'')+
      (c.length||v.length?'':`<div class="mut">${esc(t('Nichts offen.','Nothing open.'))}</div>`);return}
  const p=WB.page;if(!p){det.innerHTML=back;return}
  det.innerHTML=back+`<h3>${esc(p.title)}</h3><div class="mut">${esc(t(...(WBART[p.art]||[p.art,p.art])))} · ${esc(t('zuletzt geändert ','last changed '))}${esc(wbWhen(p.changed))}</div>
    <ul class="facts wbsents">${p.saetze.map(s=>`<li><span>${esc(s.text)}<br><small class="mut">${wbSrcIn(s)}${s.mark==='widerspruch'?' · <b class="err">'+esc(t('Widerspruch','Contradiction'))+'</b>':''}${s.flag==='veraltet'?' · <span class="pill warn">'+esc(t('veraltet?','out of date?'))+'</span>':''}</small></span><button type="button" class="b" data-wbbad="${esc(String(s.id))}">${esc(t('Stimmt nicht','Wrong'))}</button></li>`).join('')}</ul>
    <div class="row">${WK_ON?`<button type="button" class="b p" data-wbmap="${esc(p.id)}">${esc(t('Auf der Karte zeigen','Show on the map'))}</button>`:''}<button type="button" class="b" data-wbagain="${esc(p.id)}">${esc(t('Neu schreiben','Write again'))}</button><button type="button" class="b" data-wbdel="${esc(p.id)}">${esc(t('Seite löschen','Delete page'))}</button></div>`}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#wbview [data-wbbad],#wbview [data-wbagain],#wbview [data-wbdel],#wbview [data-wbdoc],#wbview [data-wbright],#wbview [data-wbstill],#wbview [data-wbback],#wbview [data-wbmap]');if(!b)return;const D=b.dataset;
  if(D.wbback){WB.sel='';WB.page=null;wbDraw();return}
  if(D.wbdoc){e.preventDefault();if(typeof docView==='function')docView(D.wbdoc);return}
  if(D.wbmap){wkaFocus(D.wbmap);return}
  if(D.wbright||D.wbstill){b.disabled=true;const r=await apiTry('/api/profile/wissensbuch/satz/'+encodeURIComponent(D.wbright||D.wbstill)+(D.wbright?'/stimmt':'/noch'),{method:'POST'});
    if(!r.r.ok){wbSay(r.d.detail,true);b.disabled=false;return}await wbLoad();wbSay(D.wbright?t('Geklärt; die anderen Werte kommen nicht wieder.','Settled; the other values do not come back.'):t('Gemerkt.','Noted.'));return}
  if(D.wbbad){b.disabled=true;const r=await apiTry('/api/profile/wissensbuch/satz/'+encodeURIComponent(D.wbbad),{method:'DELETE'});
    if(!r.r.ok){wbSay(r.d.detail,true);b.disabled=false;return}await wbLoad();wbSay(t('Satz entfernt; aus diesem Dokument kommt er nicht wieder.','Sentence removed; it does not come back from this document.'));return}
  if(D.wbagain||D.wbdel){const again=!!D.wbagain,id=D.wbagain||D.wbdel;
    if(!again&&!confirm(t('Seite löschen? Ihre Dokumente werden später neu eingearbeitet.','Delete the page? Its documents are worked in again later.')))return;
    const r=await apiTry('/api/profile/wissensbuch/'+encodeURIComponent(id)+(again?'/neu':''),{method:again?'POST':'DELETE'});
    if(!r.r.ok){wbSay(r.d.detail,true);return}WB.sel='';WB.page=null;await wbLoad();
    wbSay(again?t('Die Seite entsteht in ruhigen Minuten neu.','The page is written again in quiet minutes.'):t('Seite gelöscht.','Page deleted.'))}})}
// "Ins Wissensbuch" under an answer (chat.js): the panel kept the answer and its sources; the click only names its id
async function wbFile(id,b){b.disabled=true;const r=await apiTry('/api/profile/wissensbuch/ablegen',xjson('POST',{id}));
  if(!r.r.ok){b.textContent=t('Nicht mehr möglich','No longer possible');return}
  b.textContent=r.d.saetze?t(`Im Wissensbuch: ${r.d.saetze} Sätze`,`In the knowledge book: ${r.d.saetze} sentences`):t('Kein Satz mit Quelle gefunden','No sentence with a source found');
  wbShow()}

// ---------------------------------------------------------------- Karte (wissenskarte.py)
const WKA={data:null,um:'',doc:'',art:'',tiefe:2,sel:null,pos:{},lay:'',seq:0,view:{x:0,y:0,k:1},q:'',more:false,msg:'',same:null};
const WK_SVG='http://www.w3.org/2000/svg';
function wkaS(tag,attrs,text){const n=document.createElementNS(WK_SVG,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,String(v));if(text!=null)n.textContent=String(text);return n}
const wkaArt=k=>{const a=WKA.data&&WKA.data.arten[k];return a?(L==='en'?a[1]:a[0]):k};
function wkaFocus(id){WKA.um=id;WKA.doc='';WKA.art='';WKA.sel={k:'n',id};icTabSet('wbuch','karte');if(!$('wkview'))wbOpen();else wkaLoad()}
function wkaBody(){const w=document.createElement('div');w.className='wk';w.id='wkview';
  w.innerHTML=`<div class="wktools"></div><div class="wkgrid"><div class="wkside"></div><div class="wkmap" tabindex="0" aria-label="${esc(t('Wissenskarte','Knowledge map'))}"></div><div class="wkdet"></div></div><div class="wkmsg mut" role="status"></div>`;
  wkaMapEvents(w.querySelector('.wkmap'));setTimeout(wkaLoad,0);return w}
async function wkaLoad(){const seq=++WKA.seq,qs=new URLSearchParams();if(WKA.um){qs.set('um',WKA.um);qs.set('tiefe',String(WKA.tiefe))}else if(WKA.doc)qs.set('doc',WKA.doc);else if(WKA.art)qs.set('art',WKA.art);
  const {r,d}=await apiTry('/api/profile/wissenskarte'+(qs.toString()?'?'+qs:''));if(seq!==WKA.seq)return;
  if(!r.ok){WKA.msg=errSay(r.status,d.detail,'');wkaPaint();return}
  WKA.data=d;WKA.msg='';if(WKA.um&&!d.um)WKA.um='';if(WKA.doc&&!d.doc)WKA.doc='';if(WKA.art&&!d.art)WKA.art='';
  const lay=[d.um,d.doc,d.art,WKA.tiefe].join('|'),fit=lay!==WKA.lay;if(fit){WKA.pos={};WKA.lay=lay}   // another part: placed anew; the same part keeps its places
  wkaLayout();if(fit)wkaFit();wkaPaint()}
// placing the points: around a page in rings (the page in the middle), else a force layout that always starts the same;
// a point already placed (or dragged) keeps its place, so nothing jumps when more comes in
function wkaLayout(){const d=WKA.data;if(!d)return;const ns=d.nodes,P=WKA.pos,fresh=ns.filter(n=>!P[n.id]);if(!fresh.length)return;
  if(d.um){const ring1=new Set(),adj={};for(const e of d.edges){(adj[e.a]=adj[e.a]||[]).push(e.b);(adj[e.b]=adj[e.b]||[]).push(e.a)}
    for(const x of adj[d.um]||[])ring1.add(x);const r1=[...ring1],r2=ns.map(n=>n.id).filter(x=>x!==d.um&&!ring1.has(x));
    const at={};at[d.um]=[0,0];r1.forEach((x,i)=>{const a=2*Math.PI*i/Math.max(r1.length,1)-Math.PI/2;at[x]=[Math.cos(a)*240,Math.sin(a)*240]});
    r2.forEach((x,i)=>{const par=(adj[x]||[]).find(y=>at[y]&&y!==d.um);const base=par?Math.atan2(at[par][1],at[par][0]):2*Math.PI*i/Math.max(r2.length,1);
      const a=base+((i%3)-1)*0.28;at[x]=[Math.cos(a)*460,Math.sin(a)*460]});
    for(const n of fresh)P[n.id]=at[n.id]||[0,0];return}
  const idx={},N=ns.length;ns.forEach((n,i)=>idx[n.id]=i);
  const p=ns.map((n,i)=>P[n.id]?[...P[n.id]]:[Math.cos(2*Math.PI*i/N)*Math.sqrt(N)*60,Math.sin(2*Math.PI*i/N)*Math.sqrt(N)*60]);
  const fixed=ns.map(n=>!!P[n.id]),K=170,E=d.edges.map(e=>[idx[e.a],idx[e.b]]).filter(([a,b])=>a!=null&&b!=null);
  for(let it=0;it<240;it++){const f=p.map(()=>[0,0]),temp=40*(1-it/240)+2;
    for(let i=0;i<N;i++)for(let j=i+1;j<N;j++){let dx=p[i][0]-p[j][0],dy=p[i][1]-p[j][1],dd=Math.hypot(dx,dy)||0.1;const rep=K*K/dd;dx/=dd;dy/=dd;
      f[i][0]+=dx*rep;f[i][1]+=dy*rep;f[j][0]-=dx*rep;f[j][1]-=dy*rep}
    for(const [a,b] of E){let dx=p[a][0]-p[b][0],dy=p[a][1]-p[b][1],dd=Math.hypot(dx,dy)||0.1;const att=dd*dd/K;dx/=dd;dy/=dd;
      f[a][0]-=dx*att;f[a][1]-=dy*att;f[b][0]+=dx*att;f[b][1]+=dy*att}
    for(let i=0;i<N;i++){if(fixed[i])continue;const m=Math.hypot(f[i][0],f[i][1])||1;p[i][0]+=f[i][0]/m*Math.min(m,temp);p[i][1]+=f[i][1]/m*Math.min(m,temp)}}
  ns.forEach((n,i)=>{if(!P[n.id])P[n.id]=p[i]})}
const wkaW=n=>Math.min(260,Math.max(80,(n.title.length*7)+38)),WK_H=34;
function wkaFit(){const d=WKA.data,box=document.querySelector('#wkview .wkmap');if(!d||!box||!d.nodes.length)return;
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const n of d.nodes){const [x,y]=WKA.pos[n.id],w=wkaW(n)/2;x0=Math.min(x0,x-w);x1=Math.max(x1,x+w);y0=Math.min(y0,y-WK_H);y1=Math.max(y1,y+WK_H)}
  const W=box.clientWidth||800,H=box.clientHeight||520,k=Math.max(0.25,Math.min(1.4,Math.min(W/(x1-x0+60),H/(y1-y0+60))));
  WKA.view={k,x:W/2-k*(x0+x1)/2,y:H/2-k*(y0+y1)/2}}
function wkaPaint(){const w=$('wkview');if(!w)return;const d=WKA.data;
  w.querySelector('.wkmsg').textContent=WKA.msg;
  const tools=w.querySelector('.wktools');tools.textContent='';
  if(!d){tools.appendChild(icEl('span','mut',WKA.msg?'':t('Lade die Karte …','Loading the map …')));return}
  const um=d.nodes.find(n=>n.id===d.um),dc=d.docs.find(x=>x.id===d.doc);
  const crumb=icEl('span','wkcrumb');crumb.appendChild(icChip(t('Alles','Everything'),!um&&!dc&&!d.art,()=>{WKA.um='';WKA.doc='';WKA.art='';WKA.sel=null;wkaLoad()}));
  // the points from documents by kind (numbers only from the panel); a kind shows its points with their neighbours
  if(d.ents)for(const [k,n] of Object.entries(d.knoten||{})){if(!n)continue;const c=icChip(t(...WKKPL[k])+' '+n,d.art===k,()=>{WKA.art=d.art===k?'':k;WKA.um='';WKA.doc='';WKA.sel=null;wkaLoad()},'wkk '+WKKCLS[k]);crumb.appendChild(c)}
  if(um){crumb.appendChild(icChip(t('Um ','Around ')+um.title,true,null));const seg=icEl('span','segc');
    for(const k of [1,2]){const b=icEl('button',WKA.tiefe===k?'on':'',k===1?t('1 Schritt','1 step'):t('2 Schritte','2 steps'));b.type='button';b.setAttribute('aria-pressed',String(WKA.tiefe===k));b.onclick=()=>{WKA.tiefe=k;wkaLoad()};seg.appendChild(b)}crumb.appendChild(seg)}
  if(dc)crumb.appendChild(icChip(t('Dokument ','Document ')+dc.name,true,null));
  tools.appendChild(crumb);
  const sum=icEl('span','mut wksum',t(`${d.nodes.length} Dinge · ${d.edges.length} Verbindungen`,`${d.nodes.length} things · ${d.edges.length} connections`)+(d.cut?t(' (Ausschnitt)',' (part)'):'')+(d.wait?t(` · ${d.wait} Dokumente warten`,` · ${d.wait} documents waiting`):'')+(d.running?t(' · arbeitet',' · working'):''));
  tools.appendChild(sum);
  const zoom=icEl('span','wkzoom');for(const [lab,act,name] of [['−',()=>wkaZoom(1/1.25),t('Kleiner','Zoom out')],['+',()=>wkaZoom(1.25),t('Größer','Zoom in')],['⤢',()=>{wkaFit();wkaDraw()},t('Alles zeigen','Fit')]]){const b=icEl('button','b',lab);b.type='button';b.title=name;b.setAttribute('aria-label',name);b.onclick=act;zoom.appendChild(b)}
  tools.appendChild(zoom);
  const ex=document.createElement('details');ex.className='wkexp';ex.innerHTML=`<summary class="b">${esc(t('Exportieren','Export'))}</summary><div class="wkexpm"></div>`;
  const m=ex.querySelector('.wkexpm'),qs=new URLSearchParams();if(d.um){qs.set('um',d.um);qs.set('tiefe',String(WKA.tiefe))}else if(d.doc)qs.set('doc',d.doc);else if(d.art)qs.set('art',d.art);qs.set('lang',L==='en'?'en':'de');
  for(const [fmt,lab] of [['mermaid','Mermaid'],['dot','Graphviz']]){const a=icEl('a','b',lab);a.href='/api/profile/wissenskarte/export?fmt='+fmt+'&'+qs;a.setAttribute('download','Wissenskarte.'+(fmt==='dot'?'dot':'mmd'));m.appendChild(a)}
  for(const [kind,lab] of [['svg',t('Bild (SVG)','Picture (SVG)')],['png',t('Bild (PNG)','Picture (PNG)')]]){const b=icEl('button','b',lab);b.type='button';b.onclick=()=>wkaSave(kind);m.appendChild(b)}
  tools.appendChild(ex);
  wkaSide(w);wkaDraw();wkaDetail(w)}
function wkaSide(w){const d=WKA.data,side=w.querySelector('.wkside');side.textContent='';
  const q=icEl('input','');q.type='search';q.placeholder=t('In der Karte suchen','Search the map');q.setAttribute('aria-label',q.placeholder);q.value=WKA.q;
  q.oninput=()=>{WKA.q=q.value;const pos=q.selectionStart;wkaSide(w);const n=w.querySelector('.wkside input');n.focus();n.setSelectionRange(pos,pos)};side.appendChild(q);
  const qq=WKA.q.trim().toLowerCase(),ns=d.nodes.filter(n=>!qq||n.title.toLowerCase().includes(qq)).sort((a,b)=>b.deg-a.deg||a.title.localeCompare(b.title));
  side.appendChild(icEl('div','ld-grp',t('Dinge','Things')));
  for(const n of WKA.more?ns:ns.slice(0,12)){const r=icEl('div','ld-row'+(WKA.sel&&WKA.sel.k==='n'&&WKA.sel.id===n.id?' on':''));r.tabIndex=0;r.setAttribute('role','button');
    const dot=icEl('span','wkdot '+wkaNodeCls(n));const mid=icEl('span','ld-mid');mid.appendChild(icEl('b','',n.title));r.append(dot,mid,icEl('span','ld-right',String(n.deg)));
    const go=()=>{WKA.sel={k:'n',id:n.id};wkaDraw();wkaDetail(w);wkaSide(w)};r.onclick=go;r.ondblclick=()=>wkaFocus(n.id);r.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();go()}};side.appendChild(r)}
  if(ns.length>12)side.appendChild(icLink(WKA.more?t('Weniger zeigen','Show fewer'):t(`Weitere ${ns.length-12} zeigen`,`Show ${ns.length-12} more`),()=>{WKA.more=!WKA.more;wkaSide(w)}));
  if(!ns.length)side.appendChild(icEl('div','mut',d.total.edges?t('Nichts gefunden.','Nothing found.'):t('Noch keine Verbindungen. Sie entstehen in ruhigen Minuten nach dem Wissensbuch.','No connections yet. They are made in quiet minutes after the knowledge book.')));
  if(d.docs.length){side.appendChild(icEl('div','ld-grp',t('Dokumente','Documents')));
    for(const x of d.docs.slice(0,12)){const r=icEl('div','ld-row wkdoc'+(d.doc===x.id?' on':''));r.tabIndex=0;r.setAttribute('role','button');r.draggable=true;
      const mid=icEl('span','ld-mid');mid.appendChild(icEl('b','',x.name));r.append(mid,icEl('span','ld-right',String(x.n)));
      const go=()=>{WKA.doc=x.id;WKA.um='';WKA.sel=null;wkaLoad()};r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();go()}};
      r.ondragstart=e=>{e.dataTransfer.setData('text/plain','wkdoc:'+x.id);e.dataTransfer.effectAllowed='copy'};side.appendChild(r)}
    side.appendChild(icEl('div','wkdrop mut',t('Dokument auf die Karte ziehen: seine Zusammenhänge','Drag a document onto the map: its connections')))}}
function wkaZoom(f){const box=document.querySelector('#wkview .wkmap');if(!box)return;const W=box.clientWidth/2,H=box.clientHeight/2,v=WKA.view,k=Math.max(0.2,Math.min(3,v.k*f));
  v.x=W-(W-v.x)*k/v.k;v.y=H-(H-v.y)*k/v.k;v.k=k;wkaDraw()}
// the edge ends at the border of the box around a point, so its arrow stays visible
function wkaEnd(n,from){const [x,y]=WKA.pos[n.id],[fx,fy]=from,dx=fx-x,dy=fy-y,hw=wkaW(n)/2+3,hh=WK_H/2+3;
  const s=Math.min(hw/Math.max(Math.abs(dx),1e-6),hh/Math.max(Math.abs(dy),1e-6));return [x+dx*Math.min(s,1),y+dy*Math.min(s,1)]}
function wkaDraw(){const box=document.querySelector('#wkview .wkmap'),d=WKA.data;if(!box||!d)return;box.textContent='';
  const svg=wkaS('svg',{class:'wksvg',role:'img','aria-label':t('Wissenskarte','Knowledge map'),width:'100%',height:'100%'});
  const defs=wkaS('defs');for(const [id,cls] of [['wka','wkah'],['wkc','wkah c'],['wks','wkah s']]){const mk=wkaS('marker',{id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});mk.appendChild(wkaS('path',{d:'M0,0L10,5L0,10z',class:cls}));defs.appendChild(mk)}
  svg.appendChild(defs);const v=WKA.view,g=wkaS('g',{transform:`translate(${v.x},${v.y}) scale(${v.k})`});svg.appendChild(g);
  const byId={};for(const n of d.nodes)byId[n.id]=n;const sel=WKA.sel,near=new Set();
  if(sel&&sel.k==='n'){near.add(sel.id);for(const e of d.edges){if(e.a===sel.id)near.add(e.b);if(e.b===sel.id)near.add(e.a)}}
  const labels=v.k>=0.7||d.edges.length<=40;
  for(const e of d.edges){const a=byId[e.a],b=byId[e.b];if(!a||!b)continue;const on=sel&&(sel.k==='e'&&sel.id===e.id||sel.k==='n'&&(e.a===sel.id||e.b===sel.id));
    const [x1,y1]=wkaEnd(a,WKA.pos[b.id]),[x2,y2]=wkaEnd(b,WKA.pos[a.id]);
    const eg=wkaS('g',{class:'wke'+(e.cause?' c':'')+(on?' s':'')+(sel&&!on?' dim':''),'data-e':e.id});
    eg.appendChild(wkaS('line',{x1,y1,x2,y2,class:'hit'}));eg.appendChild(wkaS('line',{x1,y1,x2,y2,'marker-end':`url(#${on?'wks':e.cause?'wkc':'wka'})`}));
    if(labels||on){const lab=wkaArt(e.art)+(e.detail?' · '+e.detail:''),mx=(x1+x2)/2,my=(y1+y2)/2,lw=lab.length*6.2+12;
      eg.appendChild(wkaS('rect',{x:mx-lw/2,y:my-9,width:lw,height:17,rx:8,class:'lab'}));eg.appendChild(wkaS('text',{x:mx,y:my+4,'text-anchor':'middle'},lab))}
    g.appendChild(eg)}
  for(const n of d.nodes){const [x,y]=WKA.pos[n.id],w=wkaW(n),on=sel&&sel.k==='n'&&sel.id===n.id;
    const ng=wkaS('g',{class:'wkn '+wkaNodeCls(n)+(n.ent?' k':'')+(on?' s':'')+(n.id===d.um?' um':'')+(sel&&sel.k==='n'&&!near.has(n.id)?' dim':''),'data-n':n.id,transform:`translate(${x},${y})`});
    ng.appendChild(wkaS('rect',{x:-w/2,y:-WK_H/2,width:w,height:WK_H,rx:n.ent?6:WK_H/2}));ng.appendChild(wkaS('circle',{cx:-w/2+16,cy:0,r:5}));
    const tx=wkaS('text',{x:-w/2+28,y:4},n.title.length>30?n.title.slice(0,29)+'…':n.title);ng.appendChild(tx);g.appendChild(ng)}
  box.appendChild(svg);
  if(!d.nodes.length){const e=icEl('div','wkempty mut',d.total.edges?t('Hier gibt es keine Verbindungen.','No connections here.'):t('Noch keine Verbindungen. Sie entstehen in ruhigen Minuten aus den Seiten des Wissensbuchs.','No connections yet. They are made in quiet minutes from the pages of the knowledge book.'));box.appendChild(e)}}
// pan the map by dragging the background, move a point by dragging it, tap selects, double tap puts it in the middle;
// a document dropped on the map shows its part
function wkaMapEvents(box){let drag=null;const pts=new Map();let pinch=null;
  // wheel and two fingers zoom around the middle of the map
  box.addEventListener('wheel',e=>{e.preventDefault();wkaZoom(e.deltaY<0?1.15:1/1.15)},{passive:false});
  const twoApart=()=>{const [a,b]=[...pts.values()];return Math.hypot(a[0]-b[0],a[1]-b[1])||1};
  box.addEventListener('pointerdown',e=>{pts.set(e.pointerId,[e.clientX,e.clientY]);if(pts.size===2){drag=null;pinch=twoApart();return}},true);
  box.addEventListener('pointermove',e=>{if(!pts.has(e.pointerId))return;pts.set(e.pointerId,[e.clientX,e.clientY]);
    if(pinch&&pts.size===2){const d=twoApart();wkaZoom(d/pinch);pinch=d;e.stopImmediatePropagation()}},true);
  const lift=e=>{pts.delete(e.pointerId);if(pts.size<2)pinch=null};
  box.addEventListener('pointerup',lift,true);box.addEventListener('pointercancel',lift,true);
  box.addEventListener('pointerdown',e=>{if(e.button!==0||pinch)return;const ng=e.target.closest('[data-n]'),eg=e.target.closest('[data-e]');
    drag={x:e.clientX,y:e.clientY,n:ng&&ng.dataset.n,e:eg&&!ng?+eg.dataset.e:null,moved:false,v:{...WKA.view}};
    if(drag.n)drag.p=[...WKA.pos[drag.n]];box.setPointerCapture(e.pointerId)});
  box.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)<4)return;drag.moved=true;
    if(drag.n){WKA.pos[drag.n]=[drag.p[0]+dx/WKA.view.k,drag.p[1]+dy/WKA.view.k]}else{WKA.view.x=drag.v.x+dx;WKA.view.y=drag.v.y+dy}wkaDraw()});
  box.addEventListener('pointerup',()=>{if(!drag)return;const d=drag;drag=null;if(d.moved)return;const w=$('wkview');
    if(d.n)WKA.sel={k:'n',id:d.n};else if(d.e!=null)WKA.sel={k:'e',id:d.e};else WKA.sel=null;wkaDraw();if(w){wkaDetail(w);wkaSide(w)}});
  box.addEventListener('dblclick',e=>{const ng=e.target.closest('[data-n]');if(ng)wkaFocus(ng.dataset.n)});
  box.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='=')wkaZoom(1.25);else if(e.key==='-')wkaZoom(1/1.25);else if(e.key==='0'){wkaFit();wkaDraw()}});
  box.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('text/plain')){e.preventDefault();box.classList.add('drop')}});
  box.addEventListener('dragleave',()=>box.classList.remove('drop'));
  box.addEventListener('drop',e=>{box.classList.remove('drop');const m=/^wkdoc:([0-9a-f]{12})$/.exec(e.dataTransfer.getData('text/plain')||'');if(!m)return;e.preventDefault();
    WKA.doc=m[1];WKA.um='';WKA.sel=null;wkaLoad()})}
function wkaSrc(e){const b=icEl('a','',e.name+(e.page?t(' · S. ',' · p. ')+e.page:''));b.href='#';b.onclick=ev=>{ev.preventDefault();if(typeof docView==='function')docView(e.doc)};return b}
function wkaEdgeRow(e,byId){const li=icEl('li','');const s=icEl('span','');const a=byId[e.a],b=byId[e.b];
  s.append(icEl('b','',a?a.title:'?'),document.createTextNode(' '),icEl('b',e.cause?'wkcause':'',wkaArt(e.art)),document.createTextNode(' '+(b?b.title:'?')+(e.detail?' · '+e.detail:'')),document.createElement('br'));
  const sm=icEl('small','mut');sm.appendChild(wkaSrc(e));s.appendChild(sm);const x=icEl('button','b',t('Stimmt nicht','Wrong'));x.type='button';x.onclick=()=>wkaWrong(e.id,x);li.append(s,x);return li}
function wkaDetail(w){const det=w.querySelector('.wkdet'),d=WKA.data;det.textContent='';if(!d)return;const byId={};for(const n of d.nodes)byId[n.id]=n;const sel=WKA.sel;
  if(!sel){det.appendChild(icEl('h3','',t('Ausgewählt','Selected')));det.appendChild(icEl('div','mut',t('Tippe einen Punkt oder eine Verbindung an. Doppelt tippen stellt den Punkt in die Mitte.','Tap a point or a connection. A double tap puts the point in the middle.')));
    det.appendChild(icEl('div','mut wklegend',t('Gestrichelt: Ursache und Wirkung, nur wenn die Quelle den Grund nennt.','Dashed: cause and effect, only when the source names the reason.')));return}
  if(sel.k==='e'){const e=d.edges.find(x=>x.id===sel.id);if(!e)return;det.appendChild(icEl('h3','',wkaArt(e.art)));const ul=icEl('ul','facts');ul.appendChild(wkaEdgeRow(e,byId));det.appendChild(ul);return}
  const n=byId[sel.id];if(!n)return;const h=icEl('h3','');h.append(icEl('span','wkdot '+wkaNodeCls(n)),document.createTextNode(n.title));det.appendChild(h);
  const kind=n.ent?(d.ent_arten&&d.ent_arten[n.ent]?t(...d.ent_arten[n.ent]):n.art):t(...(WBART[n.art]||[n.art,n.art]));
  det.appendChild(icEl('div','mut',kind+' · '+(n.ent?t(`${n.n} Stellen`,`${n.n} passages`):t(`${n.n} Sätze`,`${n.n} sentences`))+' · '+t(`${n.deg} Verbindungen`,`${n.deg} connections`)));
  const mine=d.edges.filter(e=>e.a===n.id||e.b===n.id);if(mine.length){det.appendChild(icEl('h4','',t('Verbindungen','Connections')));const ul=icEl('ul','facts');for(const e of mine)ul.appendChild(wkaEdgeRow(e,byId));det.appendChild(ul)}
  const row=icEl('div','row');const mid=icEl('button','b p',t('In die Mitte','Into the middle'));mid.type='button';mid.onclick=()=>wkaFocus(n.id);row.appendChild(mid);
  if(!n.ent){const op=icEl('button','b',t('Seite öffnen','Open page'));op.type='button';op.onclick=()=>{WB.sel=n.id;icTabSet('wbuch','show');wbOpen();wbPick(n.id)};row.appendChild(op)}
  det.appendChild(row);if(n.ent)wkaOwn(det,n)}
// a point from documents: only the owner renames, merges (same kind) or deletes it, each with the code of „Bestätigen“
function wkaOwn(det,n){const kid=n.id.slice(1),box=icEl('div','wkown');
  const nm=icEl('input','');nm.type='text';nm.maxLength=80;nm.value=n.title;nm.setAttribute('aria-label',t('Neuer Name','New name'));
  const ren=icEl('button','b',t('Umbenennen','Rename'));ren.type='button';codeLock(ren,'confirm');
  ren.onclick=()=>wkaAct(ren,'/api/profile/wissenskarte/knoten/'+kid+'/name',{method:'POST',body:JSON.stringify({name:nm.value.trim()})},t('Umbenannt; der alte Name findet ihn weiter.','Renamed; the old name still finds it.'));
  const r1=icEl('div','row');r1.append(nm,ren);box.appendChild(r1);
  const sel=icEl('select','');sel.setAttribute('aria-label',t('Zusammenführen mit','Merge with'));sel.appendChild(new Option(t('Zusammenführen mit …','Merge with …'),''));
  const mg=icEl('button','b',t('Zusammenführen','Merge'));mg.type='button';mg.disabled=true;codeLock(mg,'confirm');sel.onchange=()=>{mg.disabled=!sel.value};
  mg.onclick=()=>{if(!sel.value)return;const other=sel.options[sel.selectedIndex].text;if(!confirm(t(`„${n.title}“ in „${other}“ aufgehen lassen? Stellen und Verbindungen wandern mit.`,`Merge "${n.title}" into "${other}"? Passages and connections move along.`)))return;
    wkaAct(mg,'/api/profile/wissenskarte/knoten/'+kid+'/zusammen',{method:'POST',body:JSON.stringify({mit:+sel.value})},t('Zusammengeführt.','Merged.'),'k'+sel.value)};
  const r2=icEl('div','row');r2.append(sel,mg);box.appendChild(r2);
  apiTry('/api/profile/wissenskarte/knoten?art='+encodeURIComponent(n.ent)).then(({r,d})=>{if(!r.ok)return;for(const x of d.knoten||[])if('k'+x.id!==n.id)sel.appendChild(new Option(x.name,String(x.id)))});
  const del=icEl('button','b danger',t('Löschen','Delete'));del.type='button';codeLock(del,'confirm');
  del.onclick=()=>{if(!confirm(t(`„${n.title}“ löschen? Aus diesen Dokumenten kommt der Punkt nicht wieder.`,`Delete "${n.title}"? The point does not come back from these documents.`)))return;
    wkaAct(del,'/api/profile/wissenskarte/knoten/'+kid,{method:'DELETE'},t('Gelöscht; aus diesen Dokumenten kommt er nicht wieder.','Deleted; it does not come back from these documents.'),'')};
  box.appendChild(del);det.appendChild(box)}
async function wkaAct(b,path,opts,done,next){b.disabled=true;const {r,d}=await apiTry(path,Object.assign({headers:{'Content-Type':'application/json'}},opts));b.disabled=false;
  if(!r.ok){WKA.msg=errSay(r.status,d.detail,'');wkaPaint();return}
  if(next!==undefined){if(WKA.um===WKA.sel.id)WKA.um=next;WKA.sel=next?{k:'n',id:next}:null}
  await wkaLoad();WKA.msg=done;wkaPaint()}
async function wkaWrong(id,b){b.disabled=true;const r=await apiTry('/api/profile/wissenskarte/kante/'+encodeURIComponent(id),{method:'DELETE'});
  if(!r.r.ok){WKA.msg=errSay(r.status,r.d.detail,'');b.disabled=false;wkaPaint();return}WKA.sel=null;await wkaLoad();WKA.msg=t('Verbindung entfernt; aus diesem Dokument kommt sie nicht wieder.','Connection removed; it does not come back from this document.');wkaPaint()}
// the picture as SVG or PNG: a copy of the drawn map with its colours written in, made here, nothing from outside
function wkaSave(kind){const svg=document.querySelector('#wkview .wksvg'),d=WKA.data;if(!svg||!d||!d.nodes.length)return;
  const c=svg.cloneNode(true),g=svg.querySelector('g'),bb=g.getBBox(),pad=24;c.querySelector('g').removeAttribute('transform');
  const src=svg.querySelectorAll('g *'),dst=c.querySelectorAll('g *');src.forEach((s,i)=>{const cs=getComputedStyle(s);for(const p of ['fill','stroke','stroke-width','stroke-dasharray','opacity','font-size','font-weight','font-family'])dst[i].style.setProperty(p,cs.getPropertyValue(p))});
  c.setAttribute('viewBox',`${bb.x-pad} ${bb.y-pad} ${bb.width+2*pad} ${bb.height+2*pad}`);c.setAttribute('width',Math.round(bb.width+2*pad));c.setAttribute('height',Math.round(bb.height+2*pad));c.setAttribute('xmlns',WK_SVG);
  const bg=wkaS('rect',{x:bb.x-pad,y:bb.y-pad,width:bb.width+2*pad,height:bb.height+2*pad});bg.style.fill=getComputedStyle(document.body).getPropertyValue('--card')||'#fff';c.insertBefore(bg,c.querySelector('g'));
  c.querySelectorAll('marker path').forEach((p,i)=>{const s=svg.querySelectorAll('marker path')[i];p.style.fill=getComputedStyle(s).fill});
  const blob=new Blob([new XMLSerializer().serializeToString(c)],{type:'image/svg+xml'}),url=URL.createObjectURL(blob);
  const give=(u,name)=>{const a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),4000)};
  if(kind==='svg'){give(url,'Wissenskarte.svg');return}
  const img=new Image();img.onload=()=>{const cv=document.createElement('canvas'),s=2;cv.width=Math.min(8000,img.width*s);cv.height=Math.min(8000,img.height*s);const x=cv.getContext('2d');x.scale(cv.width/img.width,cv.height/img.height);x.drawImage(img,0,0);
    URL.revokeObjectURL(url);cv.toBlob(b=>{if(b)give(URL.createObjectURL(b),'Wissenskarte.png')},'image/png')};img.src=url}
