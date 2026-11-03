// Zustand → Technik (technik.py, plan technische-doku.md): how the Spark is built, from the code of the installed
// version. Four views: the picture (click a box: what it does, its files and modules, where it writes), the way of
// one request in 8 steps (the way lights up), every storage place (filters, search, list with detail) and the
// building blocks. Admin only; names of modules and paths, never contents. Only text from the data, always esc().
const TK={d:null,lang:'',view:'bild',sel:'antwort',step:0,filt:'alle',q:'',row:null,full:false,zoom:1,page:null,pd:{},play:null,mk:null,blink:false};
const TKZ=[1,1.5,2,3];
async function loadTechnik(){const lang=L==='en'?'en':'de';
  if(!TK.d||TK.lang!==lang){TK.d=await (await api('/api/admin/technik'+(lang==='en'?'?lang=en':''))).json();TK.lang=lang}
  if(TK.view==='knoten'&&TK.page){await knOpen(TK.page);return}
  tkRender();tkFocusPic()}
const tkNode=id=>TK.d.nodes.find(n=>n.id===id);
const tkGroup=id=>TK.d.groups.find(g=>g.id===id);
// the overview (technik.py BILD, ZONEN, LINIEN): zones for where a part lives (devices, the Spark inside, the home
// network and the internet going out), lines at right angles from the data. Plan ueberblick 1+3: the lines stay pale
// until a box is picked, then only its ways light up.
function tkLine(a,b){const p=(TK.d.pic.lines||{})[a+'>'+b];return p?'M'+p.map(q=>q.join(',')).join('L'):''}
function tkSvg(lit,litEdges,dim){const d=TK.d,P=d.pic,[W,H]=P.size,[BW,BH]=P.box;
  const has=(a,b)=>litEdges.includes(a+'>'+b)||litEdges.includes(b+'>'+a);
  const way={lan:t('Heimnetz','home'),net:t('unterwegs','on the way')};
  const pills=n=>(P.rein[n.id]||[]).map((k,j)=>`<g class="tk-pill ${esc(k)}"><rect x="${n.x+j*74}" y="${n.y+BH+5}" width="70" height="14" rx="7"/><text x="${n.x+j*74+35}" y="${n.y+BH+15}">${esc(way[k]||k)}</text></g>`).join('');
  const lg=P.legend,legend=`<g class="tk-legend">`+lg.kinds.map((k,j)=>`<g class="c-${esc(k.kind)}"><rect class="tk-bar" x="${lg.x}" y="${lg.y+j*14-8}" width="4" height="10" rx="2"/><text x="${lg.x+10}" y="${lg.y+j*14}">${esc(k.name)}</text></g>`).join('')+`</g>`;
  const tab=n=>n.nur?`<g class="tk-tab"><rect x="${n.x+BW-112}" y="${n.y-7}" width="104" height="14" rx="7"/><text x="${n.x+BW-60}" y="${n.y+3}">${esc(n.nur)}</text></g>`:'';
  return`<svg class="tk-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('Teile des Spark, wo sie liegen, und ihre Verbindungen','Parts of the Spark, where they live, and their connections'))}">`+
    `<defs><marker id="tkah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,1L9,5L0,9z"/></marker></defs>`+
    P.zones.map(z=>`<g class="tk-zone ${esc(z.kind)}"><rect x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="14"/><text x="${z.lx}" y="${z.y+16}">${esc(z.name)}</text></g>`).join('')+
    `<g class="tk-edges${litEdges.length?' pick':''}">`+d.edges.map(([a,b])=>`<path class="tk-edge${has(a,b)?' on':''}${b==='internet'?' net':b==='aussen'?' lan':''}" d="${tkLine(a,b)}"/>`).join('')+`</g>`+
    P.doors.map(r=>`<g class="tk-door ${esc(r.kind)}"><rect x="${r.x}" y="${r.y-9}" width="${Math.round(r.name.length*6.3+20)}" height="18" rx="9"/><text x="${r.x+10}" y="${r.y+4}">${esc(r.name)}</text></g>`).join('')+
    legend+d.nodes.map(n=>`<g class="tk-node c-${esc(n.farbe)}${n.store?' store':''}${n.nur?' opt':''}${n.id===TK.sel&&TK.view==='bild'?' sel':''}${lit.includes(n.id)?' lit':''}${dim&&!lit.includes(n.id)?' dim':''}" data-tkn="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.name)}">`+
      `<rect x="${n.x}" y="${n.y}" width="${BW}" height="${BH}" rx="${n.store?6:12}"/><rect class="tk-bar" x="${n.x+3}" y="${n.y+9}" width="4" height="${BH-18}" rx="2"/>`+
      tkTexts(n)+tab(n)+`</g>`+pills(n)).join('')+'</svg>'}
// name, symbol and line of a box; a line with "\n" (Bilder und Musik: four ports) takes two rows under a higher name
function tkTexts(n){const sub=String(n.sub).split('\n'),two=sub.length>1,y0=two?17:22;
  return`<text x="${n.x+12}" y="${n.y+y0}">${esc(n.name)}</text><text class="tk-sym" x="${n.x+12}" y="${n.y+y0+18}">${esc(n.symbol)}</text>`+
    sub.map((l,k)=>`<text class="tk-sub" x="${n.x+28}" y="${n.y+y0+17+k*13}">${esc(l)}</text>`).join('')}
function tkRows(n){return TK.d.storage.filter(r=>tkWriter(r)===n.id)}
// which box of the picture writes a storage place (for the jump from the list and the count in the detail)
function tkWriter(r){if(r.art==='state')return'state';if(r.art==='system')return/journald/.test(r.pfad)?'journal':/voices|backups/.test(r.pfad)?'ablage':'';return'users'}
function tkNodeDetail(id){const n=tkNode(id);if(!n)return'';const g=n.group&&tkGroup(n.group);const rows=tkRows(n);
  const step=TK.d.steps.findIndex(s=>s.nodes.includes(id));
  return`<div class="tk-kind">${esc(g?g.name:n.store?t('Speicher','Storage'):t('Baustein','Part'))}</div><h3>${esc(n.name)}</h3><p>${esc(n.text)}</p>`+
    (g?`<p class="mut">${esc(g.text)}</p>`:'')+
    (n.files.length?`<div class="tk-files">${n.files.map(f=>`<code>${esc(f)}</code>`).join('')}</div>`:'')+
    (g?`<details class="tk-mods"><summary>${esc(t(`${g.modules.length} Module`,`${g.modules.length} modules`))}</summary>${g.modules.map(m=>`<div class="tk-mod"><code>${esc(m.file)}</code><span>${esc(m.text)}</span></div>`).join('')}</details>`:'')+
    `<div class="ld-acts">${n.page?`<button class="b p" type="button" data-tkpage="${esc(id)}">${esc(t('Ganz genau: so arbeitet es →','In detail: how it works →'))}</button>`:''}${rows.length?`<button class="b" type="button" data-tkgo="speicher" data-tkfilt="${esc(id)}">${esc(t(`${rows.length} Speicherorte`,`${rows.length} storage places`))}</button>`:''}`+
    (step>=0?`<button class="b" type="button" data-tkgo="fluss" data-tkstep="${step}">${esc(t('Im Datenfluss zeigen','Show in the data flow'))}</button>`:'')+`</div>`}
function tkStepDetail(i){const s=TK.d.steps[i],n=TK.d.steps.length;
  return`<div class="tk-kind">${esc(t(`Schritt ${i+1} von ${n}`,`Step ${i+1} of ${n}`))}</div><h3>${esc(s.name)}</h3><p>${esc(s.text)}</p><div class="tk-files"><code>${esc(s.code)}</code></div>`+
    `<div class="ld-acts"><button class="b" type="button" data-tkstep="${i-1}" ${i?'':'disabled'}>${esc(t('Zurück','Back'))}</button><button class="b p" type="button" data-tkstep="${i+1}" ${i<n-1?'':'disabled'}>${esc(t('Weiter','Next'))}</button></div>`}
const TKF=[['alle',t('Alle','All')],['profil',t('Pro Profil','Per profile')],['global',t('Global','Global')],['system',t('System','System')],
  ['sicherung',t('In der Sicherung','In the backup')],['offen',t('Ohne Schutz','Unprotected')],['eigen',t('Eigener Speicher','Own storage')]];
function tkFilter(){const q=TK.q.trim().toLowerCase(),f=TK.filt;return TK.d.storage.filter(r=>{
  if(f==='profil'&&r.ort!=='profil')return false;if(f==='global'&&(r.ort!=='global'))return false;if(f==='system'&&r.art!=='system')return false;
  if(f==='sicherung'&&r.sicherung!=='ja')return false;if(f==='offen'&&(r.schutz||r.art==='system'))return false;if(f==='eigen'&&!r.eigen)return false;
  if(['state','users','ablage','journal'].includes(f)&&tkWriter(r)!==f)return false;
  return!q||(r.pfad+' '+r.inhalt+' '+r.grund).toLowerCase().includes(q)})}
function tkRowDetail(r){const yes=v=>v==='ja'?t('ja','yes'):v==='nein'?t('nein','no'):v;
  return`<button class="b ld-back" type="button" data-tkback="1">${esc(t('Zurück zur Liste','Back to the list'))}</button><div class="tk-kind">${esc(r.ort==='profil'?t('Pro Profil','Per profile'):r.art==='system'?t('System','System'):t('Global','Global'))}</div>`+
    `<h3>${esc(r.pfad)}</h3><p>${esc(r.inhalt)}</p><dl class="ld-facts"><dt>${esc(t('Schutz','Protection'))}</dt><dd>${esc(r.schutz||t('keiner (Datei 0600)','none (file 0600)'))}</dd>`+
    `<dt>${esc(t('Sicherung','Backup'))}</dt><dd>${esc(yes(r.sicherung))}</dd>`+(r.eigen?`<dt>${esc(t('Eigener Speicher','Own storage'))}</dt><dd>${esc(TK.d.areas[r.eigen]||r.eigen)}</dd>`:'')+
    (r.grund?`<dt>${esc(r.art==='state'?t('Warum nicht gesichert','Why not backed up'):t('Art','Kind'))}</dt><dd>${esc(r.grund)}</dd>`:'')+`</dl>`+
    (tkWriter(r)?`<div class="ld-acts"><button class="b" type="button" data-tkgo="bild" data-tknode="${esc(tkWriter(r))}">${esc(t('Im Bild zeigen','Show in the picture'))}</button></div>`:'')}
// „Vollbild“: the picture over the whole screen (with the steps in Datenfluss), zoom in steps, Escape closes
function tkFullBar(){const z=TK.zoom;
  return`<div class="tk-fsbar"><b>${esc(t('Technik','Architecture'))} · ${esc(TK.view==='knoten'?((TK.pd[TK.page+':'+(L==='en'?'en':'de')]||{}).name||''):TK.view==='fluss'?t('Datenfluss','Data flow'):t('Überblick','Overview'))}</b>`+
    `<button class="b" type="button" data-tkzoom="-"${z<=TKZ[0]?' disabled':''} aria-label="${esc(t('Kleiner','Smaller'))}">−</button>`+
    `<span class="tk-zl">${z===1?esc(t('Eingepasst','Fitted')):Math.round(z*100)+' %'}</span>`+
    `<button class="b" type="button" data-tkzoom="+"${z>=TKZ[TKZ.length-1]?' disabled':''} aria-label="${esc(t('Größer','Larger'))}">＋</button>`+
    `<button class="b" type="button" data-tkzoom="0"${z===1?' disabled':''}>${esc(t('Einpassen','Fit'))}</button>`+
    `<button class="b" type="button" data-tkclose>✕ ${esc(t('Schließen','Close'))}</button></div>`}
function tkPic(svg){return`<div class="tk-pic">${svg}</div>`}
// the row above the picture: what to do on the left (hint or steps), „Vollbild“ on the right
function tkTop(left){return`<div class="tk-top">${left}${TK.full?'':`<button class="b tk-fsbtn" type="button" data-tkfull>⛶ ${esc(t('Vollbild','Full screen'))}</button>`}</div>`}
function tkFull(on){const b=$('tkbox');if(!b)return;TK.full=on&&(TK.view==='bild'||TK.view==='fluss'||TK.view==='knoten');if(!TK.full)TK.zoom=1;
  b.classList.toggle('tk-full',TK.full);document.documentElement.classList.toggle('tk-lock',TK.full)}
function tkRender(){const d=TK.d,box=$('tkview');if(!d||!box)return;
  if(TK.full&&TK.view!=='bild'&&TK.view!=='fluss'&&TK.view!=='knoten')tkFull(false);
  if(TK.view!=='knoten')knStop();
  box.style.setProperty('--tkz',TK.zoom);box.classList.toggle('tk-zoomed',TK.zoom>1);
  document.querySelectorAll('#tktabs button').forEach(b=>{const v=TK.view==='knoten'?'bild':TK.view;b.classList.toggle('on',b.dataset.tkv===v);b.setAttribute('aria-selected',b.dataset.tkv===v?'true':'false')});
  $('tkbox').classList.remove('tk-sel');
  const ver=`<div class="mut tk-ver">${esc(t('Stand','Version'))} ${esc(d.version||'–')}</div>`;
  if(TK.view==='knoten'){const p=TK.pd[TK.page+':'+(L==='en'?'en':'de')];if(!p){TK.view='bild';tkRender();return}
    box.innerHTML=TK.full?tkFullBar()+knFlow(p):knPage(p)+ver;knShow();return}
  if(TK.view==='bild'){const n=tkNode(TK.sel)?TK.sel:'antwort';TK.sel=n;
    const lit=d.edges.filter(([a,b])=>a===n||b===n).map(([a,b])=>a+'>'+b);
    box.innerHTML=(TK.full?tkFullBar():'')+tkTop(`<span class="mut tk-hint">${esc(t('Klicke auf einen Kasten: was er tut, seine Dateien und wohin er schreibt.','Click a box: what it does, its files and where it writes.'))}</span>`)+`<div class="tk-split">${tkPic(tkSvg([],lit,false))}<div class="ld-detail tk-det">${tkNodeDetail(n)}</div></div>`+ver}
  else if(TK.view==='fluss'){const i=Math.max(0,Math.min(TK.step,d.steps.length-1)),s=d.steps[i];TK.step=i;
    box.innerHTML=(TK.full?tkFullBar():'')+tkTop(`<div class="ld-chips tk-steps">${d.steps.map((x,j)=>`<button class="ld-chip${j===i?' on':''}" type="button" data-tkstep="${j}"><b>${j+1}</b> ${esc(x.name)}</button>`).join('')}</div>`)+
      `<div class="tk-split">${tkPic(tkSvg(s.nodes,s.edges,true))}<div class="ld-detail tk-det">${tkStepDetail(i)}</div></div>`+ver}
  else if(TK.view==='speicher'){const rows=tkFilter(),sel=rows.find(r=>r.pfad===TK.row)||null;
    const extra=['state','users','ablage','journal'].includes(TK.filt)?[[TK.filt,tkNode(TK.filt).name]]:[];
    box.innerHTML=`<div class="ld-tools"><input type="search" id="tkq" maxlength="80" autocomplete="off" placeholder="${esc(t('Pfad oder Inhalt suchen','Search path or content'))}" aria-label="${esc(t('Pfad oder Inhalt suchen','Search path or content'))}"><span class="mut tk-cnt">${esc(t(`${rows.length} von ${d.storage.length}`,`${rows.length} of ${d.storage.length}`))}</span></div>`+
      `<div class="ld-chips">${TKF.concat(extra).map(([k,l])=>`<button class="ld-chip${TK.filt===k?' on':''}" type="button" data-tkfilt="${esc(k)}">${esc(l)}</button>`).join('')}</div>`+
      `<div class="ld-split"><div class="ld-list">${rows.map(r=>`<div class="ld-row${sel&&sel.pfad===r.pfad?' on':''}" role="button" tabindex="0" data-tkrow="${esc(r.pfad)}"><span class="ld-mid"><b>${esc(r.pfad)}</b><small>${esc(r.inhalt)}</small></span><span class="ld-right">`+
        (r.schutz?`<span class="ld-badge read">${esc(t('geschützt','protected'))}</span>`:r.art!=='system'?`<span class="ld-badge due">${esc(t('offen','plain'))}</span>`:'')+
        (r.sicherung==='ja'?`<span class="ld-badge sh">${esc(t('gesichert','backed up'))}</span>`:'')+`</span></div>`).join('')||`<div class="ld-empty mut">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`}</div>`+
      `<div class="ld-detail"${sel?'':' hidden'}>${sel?tkRowDetail(sel):''}</div></div>`+ver;
    const q=$('tkq');q.value=TK.q;q.addEventListener('input',()=>{TK.q=q.value;const at=q.selectionStart;tkRender();const n=$('tkq');n.focus();try{n.setSelectionRange(at,at)}catch{}});
    if(sel&&TK.narrow){$('tkbox').classList.add('tk-sel');$('tkbox').scrollIntoView({block:'start'})}}
  else{box.innerHTML=d.groups.map(g=>`<div class="ld-grp"><span>${esc(g.name)}</span><span>${g.modules.length}</span></div><div class="mut tk-gtext">${esc(g.text)}</div>`+
      g.modules.map(m=>`<div class="ld-row" role="button" tabindex="0" data-tkgroup="${esc(g.id)}"><span class="ld-mid"><b>${esc(m.file)}</b><small>${esc(m.text)}</small></span></div>`).join('')).join('')+ver}}
// Knoten-Seiten (technik_knoten.py, plan knoten-seiten.md): one box in detail. Its way is drawn from the steps: one
// column top to bottom, questions as hexagons, their exits to the right (red: stops, green: goes on at step N,
// dashed: back to step N). „Durchspielen“ lights one example's way step by step; „heute“ shows today's counts.
const KNW=480,KNX=16,KNB=262,KNS=318,KNSW=150;
function knWrap(s,max){const out=[];let cur='';for(const w of String(s||'').split(' ')){if(cur&&(cur+' '+w).length>max){out.push(cur);cur=w}else cur=cur?cur+' '+w:w}if(cur)out.push(cur);return out}
function knSvg(p){let y=14,o='',arrows='';const lay=[];
  for(const s of p.steps){const tl=knWrap(s.name,30),sl=knWrap(s.sub,38),h=Math.max(48,18+tl.length*17+sl.length*15)+(s.art==='frage'?6:0);lay.push({s,y,h,tl,sl});y+=h+(s.side&&s.side.main?34:28)}
  lay.forEach((l,k)=>{const{s,h,tl,sl}=l,y0=l.y,cx=KNX+KNB/2,rx=s.art==='start'||s.art==='ende'?24:8;
    const shape=s.art==='frage'?`<polygon points="${KNX+16},${y0} ${KNX+KNB-16},${y0} ${KNX+KNB},${y0+h/2} ${KNX+KNB-16},${y0+h} ${KNX+16},${y0+h} ${KNX},${y0+h/2}"/>`:`<rect x="${KNX}" y="${y0}" width="${KNB}" height="${h}" rx="${rx}"/>`;
    let ty=y0+(h-(tl.length*17+sl.length*15))/2+13;
    o+=`<g class="kn-st kn-${s.art}" data-kns="${esc(s.id)}" tabindex="0" role="button" aria-label="${esc(s.n+'. '+s.name)}">${shape}`+tl.map(x=>{const r=`<text x="${cx}" y="${ty}" text-anchor="middle">${esc(x)}</text>`;ty+=17;return r}).join('')+
      sl.map(x=>{const r=`<text class="kn-sub" x="${cx}" y="${ty}" text-anchor="middle">${esc(x)}</text>`;ty+=15;return r}).join('')+
      `<circle class="kn-num" cx="${KNX+6}" cy="${y0+4}" r="11"/><text class="kn-numt" x="${KNX+6}" y="${y0+8}" text-anchor="middle">${s.n}</text></g>`;
    const nx=lay[k+1];if(nx){arrows+=`<path class="kn-ar" d="M${cx},${y0+h}V${nx.y-2}"/>`+(s.side&&s.side.main?`<text class="kn-lab" x="${cx+8}" y="${y0+h+19}">${esc(s.side.main)}</text>`:'')}
    if(s.side){const sd=s.side,txt=sd.kind==='ok'?'→ '+t('weiter bei ','go on at ')+sd.n:sd.kind==='zurueck'?'↺ '+t('zurück zu ','back to ')+sd.n:sd.text;
      const ls=knWrap(txt,19),ph=Math.max(32,12+ls.length*16),py=y0+h/2-ph/2,xr=s.art==='frage'?KNX+KNB:KNX+KNB;
      arrows+=`<path class="kn-ar kn-ar-${sd.kind}" d="M${xr},${y0+h/2}H${KNS-2}"/>`;
      let yy=py+(ph-ls.length*16)/2+12;
      o+=`<g class="kn-side kn-${sd.kind}" data-kns="${esc(s.id)}!"><text class="kn-lab" x="${KNS+4}" y="${py-5}">${esc(sd.label)}</text><rect x="${KNS}" y="${py}" width="${KNSW}" height="${ph}" rx="${ph/2>18?12:ph/2}"/>`+
        ls.map(x=>{const r=`<text x="${KNS+KNSW/2}" y="${yy}" text-anchor="middle">${esc(x)}</text>`;yy+=16;return r}).join('')+`</g>`}});
  return`<svg class="tk-svg kn-svg" viewBox="0 0 ${KNW} ${y}" role="img" aria-label="${esc(t('Ablauf','Way'))}"><defs><marker id="knah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z"/></marker></defs>${arrows}${o}</svg>`}
function knHead(p){const g=p.group&&tkGroup(p.group);
  return`<div class="kn-head"><button class="b" type="button" data-tkv="bild">← ${esc(t('Überblick','Overview'))}</button><div class="kn-t"><div class="tk-kind">${esc(g?g.name:t('Baustein','Part'))}</div><h3 class="kn-h">${esc(p.name)}</h3>`+
    `<div class="tk-files">${(p.files.length?p.files:[p.sub]).map(f=>`<code>${esc(f)}</code>`).join('')}</div></div></div>`}
// each count opens the live overview that counts it (way.js .kn-tn rows)
function knToday(p){if(!p.today_keys.length)return'';const d=p.today||{};
  if(d.off==='verbrauch')return`<div class="kn-today mut">${esc(t('Zahlen für heute zählt der Verbrauchszähler; er ist aus (Funktionen → Verbrauchszähler).','Today\'s numbers are counted by the usage counter; it is off (Features → Usage counter).'))}</div>`;
  if(d.off)return`<div class="kn-today mut">${esc(t('Zahlen für heute zählt die Live-Übersicht; sie ist aus (Einstellungen → Spark → Betrieb → Logs „Live-Seite“).','Today\'s numbers are counted by the live overview; it is off (Settings → Spark → Operation → Logs “Live page”).'))}</div>`;
  return`<div class="kn-today"><b>${esc(t('Heute','Today'))}</b>${p.today_keys.map(([k,l])=>`<span class="kn-tn" data-knt="${esc(k)}" data-way="${esc(/^vb_/.test(k)?t('Zustand → Verbrauch','Status → Usage'):t('Zustand → Live','Status → Live'))}"><b>${Number(d[k]||0)}</b> ${esc(l)}</span>`).join('')}</div>`}
function knFlow(p){const pl=TK.play;
  return`<div class="kn-ex">${p.examples.length?`<span class="mut kn-exl">${esc(t('Durchspielen:','Play through:'))}</span>`+p.examples.map((e,k)=>`<button class="ld-chip${pl&&pl.k===k?' on':''}" type="button" data-tkplay="${k}">▶ ${esc(e.name)}</button>`).join(''):''}`+
    (pl?`<button class="ld-chip" type="button" data-tkplay="-1">■ ${esc(t('Aus','Off'))}</button>`:'')+`</div><div class="kn-cap" id="kncap" aria-live="polite"></div>`+
    `<div class="kn-flow"><div class="tk-pic kn-pic">${knSvg(p)}</div><ol class="kn-steps">${p.steps.map(s=>`<li data-kns="${esc(s.id)}" tabindex="0"><b>${esc(s.name)}${/[.?!]$/.test(s.name)?'':'.'}</b> ${esc(s.text)}</li>`).join('')}</ol></div>`}
function knPage(p){const sec=(id,title,body)=>body?`<div class="kn-sec" id="kn-${id}"><h4>${esc(title)}</h4>${body}</div>`:'';
  const rules=p.rules.length?`<div class="kn-tw"><table class="kn-tab"><thead><tr>${p.rules[0].map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>`+
    p.rules.slice(1).map((r,i)=>`<tr data-knr="${i}">${r.map((c,j)=>`<td class="${c==='✓'?'ok':/^✕/.test(c)?'bad':''}">${j===0?`<b>${esc(c)}</b>`:esc(c)}</td>`).join('')}</tr>`).join('')+`</tbody></table></div>`:'';
  const nb=p.neighbours.map(id=>{const n=tkNode(id);if(!n)return'';return n.page?`<button class="ld-chip" type="button" data-tkpage="${esc(id)}">${esc(n.name)}</button>`:`<button class="ld-chip" type="button" data-tkgo="bild" data-tknode="${esc(id)}">${esc(n.name)}</button>`}).join('');
  return knHead(p)+knToday(p)+sec('kurz',t('Was er macht','What it does'),`<p>${esc(p.kurz)}</p><p><b>${esc(t('Warum:','Why:'))}</b> ${esc(p.warum)}</p>`)+
    `<div class="kn-sec" id="kn-ablauf"><div class="kn-sh"><h4>${esc(t('Ablauf Schritt für Schritt','Step by step'))}</h4><button class="b tk-fsbtn" type="button" data-tkfull>⛶ ${esc(t('Vollbild','Full screen'))}</button></div>${knFlow(p)}</div>`+
    sec('regeln',t('Regeln','Rules'),rules)+p.more.map((m,k)=>sec('mehr'+k,m.title,`<ul>${m.lines.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`)).join('')+
    `<div class="kn-two">`+sec('zahlen',t('Zahlen aus dem Code','Numbers from the code'),p.numbers.length?`<div class="kn-nums">${p.numbers.map((z,i)=>`<div data-knz="${i}"${z.steps.length?' tabindex="0"':''}><b>${esc(z.value)}</b><span>${esc(z.text)}</span></div>`).join('')}</div>`:'')+
    sec('einstellen',t('Einstellen und sehen','Set and see'),(p.settings.length||p.see.length)?`<ul>${p.settings.concat(p.see).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'')+`</div>`+
    sec('code',t('Code','Code'),`<div class="kn-code">${p.code.map((c,i)=>`<div data-knc="${i}"${c.steps.length?' tabindex="0"':''}><code>${esc(c.ref)}</code><span>${esc(c.text)}</span></div>`).join('')}</div>`+
      `<p class="mut kn-small">${p.tests.length?esc(t('Selbsttests: ','Self-tests: ')+p.tests.join(', '))+' · ':''}${[...new Set(p.code.map(c=>c.file))].map(f=>`<a href="${esc(p.github+f)}" target="_blank" rel="noopener noreferrer">${esc(f)}</a>`).join(' · ')}</p>`)+
    sec('nachbarn',t('Verbunden mit','Connected to'),nb?`<div class="ld-chips">${nb}</div>`:'')}
async function knOpen(id){const lang=L==='en'?'en':'de',key=id+':'+lang;knStop();
  const fail=()=>{const d=document.querySelector('#tkview .tk-det');if(d)d.insertAdjacentHTML('beforeend',`<p class="mut">${esc(t('Die Seite kommt gerade nicht, bitte gleich noch einmal.','The page does not come right now, please try again shortly.'))}</p>`)};
  try{const r=await api('/api/admin/technik/knoten/'+encodeURIComponent(id)+(lang==='en'?'?lang=en':''));if(!r.ok){fail();return}TK.pd[key]=await r.json()}catch{fail();return}
  if(TK.page!==id)TK.mk=null;TK.page=id;TK.view='knoten';tkRender();const b=$('tkbox');if(b&&b.getBoundingClientRect().top<0)b.scrollIntoView({block:'start'})}
function knStop(){if(TK.play&&TK.play.timer)clearInterval(TK.play.timer);TK.play=null}
// one example: every 1.1 s the next step lights (its exit too); the caption says which step and, at the end, the result
function knShow(){const p=TK.pd[TK.page+':'+(L==='en'?'en':'de')],pl=TK.play,box=$('tkview');if(!p||!box)return;
  const ex=pl&&p.examples[pl.k],seen=ex?ex.path.slice(0,pl.i+1):[],cur=seen[seen.length-1];
  box.querySelectorAll('[data-kns]').forEach(e=>{const id=e.dataset.kns;e.classList.toggle('lit',seen.includes(id));e.classList.toggle('cur',id===cur);e.classList.toggle('dim',!!ex&&!seen.includes(id))});
  knMarkApply(false);
  if(ex&&knWide()){const li=box.querySelector('.kn-steps li.cur');if(li)knInView(li)}
  const cap=$('kncap');if(!cap)return;if(!ex){cap.textContent='';return}
  const st=p.steps.find(s=>s.id===cur.replace('!','')),end=pl.i>=ex.path.length-1;
  cap.innerHTML=`<b>${esc(ex.name)}</b> · `+(end?esc(ex.result):esc(st?(cur.endsWith('!')?st.side.label+': '+(st.side.text||t('weiter bei ','go on at ')+st.side.n):st.n+'. '+st.name):''))}
function knPlay(k){knStop();if(k<0){tkRender();return}TK.mk=null;TK.play={k,i:0,timer:null};tkRender();knShow();
  TK.play.timer=setInterval(()=>{const p=TK.pd[TK.page+':'+(L==='en'?'en':'de')],pl=TK.play;if(!pl||!p||TK.view!=='knoten'||!$('kncap')){knStop();return}
    const ex=p.examples[pl.k];if(pl.i>=ex.path.length-1){clearInterval(pl.timer);pl.timer=null;return}pl.i++;knShow()},1100)}
// a click on a bubble marks it and its text (frame, blinks twice, the rest fades); a click on the text, a rule, a number
// or a code line marks its bubble. Wide: the list beside the picture scrolls to the text; narrow (phone): the text opens
// as a card under the bubble. With a mouse, pointing at one lights the other (Dominik 2026-10-14: 1+3, phone 2, A-D).
const knPd=()=>TK.pd[TK.page+':'+(L==='en'?'en':'de')];
const knBase=e=>e.dataset.kns.replace('!','');
function knWide(){const f=document.querySelector('#tkview .kn-flow');return!!f&&getComputedStyle(f).display==='grid'}
const knSmooth=()=>matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';
function knInView(el){const r=el.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)el.scrollIntoView({block:'nearest',behavior:knSmooth()})}
function knBlink(els){els.forEach(e=>{e.classList.remove('blink');void e.getBoundingClientRect();e.classList.add('blink')})}
// what belongs to a step: its rules rows, numbers and code lines (from technik_knoten.schritte)
function knRel(p,id){const out=[];p.rules.slice(1).forEach((r,i)=>{if((p.rule_steps[i]||[]).includes(id))out.push(['r',i,t('Regel','Rule'),r[0]])});
  p.numbers.forEach((z,i)=>{if(z.steps.includes(id))out.push(['z',i,t('Zahl','Number'),z.value+' '+z.text])});
  p.code.forEach((c,i)=>{if(c.steps.includes(id))out.push(['c',i,t('Code','Code'),c.ref])});return out}
function knRelHtml(p,id){const r=knRel(p,id);if(!r.length)return'';
  return`<div class="kn-rel"><span class="mut">${esc(t('Passt dazu:','Belongs to it:'))}</span>${r.map(([k,i,l,x])=>`<button class="ld-chip" type="button" data-knto="${k}${i}"><b>${esc(l)}</b> ${esc(x.length>48?x.slice(0,47)+'…':x)}</button>`).join('')}</div>`}
// the bubble itself, small, under a clicked line whose bubble is out of sight (Dominik 2026-10-14: no scrolling up)
function knMini(st){return`<span class="kn-mini kn-mini-${esc(st.art)}"><i>${st.n}</i><b>${esc(st.name)}</b>${st.sub?`<small>${esc(st.sub)}</small>`:''}</span>`}
function knInline(p,src,ids,withText){const sts=ids.map(i=>p.steps.find(s=>s.id===i)).filter(Boolean);if(!sts.length)return null;
  const html=`<div class="kn-inl">${sts.map(st=>`<div class="kn-inl1">${knMini(st)}${withText?`<p>${esc(st.text)}</p>`:''}</div>`).join('')}`+
    `<button class="b kn-up" type="button" data-knup="${esc(sts[0].id)}">↑ ${esc(t('Im Ablauf zeigen','Show in the way'))}</button></div>`;
  if(src.tagName==='TR'){src.insertAdjacentHTML('afterend',`<tr class="kn-inltr"><td colspan="${src.children.length}">${html}</td></tr>`);return src.nextElementSibling}
  if(src.tagName==='LI'){src.insertAdjacentHTML('beforeend',html);return src.lastElementChild}
  src.insertAdjacentHTML('afterend',html);return src.nextElementSibling}
const knSeen=el=>{const r=el.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight};
function knMarkApply(blink,from,src){const box=$('tkview'),p=knPd();if(!box||!p)return;const id=TK.mk,top=src?src.getBoundingClientRect().top:0;
  box.querySelectorAll('.kn-rel,.kn-pop,.kn-inl,.kn-inltr').forEach(e=>e.remove());
  box.querySelectorAll('[data-kns]').forEach(e=>{const on=!!id&&knBase(e)===id;e.classList.toggle('mk',on);e.classList.toggle('mdim',!!id&&!on)});
  const items=[['knr',i=>p.rule_steps[i]||[]],['knz',i=>p.numbers[i].steps],['knc',i=>p.code[i].steps]];
  for(const[a,f]of items)box.querySelectorAll(`[data-${a}]`).forEach(e=>e.classList.toggle('mk',!!id&&f(+e.dataset[a]).includes(id)));
  if(!id)return;const st=p.steps.find(s=>s.id===id);if(!st)return;
  const li=box.querySelector(`.kn-steps li[data-kns="${id}"]`),g=box.querySelector(`.kn-svg g.kn-st[data-kns="${id}"]`);
  if(li)li.insertAdjacentHTML('beforeend',knRelHtml(p,id));
  if(!knWide()&&from==='bild'&&g){const pic=g.closest('.kn-pic'),r=g.getBoundingClientRect(),q=pic.getBoundingClientRect();
    pic.insertAdjacentHTML('beforeend',`<div class="kn-pop" style="top:${Math.round(r.bottom-q.top+pic.scrollTop+6)}px"><button class="b kn-popx" type="button" data-knmk="" aria-label="${esc(t('Schließen','Close'))}">${ic('x')}</button><b>${esc(st.n+'. '+st.name)}</b> ${esc(st.text)}${knRelHtml(p,id)}</div>`)}
  if(!blink)return;const pop=box.querySelector('.kn-pop');
  if(from==='bild'){knBlink([g,pop||li].filter(Boolean));if(pop)knInView(pop);else if(li)knInView(li);return}
  // a line or the text was clicked: the page stays where it is; a bubble out of sight shows up under the line
  // what was added or removed above the clicked line must not move it (it stays where the eye is)
  if(src){const d=src.getBoundingClientRect().top-top;if(Math.abs(d)>1)scrollBy(0,d)}
  const ids=from==='item'&&src?knItemSteps(src):[id],inl=src&&g&&!knSeen(g)?knInline(p,src,ids,from==='item'):null;
  knBlink([inl||g,from==='item'?li:null].filter(Boolean))}
function knMark(id,from,src){if(TK.play){knStop();tkRender()}TK.mk=id&&TK.mk===id&&from!=='item'?null:id||null;knMarkApply(true,from,src&&src.isConnected?src:null)}
function knItemSteps(e){const p=knPd();for(const[a,f]of[['knr',i=>p.rule_steps[i]||[]],['knz',i=>p.numbers[i].steps],['knc',i=>p.code[i].steps]])if(e.dataset[a]!==undefined)return f(+e.dataset[a]);return[]}
function knItem(k,i){const e=document.querySelector(`#tkview [data-kn${k}="${i}"]`);if(!e)return;const st=knItemSteps(e);if(!st.length)return;knMark(st[0],'item',e)}
function knUp(id){const g=document.querySelector(`#tkview .kn-svg g.kn-st[data-kns="${id}"]`);if(!g)return;g.scrollIntoView({block:'center',behavior:knSmooth()});knBlink([g])}
function knGoItem(v){const k=v[0],i=+v.slice(1),e=document.querySelector(`#tkview [data-kn${k}="${i}"]`);if(!e)return;knInView(e);knBlink([e])}
// with a mouse: pointing at a bubble lights its text and the other way round
function knHover(e,on){if(TK.view!=='knoten'||!matchMedia('(hover: hover)').matches)return;const x=e.target.closest&&e.target.closest('#tkview [data-kns]');if(!x)return;
  const id=knBase(x);document.querySelectorAll('#tkview [data-kns]').forEach(y=>{if(knBase(y)===id)y.classList.toggle('hv',on)})}
// on a phone the picture scrolls sideways: bring the chosen box (or the first lit one) into view
function tkFocusPic(){const pic=document.querySelector('#tkview .tk-pic');if(!pic||pic.scrollWidth<=pic.clientWidth)return;
  const n=pic.querySelector('.tk-node.sel,.tk-node.lit');if(!n)return;const r=n.getBoundingClientRect(),p=pic.getBoundingClientRect();
  pic.scrollLeft+=r.left-p.left-(p.width-r.width)/2}
// the data flow: a new step blinks its chip and its boxes (a box clicked there blinks with its step)
function tkBlinkFlow(){const b=TK.blink;TK.blink=false;if(!b||TK.view!=='fluss')return;const v=$('tkview');if(!v)return;
  const chip=v.querySelector('.tk-steps .ld-chip.on');knBlink([chip,...v.querySelectorAll(typeof b==='string'?`.tk-node[data-tkn="${b}"]`:'.tk-node.lit')].filter(Boolean));if(chip)chip.scrollIntoView({block:'nearest',inline:'nearest'})}
function tkClick(e){const k=TK.view==='knoten'&&e.target.closest('[data-knto],[data-knmk],[data-knup],[data-kns],[data-knr],[data-knz],[data-knc]');
  if(k&&!e.target.closest('a,button:not([data-knto]):not([data-knmk]):not([data-knup])')){if(k.dataset.knto){knGoItem(k.dataset.knto);return}if(k.dataset.knmk!==undefined){knMark(null);return}if(k.dataset.knup){knUp(k.dataset.knup);return}
    if(k.closest('.kn-inl'))return;
    if(k.dataset.kns){knMark(knBase(k),k.closest('.kn-svg')?'bild':'text',k.closest('.kn-svg')?null:k);return}
    for(const a of['r','z','c'])if(k.dataset['kn'+a]!==undefined){knItem(a,+k.dataset['kn'+a]);return}}
  const x=e.target.closest('[data-tkv],[data-tkn],[data-tkstep],[data-tkfilt],[data-tkrow],[data-tkgo],[data-tkback],[data-tkgroup],[data-tkfull],[data-tkzoom],[data-tkclose],[data-tkpage],[data-tkplay]');if(!x||!TK.d)return;
  if(x.dataset.tkpage){knOpen(x.dataset.tkpage);return}
  if(x.dataset.tkplay!==undefined){knPlay(+x.dataset.tkplay);return}
  if(x.dataset.tkfull!==undefined)tkFull(true);
  else if(x.dataset.tkclose!==undefined)tkFull(false);
  else if(x.dataset.tkzoom){const i=TKZ.indexOf(TK.zoom),z=x.dataset.tkzoom;TK.zoom=z==='0'?1:TKZ[Math.max(0,Math.min(TKZ.length-1,i+(z==='+'?1:-1)))]}
  else if(x.dataset.tkv){if(TK.view==='knoten'&&TK.page)TK.sel=TK.page;TK.view=x.dataset.tkv;TK.row=null}
  else if(x.dataset.tkgo){TK.view=x.dataset.tkgo;if(x.dataset.tkfilt){TK.filt=x.dataset.tkfilt;TK.q='';TK.row=null}if(x.dataset.tkstep)TK.step=+x.dataset.tkstep;if(x.dataset.tknode)TK.sel=x.dataset.tknode}
  else if(x.dataset.tkn){const n=x.dataset.tkn;
    if(TK.view==='fluss'&&!TK.d.steps[TK.step].nodes.includes(n)){const i=TK.d.steps.findIndex((s,j)=>j>TK.step&&s.nodes.includes(n)),j=i>=0?i:TK.d.steps.findIndex(s=>s.nodes.includes(n));
      if(j>=0){TK.step=j;TK.blink=n}else{TK.sel=n;TK.view='bild';TK.step=0}}
    else if(TK.view==='fluss'){TK.sel=n;TK.view='bild'}else TK.sel=n}
  else if(x.dataset.tkstep!==undefined){const i=+x.dataset.tkstep;if(i<0||i>=TK.d.steps.length)return;TK.step=i;TK.blink=true}
  else if(x.dataset.tkfilt){TK.filt=x.dataset.tkfilt;TK.row=null}
  else if(x.dataset.tkrow){TK.row=x.dataset.tkrow;TK.narrow=$('tkbox').getBoundingClientRect().width<660}
  else if(x.dataset.tkback){TK.row=null}
  else if(x.dataset.tkgroup){const g=tkGroup(x.dataset.tkgroup);TK.view='bild';if(g&&g.node)TK.sel=g.node}
  tkRender();tkFocusPic();tkBlinkFlow();if(x.dataset.tkfull!==undefined){const c=document.querySelector('#tkview [data-tkclose]');if(c)c.focus()}}
(()=>{const b=$('tkbox');if(!b)return;b.addEventListener('click',tkClick);
  b.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-tkn],[data-tkrow],[data-tkgroup],[data-kns],[data-knz],[data-knc]')){e.preventDefault();tkClick(e)}});
  b.addEventListener('mouseover',e=>knHover(e,true));b.addEventListener('mouseout',e=>knHover(e,false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&TK.mk&&TK.view==='knoten'){knMark(null);return}if(e.key==='Escape'&&TK.full){tkFull(false);tkRender();const f=document.querySelector('#tkview [data-tkfull]');if(f)f.focus()}})})();
window.loadTechnik=loadTechnik;window.tkFull=tkFull;
