// Zustand → Technik (technik.py, plan technische-doku.md): how the Spark is built, from the code of the installed
// version. Four views: the picture (click a box: what it does, its files and modules, where it writes), the way of
// one request in 8 steps (the way lights up), every storage place (filters, search, list with detail) and the
// building blocks. Admin only; names of modules and paths, never contents. Only text from the data, always esc().
const TK={d:null,lang:'',view:'bild',sel:'antwort',step:0,filt:'alle',q:'',row:null,full:false,zoom:1};
const TKW=156,TKH=52,TKZ=[1,1.5,2,3];
async function loadTechnik(){const lang=L==='en'?'en':'de';
  if(!TK.d||TK.lang!==lang){TK.d=await (await api('/api/admin/technik'+(lang==='en'?'?lang=en':''))).json();TK.lang=lang}
  tkRender();tkFocusPic()}
const tkNode=id=>TK.d.nodes.find(n=>n.id===id);
const tkGroup=id=>TK.d.groups.find(g=>g.id===id);
function tkCenter(n){return[n.x+TKW/2,n.y+TKH/2]}
// a line from the side of one box to the side of the other (the back way to the device goes over the top)
function tkPath(a,b){const A=tkNode(a),B=tkNode(b);if(!A||!B)return'';const[ax,ay]=tkCenter(A),[bx,by]=tkCenter(B);
  if(a==='antwort'&&b==='geraet')return`M${ax},${A.y}V10H${bx}V${B.y}`;
  if(Math.abs(bx-ax)>Math.abs(by-ay)*1.2){const r=bx>ax,x1=r?A.x+TKW:A.x,x2=r?B.x:B.x+TKW,m=(x1+x2)/2;return`M${x1},${ay}C${m},${ay} ${m},${by} ${x2},${by}`}
  const d=by>ay,y1=d?A.y+TKH:A.y,y2=d?B.y:B.y+TKH,m=(y1+y2)/2;return`M${ax},${y1}C${ax},${m} ${bx},${m} ${bx},${y2}`}
function tkSvg(lit,litEdges,dim){const d=TK.d;
  const boxes=[[t('Geräte','Devices'),4,20,180,385],[t('Panel :31080 / :31443','Panel :31080 / :31443'),188,20,552,325],
    [t('Dienste','Services'),752,20,184,325],['/var/lib/speech-spark · journald',188,355,748,85]];
  const has=(a,b)=>litEdges.includes(a+'>'+b)||litEdges.includes(b+'>'+a);
  return`<svg class="tk-svg" viewBox="0 0 940 445" role="img" aria-label="${esc(t('Teile des Spark und ihre Verbindungen','Parts of the Spark and their connections'))}">`+
    boxes.map(b=>`<rect class="tk-grp" x="${b[1]}" y="${b[2]}" width="${b[3]}" height="${b[4]}" rx="14"/><text class="tk-glab" x="${b[1]+12}" y="${b[2]+16}">${esc(b[0])}</text>`).join('')+
    d.edges.map(([a,b])=>`<path class="tk-edge${has(a,b)?' on':''}" d="${tkPath(a,b)}"/>`).join('')+
    d.nodes.map(n=>`<g class="tk-node${n.store?' store':''}${n.id===TK.sel&&TK.view==='bild'?' sel':''}${lit.includes(n.id)?' lit':''}${dim&&!lit.includes(n.id)?' dim':''}" data-tkn="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.name)}">`+
      `<rect x="${n.x}" y="${n.y}" width="${TKW}" height="${TKH}" rx="${n.store?6:12}"/><text x="${n.x+12}" y="${n.y+22}">${esc(n.name)}</text><text class="tk-sub" x="${n.x+12}" y="${n.y+39}">${esc(n.sub)}</text></g>`).join('')+'</svg>'}
function tkRows(n){return TK.d.storage.filter(r=>tkWriter(r)===n.id)}
// which box of the picture writes a storage place (for the jump from the list and the count in the detail)
function tkWriter(r){if(r.art==='state')return'state';if(r.art==='system')return/journald/.test(r.pfad)?'journal':/voices|backups/.test(r.pfad)?'ablage':'';return'users'}
function tkNodeDetail(id){const n=tkNode(id);if(!n)return'';const g=n.group&&tkGroup(n.group);const rows=tkRows(n);
  const step=TK.d.steps.findIndex(s=>s.nodes.includes(id));
  return`<div class="tk-kind">${esc(g?g.name:n.store?t('Speicher','Storage'):t('Baustein','Part'))}</div><h3>${esc(n.name)}</h3><p>${esc(n.text)}</p>`+
    (g?`<p class="mut">${esc(g.text)}</p>`:'')+
    (n.files.length?`<div class="tk-files">${n.files.map(f=>`<code>${esc(f)}</code>`).join('')}</div>`:'')+
    (g?`<details class="tk-mods"><summary>${esc(t(`${g.modules.length} Module`,`${g.modules.length} modules`))}</summary>${g.modules.map(m=>`<div class="tk-mod"><code>${esc(m.file)}</code><span>${esc(m.text)}</span></div>`).join('')}</details>`:'')+
    `<div class="ld-acts">${rows.length?`<button class="b" type="button" data-tkgo="speicher" data-tkfilt="${esc(id)}">${esc(t(`${rows.length} Speicherorte`,`${rows.length} storage places`))}</button>`:''}`+
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
  return`<div class="tk-fsbar"><b>${esc(t('Technik','Architecture'))} · ${esc(TK.view==='fluss'?t('Datenfluss','Data flow'):t('Überblick','Overview'))}</b>`+
    `<button class="b" type="button" data-tkzoom="-"${z<=TKZ[0]?' disabled':''} aria-label="${esc(t('Kleiner','Smaller'))}">−</button>`+
    `<span class="tk-zl">${z===1?esc(t('Eingepasst','Fitted')):Math.round(z*100)+' %'}</span>`+
    `<button class="b" type="button" data-tkzoom="+"${z>=TKZ[TKZ.length-1]?' disabled':''} aria-label="${esc(t('Größer','Larger'))}">＋</button>`+
    `<button class="b" type="button" data-tkzoom="0"${z===1?' disabled':''}>${esc(t('Einpassen','Fit'))}</button>`+
    `<button class="b" type="button" data-tkclose>✕ ${esc(t('Schließen','Close'))}</button></div>`}
function tkPic(svg){return`<div class="tk-pic">${svg}</div>`}
// the row above the picture: what to do on the left (hint or steps), „Vollbild“ on the right
function tkTop(left){return`<div class="tk-top">${left}${TK.full?'':`<button class="b tk-fsbtn" type="button" data-tkfull>⛶ ${esc(t('Vollbild','Full screen'))}</button>`}</div>`}
function tkFull(on){const b=$('tkbox');if(!b)return;TK.full=on&&(TK.view==='bild'||TK.view==='fluss');if(!TK.full)TK.zoom=1;
  b.classList.toggle('tk-full',TK.full);document.documentElement.classList.toggle('tk-lock',TK.full)}
function tkRender(){const d=TK.d,box=$('tkview');if(!d||!box)return;
  if(TK.full&&TK.view!=='bild'&&TK.view!=='fluss')tkFull(false);
  box.style.setProperty('--tkz',TK.zoom);box.classList.toggle('tk-zoomed',TK.zoom>1);
  document.querySelectorAll('#tktabs button').forEach(b=>{b.classList.toggle('on',b.dataset.tkv===TK.view);b.setAttribute('aria-selected',b.dataset.tkv===TK.view?'true':'false')});
  $('tkbox').classList.remove('tk-sel');
  const ver=`<div class="mut tk-ver">${esc(t('Stand','Version'))} ${esc(d.version||'–')}</div>`;
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
// on a phone the picture scrolls sideways: bring the chosen box (or the first lit one) into view
function tkFocusPic(){const pic=document.querySelector('#tkview .tk-pic');if(!pic||pic.scrollWidth<=pic.clientWidth)return;
  const n=pic.querySelector('.tk-node.sel,.tk-node.lit');if(!n)return;const r=n.getBoundingClientRect(),p=pic.getBoundingClientRect();
  pic.scrollLeft+=r.left-p.left-(p.width-r.width)/2}
function tkClick(e){const x=e.target.closest('[data-tkv],[data-tkn],[data-tkstep],[data-tkfilt],[data-tkrow],[data-tkgo],[data-tkback],[data-tkgroup],[data-tkfull],[data-tkzoom],[data-tkclose]');if(!x||!TK.d)return;
  if(x.dataset.tkfull!==undefined)tkFull(true);
  else if(x.dataset.tkclose!==undefined)tkFull(false);
  else if(x.dataset.tkzoom){const i=TKZ.indexOf(TK.zoom),z=x.dataset.tkzoom;TK.zoom=z==='0'?1:TKZ[Math.max(0,Math.min(TKZ.length-1,i+(z==='+'?1:-1)))]}
  else if(x.dataset.tkv){TK.view=x.dataset.tkv;TK.row=null}
  else if(x.dataset.tkgo){TK.view=x.dataset.tkgo;if(x.dataset.tkfilt){TK.filt=x.dataset.tkfilt;TK.q='';TK.row=null}if(x.dataset.tkstep)TK.step=+x.dataset.tkstep;if(x.dataset.tknode)TK.sel=x.dataset.tknode}
  else if(x.dataset.tkn){if(TK.view==='fluss'){const i=TK.d.steps.findIndex(s=>s.nodes.includes(x.dataset.tkn));TK.sel=x.dataset.tkn;TK.view='bild';if(i<0)TK.step=0}else TK.sel=x.dataset.tkn}
  else if(x.dataset.tkstep!==undefined){const i=+x.dataset.tkstep;if(i<0||i>=TK.d.steps.length)return;TK.step=i}
  else if(x.dataset.tkfilt){TK.filt=x.dataset.tkfilt;TK.row=null}
  else if(x.dataset.tkrow){TK.row=x.dataset.tkrow;TK.narrow=$('tkbox').getBoundingClientRect().width<660}
  else if(x.dataset.tkback){TK.row=null}
  else if(x.dataset.tkgroup){const g=tkGroup(x.dataset.tkgroup);TK.view='bild';if(g&&g.node)TK.sel=g.node}
  tkRender();tkFocusPic();if(x.dataset.tkfull!==undefined){const c=document.querySelector('#tkview [data-tkclose]');if(c)c.focus()}}
(()=>{const b=$('tkbox');if(!b)return;b.addEventListener('click',tkClick);
  b.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-tkn],[data-tkrow],[data-tkgroup]')){e.preventDefault();tkClick(e)}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&TK.full){tkFull(false);tkRender();const f=document.querySelector('#tkview [data-tkfull]');if(f)f.focus()}})})();
window.loadTechnik=loadTechnik;window.tkFull=tkFull;
