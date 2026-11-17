// Leseansicht (Dominik 2026-11-17, „Dokumente suchen und lesen“: Lesen im schmalen Band unübersichtlich): ein Dokument
// liest sich in einer eigenen Ansicht über die ganze Fläche rechts vom Menü (am Handy die ganze Seite). Oben die
// Leiste: Zurück, Titel mit Seite, Text | Original, Suche im Dokument mit „1 von N“ und ⌃⌄. Links das Inhaltsverzeichnis
// aus den Überschriften (feste Regeln, documents.pieces), in der Mitte eine ruhige Lesespalte. Sie öffnet an der
// Fundstelle: opt.n (das Stück eines Treffers), sonst opt.page oder opt.at (Aufnahme „bei 12:30“); opt.q markiert die
// Wörter der Suche. Jeder Weg hinein läuft über docView (me.js): Suche, Assistent, Finden, Mappen, Wissensbuch,
// Auswertungen, Hörstück. Der Text des Dokuments kommt nur als Textknoten auf die Seite, Markierungen setzt das DOM
// (splitText + <mark>), nie innerHTML mit Dokumenttext.
const LS={id:'',d:null,opt:{},marks:[],cur:-1,first:0,next:null,art:'text',back:null,timer:0,lastPage:null};
function leseBox(){let m=$('lesemodal');if(m)return m;
  m=document.createElement('div');m.id='lesemodal';m.className='modal lesen';m.style.display='none';
  m.setAttribute('role','dialog');m.setAttribute('aria-modal','true');m.setAttribute('aria-labelledby','lstitle');
  m.innerHTML=`<div class="lsbar"><button type="button" class="b t lsback" id="lsback">${ic('back')}<span id="lsbackt"></span></button>`+
    `<div class="lstt"><b id="lstitle"></b><small id="lssub"></small></div>`+
    `<span class="lsseg" id="lsseg" role="group" aria-label="${esc(t('Ansicht','View'))}"><button type="button" data-lsart="text" aria-pressed="true">${esc(t('Text','Text'))}</button><button type="button" data-lsart="orig" aria-pressed="false">${esc(t('Original','Original'))}</button></span>`+
    `<span class="lsfind" id="lsfind">${ic('find')}<input id="lsq" type="search" maxlength="100" autocomplete="off" placeholder="${esc(t('Im Dokument suchen','Search in the document'))}" aria-label="${esc(t('Im Dokument suchen','Search in the document'))}">`+
    `<small id="lsn" aria-live="polite"></small><button type="button" class="b i" id="lsprev" aria-label="${esc(t('Vorige Stelle','Previous place'))}">${ic('up')}</button><button type="button" class="b i" id="lsnext" aria-label="${esc(t('Nächste Stelle','Next place'))}">${ic('down')}</button></span></div>`+
    `<div class="lsbody"><nav class="lstoc" id="lstoc" aria-label="${esc(t('Inhalt','Contents'))}"></nav><div class="lspaper" id="lspaper"><div class="lscol" id="lscol"></div></div><div class="lsorig" id="lsorig" hidden></div></div>`;
  document.body.appendChild(m);
  $('lsback').onclick=leseZu;
  $('lsseg').onclick=e=>{const b=e.target.closest('[data-lsart]');if(b)leseArt(b.dataset.lsart)};
  $('lsq').oninput=()=>{clearTimeout(LS.timer);LS.timer=setTimeout(()=>{leseMark($('lsq').value);leseGeh(0)},200)};
  $('lsq').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();leseGeh(e.shiftKey?-1:1)}
    else if(e.key==='Escape'&&$('lsq').value){e.preventDefault();e.stopPropagation();$('lsq').value='';leseMark('')}};
  $('lsprev').onclick=()=>leseGeh(-1);$('lsnext').onclick=()=>leseGeh(1);
  $('lstoc').onclick=e=>{const h=e.target.closest('[data-lsn]');if(h)leseZu_n(+h.dataset.lsn,h.dataset.lst)};
  $('lscol').onclick=e=>{const p=e.target.closest('[data-lsplay]');if(p){lesePlay(+p.dataset.lsplay);return}
    const r=e.target.closest('[data-lsrel]');if(r)leseOpen(r.dataset.lsrel,{});
    const mo=e.target.closest('[data-lsmore]');if(mo)leseMehr(mo.dataset.lsmore==='davor',mo)};
  m.addEventListener('keydown',e=>{if(e.key==='Escape'&&e.target.id!=='lsq'){e.preventDefault();e.stopPropagation();leseZu()}
    else if((e.ctrlKey||e.metaKey)&&e.key==='f'){e.preventDefault();$('lsq').focus();$('lsq').select()}});
  return m}
// open document id; opt {n, page, at, q}
async function leseOpen(id,opt){const m=leseBox();opt=opt||{};
  if(m.style.display!=='grid')LS.back=document.activeElement;
  LS.id=id;LS.opt=opt;LS.d=null;LS.marks=[];LS.cur=-1;LS.art='text';LS.lastPage=null;
  $('lsbackt').textContent=opt.q?t(`Suche „${opt.q}“`,`Search "${opt.q}"`):t('Zurück','Back');
  $('lstitle').textContent=t('Lade …','Loading …');$('lssub').textContent='';$('lstoc').innerHTML='';$('lsq').value=opt.q||'';$('lsn').textContent='';
  $('lscol').textContent='';$('lsorig').hidden=true;$('lsorig').textContent='';$('lspaper').hidden=false;leseSeg();
  m.style.display='grid';document.body.classList.add('lesen-offen');$('lsback').focus();
  try{const d=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text'+(opt.n!=null?'?um='+(+opt.n):''))).json();
    if(LS.id!==id)return;LS.d=d;LS.first=d.start||0;LS.next=d.next;
    const doc=typeof docFind==='function'?docFind(id):null;
    $('lstitle').textContent=doc&&typeof docTitle==='function'?docTitle(doc):d.name;
    leseSub();leseToc();leseText(d.parts,false);
    if(d.start>0)leseKnopf(true);if(d.next!=null)leseKnopf(false);
    if(d.related&&d.related.length)leseRel(d.related);
    if(!d.parts.length){const p=document.createElement('p');p.className='mut';p.textContent=d.state==='reading'?t('Wird noch gelesen.','Still being read.'):t('Kein Text.','No text.');$('lscol').appendChild(p)}
    $('lsseg').hidden=!d.file;
    leseMark(opt.q||'');leseZiel()}
  catch(x){$('lstitle').textContent=t('Dokument','Document');$('lscol').textContent=x.message}}
function leseZu(){const m=$('lesemodal');if(!m)return;m.style.display='none';document.body.classList.remove('lesen-offen');
  const a=$('lsaudio');if(a)a.pause();$('lsorig').textContent='';LS.id='';
  if(LS.back&&document.contains(LS.back))LS.back.focus();LS.back=null}
// the line under the title: kind, pages, who shared it; while reading the page of the place in view
function leseSub(page){const d=LS.d;if(!d)return;const bits=[];
  if(page&&d.kind!=='audio')bits.push(t(`Seite ${page}`,`Page ${page}`));
  if(d.owner)bits.push(t('von ','from ')+d.owner);
  $('lssub').textContent=bits.join(' · ')}
function leseToc(){const d=LS.d,box=$('lstoc');box.innerHTML='';const hs=d.heads||[];
  $('lesemodal').classList.toggle('lsnotoc',hs.length<2);if(hs.length<2)return;
  const h=document.createElement('div');h.className='lstoch';h.textContent=t('Inhalt','Contents');box.appendChild(h);
  for(const x of hs){const b=document.createElement('button');b.type='button';b.className='lstocx';b.dataset.lsn=String(x.n);b.dataset.lst=x.t;
    const s=document.createElement('span');s.textContent=x.t;b.appendChild(s);box.appendChild(b)}}
// the pieces as paragraphs; a page or a place in a recording as a quiet line; a heading line as h3
function leseText(parts,vorne){const col=$('lscol'),frag=document.createDocumentFragment(),d=LS.d;let page=vorne?null:LS.lastPage;
  if(!vorne&&!$('lsaudio')&&d.kind==='audio'&&d.file){const a=document.createElement('audio');a.id='lsaudio';a.controls=true;a.preload='none';
    a.src='/api/profile/wissen/'+encodeURIComponent(LS.id)+'/file?view=1';frag.appendChild(a)}
  for(const p of parts){
    if(p.at&&p.page!==page){page=p.page;const h=document.createElement('div');h.className='lspg';h.dataset.page=String(p.page);
      const s=document.createElement('span');s.textContent=p.at;h.appendChild(s);
      if(d.file){const pl=document.createElement('button');pl.type='button';pl.className='b i';pl.appendChild(icNode('play'));pl.setAttribute('aria-label',t('Hier anhören','Listen here'));pl.dataset.lsplay=String(p.page);h.appendChild(pl)}
      frag.appendChild(h)}
    else if(!p.at&&p.page&&p.page!==page){page=p.page;const h=document.createElement('div');h.className='lspg';h.dataset.page=String(p.page);
      const s=document.createElement('span');s.textContent=t('Seite ','Page ')+p.page;h.appendChild(s);frag.appendChild(h)}
    const sec=document.createElement('div');sec.className='lsteil';sec.dataset.n=String(p.n);if(p.page)sec.dataset.page=String(p.page);
    const heads=new Set((p.part||'').split(', ').filter(Boolean));
    for(const block of String(p.text).split(/\n{2,}/)){const b=block.trim();if(!b)continue;
      const first=b.split('\n',1)[0],rest=b.slice(first.length).trim(),line=first.replace(/^#{1,6}\s+/,'').replace(/^\*\*(.+)\*\*$/,'$1').trim();
      if(/^#{1,6}\s/.test(first)||heads.has(line)){const h=document.createElement('h3');h.textContent=line;sec.appendChild(h);if(!rest)continue;
        sec.appendChild(leseAbsatz(rest))}
      else sec.appendChild(leseAbsatz(b))}
    frag.appendChild(sec)}
  if(!vorne)LS.lastPage=page;
  if(vorne){const top=col.querySelector('.lsteil,.lspg');col.insertBefore(frag,top)}else col.insertBefore(frag,col.querySelector('[data-lsmore="weiter"]'))}
function leseAbsatz(text){const p=document.createElement('p');p.className=/^\|/.test(text)?'lstab':'';p.textContent=text;return p}
function leseKnopf(davor){const b=document.createElement('button');b.type='button';b.className='b lsmore';b.dataset.lsmore=davor?'davor':'weiter';
  b.textContent=davor?t('Davor lesen','Read what comes before'):t('Weiterlesen','Read on');
  const col=$('lscol');if(davor)col.insertBefore(b,col.firstChild);else col.appendChild(b)}
// long documents come a part at a time (the assistant always searches the whole text)
async function leseMehr(davor,b){const id=LS.id;b.disabled=true;
  try{const from=davor?Math.max(0,LS.first-60):LS.next;
    const r=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text?start='+from)).json();if(LS.id!==id)return;
    const keep=$('lspaper').scrollHeight-$('lspaper').scrollTop;
    if(davor){const parts=r.parts.slice(0,LS.first-from);b.remove();leseText(parts,true);LS.first=from;if(from>0)leseKnopf(true);
      $('lspaper').scrollTop=$('lspaper').scrollHeight-keep}
    else{b.remove();leseText(r.parts,false);LS.next=r.next;if(r.next!=null)leseKnopf(false)}
    leseMark($('lsq').value,true)}
  catch(x){b.disabled=false;b.textContent=x.message}}
function leseRel(list){const r=document.createElement('div');r.className='dvrel lsrel';const h=document.createElement('small');h.className='mut';h.textContent=t('Dazu gehören: ','Belongs with: ');r.appendChild(h);
  for(const x of list){const b=document.createElement('button');b.type='button';b.className='dtag';b.textContent=x.title||x.name;b.dataset.lsrel=x.id;
    b.title={Nummer:t('gleiche Nummer','same number'),Absender:t('gleicher Absender','same sender'),Tags:t('gleiche Schlagwörter','same keywords')}[x.why]||'';r.appendChild(b)}
  $('lscol').appendChild(r)}
// the words of the search marked in the text (each word from 2 letters, also inside longer words: „Kündigung“ in
// „Kündigungsfrist“), counted for „1 von N“; keep: after more text came, stay at the same mark
function leseMark(q,keep){const col=$('lscol'),old=LS.marks[LS.cur];
  for(const m of col.querySelectorAll('mark')){const p=m.parentNode;p.replaceChild(document.createTextNode(m.textContent),m);p.normalize()}
  LS.marks=[];LS.cur=-1;for(const b of $('lstoc').querySelectorAll('.lstocx'))b.classList.remove('treffer');
  const re=docWortRe(q);   // the same words as the list's snippets (me.js)
  if(re){
    const walk=document.createTreeWalker(col,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentNode.closest('button,audio,.lspg')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
    const nodes=[];while(walk.nextNode())nodes.push(walk.currentNode);
    for(let node of nodes){re.lastIndex=0;let m;
      while((m=re.exec(node.data))){const hit=node.splitText(m.index);node=hit.splitText(m[0].length);
        const mk=document.createElement('mark');hit.parentNode.replaceChild(mk,hit);mk.appendChild(hit);LS.marks.push(mk);re.lastIndex=0}}}
  if(keep&&old)LS.cur=LS.marks.findIndex(x=>x.textContent===old.textContent&&x.closest('.lsteil')===old.closest('.lsteil'));
  // the table of contents shows where the words stand
  const hs=[...$('lstoc').querySelectorAll('.lstocx')];
  if(hs.length){const h3=[...col.querySelectorAll('h3')];
    for(const mk of LS.marks){let last=null;for(const h of h3){if(h.compareDocumentPosition(mk)&Node.DOCUMENT_POSITION_FOLLOWING||h.contains(mk))last=h;else break}
      const b=last&&hs.find(x=>x.dataset.lst===last.textContent);if(b)b.classList.add('treffer')}}
  leseZahl()}
function leseZahl(){const n=LS.marks.length;$('lsn').textContent=$('lsq').value.trim()?(n?t(`${LS.cur+1||0} von ${n}`,`${LS.cur+1||0} of ${n}`):t('keine Stelle','no place')):'';
  $('lsprev').disabled=$('lsnext').disabled=!n}
function leseGeh(dir){const n=LS.marks.length;if(!n){leseZahl();return}
  if(LS.cur>=0)LS.marks[LS.cur].classList.remove('cur');
  LS.cur=dir===0?0:(LS.cur+dir+n)%n;const mk=LS.marks[LS.cur];mk.classList.add('cur');mk.scrollIntoView({block:'center'});
  leseSub(+(mk.closest('.lsteil').dataset.page||0)||0);leseZahl();leseTocAn(mk)}
// the heading the place stands under is lit in the table of contents
function leseTocAn(el){let last=null;for(const h of $('lscol').querySelectorAll('h3')){if(h.compareDocumentPosition(el)&Node.DOCUMENT_POSITION_FOLLOWING||h.contains(el))last=h;else break}
  for(const b of $('lstoc').querySelectorAll('.lstocx'))b.classList.toggle('on',!!last&&b.dataset.lst===last.textContent)}
// open at the place: the piece of the hit (its first mark, else the piece lit), else the page or the place in a recording
function leseZiel(){const o=LS.opt,col=$('lscol');let sec=o.n!=null?col.querySelector(`.lsteil[data-n="${+o.n}"]`):null;
  if(!sec&&o.page)sec=col.querySelector(`.lspg[data-page="${+o.page}"]`)||col.querySelector(`.lsteil[data-page="${+o.page}"]`);
  if(!sec&&o.at)sec=[...col.querySelectorAll('.lspg')].find(x=>x.textContent===o.at);
  const i=sec?LS.marks.findIndex(m=>sec.contains(m)||(sec.compareDocumentPosition(m)&Node.DOCUMENT_POSITION_FOLLOWING)):-1;
  if(i>=0){LS.cur=i-1;leseGeh(1);return}
  if(LS.marks.length&&!sec){LS.cur=-1;leseGeh(1);return}
  if(sec){if(sec.classList.contains('lsteil'))sec.classList.add('lsstelle');sec.scrollIntoView({block:'start'});leseSub(+(sec.dataset.page||0)||0)}
  else $('lspaper').scrollTop=0}
// a heading of the table of contents: in the loaded text it scrolls there, else the part around it comes
async function leseZu_n(n,title){const sec=$('lscol').querySelector(`.lsteil[data-n="${n}"]`);
  for(const b of $('lstoc').querySelectorAll('.lstocx'))b.classList.toggle('on',+b.dataset.lsn===n&&b.dataset.lst===title);
  if(sec){const h=[...sec.querySelectorAll('h3')].find(x=>x.textContent===title);(h||sec).scrollIntoView({block:'start'});leseSub(+(sec.dataset.page||0)||0);return}
  leseOpen(LS.id,Object.assign({},LS.opt,{n,page:0,at:''}))}
function lesePlay(secs){const a=$('lsaudio');if(!a)return;
  const go=()=>{try{a.currentTime=secs}catch{}a.play().catch(()=>{})};if(a.readyState>0)go();else{a.preload='auto';a.addEventListener('loadedmetadata',go,{once:true});a.load()}}
function leseSeg(){for(const b of $('lsseg').querySelectorAll('[data-lsart]'))b.setAttribute('aria-pressed',String(b.dataset.lsart===LS.art))}
// Original: a PDF in the browser's own viewer at the page of the place, a picture large, other files to download
function leseArt(art){LS.art=art;leseSeg();const d=LS.d;if(!d)return;const o=$('lsorig');
  $('lspaper').hidden=art!=='text';$('lsfind').hidden=art!=='text';o.hidden=art==='text';
  $('lesemodal').classList.toggle('lsorigan',art!=='text');
  if(art==='text'){o.textContent='';return}
  o.textContent='';const url='/api/profile/wissen/'+encodeURIComponent(LS.id)+'/file',name=d.name||'',pdf=/\.pdf$/i.test(name);
  const cur=LS.marks[LS.cur],sec=cur?cur.closest('.lsteil'):$('lscol').querySelector('.lsstelle'),page=+(sec&&sec.dataset.page)||+(LS.opt.page||0)||1;
  const row=document.createElement('div');row.className='lsorow';
  const dl=document.createElement('a');dl.className='b';dl.href=url;dl.rel='noopener';dl.appendChild(icNode('download'));dl.append(' '+t('Herunterladen','Download'));
  if(pdf){const nw=document.createElement('a');nw.className='b';nw.href=url+'?view=1#page='+page;nw.target='_blank';nw.rel='noopener';nw.textContent=t('In neuem Fenster','In a new window');row.appendChild(nw)}
  row.appendChild(dl);o.appendChild(row);
  if(pdf){const f=document.createElement('iframe');f.className='lspdf';f.title=name;f.src=url+'?view=1#page='+page;o.appendChild(f)}
  else if(d.kind==='picture'){const img=document.createElement('img');img.alt='';img.src=url+'?view=1';o.appendChild(img)}
  else if(d.kind==='audio'){const a=$('lsaudio');if(a)o.appendChild(a.cloneNode())}
  else{const p=document.createElement('p');p.className='mut';p.textContent=t('Dieses Original zeigt der Browser nicht selbst; „Herunterladen“ öffnet es mit dem passenden Programm.','The browser does not show this original itself; "Download" opens it with the fitting program.');o.appendChild(p)}}
// another page from the menu (goSec clicks its button) closes the Leseansicht, it never stays over that page
document.addEventListener('click',e=>{if(LS.id&&e.target.closest&&e.target.closest('nav button[data-s]'))leseZu()},true);
