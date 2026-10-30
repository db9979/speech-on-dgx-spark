// Fernzugang (fernzugang.py, plan ssh-vermittlung stage 1): Fernzugang → Systeme. Servers elsewhere call the panel
// through their anchor (anker/spark-anker.py); an admin opens their shell here. Every name and number goes through
// textContent; xterm.js (MIT, pinned in fernzugang.XTERM) loads from the panel only when a shell opens. „Shell“ and
// „Koppeln (Code)“ ask for a fresh code or passkey (stufen „Schutz ändern“). The chips beside the terminal are fixed
// commands: a tap puts one into the line, Enter is always the person's own. The shell's output never leaves the page.
// „Frag den Assistenten“ (stage 2b, switch chat.fernzugang_hilfe): the own language model answers as text; a command in
// it is inserted only with „Einfügen“, a dangerous one (fernzugang.GEFAHR, fixed rules) only on a second tap; Enter is
// always the person's. With the panel open, the page asks for suggestions after Enter (one in vorschlag_s seconds).
// „Herauslösen“ moves the open shell into its own window (the panel page with #fernfenster): that window asks this one
// for its own one-time ticket over postMessage (same origin only), never in its address; „Zurückholen“ takes it back.
// In the terminal the browser's own shortcuts are held back (fzFang); „Alle Tasten“ adds full screen and the Keyboard
// Lock API (Chrome, Edge), so even Strg+W or Esc go to the shell; Esc held for 2 s leaves.
// Layout A (Dominik 2026-10-28 20:07): terminal with an icon bar, one row of chips below it, the assistant as a column
// on the right (width dragged and kept in this browser, folds away); the session's facts behind the ⓘ of the red line;
// the page never scrolls (fzLayout); the panel's menu folds away while a terminal is open (fzMenu). Phone: the
// assistant is a sheet from below.
const FZ={d:null,sel:'',tab:'systeme',timer:0,ws:null,term:null,sitz:null,code:null,ctrl:false,alt:false,sid:'',pop:null,weg:null,hist:[],ki:null,vt:0,vlast:0,fs:null,fb:null};
// „Dateien“ (ferndateien.py, stage 3): SFTP in the same SSH connection, on the unlocked page; names come as text only,
// a download goes through a one-time link, an upload as the raw file (at most chat.fernzugang_datei_mb).
// what the own window takes over from its opener (admin_get): the rules and the assistant's limits
const FZ_MIT=['chips','folge','erklaert','sudo_tip','hinweis','hilfe','gefahr','ki_zeilen','ki_zeilen_wahl','ki_zeichen','ziel_min','hilfe_befehle','vorschlag_s','notizen','notiz_max'];
const FZ_FENSTER=location.hash==='#fernfenster'&&!!window.opener;
const FZ_SPALTE=[280,520];   // the assistant's column: its width in pixels, dragged between these
function fzEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function fzBtn(txt,cls,fn){const b=fzEl('button','b'+(cls?' '+cls:''),txt);b.type='button';b.onclick=fn;return b}
function fzZeit(s){if(!s)return'–';const d=new Date(s*1000),h=new Date();
  const uhr=d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===h.toDateString()?uhr:d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'numeric'})+' '+uhr}
function fzMin(s){const m=Math.max(0,Math.round((Date.now()/1000-s)/60));return m<60?m+' min':Math.floor(m/60)+' h '+(m%60)+' min'}
// messages of the page as a short toast (sayToast), never as a line under it; an empty one changes nothing
function fzMsg(text,bad){if(text)sayToast(text,bad?8000:4000,{bad:!!bad})}
function fzUhr(s){return new Date(s*1000).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'})}
function fzStand(g){return g.stand==='abbau'?['warn',t('wird beim nächsten Kontakt abgebaut','removed at next contact')]
  :g.hostkey_falsch?['bad',t('Host-Schlüssel falsch','host key wrong')]:!g.erlaubt?['warn',t('gesperrt','blocked')]
  :g.online?['ok',t('online','online')]:['',t('offline','offline')]}
// the kind of system as its icon (fixed pictures, never text from outside)
const FZ_SVG={linux:'<path d="M7 9l3 3-3 3M12 15h5"/>',windows:'<path d="M4 5h7v6H4zM13 5h7v6h-7zM4 13h7v6H4zM13 13h7v6h-7z"/>',
  macos:'<rect x="5" y="5" width="14" height="10" rx="1.5"/><path d="M3 19h18"/>'};
function fzIcon(g,gross){const a=FZ_SVG[g.art]?g.art:'linux',s=fzEl('span','fzos '+a+(gross?' gross':''));
  s.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+FZ_SVG[a]+'</svg>';return s}
// what a running shell keeps when the page locks meanwhile: the rules of the chips and the assistant, never the systems
const FZ_BLEIBT=FZ_MIT.concat(['max','leerlauf']);
async function fzLoad(){clearTimeout(FZ.timer);const box=$('fzbox');if(!box||document.body.classList.contains('mgr')||FZ_FENSTER)return;
  try{const r=await api('/api/admin/fernzugang');const d=await r.json();
    if(d.gesperrt&&FZ.d&&(FZ.ws||FZ.weg||FZ.fs||FZ.fb))for(const k of FZ_BLEIBT)if(FZ.d[k]!==undefined)d[k]=FZ.d[k];
    FZ.d=d;
    if(FZ.weg&&!d.gesperrt&&!(d.offen||[]).some(x=>x.id===FZ.weg.sid)){FZ.weg=null;FZ.pop=null;FZ.sitz=null;fzBanner();fzWegZeigen()}
    if(FZ.fb&&d.gesperrt){fbTrennen(t('Die Seite ist gesperrt: der Bildschirm ist zu.','The page is locked: the screen is closed.'));return}
    if(FZ.fs&&d.gesperrt&&!FZ.fs.laeuft){fzFSchliessen(t('Die Seite ist gesperrt: die Dateien sind zu.','The page is locked: the files are closed.'));return}   // locked: nothing of the server stays shown
    if(FZ.fs&&!FZ.fs.laeuft&&!d.gesperrt&&!(d.offen||[]).some(x=>x.id===FZ.fs.id)){fzFZu(t('Die Dateien-Sitzung ist zu (Leerlauf, Trennen oder Notaus).','The files session is closed (idle, disconnect or emergency stop).'));return}
    fzShow();if(window.shLoad)shLoad()}catch(e){fzMsg(e.message,true)}
  if(document.querySelector('section#fern.on'))FZ.timer=setTimeout(fzLoad,FZ.ws||FZ.fs||FZ.fb?15000:10000)}
function fzFehler(e){fzMsg(e.message,true);if(e.status===423)fzLoad()}   // locked meanwhile: the page shows „Entsperren“
// locked: nothing of the systems stays in the page, not even hidden
function fzLeeren(){for(const id of ['fzlist','fzdetail','fzjetztlist','fzstatus','fzverlauflist','fzcode','fzflist','fzcrumbs'])$(id).textContent='';
  $('fzdetail').hidden=true;$('fzjetzt').hidden=true;FZ.sel='';FZ.auf=false;FZ.code=null;FZ.ordner='';FZ.neuOrdner=false;FZ.ordnerEdit=false;fzMenuZu();
  for(const id of ['fzkoppelnmodal','fzverlaufmodal'])$(id).style.display='none'}
// the tabs „Systeme | Spontanhilfe“: only on the unlocked page and only while Spontanhilfe is on; true on its tab
// something open (a shell, also while it connects or reconnects, its own window, files, a screen): the list, its tabs and
// the status line above stay away, so nothing above the terminal comes and goes (Dominik 2026-10-30: the shell jumped)
function fzOffen(){const v=$('fzview');return !!FZ.ws||!!FZ.weg||!!FZ.fs||!!FZ.fb||!!(v&&!v.hidden)}
function fzTabs(){const d=FZ.d,h=typeof SH!=='undefined'&&SH.d,busy=fzOffen();
  const zeig=!!(d&&d.on&&!d.gesperrt&&!d.notaus&&!busy&&h&&h.on&&!h.gesperrt&&!h.notaus);
  if(!zeig)FZ.tab='systeme';$('fztabs').hidden=!zeig;
  for(const b of $('fztabs').querySelectorAll('button')){const on=b.dataset.tab===FZ.tab;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on))}
  return FZ.tab!=='systeme'}
function fzTab(tab){FZ.tab=tab;fzShow();if(window.shShow)shShow();fzSeite()}
function fzShow(){const d=FZ.d,box=$('fzmain');if(!d||!box)return;const zu=!!(d.on&&d.gesperrt),busy=fzOffen();
  $('fzoff').hidden=!!d.on;$('fznotaus').hidden=!d.notaus;$('fzsperrmin').textContent=d.entsperrt_min||60;
  $('fzgesperrt').hidden=!zu||busy||!!d.notaus;$('fzneu').hidden=!d.on||zu||!!d.notaus;
  $('fzlock').hidden=!d.on||zu||!d.entsperrt_bis;clearTimeout(FZ.st);
  fzSperreBald();
  if(d.entsperrt_bis){$('fzlockbis').textContent=t('Entsperrt bis ','Unlocked until ')+fzUhr(d.entsperrt_bis);
    FZ.st=setTimeout(fzLoad,Math.max(1000,d.entsperrt_bis*1000-Date.now()+1500))}   // its minutes are over: locked at once
  if(zu||!d.on)fzLeeren();
  if(fzTabs())$('fzneu').hidden=true;box.hidden=!d.on||zu||busy||FZ.tab!=='systeme';$('fzstatus').hidden=box.hidden;if(box.hidden)return;
  const c=d.counts||{},st=$('fzstatus');st.textContent='';
  for(const [n,de,en,cls] of [[c.online,' online',' online','ok'],[c.gekoppelt,' gekoppelt',' paired',''],
    [c.sitzungen,c.sitzungen===1?' Sitzung offen':' Sitzungen offen',c.sitzungen===1?' session open':' sessions open',c.sitzungen?'bad':'']]){
    const s=fzEl('span','fzst');s.append(fzEl('span','fzdot '+cls),fzEl('b','',String(n||0)),document.createTextNode(t(de,en)));st.appendChild(s)}
  $('fzallevt').textContent=t(`${d.verlauf_tage||30} Tage ›`,`${d.verlauf_tage||30} days ›`);
  const gs=d.geraete||[];if(FZ.sel&&!gs.some(g=>g.id===FZ.sel)){FZ.sel='';FZ.auf=false}
  const ord=d.ordner_an?(d.ordner||[]):null;if(FZ.ordner&&!(ord||[]).some(o=>o.id===FZ.ordner))FZ.ordner='';
  if(!FZ.sel&&!FZ.ordner&&gs[0]&&!NARROW())FZ.sel=gs[0].id;
  const q=$('fzsuche').value.trim().toLowerCase(),list=$('fzlist');list.textContent='';
  if(!gs.length)list.appendChild(fzEl('div','mut fzleer',t('Noch kein System gekoppelt. „+ System koppeln“ zeigt den Befehl für das neue System.','No system paired yet. "+ Pair a system" shows the command for the new system.')));
  const tr=FZ.treffer&&FZ.treffer.q.toLowerCase()===q?FZ.treffer.t:{};
  const passt=gs.filter(g=>!q||(g.name+' '+(g.os||'')).toLowerCase().includes(q)||!!tr[g.id]),bereit=g=>g.online&&g.erlaubt&&!g.hostkey_falsch&&g.stand!=='abbau';
  if(ord)fzOrdnerListe(list,ord,passt,tr,!!q);
  else for(const [de,en,teil] of [['Online','Online',passt.filter(bereit)],['Offline oder gesperrt','Offline or blocked',passt.filter(g=>!bereit(g))]]){
    if(!teil.length)continue;list.appendChild(fzEl('div','fzgrp',t(de,en)+' · '+teil.length));
    for(const g of teil)list.appendChild(fzSysZeile(g,tr))}
  if(q&&!passt.length)list.appendChild(fzEl('div','mut fzleer',t('Kein System passt.','No system matches.')));
  const akt=fzAktBereit(gs);$('fzalleakt').hidden=!akt.length;$('fzalleaktn').textContent=akt.length?'('+akt.length+')':'';
  const o=d.offen||[],jl=$('fzjetztlist');$('fzjetzt').hidden=!o.length;jl.textContent='';for(const x of o)jl.appendChild(fzJetztZeile(x,true));
  fzDetail();if($('fzverlaufmodal').style.display==='grid')fzVerlauf();fzSeite()}
// one system in the list on the left: icon, name (📝 with a note, a tag with a session), the second line, a hit in its note
function fzSysZeile(g,tr){const [lvl]=fzStand(g),row=fzEl('button','fzrow'+(g.id===FZ.sel?' on':''));row.type='button';row.dataset.id=g.id;
      const tx=fzEl('span','fzrtext'),nm=fzEl('span','fzrname');nm.appendChild(fzEl('b','',g.name));if(g.notiz){const n=fzEl('span','fznzmark','📝');n.title=t('hat eine Notiz','has a note');nm.appendChild(n)}if(g.sitzungen)nm.appendChild(fzEl('span','fztag',t('Sitzung','Session')));
      tx.append(nm,fzEl('small','',[g.os,fzWie(g),g.anker_neu?t('Anker: neu ','anchor: new ')+g.anker_neu:''].filter(Boolean).join(' · ')));
      const h=tr[g.id];if(h){const sn=fzEl('small','fznzsnip');sn.append(document.createTextNode(t('Notiz: „','Note: "')+h.vor),fzEl('mark','',h.treffer),document.createTextNode(h.nach+t('“','"')));tx.appendChild(sn)}
      row.append(fzIcon(g),tx,fzEl('span','fzdot '+(g.sitzungen?'bad':lvl)));row.onclick=()=>{FZ.sel=g.id;FZ.ordner='';FZ.auf=true;fzShow()};return row}
// online since, offline since, or why it may not connect: the second line of a system
function fzWie(g){return g.stand==='abbau'?t('wird abgebaut','being removed'):g.hostkey_falsch?t('Host-Schlüssel falsch','host key wrong')
  :!g.erlaubt?t('darf sich nicht verbinden','may not connect'):g.online?t('online seit ','online since ')+fzZeit(g.online_seit)
  :g.weg?t('offline seit ','offline since ')+fzZeit(g.weg):t('offline','offline')}
// „Gerade verbunden“: who has a session open, from where (Zuhause or Internet, the address shortened) and with what
const FZ_CLIENT={browser:['Browser','Browser'],iphone:['iPhone','iPhone'],android:['Android','Android'],fenster:['Fenster','Window']};
function fzWoher(h){return h==='internet'?t('Internet','Internet'):t('Zuhause','Home')}
function fzArt(a){return a==='shell'?t('Shell','Shell'):a==='bildschirm'?t('Bildschirm','Screen'):a==='dateien'?t('Dateien','Files'):a}
function fzJetztZeile(x,mitSystem){const d=FZ.d,name=((d.geraete||[]).find(g=>g.id===x.geraet)||{}).name||'';
  const r=fzEl('div','fzjrow'),tx=fzEl('div','fzjtext'),wo=fzWoher(x.herkunft)+(x.ip?' ('+x.ip+')':''),seit=t('seit ','since ')+fzZeit(x.seit);
  tx.append(fzEl('b','',(mitSystem?name:x.admin)+' · '+fzArt(x.art)),
    fzEl('small','',(mitSystem?[x.admin,wo,seit]:[t(...(FZ_CLIENT[x.client]||FZ_CLIENT.browser)),wo,seit]).join(' · ')));
  r.append(fzEl('span','fzdot bad'),tx,fzBtn(t('Trennen','Disconnect'),'danger',async()=>{try{await api(`/api/admin/fernzugang/sitzung/${x.id}/trennen`,{method:'POST'});fzLoad()}catch(e){fzFehler(e)}}));return r}
function fzDetail(){const d=FZ.d,box=$('fzdetail'),g=(d.geraete||[]).find(x=>x.id===FZ.sel);box.textContent='';box.hidden=!g;
  const fo=!g&&FZ.ordner&&d.ordner_an?(d.ordner||[]).find(o=>o.id===FZ.ordner):null;
  if(fo){box.hidden=false;$('fzsplit').classList.toggle('fzauf',!!FZ.auf);fzOrdnerDetail(box,fo);return}
  $('fzsplit').classList.toggle('fzauf',!!g&&!!FZ.auf);if(!g)return;const [lvl,word]=fzStand(g),c=d.counts||{};
  const bk=fzEl('button','fzback','‹ '+t('Alle Systeme','All systems'));bk.type='button';bk.onclick=()=>{FZ.auf=false;fzShow()};box.appendChild(bk);
  const hd=fzEl('div','fzdkopf'),ht=fzEl('div','fzdtext'),nm=fzEl('div','fzdname');nm.append(fzEl('b','',g.name),fzEl('span','pill '+lvl,word));
  ht.append(nm,fzEl('div','mut',[g.os,g.anker?t('Anker ','anchor ')+g.anker:'',g.online?t('online seit ','online since ')+fzZeit(g.online_seit)+' ('+fzMin(g.online_seit)+')':fzWie(g)].filter(Boolean).join(' · ')));
  hd.append(fzIcon(g,true),ht);box.appendChild(hd);
  const kn=fzEl('div','fzknoepfe');
  const sh=fzBtn(t('Shell','Shell'),'p fzk',()=>fzOpen(g));sh.disabled=!g.online||g.hostkey_falsch||!g.erlaubt||g.stand==='abbau'||(c.sitzungen||0)>=d.max;
  const da=fzBtn(t('Dateien','Files'),'fzk',()=>fzDateien(g)),bs=fzBtn(t('Bildschirm','Screen'),'fzk',()=>fbOpen(g));da.disabled=sh.disabled;
  bs.disabled=sh.disabled||!d.bildschirm||!g.bild||!g.bild_anker;if(!d.bildschirm)bs.hidden=true;
  const cut=fzBtn(t('Anker trennen','Disconnect anchor'),'fzankercut',async()=>{try{await api(`/api/admin/fernzugang/geraete/${g.id}/trennen`,{method:'POST'});fzMsg(t('Getrennt. Der Anker kommt nach seiner Pause wieder, solange er sich verbinden darf.','Disconnected. The anchor comes back after its pause while it may connect.'));fzLoad()}catch(e){fzFehler(e)}});
  cut.disabled=!g.online;kn.append(sh,da,bs,fzEl('span','fzfill'),cut);box.appendChild(kn);
  if(d.bildschirm&&!(g.bild&&g.bild_anker))box.appendChild(fzEl('div','fh',g.bild?t('Für den Bildschirm ist der Anker zu alt: dort noch einmal „sudo spark-anker bildschirm“ mit dem Programm aus dem Panel.','The anchor is too old for the screen: run "sudo spark-anker bildschirm" there again with the program from the panel.'):t('Bildschirm: auf dem System einmal „sudo spark-anker bildschirm“.','Screen: run "sudo spark-anker bildschirm" once on the system.')));
  if(g.hostkey_falsch)box.appendChild(fzEl('div','note err',t('Das System zeigt einen anderen Host-Schlüssel als bei der Kopplung: keine Verbindung. War das eine Neuinstallation, „Entfernen“ und neu koppeln.','The system shows another host key than at pairing: no connection. If it was reinstalled, "Remove" and pair again.')));
  if(g.anker_neu||g.update_stand)box.appendChild(fzAktBlock(g));
  const grid=fzEl('div','fzdgrid'),li=fzEl('div','fzdcol'),re=fzEl('div','fzdcol');grid.append(li,re);box.appendChild(grid);
  const o=(d.offen||[]).filter(x=>x.geraet===g.id);
  if(o.length){li.appendChild(fzEl('div','fzgrp',t('Gerade verbunden','Connected now')));const w=fzEl('div','fzjetztbox');for(const x of o)w.appendChild(fzJetztZeile(x,false));li.appendChild(w)}
  li.appendChild(fzEl('div','fzgrp',t('Angaben','Details')));
  const dl=fzEl('dl','fzfacts'),key=fzEl('dd','fzkey');
  if(g.fp){key.append(fzEl('code','',fzKurz(g.fp)),fzEl('span','fzok',' ✓ '));const k=fzEl('button','fzlink',t('Kopieren','Copy'));k.type='button';k.title=t('Ganzen Schlüssel kopieren','Copy the whole key');k.onclick=e=>copyString(g.fp,e.currentTarget);key.appendChild(k)}else key.textContent='–';
  dl.append(fzEl('dt','',t('Host-Schlüssel','Host key')),key);
  for(const [k,v] of [[t('Anmeldung','Sign-in'),t('ed25519 aus dem Tresor · Benutzer ','ed25519 from the vault · user ')+'spark'],[t('Gekoppelt','Paired'),fzZeit(g.seit)],
    [t('Leerlauf trennt','Idle ends'),t('nach ','after ')+d.leerlauf+' min']])dl.append(fzEl('dt','',k),fzEl('dd','',v));
  li.appendChild(dl);
  const nz=fzNotizFuer(g.id);if(nz){const fo=nz.contains(document.activeElement)?document.activeElement:null;li.appendChild(nz);if(fo&&document.activeElement!==fo){const a=fo.selectionStart,b=fo.selectionEnd;fo.focus();if(a!=null)fo.setSelectionRange(a,b)}}
  const sw=fzEl('div','setrow');const lb=fzEl('div','lbl');lb.append(fzEl('b','',t('Darf sich verbinden','May connect')),fzEl('span','',t('Aus: der Anker wird abgewiesen.','Off: the anchor is refused.')));
  const tg=fzEl('label','tgl'),inp=document.createElement('input');inp.type='checkbox';inp.checked=!!g.erlaubt;inp.disabled=g.stand==='abbau';inp.setAttribute('aria-label',t('Darf sich verbinden','May connect'));tg.append(inp,fzEl('i'));
  inp.onchange=async()=>{try{await api(`/api/admin/fernzugang/geraete/${g.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({erlaubt:inp.checked})});fzLoad()}catch(e){inp.checked=!inp.checked;fzFehler(e)}};
  sw.append(lb,tg);li.appendChild(sw);
  re.appendChild(fzEl('div','fzgrp',t(`Verlauf · ${d.verlauf_tage||30} Tage`,`History · ${d.verlauf_tage||30} days`)));
  const v=(d.verlauf||[]).filter(x=>x.system===g.name),tab=fzEl('div','fzvtab');
  if(!v.length)tab.appendChild(fzEl('div','mut',t('Noch keine Sitzung.','No session yet.')));for(const x of v.slice(0,5))tab.appendChild(fzVerlaufZeile(x,false));
  re.appendChild(tab);if(v.length){const a=fzEl('button','fzlink',t('Alle anzeigen ›','Show all ›'));a.type='button';a.onclick=()=>fzVerlaufZeigen(g.name);re.appendChild(a)}
  const ft=fzEl('div','fzdfuss'),rm=fzBtn(t('Entfernen …','Remove …'),'danger',()=>fzRemove(g));
  ft.append(fzEl('span','fh',t('Entfernen baut alles ab, was der Anker auf dem System eingerichtet hat.','Remove takes down everything the anchor set up on the system.')),rm);box.appendChild(ft)}
// Anker aktualisieren (fernanker.py): the panel's own signed program over the anchor's channel; an anchor before 1.3.0
// gets the one line `… | sudo python3 - aktualisieren` (Kopieren, or „In die Shell einfügen“: a shell opens, the line
// is typed in, never Enter)
const FZ_UPD={gesendet:['gesendet, der Anker lädt und prüft …','sent, the anchor fetches and checks …'],laeuft:['geprüft, wird eingespielt …','checked, being installed …'],
  ok:['aktualisiert','updated'],zurueck:['zurück auf der Version davor: die neue kam nicht zum Panel','back on the version before: the new one did not reach the panel'],
  kein_schluessel:['ohne Signaturschlüssel: einmal die Zeile unten','no signing key: run the line below once'],nicht_neuer:['nichts Neueres','nothing newer'],
  laden:['Laden vom Panel ging nicht','fetching from the panel failed'],gross:['Programm zu groß','program too big'],pruefsumme:['Prüfsumme passt nicht','checksum does not match'],
  version:['Version passt nicht','version does not match'],signatur:['Signatur passt nicht: nichts geändert','signature does not match: nothing changed'],
  schreiben:['Schreiben ging nicht','writing failed'],unlesbar:['unlesbar','unreadable']};
function fzAktBereit(gs){return (gs||[]).filter(g=>g.anker_neu&&g.anker_fern&&g.online&&!g.sitzungen&&g.stand!=='abbau')}
function fzAktBlock(g){const b=fzEl('div','fzakt');const kopf=fzEl('div','fzaktkopf');
  kopf.appendChild(fzEl('span','',t('Anker ','Anchor ')+(g.anker||'?')+(g.anker_neu?t(' · neu: ',' · new: ')+g.anker_neu:'')));
  if(g.anker_neu&&g.anker_fern){const k=fzBtn(t('Aktualisieren','Update'),'p',()=>fzAktualisieren([g.id]));k.id='fzakt1';k.disabled=!g.online||!!g.sitzungen||g.stand==='abbau';
    k.title=!g.online?t('Erst wenn das System online ist.','Only while the system is online.'):g.sitzungen?t('Erst die Sitzung trennen: der Anker startet neu.','Disconnect the session first: the anchor restarts.'):'';kopf.appendChild(k)}
  else if(g.anker_neu){const k=fzBtn(t('Zeile zeigen','Show the line'),'',()=>fzAktZeile(g,b,k));k.id='fzaktzeile';kopf.appendChild(k)}
  b.appendChild(kopf);
  if(g.update_stand&&FZ_UPD[g.update_stand])b.appendChild(fzEl('div','fh',t('Zuletzt: ','Last: ')+t(...FZ_UPD[g.update_stand])));
  if(g.anker_neu&&!g.anker_fern)b.appendChild(fzEl('div','fh',t('Dieser Anker kann das Aktualisieren aus dem Panel noch nicht: einmal diese Zeile auf dem System (mit sudo, ohne Code); Kopplung und Schlüssel bleiben.','This anchor cannot take updates from the panel yet: run this line on the system once (with sudo, no code); pairing and keys stay.')));
  return b}
async function fzAktZeile(g,box,knopf){let d;try{const r=await api('/api/admin/fernzugang/aktualisieren/befehl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});d=await r.json()}catch(e){fzFehler(e);return}
  knopf.remove();const z=g.art==='macos'&&d.befehl_mac?d.befehl_mac:d.befehl;const pre=fzEl('pre','fzcmd',z);pre.id='fzaktbefehl';box.appendChild(pre);
  const row=fzEl('div','row');row.append(fzBtn(t('Kopieren','Copy'),'',e=>copyString(z,e.target)));
  const ein=fzBtn(t('In die Shell einfügen','Paste into the shell'),'',()=>{FZ.nachher=z;fzOpen(g)});ein.id='fzakteinf';ein.disabled=!g.online||g.hostkey_falsch||!g.erlaubt;
  ein.title=t('Öffnet eine Shell und schreibt die Zeile hinein; Enter drückst du selbst.','Opens a shell and types the line in; you press Enter yourself.');row.appendChild(ein);box.appendChild(row)}
async function fzAktualisieren(ids){try{const r=await api('/api/admin/fernzugang/aktualisieren',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraete:ids})});const d=await r.json();
    const teile=[[d.gesendet,'gesendet','sent'],[d.aktuell,'schon aktuell','up to date'],[d.alt,'brauchen einmal die Zeile','need the line once'],[d.offline,'offline','offline'],[d.belegt,'mit offener Sitzung','with a session open']]
      .filter(x=>x[0]).map(x=>x[0]+' '+t(x[1],x[2]));fzMsg(t('Aktualisieren auf ','Update to ')+d.version+': '+teile.join(' · '),!d.gesendet);fzLoad()}catch(e){fzFehler(e)}}
async function fzRemove(g){if(g.notiz&&confirm(t(`„${g.name}“ hat eine Notiz. Sie wird mit dem System gelöscht. Notiz vorher herunterladen?`,`"${g.name}" has a note. It is deleted with the system. Download the note first?`)))fzNotizLadenDatei(g);
  if(!confirm(t(`„${g.name}“ entfernen? Der Schlüssel gilt sofort nicht mehr; der Anker baut auf dem System alles ab, was er eingerichtet hat (jetzt oder beim nächsten Kontakt). Danach fragt der Spark nach Code oder Passkey.`,`Remove "${g.name}"? The key stops at once; the anchor removes everything it set up on the system (now or at its next contact). Then the Spark asks for a code or passkey.`)))return;
  try{const r=await api(`/api/admin/fernzugang/geraete/${g.id}`,{method:'DELETE'});const d=await r.json();
    fzMsg(d.stand==='abbau'?t('Entfernt. Der Anker baut sich ab; ist er offline, beim nächsten Kontakt. Von Hand auf dem System: sudo spark-anker entfernen','Removed. The anchor removes itself; when offline, at its next contact. By hand on the system: sudo spark-anker entfernen'):'');FZ.sel='';FZ.auf=false;fzLoad()}catch(e){fzFehler(e)}}
// „Entsperren“, „Verlängern“ (a fresh code or passkey each time) and „Sperren“
async function fzEntsperren(){try{await api('/api/admin/fernzugang/entsperren',{method:'POST'});fzMsg('');fzLoad()}catch(e){fzMsg(e.message,true)}}
async function fzSperren(){try{await api('/api/admin/fernzugang/entsperren',{method:'DELETE'})}catch(e){fzMsg(e.message,true)}fzLeeren();fzLoad()}
// „System koppeln“: a sheet with the name and the kind of system, then a fresh code; the code is shown once, never in the command
function fzKoppelnAuf(){$('fzkoppelnmodal').style.display='grid';fzKoppelnOrdner();fzKoppelnZeigen();fzProtokoll();setTimeout(()=>$('fzname').focus(),50)}
function fzOsWahl(os){FZ.os=os;for(const b of $('fzos').querySelectorAll('button')){const on=b.dataset.os===os;b.classList.toggle('on',on);b.setAttribute('aria-checked',on?'true':'false')}
  $('fzwin').hidden=os!=='windows';$('fzgo').disabled=os==='windows';fzKoppelnZeigen()}
async function fzKoppeln(){const name=$('fzname').value.trim();if(!name){$('fzname').focus();return}if(FZ.os==='windows')return;
  try{const r=await api('/api/admin/fernzugang/koppeln',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,os:FZ.os,origin:location.origin,ordner:$('fzkordner').value||''})});
    FZ.code=Object.assign(await r.json(),{name,bis:Date.now()/1000+0});FZ.code.bis+=FZ.code.gilt_s;$('fzname').value='';fzKoppelnZeigen();fzLoad()}catch(e){fzFehler(e)}}
function fzKoppelnZeigen(){const box=$('fzcode');if(!box)return;box.textContent='';const k=FZ.code,mac=FZ.os==='mac';
  if(FZ.os==='windows')return;
  if(!k||Date.now()/1000>k.bis){FZ.code=null;return}
  box.appendChild(fzEl('div','',t(`Einmal-Code für „${k.name}“. Er wird nur jetzt gezeigt und gilt bis `,`One-time code for "${k.name}". It is shown only now and counts until `)+fzZeit(k.bis)+'.'));
  box.appendChild(fzEl('div','fzbig',k.code));
  if(k.link)fzKoppelnLink(box,k);
  box.appendChild(fzEl('div','fh',mac?t('Auf dem Mac (ab macOS 13) diese eine Zeile im Terminal einfügen. Sie fragt dann nach dem Code; er steht nie im Befehl. Sie schaltet die Entfernte Anmeldung nur für den Anker ein, wenn sie aus war.','On the Mac (from macOS 13) paste this one line in the terminal. It then asks for the code; it is never in the command. It switches Remote Login on only for the anchor when it was off.')
    :t('Auf dem System (Debian, Ubuntu, Raspberry Pi OS mit laufendem sshd) diese eine Zeile im Terminal einfügen. Sie fragt dann nach dem Code; er steht nie im Befehl.','On the system (Debian, Ubuntu, Raspberry Pi OS with sshd running) paste this one line in the terminal. It then asks for the code; it is never in the command.')));
  box.appendChild(fzEl('pre','fzcmd',k.befehl));
  const row=fzEl('div','row');row.appendChild(fzBtn(t('Kopieren','Copy'),'',e=>copyString(k.befehl,e.target)));box.appendChild(row);
  if(mac&&k.befehl_mac){box.appendChild(fzEl('div','fh',t('Oder mit Apples eigenem Python:','Or with Apple\'s own Python:')));box.appendChild(fzEl('pre','fzcmd',k.befehl_mac));
    const rm=fzEl('div','row');rm.appendChild(fzBtn(t('Kopieren','Copy'),'',e=>copyString(k.befehl_mac,e.target)));box.appendChild(rm)}
  const pr=fzEl('details','fzpruef');pr.appendChild(fzEl('summary','',t('Prüfen (freiwillig)','Check (optional)')));
  pr.appendChild(fzEl('div','fh',t('SHA-256 des Programms, wie es das Panel ausliefert; auf dem System mit curl -fsSL …/fernzugang/anker | sha256sum vergleichen (Mac: shasum -a 256):','SHA-256 of the program as the panel hands it out; compare on the system with curl -fsSL …/fernzugang/anker | sha256sum (Mac: shasum -a 256):')));
  pr.appendChild(fzEl('code','fzsha',(k.anker||{}).sha256||''));if(k.fp)pr.appendChild(fzEl('div','fh',t('Zertifikat des Panels (festgelegt): ','Panel certificate (pinned): ')+k.fp));
  box.appendChild(pr)}
// the „Einmal-Link“ beside the code: opened on the new system it shows the one line; the code is never in it
function fzKoppelnLink(box,k){const w=fzEl('div','fzklink');
  w.appendChild(fzEl('div','fh',t('Einmal-Link für das neue System (gilt so lange wie der Code, nur bis zum Koppeln). Auf dem System öffnen: er zeigt die eine Zeile, der Code steht nie darin.','One-time link for the new system (counts as long as the code, only until pairing). Open it on the system: it shows the one line, the code is never in it.')));
  w.appendChild(fzEl('code','fzlinktext',k.link));
  const row=fzEl('div','row');row.appendChild(fzBtn(t('Kopieren','Copy'),'',e=>copyString(k.link,e.target)));
  if(navigator.share)row.appendChild(fzBtn(t('Teilen','Share'),'',()=>navigator.share({title:t('System koppeln','Pair a system'),url:k.link}).catch(()=>{})));
  row.appendChild(fzBtn(t('Per E-Mail','By e-mail'),'',()=>{location.href='mailto:?subject='+encodeURIComponent(t('System koppeln','Pair a system'))+'&body='+encodeURIComponent(k.link)}));
  w.appendChild(row);
  if(k.qr){const img=document.createElement('img');img.className='fzqr';img.alt=t('QR-Code des Links','QR code of the link');img.src='data:image/svg+xml;base64,'+btoa(k.qr);w.appendChild(img)}
  box.appendChild(w)}
// „Verlauf“: the sessions of the last days, of one system or of all, no content
function fzVerlaufZeile(x,mitSystem){const r=fzEl('div','fzvrow');
  r.append(fzEl('span','',fzZeit(x.t)),fzEl('span','',[mitSystem?x.system:'',x.admin,fzArt(x.art)].filter(Boolean).join(' · ')),fzEl('span','mut',x.min+' min · '+fzWoher(x.herkunft)));return r}
function fzVerlaufZeigen(sys){FZ.vsys=sys||'';$('fzverlaufmodal').style.display='grid';fzVerlauf()}
function fzVerlauf(){const d=FZ.d,list=$('fzverlauflist');if(!d||!list)return;list.textContent='';const s=FZ.vsys,v=(d.verlauf||[]).filter(x=>!s||x.system===s);
  $('fzvhead').textContent=t('Verlauf · ','History · ')+(s||t('alle Systeme','all systems'));
  $('fzverlaufh').textContent=t(`Die Sitzungen der letzten ${d.verlauf_tage||30} Tage: Zeit, System, Admin, Art, Dauer und von wo. Nie eine Adresse, nie was lief.`,`The sessions of the last ${d.verlauf_tage||30} days: time, system, admin, kind, duration and from where. Never an address, never what ran.`);
  if(!v.length){list.appendChild(fzEl('div','mut',t('Noch keine Sitzung.','No session yet.')));return}
  for(const x of v)list.appendChild(fzVerlaufZeile(x,!s))}
async function fzVerlaufWeg(){if(!confirm(t('Den ganzen Verlauf des Fernzugangs löschen?','Delete the whole remote access history?')))return;
  try{await api('/api/admin/fernzugang/verlauf',{method:'DELETE'});fzLoad()}catch(e){fzFehler(e)}}
function fzProtokoll(){const p=$('fzlog');if(!p)return;p.textContent='fernzugang: entsperrt | admin | 60\nfernzugang: anker_auf | ok | 1\nfernzugang: sitzung_auf | admin | 1\nfernzugang: sitzung_zu | leerlauf | 15\nfernzugang: hoch | ok | 2048\nfernzugang: koppeln_code | admin | 1'}
// ---------------------------------------------------------------- the terminal
function fzLaden(){if(window.Terminal)return Promise.resolve();
  return new Promise((ok,bad)=>{const l=document.createElement('link');l.rel='stylesheet';l.href='/static/xterm/xterm.css?v='+encodeURIComponent(SPARK_VER);document.head.appendChild(l);
    const s=document.createElement('script');s.src='/static/xterm/xterm.js?v='+encodeURIComponent(SPARK_VER);s.onload=()=>ok();s.onerror=()=>bad(new Error(t('xterm.js fehlt','xterm.js missing')));document.head.appendChild(s)})}
function fzGroesse(){const el=$('fzterm');const w=Math.max(320,el.clientWidth-16),h=Math.max(200,el.clientHeight-16);
  return [Math.max(20,Math.min(400,Math.floor(w/8.6))),Math.max(5,Math.min(200,Math.floor(h/17.5)))]}
async function fzOpen(g){if(FZ.ws||FZ.weg||FZ.fs||FZ.fb){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}
  try{await fzLaden()}catch(e){fzMsg(e.message,true);return}
  fzZeigen();const [cols,rows]=fzGroesse();let tk;
  try{const r=await api('/api/admin/fernzugang/sitzung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraet:g.id,cols,rows})});tk=(await r.json()).ticket}
  catch(e){fzZu(e.message);return}
  FZ.letzt=g;fzTerm(tk,{name:g.name,gid:g.id,art:g.art||'linux',seit:Date.now()/1000,max:FZ.d.max,leer:FZ.d.leerlauf},cols,rows)}
// the terminal for one ticket: a new session, or one this window takes over (its own window, or back into the tab)
function fzTerm(tk,sitz,cols,rows){
  const term=new window.Terminal({cursorBlink:true,fontSize:14,cols,rows,scrollback:2000,theme:{background:'#0b1020'}});
  $('fzterm').textContent='';term.open($('fzterm'));term.attachCustomKeyEventHandler(fzFang);term.focus();FZ.term=term;
  FZ.sitz=sitz;FZ.fp='';FZ.mess=null;FZ.lahm=0;FZ.lahmGesagt=false;fzBanner();fzInfo('');fzHilfeNeu();$('fztname').textContent=sitz.name;fzLayout();
  term.write(t('Verbinde mit ','Connecting to ')+sitz.name+' …\r\n');const enc=new TextEncoder();
  term.onData(x=>{const ws=FZ.ws;if(!ws||ws.readyState!==1)return;if(FZ.ctrl&&x.length===1){const c=x.toUpperCase().charCodeAt(0);if(c>=64&&c<96)x=String.fromCharCode(c-64);FZ.ctrl=false;fzKeys()}
    if(FZ.alt&&x.length===1){x='\x1b'+x;FZ.alt=false;fzKeys()}fzZeile(x);if(FZ.bald)fzBald(0);ws.send(enc.encode(x))});
  fzVerbinde(tk,term);window.addEventListener('resize',fzResize)}
// one WebSocket for the terminal (the first, or after a drop with a fresh ticket of the same login): the panel's
// heartbeat comes every 5 s (answered at once: its round trip and the rate are the panel's measurement, fzMess);
// nothing for 50 s counts as a dropped line
function fzVerbinde(tk,term){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/fernzugang/terminal?t='+encodeURIComponent(tk));
  ws.binaryType='arraybuffer';FZ.ws=ws;FZ.grund='';FZ.zuletzt=Date.now();clearInterval(FZ.pt);
  FZ.pt=setInterval(()=>{if(FZ.ws===ws&&ws.readyState===1&&Date.now()-FZ.zuletzt>50000)ws.close(4000)},5000);
  ws.onmessage=ev=>{FZ.zuletzt=Date.now();if(ev.data instanceof ArrayBuffer){term.write(new Uint8Array(ev.data),()=>{if(FZ.ziel)fzZielTick(false)});return}let m;try{m=JSON.parse(ev.data)}catch{return}
    if(m.typ==='stand'&&m.stand==='offen'){FZ.sid=m.id||'';FZ.wieder=null;fzWiederZeigen();if(FZ.nachher){const l=FZ.nachher;FZ.nachher='';setTimeout(()=>fzEinfuegen(l),400)}if(m.wieder)term.reset();fzResize();
      term.write('\x1b[2m'+(m.wieder?t('Wieder verbunden · ','Connected again · '):t('Verbunden · SSH · Host-Schlüssel ','Connected · SSH · host key ')+m.fp+t(' geprüft',' checked')+' ')+'\x1b[0m\r\n');FZ.fp=String(m.fp||'');fzInfo(FZ.fp);fzBanner()}
    if(m.typ==='bald')fzBald(Number(m.s)||0);
    if(m.typ==='puls'){if(Number.isInteger(m.t)&&m.t>0)ws.send(JSON.stringify({typ:'pong',t:m.t}));fzMess(m)}
    if(m.typ==='fehler'||m.typ==='zu')FZ.grund=m.grund;if(m.typ==='weg')FZ.grund='weg'};
  ws.onclose=()=>{if(FZ.ws!==ws)return;clearInterval(FZ.pt);if(FZ.grund==='weg'){fzWeg();return}
    if(!FZ.grund&&FZ.sid){fzWieder(term);return}if(FZ_FENSTER){window.close();return}fzZu(fzGrund(FZ.grund))}}
// the line dropped without a reason from the panel: the panel holds the shell (2 minutes); a fresh ticket of the same
// login (the page still unlocked) takes it again and the screen comes back; else „Verbindung verloren“
async function fzWieder(term){const sid=FZ.sid,bis=Date.now()+115000;FZ.wieder={sid};fzWiederZeigen();
  while(FZ.wieder&&FZ.wieder.sid===sid&&Date.now()<bis){
    try{const r=await api(`/api/admin/fernzugang/sitzung/${sid}/wieder`,{method:'POST'});const d=await r.json();if(!FZ.wieder)return;fzVerbinde(d.ticket,term);return}
    catch(e){if(e.status===404||e.status===423||e.status===503)break}
    await new Promise(ok=>setTimeout(ok,3000))}
  if(!FZ.wieder||FZ.wieder.sid!==sid)return;FZ.wieder=null;fzWiederZeigen();FZ.ws=null;if(FZ_FENSTER){window.close();return}fzZu(fzGrund('verloren'))}
function fzWiederZeigen(){const b=$('fzwieder');if(b){b.hidden=!FZ.wieder;fzTopLine()}}
// „Sitzung endet in m:ss“ (the panel says so BALD_S before the idle end): any key or „Weiterarbeiten“ counts
function fzBald(sek){clearInterval(FZ.baldt);FZ.bald=sek>0?Date.now()+sek*1000:0;const b=$('fzbald');if(!b)return;
  const tick=()=>{const rest=Math.max(0,Math.round((FZ.bald-Date.now())/1000));$('fzbaldtext').textContent=t('Sitzung endet in ','Session ends in ')+Math.floor(rest/60)+':'+String(rest%60).padStart(2,'0')};
  b.hidden=!FZ.bald;fzTopLine();if(FZ.bald){tick();FZ.baldt=setInterval(tick,1000)}}
function fzWeiter(){if(FZ.ws&&FZ.ws.readyState===1)FZ.ws.send(JSON.stringify({typ:'weiter'}));fzBald(0);if(FZ.term)FZ.term.focus()}
// the page's unlock: 2 minutes before its end the line says so, with „Verlängern“ (a fresh code or passkey)
function fzSperreBald(){clearInterval(FZ.sbt);const b=$('fzsperrbald');if(!b)return;const bis=FZ.d&&!FZ.d.gesperrt&&FZ.d.entsperrt_bis;
  const tick=()=>{const rest=bis?Math.round(bis-Date.now()/1000):0;const an=rest>0&&rest<=120;b.hidden=!an;fzTopLine();
    if(an)$('fzsperrtext').textContent=t('Entsperrung endet in ','Unlock ends in ')+Math.floor(rest/60)+':'+String(rest%60).padStart(2,'0')};
  tick();if(bis)FZ.sbt=setInterval(tick,1000)}
const FZ_GRUND={leerlauf:['Leerlauf: die Sitzung ist zu.','Idle: the session is closed.'],notaus:['Notaus: alle Sitzungen sind zu.','Emergency stop: every session is closed.'],
  hostkey:['Der Host-Schlüssel passt nicht zur Kopplung: keine Verbindung.','The host key does not match the pairing: no connection.'],ssh:['SSH-Anmeldung ging nicht (Benutzer spark, Schlüssel des Panels).','SSH sign-in failed (user spark, the panel key).'],
  zu_gross:['Zu viel auf einmal eingefügt (höchstens 64 KB).','Too much pasted at once (64 KB at most).'],sshd:['Auf dem Server hört kein sshd auf 127.0.0.1:22.','No sshd listens on 127.0.0.1:22 on the server.'],
  anker:['Der Anker hat nicht geantwortet.','The anchor did not answer.'],server:['Der Server hat die Sitzung beendet.','The server ended the session.'],getrennt:['Getrennt.','Disconnected.'],alle:['Alle getrennt.','All disconnected.'],
  verloren:['Verbindung verloren: die Sitzung ist zu.','Connection lost: the session is closed.'],shell:['Die Shell auf dem Server ist zu Ende.','The shell on the server has ended.'],
  browser:['Das Fenster wurde geschlossen.','The window was closed.'],aus:['Der Fernzugang wurde ausgeschaltet.','Remote access was switched off.'],abmelden:['Abgemeldet: die Sitzung ist zu.','Signed out: the session is closed.']};
function fzGrund(g){return g&&FZ_GRUND[g]?t(...FZ_GRUND[g]):t('Sitzung beendet.','Session ended.')}
function fzResize(){if(!FZ.term||!FZ.ws||FZ.ws.readyState!==1)return;const [c,r]=fzGroesse();if(c===FZ.term.cols&&r===FZ.term.rows)return;FZ.term.resize(c,r);FZ.ws.send(JSON.stringify({typ:'groesse',cols:c,rows:r}))}
function fzTopBar(){let top=0;for(const h of [document.querySelector('header'),$('apbar')]){if(!h)continue;const cs=getComputedStyle(h);
    if((cs.position==='sticky'||cs.position==='fixed')&&cs.display!=='none'&&h.offsetWidth>=document.documentElement.clientWidth-4)top=Math.max(top,h.offsetHeight)}return top}
addEventListener('resize',()=>{if(FZ.sitz)fzBanner()});
// the bars change with the page (the app view's bar comes and goes): the line follows them
if(window.ResizeObserver){const ro=new ResizeObserver(()=>{const b=$('fztop');if(b&&!b.hidden)b.style.setProperty('--fzbtop',fzTopBar()+'px')});
  for(const h of [document.querySelector('header'),$('apbar')])if(h)ro.observe(h)}
// the slim lines at the top of the content (a remote session, a Spontanhilfe): below the bar that stays on top (the
// header, or the app view's bar on a phone); one place for both, the second line under the first
function fzTopLine(){const top=$('fztop');top.hidden=['fzbanner','shbanner','fzwieder','fzbald','fzsperrbald'].every(id=>!$(id)||$(id).hidden);if(!top.hidden)top.style.setProperty('--fzbtop',fzTopBar()+'px')}
function fzBanner(){const b=$('fzbanner');if(!FZ.sitz){b.hidden=true;document.body.classList.remove('fzaktiv');fzInfoPop(false);fzTopLine();return}b.hidden=false;document.body.classList.add('fzaktiv');fzTopLine();
  $('fzbtext').textContent=$('fzvolltext').textContent=(FZ.sitz.art==='dateien'?t('Fern-Dateien offen · ','Remote files open · '):FZ.sitz.art==='bildschirm'?t('Fern-Bildschirm offen · ','Remote screen open · '):t('Fernsitzung aktiv · ','Remote session active · '))+FZ.sitz.name+' · '+fzMin(FZ.sitz.seit);b.title=t('Notaus trennt sofort','The emergency stop ends it at once');
  $('fzbleer').textContent=FZ.sitz.leer?' · '+t('Leerlauf trennt nach ','idle ends after ')+FZ.sitz.leer+' min':'';$('fzbinfo').hidden=!FZ.ws;
  clearTimeout(FZ.bt);FZ.bt=setTimeout(fzBanner,30000)}
// the line as the panel measured it (numbers only): the round trip quietly in the red line, round trip and rate in
// „Diese Sitzung“; output that had to wait at a low rate twice in a row: one hint per session to the direct https way
function fzMess(m){const rtt=Number.isInteger(m.rtt_ms)?m.rtt_ms:null,kb=Number.isInteger(m.kb_s)?m.kb_s:0;FZ.mess={rtt,kb,stau:!!m.stau};
  const e=$('fzbmess');if(e)e.textContent=rtt===null?'':' · '+rtt+' ms';
  if(m.stau)FZ.lahm=kb<(Number(m.langsam)||100)?(FZ.lahm||0)+1:0;
  if(FZ.lahm>=2&&!FZ.lahmGesagt){FZ.lahmGesagt=true;sayToast(t(`Langsame Verbindung (etwa ${kb} KB/s). Über den Proxy der Synology kommen nur etwa 50 bis 70 KB/s an; der direkte https-Zugang ist deutlich schneller, besonders für Bildschirm und große Dateien.`,`Slow connection (about ${kb} KB/s). Through the Synology proxy only about 50 to 70 KB/s arrive; the direct https access is much faster, above all for the screen and big files.`),12000,{})}
  if($('fzinfopop')&&!$('fzinfopop').hidden)fzInfo(FZ.fp)}
// „Diese Sitzung“ behind the ⓘ (red line and terminal bar): the host key shortened, whole on hover and „kopieren“
function fzKurz(fp){fp=String(fp||'');const i=fp.indexOf(':')+1;return fp.length>i+12?fp.slice(0,i+4)+'…'+fp.slice(-6):fp}
function fzInfo(fp){const dl=$('fzinfo');dl.textContent='';const s=FZ.sitz||{},c=(FZ.d&&FZ.d.counts)||{};
  const os={linux:'Linux',macos:'macOS',windows:'Windows'}[s.art]||'';
  for(const [k,v] of [[t('System','System'),[s.name||'',os].filter(Boolean).join(' · ')],[t('Host-Schlüssel','Host key'),fp||'…'],[t('Anmeldung','Sign-in'),t('frischer Code oder Passkey','fresh code or passkey')],
    [t('Sitzungen','Sessions'),s.max?(c.sitzungen||1)+t(' von höchstens ',' of at most ')+s.max:'–'],
    [t('Verbindung','Connection'),FZ.mess&&FZ.mess.rtt!==null?FZ.mess.rtt+' ms'+(FZ.mess.kb?' · '+FZ.mess.kb+' KB/s':''):t('wird gemessen …','being measured …')],[t('Aufgezeichnet','Recorded'),t('nichts (nur Wörter und Zahlen im Log)','nothing (only words and numbers in the log)')]]){
    const dd=fzEl('dd','',v);if(v===fp&&fp){dd.textContent=fzKurz(fp)+' ';dd.title=fp;dd.dataset.voll=fp;dd.appendChild(fzEl('span','fzok','✓ '+t('geprüft','checked')))}dl.append(fzEl('dt','',k),dd)}
  $('fztkey').hidden=!fp;$('fztkey').title=fp||'';$('fzkeycopy').disabled=!fp}
function fzInfoPop(open,btn){const p=$('fzinfopop');if(!p)return;open=open===undefined?p.hidden:!!open;
  if(open&&!FZ.ws)open=false;p.hidden=!open;for(const id of ['fzbinfo','fzinfobtn'])$(id).setAttribute('aria-expanded',open&&btn===$(id)?'true':'false');
  if(!open)return;fzInfo(FZ.fp);const r=(btn||$('fzbinfo')).getBoundingClientRect(),w=p.offsetWidth;
  p.style.top=Math.round(r.bottom+6)+'px';p.style.left=Math.round(Math.max(8,Math.min(innerWidth-w-8,r.left-20)))+'px'}
document.addEventListener('click',e=>{const p=$('fzinfopop');if(p&&!p.hidden&&!p.contains(e.target)&&!e.target.closest('#fzbinfo,#fzinfobtn'))fzInfoPop(false)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('fzinfopop')&&!$('fzinfopop').hidden)fzInfoPop(false)});
// the chips after the person's own last command line (FZ.zeile: only that line, only in this page, never the output,
// never sent anywhere): fernzugang.FOLGE's fixed rules, {1} = the own first argument, shell-quoted; else the fixed CHIPS
function fzQuote(a){return /^[A-Za-z0-9@%_+=:,.\/-]+$/.test(a)?a:"'"+a.replace(/'/g,"'\\''")+"'"}
function fzFolge(line){const w=String(line||'').trim().split(/\s+/).filter(Boolean);if(w[0]==='sudo')w.shift();
  for(const [words,next] of (FZ.d&&FZ.d.folge)||[]){if(!Array.isArray(words)||!Array.isArray(next)||words.length>w.length||!words.every((x,i)=>x===w[i]))continue;
    const arg=w[words.length];const out=next.filter(c=>typeof c==='string'&&(!c.includes('{1}')||arg)).map(c=>({c:c.split('{1}').join(arg?fzQuote(arg):''),r:c}));
    if(out.length)return out.slice(0,4)}
  return null}
function fzZeile(x){if(x==='\r'){FZ.zeile=FZ.buf||'';FZ.buf='';FZ.ki=null;fzMerke(FZ.zeile);fzChips();fzVorschlagPlan();fzZielTick(true);return}
  if(x==='\x7f'){FZ.buf=(FZ.buf||'').slice(0,-1);return}
  if(/[\x00-\x1f]/.test(x)){if(x.endsWith('\r')&&!/[\x00-\x0c\x0e-\x1f]/.test(x)){FZ.buf=(FZ.buf||'')+x.slice(0,-1);fzZeile('\r')}else FZ.buf='';return}
  FZ.buf=((FZ.buf||'')+x).slice(-500)}
// a fixed line after the own command (fernzugang.HINWEIS: how to leave screen or tmux without ending it there)
function fzHinweis(line){const w=String(line||'').trim().split(/\s+/).filter(Boolean);if(w[0]==='sudo')w.shift();
  for(const [words,x] of (FZ.d&&FZ.d.hinweis)||[]){if(Array.isArray(words)&&Array.isArray(x)&&words.length<=w.length&&words.every((y,i)=>y===w[i]))return t(String(x[0]),String(x[1]))}return ''}
function fzChips(){const w=$('fzchips');w.textContent='';const ki=Array.isArray(FZ.ki)&&FZ.ki.length?FZ.ki:null,f=ki||fzFolge(FZ.zeile),was=$('fzchipwas');
  const hw=$('fzchiphint');if(hw){const h=fzHinweis(FZ.zeile);hw.hidden=!h;hw.textContent=h}
  was.hidden=!f;was.textContent=ki?t('✦ Assistent:','✦ assistant:'):t('passend:','fitting:');was.title=ki?t('Vorschläge des Assistenten','The assistant\'s suggestions'):t('Passend zu deinem letzten Befehl','Fitting your last command');
  const gr=ki&&Array.isArray(FZ.kig)?FZ.kig:[];
  (f||(FZ.d&&FZ.d.chips)||[]).forEach((x,i)=>{const c=typeof x==='string'?x:x.c,r=typeof x==='string'?x:x.r;
    const b=fzChip(c,ki?(gr[i]?t('Vorschlag des Assistenten: ','Suggested by the assistant: ')+gr[i]:t('Vom Assistenten vorgeschlagen','Suggested by the assistant')):fzErklaert(r));if(ki){b.prepend(fzEl('span','fzstern','✦'));b.classList.add('fzki')}w.appendChild(b)});fzRand()}
// what a fixed chip does (fernzugang.ERKLAERT, one source with the chips), by the command as it stands in the rule
function fzErklaert(r){const e=FZ.d&&FZ.d.erklaert&&FZ.d.erklaert[r];return Array.isArray(e)?t(String(e[0]),String(e[1])):''}
// the chip's tooltip: on hover and focus at once (not the browser's slow title), on touch after a long press; text only
function fzTipZeig(b){const tip=$('fztip'),x=b&&b.dataset.tip;if(!tip)return;if(!x){tip.hidden=true;return}tip.textContent=x;tip.hidden=false;
  const r=b.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;let top=r.top-h-6;if(top<4)top=r.bottom+6;
  tip.style.top=Math.round(top)+'px';tip.style.left=Math.round(Math.max(4,Math.min(innerWidth-w-4,r.left+r.width/2-w/2)))+'px'}
function fzTipWeg(){const tip=$('fztip');if(tip)tip.hidden=true}
function fzTipAn(b){b.addEventListener('mouseenter',()=>fzTipZeig(b));b.addEventListener('mouseleave',fzTipWeg);b.addEventListener('focus',()=>fzTipZeig(b));b.addEventListener('blur',fzTipWeg);
  b.addEventListener('touchstart',()=>{clearTimeout(b._lp);b._lp=setTimeout(()=>{b._lang=true;fzTipZeig(b)},500)},{passive:true});
  b.addEventListener('touchend',e=>{clearTimeout(b._lp);if(b._lang){b._lang=false;e.preventDefault();setTimeout(fzTipWeg,1800)}});b.addEventListener('touchmove',()=>clearTimeout(b._lp),{passive:true})}
// the chip row scrolls sideways: soft edges show that more is there
function fzRand(){const w=$('fzchips');if(!w)return;const l=w.scrollLeft>2,r=w.scrollLeft+w.clientWidth<w.scrollWidth-2;w.classList.toggle('fzlinks',l);w.classList.toggle('fzrechts',r)}
// the fixed rules of this kind of system (fernzugang.GEFAHR): the first one a command matches, else null
function fzGefahr(c){const g=(FZ.d&&FZ.d.gefahr)||{},rules=g[(FZ.sitz&&FZ.sitz.art)||'linux']||g.linux||[];
  for(const [rx,de,en] of rules){try{if(new RegExp(rx,'i').test(c))return t(de,en)}catch{}}return null}
// one command to insert: only into the line, never with Enter (one line only); a dangerous one needs a second tap
function fzChip(c,was){c=String(c).replace(/[\r\n]+/g,' ').trim();const b=fzEl('button','fzchip');b.type='button';const g=fzGefahr(c),sm=fzEl('small','',t('Einfügen','Insert'));
  const code=fzEl('code','',c),tip=[was||''];if(g){b.classList.add('fzgefahr');b.append(fzEl('span','fzvorsicht',t('Vorsicht','Caution')));tip.push(t('Vorsicht: ','Caution: ')+g)}
  else if(/^sudo\s/.test(c)){b.append(fzEl('span','fzinfo',t('braucht sudo','needs sudo')));const s=FZ.d&&FZ.d.sudo_tip;if(Array.isArray(s))tip.push(t(String(s[0]),String(s[1])))}
  if(/<[^<>]+>/.test(c))tip.push(t('<…> trägst du selbst ein: der Cursor wartet dort.','You fill in <…>: the cursor waits there.'));b.append(code,sm);
  const x=tip.filter(Boolean).join(' · ');if(x){b.dataset.tip=x;b.setAttribute('aria-description',x)}fzTipAn(b);
  b.onclick=()=>{if(g&&!b.classList.contains('scharf')){b.classList.add('scharf');sm.textContent=t('Wirklich einfügen?','Really insert?');
      clearTimeout(b._t);b._t=setTimeout(()=>{b.classList.remove('scharf');sm.textContent=t('Einfügen','Insert')},4000);return}
    b.classList.remove('scharf');sm.textContent=t('Einfügen','Insert');fzEinfuegen(c)};return b}
// into the line only, never Enter; a gap <…> is left out and the cursor goes back to the first one (arrow keys)
function fzEinfuegen(c){if(!FZ.term)return;if(NARROW())fzBlatt(false);const i=c.search(/<[^<>]+>/),s=c.replace(/<[^<>]+>/g,'');FZ.term.paste(s);
  if(i>=0&&FZ.ws&&FZ.ws.readyState===1){const back=s.length-i;if(back>0)FZ.ws.send(new TextEncoder().encode('\x1b[D'.repeat(back)))}FZ.term.focus()}
// the assistant: only while the switch is on; the commands only kept for it (the last hilfe_befehle, in this page)
function fzHilfeNeu(){FZ.hist=[];FZ.ki=null;clearTimeout(FZ.vt);fzZielEnde('');const h=$('fzhilfe');if(!h)return;fzSeiteWahl(FZ.seite);$('fzview').classList.toggle('fzki',!!(FZ.d&&FZ.d.hilfe)||!$('fznotizseite').hidden);
  $('fzschirm').checked=false;$('fzantwort').textContent='';$('fzfrage').value='';$('fzgekuerzt').hidden=true;
  const sel=$('fzzeilen'),d=FZ.d||{},n=Number(d.ki_zeilen)||80;sel.textContent='';
  for(const z of [...new Set([...(d.ki_zeilen_wahl||[80,300,1000]),n])].sort((a,b)=>a-b)){const o=fzEl('option','',String(z));o.value=String(z);sel.appendChild(o)}sel.value=String(n)}
function fzMerke(line){if(!(FZ.d&&FZ.d.hilfe)||!line.trim())return;FZ.hist.push(line.slice(0,300));FZ.hist=FZ.hist.slice(-((FZ.d&&FZ.d.hilfe_befehle)||10))}
// the visible screen, only with „Bildschirm mitschicken“: the last lines as chosen in the drawer (ki_zeilen), at most
// ki_zeichen characters, the newest kept; cut, the drawer says „gekürzt“
function fzSchirm(){FZ.gek=false;if(!$('fzschirm').checked||!FZ.term)return '';const b=FZ.term.buffer.active,n=Number($('fzzeilen').value)||(FZ.d&&FZ.d.ki_zeilen)||80,out=[];
  for(let i=Math.max(0,b.length-n);i<b.length;i++){const l=b.getLine(i);out.push(l?l.translateToString(true):'')}
  let s=out.join('\n').replace(/\s+$/,'');const max=(FZ.d&&FZ.d.ki_zeichen)||60000;if(s.length>max){s=s.slice(-max);FZ.gek=true}return s}
async function fzHilfe(art,body,signal){const r=await api('/api/admin/fernzugang/hilfe'+(art!=='frage'?'?art='+art:''),{method:'POST',headers:{'Content-Type':'application/json'},signal,
  body:JSON.stringify({sitzung:FZ.sid,befehle:FZ.hist,bildschirm:fzSchirm(),...body})});const d=await r.json();$('fzgekuerzt').hidden=!(FZ.gek||d.gekuerzt);return d}
// „Ziel“ (Dominik 2026-10-29 08:38): the question pinned as a goal; after each own command (the prompt back or 1.5 s
// quiet) the screen goes to the own model again, only with „Bildschirm mitschicken“, and one chip with its reason comes
// back. Never Enter; a dangerous one stays red with its second tap. One request at a time (a new one cancels the old),
// the same screen not twice, at most ziel_min a minute; „Fertig“ or „Ziel beenden“ end it.
function fzZielStart(){const q=$('fzfrage').value.trim();if(!q||!FZ.sid)return;if(!$('fzschirm').checked){$('fzzielstand').textContent='';fzMsg(t('Das Ziel braucht „Bildschirm mitschicken“.','The goal needs "Send the screen along".'),true);$('fzschirm').focus();return}
  fzZielEnde('');FZ.ziel={text:q,last:'',zeiten:[],ctl:null,t:null,wartet:true};$('fzfrage').value='';$('fzfrage').focus();$('fzziel').hidden=false;$('fzzieltext').textContent=q;
  $('fzzielchip').textContent='';fzZielStand(t('Schaut auf den Bildschirm …','Looking at the screen …'));fzZielSchritt()}
function fzZielStand(x){$('fzzielstand').textContent=x}
function fzZielEnde(x){const z=FZ.ziel;FZ.ziel=null;if(z){clearTimeout(z.t);if(z.ctl)z.ctl.abort()}const b=$('fzziel');if(!b)return;
  if(x){fzZielStand(x);$('fzzielchip').textContent=''}else b.hidden=true}
// called on every piece of output and after Enter: a command counts as ended with the prompt back or 1.5 s quiet
function fzZielTick(enter){const z=FZ.ziel;if(!z)return;if(enter)z.wartet=true;if(!z.wartet)return;clearTimeout(z.t);
  let prompt=false;try{const b=FZ.term.buffer.active,l=b.getLine(b.baseY+b.cursorY);prompt=/[$#%>]\s*$/.test(l?l.translateToString(true):'')}catch{}
  z.t=setTimeout(fzZielSchritt,prompt&&!enter?300:1500)}
async function fzZielSchritt(){const z=FZ.ziel;if(!z||!FZ.sid)return;if(!$('fzschirm').checked){fzZielEnde(t('Ziel angehalten: „Bildschirm mitschicken“ ist aus.','Goal paused: "Send the screen along" is off.'));return}
  const scr=fzSchirm();if(!scr||scr===z.last)return;
  const now=Date.now();z.zeiten=z.zeiten.filter(x=>now-x<60000);const most=(FZ.d&&FZ.d.ziel_min)||6;
  if(z.zeiten.length>=most){clearTimeout(z.t);z.t=setTimeout(fzZielSchritt,60000-(now-z.zeiten[0])+50);fzZielStand(t('Wartet kurz (höchstens ','Waiting a moment (at most ')+most+t(' Schritte je Minute) …',' steps a minute) …'));return}
  z.wartet=false;z.last=scr;z.zeiten.push(now);if(z.ctl)z.ctl.abort();const ctl=new AbortController();z.ctl=ctl;fzZielStand(t('Der Assistent denkt …','The assistant is thinking …'));
  let d;try{d=await fzHilfe('ziel',{ziel:z.text},ctl.signal)}catch(e){if(FZ.ziel===z&&!ctl.signal.aborted&&e.status!==409)fzZielStand(e.message);return}finally{if(z.ctl===ctl)z.ctl=null}
  if(FZ.ziel!==z||d.unveraendert)return;const box=$('fzzielchip');box.textContent='';
  if(d.fertig){fzZielEnde(t('Fertig: ','Done: ')+(d.grund||t('das Ziel ist erreicht.','the goal is reached.')));$('fzziel').hidden=false;return}
  if(d.unlesbar||typeof d.befehl!=='string'||!d.befehl||d.befehl.length>200||/[\x00-\x1f]/.test(d.befehl)){fzZielStand(t('Die Antwort war nicht lesbar; nach dem nächsten Befehl noch einmal.','The answer was not readable; again after the next command.'));return}
  box.appendChild(fzChip(d.befehl,String(d.grund||t('Vom Assistenten vorgeschlagen','Suggested by the assistant')).slice(0,120)));if(d.grund)box.appendChild(fzEl('div','fzzielgrund',String(d.grund).slice(0,120)));fzZielStand(t('Nächster Schritt:','Next step:'))}
// the field empties as soon as the question is sent and keeps the focus (Dominik 2026-10-29 08:35)
async function fzFragen(){const f=$('fzfrage'),q=f.value.trim(),a=$('fzantwort');if(!q||!FZ.sid)return;f.value='';f.focus();a.textContent=t('Der Assistent denkt …','The assistant is thinking …');
  try{const d=await fzHilfe('frage',{frage:q});fzAntwort(String(d.antwort||''))}catch(e){a.textContent=e.message}}
// the answer as text, each line of a code block with its own „Einfügen“ (never Enter, never sent by itself)
function fzAntwort(text){const a=$('fzantwort');a.textContent='';const rx=/```[A-Za-z0-9_-]*\n?([\s\S]*?)```/g;let last=0,m;
  const add=s=>{if(s.trim())a.appendChild(fzEl('div','',s.trim()))};
  while((m=rx.exec(text))){add(text.slice(last,m.index));a.appendChild(fzEl('pre','',m[1].replace(/\s+$/,'')));
    for(const l of m[1].split('\n'))if(l.trim())a.appendChild(fzChip(l));last=rx.lastIndex}
  add(text.slice(last))}
// suggestions after Enter: only with the assistant in sight (column, drawer or sheet open), at most one request in vorschlag_s seconds; anything but a clean
// list keeps the fixed-rule chips
function fzVorschlagPlan(){clearTimeout(FZ.vt);if(!(FZ.d&&FZ.d.hilfe)||!fzSpalteOffen()||!FZ.sid||!FZ.hist.length)return;
  const gap=((FZ.d.vorschlag_s||5)*1000)-(Date.now()-FZ.vlast);FZ.vt=setTimeout(fzVorschlag,Math.max(1200,gap))}
async function fzVorschlag(){if(!fzSpalteOffen()||!FZ.ws)return;FZ.vlast=Date.now();
  try{const d=await fzHilfe('vorschlag',{});const v=d.vorschlaege;
    if(Array.isArray(v)&&v.length>=2&&v.length<=4&&v.every(x=>typeof x==='string'&&x.length<=200&&!/[\x00-\x1f]/.test(x))){
      const g=Array.isArray(d.gruende)?d.gruende:[];FZ.kig=v.map((_,i)=>typeof g[i]==='string'&&g[i].length<=120&&!/[\x00-\x1f]/.test(g[i])?g[i]:'');FZ.ki=v;fzChips()}}catch{}}
const FZ_KEYS=[['Esc','\x1b'],['Tab','\t'],['Strg',''],['Alt',''],['←','\x1b[D'],['↑','\x1b[A'],['↓','\x1b[B'],['→','\x1b[C'],['⏎','\r'],
  ['F1','\x1bOP'],['F2','\x1bOQ'],['F3','\x1bOR'],['F4','\x1bOS'],['F5','\x1b[15~'],['F6','\x1b[17~'],['F7','\x1b[18~'],['F8','\x1b[19~'],
  ['F9','\x1b[20~'],['F10','\x1b[21~'],['F11','\x1b[23~'],['F12','\x1b[24~']];
function fzKeys(){const w=$('fzkeys');w.textContent='';for(const [l,seq] of FZ_KEYS){const b=fzEl('button','b'+((l==='Strg'&&FZ.ctrl)||(l==='Alt'&&FZ.alt)?' on':''),l==='Strg'?t('Strg','Ctrl'):l);b.type='button';
  b.onclick=()=>{if(l==='Strg'){FZ.ctrl=!FZ.ctrl;fzKeys();FZ.term&&FZ.term.focus();return}if(l==='Alt'){FZ.alt=!FZ.alt;fzKeys();FZ.term&&FZ.term.focus();return}
    if(FZ.ws&&FZ.ws.readyState===1)FZ.ws.send(new TextEncoder().encode(seq));FZ.term&&FZ.term.focus()};w.appendChild(b)}}
// the browser's own shortcuts the page may take stay in the shell: F1–F12, Tab, Alt and Strg combinations (not Strg+C
// with a selection, Strg+V and Strg+Shift+C/V: copy and paste); xterm then sends the key on as usual
function fzFang(e){if(e.type!=='keydown')return true;const k=(e.key||'').toLowerCase();
  if(fzLadeTaste(e))return false;   // the page's own: the drawer (document listener below), never to the shell
  const copy=(e.ctrlKey&&e.shiftKey&&(k==='c'||k==='v'))||(e.ctrlKey&&!e.shiftKey&&k==='v')||(e.ctrlKey&&k==='c'&&FZ.term&&FZ.term.hasSelection());
  if(!copy&&(/^f([1-9]|1[0-2])$/.test(k)||k==='tab'||e.altKey||e.ctrlKey))e.preventDefault();return true}
// „Alle Tasten“: full screen plus the Keyboard Lock API (Chromium); elsewhere a hint, the normal capture stays
// (fzLayout first: with a page scroll bar the full screen would keep its width free)
async function fzAlleTasten(){const kb=navigator.keyboard;
  if(!kb||typeof kb.lock!=='function'){fzMsg(t('Alle Tasten nur in Chrome oder Edge; sonst das Panel als App installieren. Die üblichen Tastenkürzel gehen auch so an die Shell.','All keys only in Chrome or Edge; otherwise install the panel as an app. The usual shortcuts go to the shell anyway.'),true);return}
  try{if(!document.fullscreenElement){fzLayout();document.documentElement.classList.add('fzvoll');await $('fzview').requestFullscreen()}await kb.lock();
    fzMsg(t('Alle Tasten gehen an die Shell. Zum Verlassen Esc 2 Sekunden halten.','All keys go to the shell. To leave, hold Esc for 2 seconds.'));
    const h=$('fzvollhint');h.hidden=false;clearTimeout(FZ.ht);FZ.ht=setTimeout(()=>{h.hidden=true},3000);FZ.term&&FZ.term.focus()}catch(e){if(!document.fullscreenElement)document.documentElement.classList.remove('fzvoll');fzMsg(e.message,true)}}
// full screen holds the terminal (all of it) and a drawer from the right with the chips and the assistant, closed at
// first: the edge tab or Strg+Umschalt+Leertaste (the page's own, even under Keyboard Lock); the terminal refits
function fzLadeTaste(e){return e.type==='keydown'&&e.ctrlKey&&e.shiftKey&&!e.altKey&&(e.code==='Space'||e.key===' ')}
function fzLade(open){const v=$('fzview');if(!v.classList.contains('fzki'))return;open=open===undefined?!v.classList.contains('fzlade'):!!open;v.classList.toggle('fzlade',open);
  $('fzdrawertab').setAttribute('aria-expanded',open?'true':'false');requestAnimationFrame(()=>{fzResize();if(!open&&FZ.term)FZ.term.focus()})}
document.addEventListener('keydown',e=>{if(!fzLadeTaste(e)||$('fzview').hidden)return;e.preventDefault();e.stopPropagation();fzLade()},true);
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement){if(navigator.keyboard&&typeof navigator.keyboard.unlock==='function')navigator.keyboard.unlock();
    $('fzview').classList.remove('fzlade');$('fzvollhint').hidden=true;document.documentElement.classList.remove('fzvoll');fzLayout()}
  requestAnimationFrame(()=>fzResize())});
// „Herauslösen“: the panel page in its own window; it asks here for its own ticket (fz-bereit), this tab shows „läuft im
// eigenen Fenster“ once the server moved the session (weg)
function fzHeraus(){if(!FZ.ws||!FZ.sid||!FZ.sitz)return;const w=window.open('/#fernfenster','fz'+FZ.sid,'popup,width=1100,height=720');
  if(!w){fzMsg(t('Der Browser hat das Fenster blockiert: Pop-ups für das Panel erlauben.','The browser blocked the window: allow pop-ups for the panel.'),true);return}
  FZ.pop={w,sid:FZ.sid,sitz:FZ.sitz}}
async function fzFensterTicket(sid,fenster){const r=await api(`/api/admin/fernzugang/sitzung/${sid}/fenster`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fenster})});return (await r.json()).ticket}
addEventListener('message',async e=>{if(e.origin!==location.origin||!e.data||typeof e.data!=='object')return;
  if(e.data.typ==='fz-bereit'&&FZ.pop&&e.source===FZ.pop.w){const p=FZ.pop;let tk;try{tk=await fzFensterTicket(p.sid,true)}catch(x){fzMsg(x.message,true);return}
    const mit={};for(const k of FZ_MIT)mit[k]=FZ.d?FZ.d[k]:undefined;p.w.postMessage({typ:'fz-ticket',ticket:tk,sitz:p.sitz,mit},location.origin)}
  else if(e.data.typ==='fz-ticket'&&FZ_FENSTER&&e.source===window.opener&&!FZ.ws&&typeof e.data.ticket==='string'){
    const mit=e.data.mit||{};FZ.d={chips:Array.isArray(mit.chips)?mit.chips.filter(x=>typeof x==='string'):[],folge:Array.isArray(mit.folge)?mit.folge:[],
      erklaert:mit.erklaert&&typeof mit.erklaert==='object'?mit.erklaert:{},sudo_tip:Array.isArray(mit.sudo_tip)?mit.sudo_tip:[],hinweis:Array.isArray(mit.hinweis)?mit.hinweis:[],hilfe:mit.hilfe===true,
      gefahr:mit.gefahr&&typeof mit.gefahr==='object'?mit.gefahr:{},ki_zeilen:Number(mit.ki_zeilen)||80,ki_zeilen_wahl:Array.isArray(mit.ki_zeilen_wahl)?mit.ki_zeilen_wahl.map(Number).filter(n=>n>=20&&n<=1000):[80,300,1000],ki_zeichen:Number(mit.ki_zeichen)||60000,ziel_min:Number(mit.ziel_min)||6,hilfe_befehle:Number(mit.hilfe_befehle)||10,vorschlag_s:Number(mit.vorschlag_s)||5};const sitz=e.data.sitz||{};
    try{await fzLaden()}catch(x){fzMsg(x.message,true);return}
    document.title=String(sitz.name||'')+' · '+t('Fernzugang','Remote access');fzChips();const [c,r]=fzGroesse();
    fzTerm(e.data.ticket,{name:String(sitz.name||''),gid:String(sitz.gid||''),art:['windows','macos'].includes(sitz.art)?sitz.art:'linux',seit:Number(sitz.seit)||Date.now()/1000,max:Number(sitz.max)||1,leer:Number(sitz.leer)||15},c,r)}});
function fzWeg(){const ws=FZ.ws,sitz=FZ.sitz;FZ.ws=null;FZ.grund='';FZ.zeile=FZ.buf='';FZ.hist=[];FZ.ki=null;clearTimeout(FZ.vt);fzZielEnde('');if(FZ.term){FZ.term.dispose();FZ.term=null}window.removeEventListener('resize',fzResize);clearInterval(FZ.pt);fzBald(0);
  if(FZ_FENSTER){window.close();return}
  FZ.weg={sid:FZ.sid,sitz};FZ.sitz=sitz;fzBanner();$('fzview').hidden=true;fzVerbergen();fzWegZeigen();if(ws&&ws.readyState<2)ws.close(1000)}
function fzWegZeigen(){const b=$('fzweg');if(!b)return;b.hidden=!FZ.weg;if(FZ.weg)$('fzwegname').textContent=FZ.weg.sitz?FZ.weg.sitz.name:'';if(!FZ.weg&&FZ.d)fzShow()}
async function fzZurueck(){const w=FZ.weg;if(!w)return;let tk;try{await fzLaden();tk=await fzFensterTicket(w.sid,false)}catch(e){fzMsg(e.message,true);return}
  FZ.weg=null;fzWegZeigen();fzZeigen();const [c,r]=fzGroesse();fzTerm(tk,w.sitz,c,r)}
async function fzWegTrennen(){const w=FZ.weg,p=FZ.pop;if(p&&p.w&&!p.w.closed){p.w.close();return}
  if(w&&w.sid){try{await api(`/api/admin/fernzugang/sitzung/${w.sid}/trennen`,{method:'POST'})}catch(e){fzMsg(e.message,true)}}FZ.weg=null;FZ.sitz=null;fzBanner();fzWegZeigen();fzLoad()}
function fzTrennen(){if(FZ.ws){const ws=FZ.ws;FZ.grund='getrennt';if(ws.readyState===1)ws.send(JSON.stringify({typ:'ende'}));ws.close(1000)}else if(FZ.wieder){FZ.wieder=null;fzWiederZeigen();fzZu(fzGrund('getrennt'))}else if(FZ.weg)fzWegTrennen();else if(FZ.fs)fzFSchliessen();else if(FZ.fb)fbTrennen()}
function fzZu(text){fzNotizSpeichern();const ws=FZ.ws;FZ.ws=null;FZ.nachher='';FZ.grund='';FZ.zeile=FZ.buf='';FZ.hist=[];FZ.ki=null;FZ.wieder=null;fzWiederZeigen();fzBald(0);clearTimeout(FZ.vt);fzZielEnde('');clearInterval(FZ.pt);if(ws&&ws.readyState<2)ws.close(1000);if(FZ.term){FZ.term.dispose();FZ.term=null}FZ.sitz=null;fzBanner();
  window.removeEventListener('resize',fzResize);$('fzview').hidden=true;$('fzmain').hidden=false;fzVerbergen();if(text)fzNeuKnopf(text);fzLoad()}
// every end message offers „Neu verbinden“ to the system it was (a new session, a new code only if the page is locked)
function fzNeuKnopf(text){const g=FZ.letzt;sayToast(text,20000,{bad:true,knopf:g?[t('Neu verbinden','Connect again'),()=>fzOpen(g)]:null,id:'fzwiederneu'})}
async function fzAlle(){if(!confirm(t('Jede Sitzung und jeden Anker jetzt trennen?','Disconnect every session and anchor now?')))return;
  try{const r=await api('/api/admin/fernzugang/alle-trennen',{method:'POST'});const d=await r.json();fzMsg(t('Getrennt: ','Disconnected: ')+d.n);if(FZ.ws||FZ.fb)fzTrennen();if(FZ.fs)fzFZu('');fzLoad()}catch(e){fzMsg(e.message,true)}}
// ---------------------------------------------------------------- the files (SFTP)
const fzKB=n=>n==null?'':n<1024?n+' B':n<1048576?Math.round(n/1024)+' KB':n<1073741824?(n/1048576).toFixed(1)+' MB':(n/1073741824).toFixed(1)+' GB';
async function fzDateien(g){if(FZ.ws||FZ.weg||FZ.fs||FZ.fb){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}let d;
  try{const r=await api('/api/admin/fernzugang/dateien',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraet:g.id})});d=await r.json()}catch(e){fzFehler(e);return}
  FZ.fs={id:d.id,pfad:d.pfad,max:d.max_mb,oben:null};FZ.sitz={name:g.name,seit:Date.now()/1000,max:FZ.d.max,leer:d.leerlauf,art:'dateien'};
  $('fzmain').hidden=true;$('fzstatus').hidden=true;$('fzfiles').hidden=false;fzBanner();fzMsg('');fzFInfo();fzListe(d.pfad);if(window.fgZeig)fgZeig()}
function fzFInfo(){const dl=$('fzfinfo');dl.textContent='';const s=FZ.sitz||{},fs=FZ.fs||{};
  for(const [k,v] of [[t('System','System'),s.name||''],[t('Rechte','Permissions'),t('die des Benutzers spark auf dem Server','those of the user spark on the server')],[t('Höchstens','At most'),fs.max+t(' MB je Datei',' MB per file')],
    [t('Leerlauf trennt','Idle ends'),t('nach ','after ')+s.leer+' min'],[t('Aufgezeichnet','Recorded'),t('nur Anzahl und Größe, nie Namen oder Inhalte','only counts and sizes, never names or contents')]])dl.append(fzEl('dt','',k),fzEl('dd','',v));
  $('fzfmax').textContent=t('Höchstens ','At most ')+fs.max+t(' MB. Die Datei landet im gezeigten Ordner; ohne „Ersetzen“ bleibt eine vorhandene Datei, wie sie ist.',' MB. The file lands in the folder shown; without "Replace" an existing file stays as it is.')}
async function fzListe(p){const fs=FZ.fs;if(!fs)return;let d;
  try{const r=await api(`/api/admin/fernzugang/dateien/${fs.id}/liste`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pfad:p})});d=await r.json()}
  catch(e){if(e.status===404&&/session/.test(e.detail||'')||e.status===503){fzFZu(t('Die Dateien-Sitzung ist zu.','The files session is closed.'));return}fzMsg(e.message,true);return}
  fs.pfad=d.pfad;fs.oben=d.oben;fzMsg('');
  const cr=$('fzcrumbs');cr.textContent='';let acc='';const parts=d.pfad.split('/').filter(Boolean);
  cr.appendChild(fzBtn('/','fzcrumb',()=>fzListe('/')));
  for(const x of parts){acc+='/'+x;const to=acc;cr.appendChild(fzBtn(x,'fzcrumb',()=>fzListe(to)))}
  $('fzfup').disabled=!d.oben;
  const list=$('fzflist');list.textContent='';
  if(!d.eintraege.length)list.appendChild(fzEl('div','mut',t('Der Ordner ist leer.','The folder is empty.')));
  for(const x of d.eintraege){const row=fzEl('div','fzfrow'),dir=x.art==='dir'||x.art==='linkdir',file=x.art==='file'||x.art==='linkfile';
    const nm=dir?fzBtn(x.name+'/','fzfname',()=>fzListe((d.pfad==='/'?'':d.pfad)+'/'+x.name)):fzEl('span','fzfname',x.name);
    if(x.art.startsWith('link'))nm.appendChild(fzEl('small','mut',' →'));
    row.append(fzEl('span','fzfart '+(dir?'dir':file?'file':'other'),dir?'▸':file?'·':'?'),nm,fzEl('span','mut small',file?fzKB(x.groesse):''),fzEl('span','mut small',x.zeit?fzZeit(x.zeit):''));
    if(file){const b=fzBtn(t('Laden','Download'),'',()=>fzLaden1((d.pfad==='/'?'':d.pfad)+'/'+x.name));b.disabled=x.groesse>fs.max*1048576;row.appendChild(b)}else row.appendChild(fzEl('span'));
    list.appendChild(row)}
  if(d.mehr)list.appendChild(fzEl('div','fh',t('Mehr als 1000 Einträge: nur die ersten werden gezeigt.','More than 1000 entries: only the first are shown.')))}
async function fzLaden1(p){const fs=FZ.fs;if(!fs)return;
  try{const r=await api(`/api/admin/fernzugang/dateien/${fs.id}/link`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pfad:p})});const d=await r.json();
    const a=document.createElement('a');a.href=d.url;a.rel='noopener';document.body.appendChild(a);a.click();a.remove();fzMsg(t('Download startet …','Download starting …'))}catch(e){fzMsg(e.message,true)}}
async function fzHoch(){const fs=FZ.fs,f=$('fzffile').files[0];if(!fs)return;if(!f){$('fzffile').click();return}
  if(f.size>fs.max*1048576){fzMsg(t('Größer als ','Larger than ')+fs.max+' MB.',true);return}
  const b=$('fzfsend');b.disabled=true;fzMsg(t('Lädt hoch … ','Uploading … ')+fzKB(f.size));FZ.fs.laeuft=true;
  try{await api(`/api/admin/fernzugang/dateien/${fs.id}/hoch`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Fz-Pfad':encodeURIComponent(fs.pfad),
      'X-Fz-Name':encodeURIComponent(f.name),'X-Fz-Ersetzen':$('fzfreplace').checked?'1':'0'},body:f});
    fzMsg(t('Hochgeladen: ','Uploaded: ')+fzKB(f.size));$('fzffile').value='';fzListe(fs.pfad)}catch(e){fzMsg(e.message,true)}finally{b.disabled=false;if(FZ.fs)FZ.fs.laeuft=false}}
async function fzFSchliessen(text){const fs=FZ.fs;if(!fs)return;try{await api(`/api/admin/fernzugang/dateien/${fs.id}`,{method:'DELETE'})}catch{}fzFZu(typeof text==='string'?text:'')}
function fzFZu(text){if(window.fgZu)fgZu();FZ.fs=null;FZ.sitz=null;fzBanner();$('fzfiles').hidden=true;$('fzflist').textContent='';$('fzmain').hidden=false;if(text)fzMsg(text,true);fzLoad()}
{const k=$('fzgo');if(k){$('fzheraus').onclick=fzHeraus;$('fzverlaufweg').onclick=fzVerlaufWeg;$('fzfragen').onclick=fzFragen;$('fzzielgo').onclick=fzZielStart;$('fzzielende').onclick=()=>fzZielEnde('');
  $('fzfrage').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();fzFragen()}};$('fzalletasten').onclick=fzAlleTasten;$('fzdrawertab').onclick=()=>fzLade();$('fzzurueck').onclick=fzZurueck;$('fzwegstop').onclick=fzWegTrennen;
  if(!(navigator.keyboard&&typeof navigator.keyboard.lock==='function'))$('fzalletasten').title=t('Nur in Chrome oder Edge','Only in Chrome or Edge');k.onclick=fzKoppeln;$('fzalle').onclick=fzAlle;$('fzalleakt').onclick=()=>{const a=fzAktBereit(FZ.d&&FZ.d.geraete);if(a.length&&confirm(t(`${a.length} Anker jetzt aktualisieren? Jeder startet dabei kurz neu.`,`Update ${a.length} anchors now? Each restarts briefly.`)))fzAktualisieren(a.map(g=>g.id))};$('fzbtrennen').onclick=fzTrennen;$('fzweiter').onclick=fzWeiter;$('fzbaldende').onclick=fzTrennen;$('fzsperrplus').onclick=fzEntsperren;$('fzalle2').onclick=fzAlle;
  $('fzbinfo').onclick=e=>fzInfoPop(undefined,e.currentTarget);$('fzinfobtn').onclick=e=>fzInfoPop(undefined,e.currentTarget);$('fzkeycopy').onclick=e=>{if(FZ.fp)copyString(FZ.fp,e.currentTarget)};
  $('fzmenu').onclick=()=>fzMenu(!FZ.menuAus);$('fzspalte').onclick=()=>fzSpalte($('fzview').classList.contains('fzzu'));$('fztasten').onclick=fzTastenreihe;
  $('fzspaltezu').onclick=()=>{if(document.fullscreenElement)fzLade(false);else if(NARROW())fzBlatt(false);else fzSpalte(false)};$('fzfragbtn').onclick=()=>fzBlatt(true);fzGriff();fzSpalteStart();
  if(window.ResizeObserver){new ResizeObserver(()=>fzResize()).observe($('fzterm'));const ro=new ResizeObserver(()=>{fzLayout();fzSeite()});for(const e of [document.body,...document.body.children])ro.observe(e)}   // a bar or notice above the page comes later: the height follows
  new MutationObserver(()=>{fzMenu();fzLayout();fzSeite()}).observe($('fern'),{attributes:true,attributeFilter:['class']});addEventListener('resize',()=>{fzLayout();fzSeite()});
  $('fzname').onkeydown=e=>{if(e.key==='Enter')fzKoppeln()};fzKeys();
  {const c=$('fzchips');c.addEventListener('scroll',()=>{fzRand();fzTipWeg()},{passive:true});c.addEventListener('wheel',e=>{if(Math.abs(e.deltaY)>Math.abs(e.deltaX)&&c.scrollWidth>c.clientWidth){c.scrollLeft+=e.deltaY;e.preventDefault()}},{passive:false});addEventListener('resize',fzRand)}
  // page layout A: unlock pill, the sheet „System koppeln“, the history of all systems, the search over the list
  $('fzfup').onclick=()=>{if(FZ.fs&&FZ.fs.oben)fzListe(FZ.fs.oben)};$('fzfsend').onclick=fzHoch;$('fzfstop').onclick=fzFSchliessen;
  for(const b of $('fztabs').querySelectorAll('button'))b.onclick=()=>fzTab(b.dataset.tab);$('fzentsperren').onclick=fzEntsperren;$('fzverl').onclick=fzEntsperren;$('fzsperren').onclick=fzSperren;
  $('fzneu').onclick=fzKoppelnAuf;$('fzneu2').onclick=fzKoppelnAuf;$('fzkzu').onclick=()=>{$('fzkoppelnmodal').style.display='none'};$('fzvzu').onclick=()=>{$('fzverlaufmodal').style.display='none'};
  $('fzallev').onclick=()=>fzVerlaufZeigen('');$('fzsuche').oninput=fzSucheNotiz;for(const b of $('fzsidetabs').querySelectorAll('button'))b.onclick=()=>fzSeiteWahl(b.dataset.w);FZ.os='linux';for(const b of $('fzos').querySelectorAll('button'))b.onclick=()=>fzOsWahl(b.dataset.os);
  for(const id of ['fzkoppelnmodal','fzverlaufmodal']){const m=$(id);m.addEventListener('click',e=>{if(e.target===m)m.style.display='none'});m.addEventListener('keydown',e=>{if(e.key==='Escape')m.style.display='none'})}new MutationObserver(()=>{if(FZ.d)fzChips()}).observe($('fzview'),{attributes:true,attributeFilter:['hidden']})}}
// ---------------------------------------------------------------- layout A
function fzZeigen(){$('fzview').hidden=false;$('fzmain').hidden=true;$('fzstatus').hidden=true;$('fzbox').classList.add('fzoffen');fzMenu();fzLayout();
  clearInterval(FZ.lt);FZ.lt=setInterval(fzLayout,1000)}   // notices above the page come and go: the height follows within a second
function fzVerbergen(){clearInterval(FZ.lt);$('fzbox').classList.remove('fzoffen');fzInfoPop(false);fzBlatt(false);fzMenu();$('fzview').style.removeProperty('--fzh')}
// the page never scrolls with a terminal open: the view takes what the window has left below it
function fzLayout(){const v=$('fzview');if(!v||v.hidden||FZ_FENSTER||document.fullscreenElement||!document.querySelector('section#fern.on'))return;
  const was=v.style.getPropertyValue('--fzh'),top=v.getBoundingClientRect().top+scrollY,min=NARROW()?240:300;let h=Math.max(min,Math.floor(innerHeight-top-10));v.style.setProperty('--fzh',h+'px');
  const over=document.documentElement.scrollHeight-innerHeight;if(over>0){h=Math.max(min,h-over);v.style.setProperty('--fzh',h+'px')}
  if(was!==h+'px')requestAnimationFrame(()=>fzResize())}
// „Menü ausblenden“: the panel's menu folds away while a terminal is open here (wide screens); the choice stays in this browser
// the page with the list (layout A): list and detail as high as the window allows, so the page itself never scrolls
function fzSeite(){const s=$('fzsplit');if(!s)return;if(NARROW()||$('fzmain').hidden||!document.querySelector('section#fern.on')){s.style.removeProperty('--fzsh');return}
  const top=s.getBoundingClientRect().top+scrollY;let h=Math.max(360,Math.floor(innerHeight-top-16));s.style.setProperty('--fzsh',h+'px');
  const over=document.documentElement.scrollHeight-innerHeight;if(over>0)s.style.setProperty('--fzsh',Math.max(360,h-over)+'px')}
function fzMenuWahl(){try{return localStorage.getItem('fzmenu')!=='zeigen'}catch{return true}}
function fzMenu(aus){if(aus!==undefined){FZ.menuAus=!!aus;try{localStorage.setItem('fzmenu',aus?'aus':'zeigen')}catch{}}else if(FZ.menuAus===undefined)FZ.menuAus=fzMenuWahl();
  const v=$('fzview'),on=!FZ_FENSTER&&!!v&&!v.hidden&&!!document.querySelector('section#fern.on');document.body.classList.toggle('fzohnemenu',on&&FZ.menuAus);document.body.classList.toggle('fzterminal',on);
  const b=$('fzmenu');if(b){const l=FZ.menuAus?t('Menü einblenden','Show the menu'):t('Menü ausblenden','Hide the menu');b.title=l;b.setAttribute('aria-label',l);b.setAttribute('aria-pressed',FZ.menuAus?'true':'false')}
  if(aus!==undefined)fzLayout()}
// the assistant's column: open or folded (kept), its width dragged between 280 and 520 px (kept), a double click folds it
function fzSpalteStart(){let w=340,zu=false;try{w=Number(localStorage.getItem('fzcol'))||340;zu=localStorage.getItem('fzspalte')==='zu'}catch{}
  fzBreite(w,false);fzSpalte(!zu,false)}
function fzBreite(w,keep){w=Math.round(Math.max(FZ_SPALTE[0],Math.min(FZ_SPALTE[1],w)));$('fzview').style.setProperty('--fzcol',w+'px');FZ.col=w;
  const g=$('fzgriff');g.setAttribute('aria-valuenow',String(w));g.setAttribute('aria-valuemin',String(FZ_SPALTE[0]));g.setAttribute('aria-valuemax',String(FZ_SPALTE[1]));
  if(keep!==false){try{localStorage.setItem('fzcol',String(w))}catch{}}}
function fzSpalte(open,keep){const v=$('fzview');v.classList.toggle('fzzu',!open);$('fzspalte').setAttribute('aria-pressed',open?'true':'false');
  if(keep!==false){try{localStorage.setItem('fzspalte',open?'auf':'zu')}catch{}}
  requestAnimationFrame(()=>{fzResize();if(!open&&FZ.term)FZ.term.focus()})}
function fzGriff(){const g=$('fzgriff');let x0=0,w0=0;
  g.onpointerdown=e=>{e.preventDefault();x0=e.clientX;w0=FZ.col||340;g.setPointerCapture(e.pointerId);g.classList.add('zieht')};
  g.onpointermove=e=>{if(!g.classList.contains('zieht'))return;fzBreite(w0+(x0-e.clientX),false)};
  g.onpointerup=g.onpointercancel=e=>{if(!g.classList.contains('zieht'))return;g.classList.remove('zieht');fzBreite(FZ.col,true);fzResize()};
  g.ondblclick=()=>fzSpalte(false);
  g.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();fzBreite((FZ.col||340)+(e.key==='ArrowLeft'?20:-20))}else if(e.key==='Enter'){e.preventDefault();fzSpalte(false)}}}
// the phone: the assistant as a sheet from below; „Einfügen“ closes it and the terminal has the focus
function fzBlatt(open){const v=$('fzview');if(!v)return;v.classList.toggle('fzblatt',!!open&&v.classList.contains('fzki'));$('fzfragbtn').setAttribute('aria-expanded',open?'true':'false');
  if(open)setTimeout(()=>$('fzfrage').focus(),220);else if(FZ.term&&NARROW())FZ.term.focus()}
function fzTastenreihe(){const v=$('fzview');v.classList.toggle('fzohnetasten');$('fztasten').setAttribute('aria-pressed',v.classList.contains('fzohnetasten')?'false':'true');fzLayout()}
// whether the assistant is in sight: suggestions after Enter only then
function fzSpalteOffen(){const v=$('fzview');if(!v||!v.classList.contains('fzki')||v.hidden)return false;
  if(document.fullscreenElement===v)return v.classList.contains('fzlade');if(NARROW())return v.classList.contains('fzblatt');return !v.classList.contains('fzzu')}
// ---------------------------------------------------------------- Notizen je System (fernnotiz.py)
// one note element at a time: in the detail under „Angaben“ or in the column beside the terminal (tab „Notizen“);
// light markup (# heading, - list, **bold**, `code`, ``` blocks), every code line with „Ins Terminal“ (never Enter),
// saved while typing, „gehört in den Tresor“ by the panel's fixed rules, the last versions with „Wiederherstellen“
const FZ_GEHEIM={passwort:['ein Passwort','a password'],schluessel:['ein privater Schlüssel','a private key'],token:['ein Token','a token']};
function fzNotizAn(){return !!(FZ.d&&FZ.d.notizen)}
function fzNotizInline(el,text){const rx=/\*\*([^*]+)\*\*|`([^`]+)`/g;let last=0,m;
  while((m=rx.exec(text))){if(m.index>last)el.appendChild(document.createTextNode(text.slice(last,m.index)));el.appendChild(m[1]!==undefined?fzEl('b','',m[1]):fzEl('code','',m[2]));last=rx.lastIndex}
  if(last<text.length)el.appendChild(document.createTextNode(text.slice(last)))}
function fzNotizBild(text,gid){const f=document.createDocumentFragment();let ul=null,code=false;
  for(const raw of String(text||'').split('\n')){const line=raw.replace(/\s+$/,'');
    if(/^```/.test(line.trim())){code=!code;ul=null;continue}
    if(code){if(!line.trim())continue;const r=fzEl('div','fznzcode'),c=fzEl('code','',line);r.appendChild(c);
      const b=fzEl('button','fznzins',t('Ins Terminal','Into the terminal'));b.type='button';b.onclick=()=>fzNotizTerminal(gid,line);r.appendChild(b);f.appendChild(r);continue}
    const h=line.match(/^#{1,3}\s+(.*)$/),li=line.match(/^\s*[-*•]\s+(.*)$/);
    if(li){if(!ul){ul=fzEl('ul','fznzliste');f.appendChild(ul)}const e=fzEl('li');fzNotizInline(e,li[1]);ul.appendChild(e);continue}
    ul=null;if(!line.trim()){f.appendChild(fzEl('div','fznzleer'));continue}
    const e=fzEl('div',h?'fznzh':'fznzp');fzNotizInline(e,h?h[1]:line);f.appendChild(e)}
  return f}
// „Ins Terminal“: into the open shell of this system, or a shell opens first; the line is typed in, Enter stays with the person
function fzNotizTerminal(gid,line){line=String(line).replace(/[\r\n]+/g,' ').trim();if(!line)return;
  if(FZ.ws&&FZ.sitz&&FZ.sitz.gid===gid&&FZ.ws.readyState===1){fzEinfuegen(line);return}
  if(FZ.ws||FZ.weg||FZ.fs||FZ.fb){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}
  const g=((FZ.d&&FZ.d.geraete)||[]).find(x=>x.id===gid);if(!g)return;
  if(!g.online||g.hostkey_falsch||!g.erlaubt||g.stand==='abbau'){fzMsg(t('Das System ist nicht bereit für eine Shell.','The system is not ready for a shell.'),true);return}
  fzOpen(g).then(()=>{if(FZ.ws&&FZ.sitz&&FZ.sitz.gid===gid)FZ.nachher=line})}
async function fzNotizLaden(gid){const n={gid,text:'',lesen:true,t:null,fassungen:[],warnungen:[],edit:false,stand:'',offen:false};FZ.notiz=n;fzNotizZeigen();
  try{const r=await api('/api/admin/fernzugang/notiz/'+gid);const d=await r.json();if(FZ.notiz!==n)return;Object.assign(n,d,{geladen:true})}
  catch(e){if(FZ.notiz===n){n.fehler=true;fzFehler(e)}}fzNotizZeigen()}
// where the note stands now: the column beside the terminal (its tab) or the detail of the selected system
function fzNotizFuer(gid){if(!fzNotizAn()||!gid)return null;if(!FZ.notiz||FZ.notiz.gid!==gid){fzNotizSpeichern();fzNotizLaden(gid)}return FZ.notizEl||(FZ.notizEl=fzEl('div','fznotiz'))}
function fzNotizZeigen(){const n=FZ.notiz,box=FZ.notizEl||(FZ.notizEl=fzEl('div','fznotiz'));if(!n)return;
  const fo=box.contains(document.activeElement)&&document.activeElement.tagName==='TEXTAREA'?document.activeElement:null;
  if(fo&&n.edit){fzNotizKopf(box,n);fzNotizWarn(box,n);return}       // typing: only head and hints change, the text stays as it is
  box.textContent='';box.appendChild(fzEl('div','fznzkopf'));fzNotizKopf(box,n);
  if(!n.geladen){box.appendChild(fzEl('div','mut',n.fehler?t('Nicht geladen.','Not loaded.'):t('Lädt …','Loading …')));return}
  if(n.edit){const ta=fzEl('textarea','fznztext');ta.id='fznztext';ta.value=n.text;ta.rows=10;ta.spellcheck=false;ta.setAttribute('aria-label',t('Notiz','Note'));
    ta.placeholder=t('# Überschrift\n- Punkt\n```\nsudo systemctl restart dienst\n```','# Heading\n- item\n```\nsudo systemctl restart service\n```');
    ta.oninput=()=>{n.text=ta.value;n.stand='tippt';fzNotizKopf(box,n);clearTimeout(n.timer);n.timer=setTimeout(()=>fzNotizSpeichern(),1200)};ta.onblur=()=>fzNotizSpeichern();box.appendChild(ta)}
  else{const v=fzEl('div','fznzbild');if(n.text.trim())v.appendChild(fzNotizBild(n.text,n.gid));else{v.appendChild(fzEl('div','mut',t('Noch keine Notiz. „Bearbeiten“ zum Schreiben: Dienste, Pfade, Ansprechpartner, Befehle in ```.','No note yet. "Edit" to write: services, paths, contacts, commands in ```.')))}
    v.ondblclick=()=>fzNotizEdit(true);box.appendChild(v)}
  box.appendChild(fzEl('div','fznzwarn'));fzNotizWarn(box,n);
  const fuss=fzEl('label','fzchk fznzlesen'),cb=document.createElement('input');cb.type='checkbox';cb.checked=n.lesen!==false;
  cb.onchange=()=>{n.lesen=cb.checked;fzNotizSpeichern(true)};fuss.append(cb,document.createTextNode(' '+t('Assistent darf lesen','Assistant may read')),fzEl('span','mut',' · '+t('nur eigenes Modell','own model only')));box.appendChild(fuss);
  if(n.offen){const fl=fzEl('div','fznzfass');fl.appendChild(fzEl('div','fzgrp',t('Fassungen der Notiz','Versions of the note')));
    fl.appendChild(fzEl('div','fznzfrow',(n.t?fzZeit(n.t):'–')+' · '+t('aktuell','current')));
    for(const f of n.fassungen||[]){const r=fzEl('div','fznzfrow');r.append(fzEl('span','',fzZeit(f.t)+' · '+f.zeichen+t(' Zeichen',' characters')),fzEl('span','fzfill'));
      const b=fzEl('button','fzlink',t('Wiederherstellen','Restore'));b.type='button';b.onclick=()=>fzNotizZurueck(f.t);r.appendChild(b);fl.appendChild(r)}
    fl.appendChild(fzEl('div','fh',t('Die letzten 10 Fassungen bleiben erhalten; eine neue beginnt, wenn 10 Minuten nichts gespeichert wurde.','The last 10 versions are kept; a new one starts when nothing was saved for 10 minutes.')));box.appendChild(fl)}}
function fzNotizKopf(box,n){const k=box.querySelector('.fznzkopf');if(!k)return;k.textContent='';
  k.append(fzEl('b','','📝 '+t('Notizen','Notes')),fzEl('span','fznzstand'+(n.stand==='fehler'?' bad':''),n.stand==='tippt'?'…':n.stand==='speichert'?t('speichert …','saving …'):n.stand==='fehler'?t('nicht gespeichert','not saved'):n.t?'✓ '+t('gespeichert ','saved ')+fzUhr(n.t):''),fzEl('span','fzfill'));
  if(n.edit)for(const [l,tip,fn] of [['B',t('Fett','Bold'),()=>fzNotizMark('**','**')],['•',t('Liste','List'),()=>fzNotizZeile('- ')],['</>',t('Code-Block','Code block'),()=>fzNotizMark('```\n','\n```')]]){
    const b=fzEl('button','b fznzt',l);b.type='button';b.title=tip;b.setAttribute('aria-label',tip);b.onmousedown=e=>e.preventDefault();b.onclick=fn;k.appendChild(b)}
  if(n.fassungen&&n.fassungen.length){const f=fzEl('button','b fznzt',t('Fassungen','Versions')+' ('+n.fassungen.length+')');f.type='button';f.setAttribute('aria-expanded',String(!!n.offen));f.onclick=()=>{n.offen=!n.offen;fzNotizZeigen()};k.appendChild(f)}
  const e=fzEl('button','b fznzt'+(n.edit?' p':''),n.edit?t('Fertig','Done'):t('Bearbeiten','Edit'));e.type='button';e.onclick=()=>fzNotizEdit(!n.edit);e.disabled=!n.geladen;k.appendChild(e)}
function fzNotizWarn(box,n){const w=box.querySelector('.fznzwarn');if(!w)return;w.textContent='';
  for(const x of n.warnungen||[]){const r=fzEl('div','note warn fznzw'),was=FZ_GEHEIM[x.art]||FZ_GEHEIM.token;
    r.appendChild(document.createTextNode('⚠ '+t(`Zeile ${x.zeile} sieht aus wie ${was[0]}. Das gehört in den Tresor, nicht in die Notiz. `,`Line ${x.zeile} looks like ${was[1]}. That belongs in the vault, not in the note. `)));
    const b=fzEl('button','fzlink',t('Entfernen','Remove'));b.type='button';b.onclick=()=>fzNotizWeg(x.zeile);r.appendChild(b);w.appendChild(r)}}
function fzNotizEdit(on){const n=FZ.notiz;if(!n)return;if(!on)fzNotizSpeichern();n.edit=!!on;fzNotizZeigen();if(on){const ta=$('fznztext');if(ta)ta.focus()}}
function fzNotizMark(a,b){const ta=$('fznztext'),n=FZ.notiz;if(!ta||!n)return;const s=ta.selectionStart,e=ta.selectionEnd,v=ta.value;
  ta.value=v.slice(0,s)+a+v.slice(s,e)+b+v.slice(e);ta.setSelectionRange(s+a.length,e+a.length);ta.focus();ta.oninput()}
function fzNotizZeile(p){const ta=$('fznztext');if(!ta)return;const s=ta.selectionStart,v=ta.value,i=v.lastIndexOf('\n',s-1)+1;
  if(v.slice(i,i+p.length)!==p){ta.value=v.slice(0,i)+p+v.slice(i);ta.setSelectionRange(s+p.length,s+p.length)}ta.focus();ta.oninput()}
// „Entfernen“ of a line the panel took for a secret: the line goes, the note is saved at once
function fzNotizWeg(zeile){const n=FZ.notiz;if(!n)return;const l=n.text.split('\n');if(zeile<1||zeile>l.length)return;l.splice(zeile-1,1);n.text=l.join('\n');
  const ta=$('fznztext');if(ta)ta.value=n.text;fzNotizSpeichern(true).then(()=>{if(!ta)fzNotizZeigen()})}
async function fzNotizSpeichern(jetzt){const n=FZ.notiz;if(!n||!n.geladen)return;clearTimeout(n.timer);if(n.stand!=='tippt'&&!jetzt)return;
  if(n.laeuft){n.nochmal=true;return}n.laeuft=true;n.stand='speichert';fzNotizKopf(FZ.notizEl,n);const text=n.text,lesen=n.lesen!==false;
  try{const r=await api('/api/admin/fernzugang/notiz/'+n.gid,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,lesen})});const d=await r.json();
    n.t=d.t;n.fassungen=d.fassungen||[];n.warnungen=d.warnungen||[];n.stand=n.text===text?'':'tippt';
    const g=((FZ.d&&FZ.d.geraete)||[]).find(x=>x.id===n.gid);if(g&&g.notiz!==!!text.trim()){g.notiz=!!text.trim();if(!FZ.ws)fzShow()}}
  catch(e){n.stand='fehler';fzFehler(e)}
  n.laeuft=false;if(FZ.notiz===n){fzNotizZeigen();if(n.nochmal||n.stand==='tippt'){n.nochmal=false;n.timer=setTimeout(()=>fzNotizSpeichern(true),400)}}}
async function fzNotizZurueck(tt){const n=FZ.notiz;if(!n)return;await fzNotizSpeichern();
  try{const r=await api(`/api/admin/fernzugang/notiz/${n.gid}/wiederherstellen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({t:tt})});
    Object.assign(n,await r.json(),{edit:false,stand:''});fzMsg(t('Fassung wiederhergestellt.','Version restored.'))}catch(e){fzFehler(e)}fzNotizZeigen()}
function fzNotizLadenDatei(g){const a=document.createElement('a');a.href=`/api/admin/fernzugang/notiz/${g.id}/laden`;a.download='';document.body.appendChild(a);a.click();a.remove()}
// the column beside the terminal: tabs „Assistent“ and „Notizen“ when both are there, else the one that is
function fzSeiteWahl(w){const ki=!!(FZ.d&&FZ.d.hilfe),no=fzNotizAn()&&!!(FZ.sitz&&FZ.sitz.gid);FZ.seite=w==='notiz'&&no?'notiz':ki?'ki':no?'notiz':'ki';
  $('fzsidetabs').hidden=!(ki&&no);for(const b of $('fzsidetabs').querySelectorAll('button')){const on=b.dataset.w===FZ.seite;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on))}
  $('fzhilfe').hidden=!ki||FZ.seite!=='ki';const p=$('fznotizseite');p.hidden=!no||FZ.seite!=='notiz';
  if(!p.hidden){const el=fzNotizFuer(FZ.sitz.gid);if(el&&el.parentNode!==p){p.textContent='';p.appendChild(el)}}}
// the search finds note text too: a snippet per system, asked once the typing pauses
function fzSucheNotiz(){clearTimeout(FZ.qt);const q=$('fzsuche').value.trim();if(!fzNotizAn()||q.length<2){FZ.treffer=null;fzShow();return}
  fzShow();FZ.qt=setTimeout(async()=>{try{const r=await api('/api/admin/fernzugang/notizen/suche?q='+encodeURIComponent(q));const d=await r.json();
    if($('fzsuche').value.trim()===q){FZ.treffer={q,t:d.treffer||{}};fzShow()}}catch(e){fzFehler(e)}},300)}
window.fzLoad=fzLoad;
// the menu entry Fernzugang: only for an admin (never the Verwalter) while Funktionen → Fernzugang zu Servern is on (whoami)
window.fzStart=who=>{const on=!!(who&&who.fernzugang);document.querySelectorAll('nav button[data-s=fern]').forEach(b=>b.hidden=!on)};
// the own window: only the terminal, over the whole page; it tells its opener it is ready and waits for the ticket
if(FZ_FENSTER&&$('fzview')){document.body.classList.add('fzfenster');$('fzview').hidden=false;window.opener.postMessage({typ:'fz-bereit'},location.origin)}
// ---------------------------------------------------------------- Ordner (fernordner.py, Dominik 2026-10-29 „A“)
// one level of folders like in Mail: collapsible (kept in this browser), „● online / gesamt“, „Ohne Ordner“, „+ Neuer
// Ordner“; dragging orders folders and systems, „⋯ → Verschieben nach …“ (right click, long press on the phone) moves one
// system; a click on a folder shows its overview on the right. Folders are only order: every door stays per system.
function fzZuListe(){try{return JSON.parse(localStorage.getItem('fzordnerzu')||'[]')}catch{return []}}
function fzZuKlappen(oid){const z=new Set(fzZuListe());z.has(oid)?z.delete(oid):z.add(oid);try{localStorage.setItem('fzordnerzu',JSON.stringify([...z]))}catch{}fzShow()}
function fzOrdnerVon(g){return g.ordner||''}
function fzOrdnerListe(list,ord,passt,tr,suche){const zu=new Set(fzZuListe()),gs=FZ.d.geraete||[];
  if(ord.length)list.appendChild(fzEl('div','fzgrp',t('Ordner','Folders')));
  for(const o of ord.concat([{id:'',name:t('Ohne Ordner','No folder'),symbol:''}])){
    const alle=gs.filter(g=>fzOrdnerVon(g)===o.id),teil=passt.filter(g=>fzOrdnerVon(g)===o.id);
    if(suche&&!teil.length)continue;if(!o.id&&!alle.length&&!ord.length)continue;
    const auf=suche||!o.id||!zu.has(o.id),kopf=fzEl('div','fzordner'+(o.id&&o.id===FZ.ordner?' on':'')+(o.id?'':' ohne'));kopf.dataset.ordner=o.id;
    if(o.id){const pf=fzEl('button','fzopf',auf?'▾':'▸');pf.type='button';pf.setAttribute('aria-expanded',auf?'true':'false');
      pf.setAttribute('aria-label',(auf?t('Zuklappen: ','Collapse: '):t('Aufklappen: ','Expand: '))+o.name);pf.onclick=e=>{e.stopPropagation();fzZuKlappen(o.id)};kopf.appendChild(pf)}
    const nm=fzEl('button','fzoname');nm.type='button';if(o.symbol)nm.appendChild(fzEl('span','fzosym',o.symbol));nm.appendChild(fzEl('span','',o.name));
    if(o.id)nm.onclick=()=>{FZ.ordner=o.id;FZ.sel='';FZ.auf=true;fzShow()};else nm.disabled=true;
    const on=alle.filter(g=>g.online).length,z=fzEl('span','fzozahl');z.append(fzEl('span','fzdot'+(on?' ok':'')),document.createTextNode(` ${on} / ${alle.length}`));
    z.title=t(`${on} online von ${alle.length}`,`${on} online of ${alle.length}`);kopf.append(nm,z);fzZiehZiel(kopf,o.id,null);
    if(o.id){kopf.draggable=true;kopf.ondragstart=e=>{FZ.zieh={art:'ordner',id:o.id};e.dataTransfer.effectAllowed='move';try{e.dataTransfer.setData('text/plain','')}catch{}}}
    list.appendChild(kopf);if(!auf)continue;
    const box=fzEl('div','fzoinhalt');for(const g of teil)box.appendChild(fzSysOrdnerZeile(g,tr));
    if(!teil.length&&o.id)box.appendChild(fzEl('div','mut fzoleer',t('Leer: ein System hierher ziehen oder „⋯ → Verschieben nach …“.','Empty: drag a system here or "⋯ → Move to …".')));
    list.appendChild(box)}
  if(!suche){if(FZ.neuOrdner)list.appendChild(fzOrdnerForm(null));
    else if(ord.length<(FZ.d.ordner_max||30)){const n=fzEl('button','fzlink fzneuordner',t('+ Neuer Ordner','+ New folder'));n.type='button';n.id='fzneuordner';n.onclick=()=>{FZ.neuOrdner=true;fzShow();setTimeout(()=>{const i=$('fzoname');if(i)i.focus()},30)};list.appendChild(n)}}}
// a system inside a folder: draggable, with „⋯“ (and right click, long press) for „Verschieben nach …“
function fzSysOrdnerZeile(g,tr){const w=fzEl('div','fzrowwrap'),row=fzSysZeile(g,tr),m=fzEl('button','fzmehr','⋯');m.type='button';
  m.setAttribute('aria-label',t('Mehr zu ','More for ')+g.name);m.setAttribute('aria-haspopup','menu');m.onclick=e=>{e.stopPropagation();fzOrdnerMenu(g,m)};
  w.append(row,m);w.draggable=true;w.ondragstart=e=>{FZ.zieh={art:'sys',id:g.id};w.classList.add('zieht');e.dataTransfer.effectAllowed='move';try{e.dataTransfer.setData('text/plain','')}catch{}};
  w.ondragend=()=>{w.classList.remove('zieht');fzZiehEnde()};fzZiehZiel(w,fzOrdnerVon(g),g.id);
  row.oncontextmenu=e=>{e.preventDefault();fzOrdnerMenu(g,m)};
  let lang=0;row.addEventListener('touchstart',()=>{clearTimeout(lang);lang=setTimeout(()=>{lang=-1;fzOrdnerMenu(g,m)},550)},{passive:true});
  row.addEventListener('touchend',e=>{if(lang===-1)e.preventDefault();clearTimeout(lang);lang=0});row.addEventListener('touchmove',()=>{clearTimeout(lang);lang=0},{passive:true});
  return w}
// where something dragged may land: on a folder (a system goes to its end, a folder before it) or before a system
function fzZiehZiel(el,oid,vor){el.ondragover=e=>{const z=FZ.zieh;if(!z||(z.art==='ordner'&&(!oid||vor)))return;e.preventDefault();el.classList.add('ziel')};
  el.ondragleave=()=>el.classList.remove('ziel');
  el.ondrop=e=>{const z=FZ.zieh;el.classList.remove('ziel');if(!z)return;e.preventDefault();e.stopPropagation();FZ.zieh=null;
    if(z.art==='ordner'){if(oid&&!vor&&z.id!==oid)fzOrdnung(z.id,oid,null,null)}else if(z.id!==vor)fzOrdnung(null,null,z.id,{oid,vor})}}
function fzZiehEnde(){FZ.zieh=null;for(const e of document.querySelectorAll('#fzlist .ziel'))e.classList.remove('ziel')}
// the whole order after a drop: folders (one moved before another) and systems (one moved into a folder, maybe before another)
async function fzOrdnung(ordner,vorOrdner,gid,ziel){const d=FZ.d,ord=(d.ordner||[]).map(o=>o.id);let gs=(d.geraete||[]).map(g=>[g.id,fzOrdnerVon(g)]);
  if(ordner){ord.splice(ord.indexOf(ordner),1);ord.splice(ord.indexOf(vorOrdner),0,ordner)}
  if(gid){gs=gs.filter(p=>p[0]!==gid);const i=ziel.vor?gs.findIndex(p=>p[0]===ziel.vor):-1;
    if(i>=0)gs.splice(i,0,[gid,ziel.oid]);else{let j=-1;gs.forEach((p,k)=>{if(p[1]===ziel.oid)j=k});gs.splice(j>=0?j+1:gs.length,0,[gid,ziel.oid])}}
  try{await api('/api/admin/fernzugang/ordnung',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({ordner:ord,systeme:gs})});fzLoad()}catch(e){fzFehler(e)}}
// „⋯ → Verschieben nach …“: a small menu with the folders and „Ohne Ordner“
function fzOrdnerMenu(g,an){fzMenuZu();const m=fzEl('div','fzomenu');m.id='fzomenu';m.setAttribute('role','menu');m.appendChild(fzEl('div','fzomkopf',t('Verschieben nach …','Move to …')));
  for(const o of (FZ.d.ordner||[]).concat([{id:'',name:t('Ohne Ordner','No folder'),symbol:''}])){const b=fzEl('button','',(o.symbol?o.symbol+' ':'')+o.name);b.type='button';b.setAttribute('role','menuitem');
    b.disabled=fzOrdnerVon(g)===o.id;b.onclick=()=>{fzMenuZu();fzVerschieben(g.id,o.id)};m.appendChild(b)}
  document.body.appendChild(m);const r=an.getBoundingClientRect();m.style.top=Math.min(innerHeight-m.offsetHeight-8,r.bottom+4)+'px';m.style.left=Math.max(8,Math.min(innerWidth-m.offsetWidth-8,r.right-m.offsetWidth))+'px';
  const f=m.querySelector('button:not([disabled])');if(f)f.focus();
  setTimeout(()=>{document.addEventListener('pointerdown',fzMenuAussen,true);document.addEventListener('keydown',fzMenuTaste,true)},0)}
function fzMenuAussen(e){const m=$('fzomenu');if(m&&!m.contains(e.target))fzMenuZu()}
function fzMenuTaste(e){if(e.key==='Escape'){e.preventDefault();fzMenuZu()}}
function fzMenuZu(){const m=$('fzomenu');if(m)m.remove();document.removeEventListener('pointerdown',fzMenuAussen,true);document.removeEventListener('keydown',fzMenuTaste,true)}
async function fzVerschieben(gid,oid){try{await api(`/api/admin/fernzugang/geraete/${gid}/ordner`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ordner:oid})});fzLoad()}catch(e){fzFehler(e)}}
// a new folder (o null) or „Umbenennen“ / „Symbol“ of one: symbol and name in one row
function fzOrdnerForm(o){const f=fzEl('form','fzoform'),sy=document.createElement('input'),nm=document.createElement('input');
  sy.id='fzosymbol';sy.maxLength=8;sy.value=o?o.symbol:'📁';sy.setAttribute('aria-label',t('Symbol','Symbol'));sy.className='fzosyminp';
  nm.id='fzoname';nm.maxLength=40;nm.value=o?o.name:'';nm.placeholder=t('Name des Ordners','Folder name');nm.setAttribute('aria-label',t('Name des Ordners','Folder name'));nm.autocomplete='off';
  const ok=fzEl('button','b p',o?t('Sichern','Save'):t('Anlegen','Create'));ok.type='submit';const ab=fzBtn(t('Abbrechen','Cancel'),'',()=>{FZ.neuOrdner=false;FZ.ordnerEdit=false;fzShow()});
  f.append(sy,nm,ok,ab);f.onsubmit=async e=>{e.preventDefault();const body={name:nm.value.trim(),symbol:sy.value.trim()};if(!body.name){nm.focus();return}
    try{const r=await api(o?`/api/admin/fernzugang/ordner/${o.id}`:'/api/admin/fernzugang/ordner',{method:o?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();FZ.neuOrdner=false;FZ.ordnerEdit=false;if(!o&&d.id){FZ.ordner=d.id;FZ.sel=''}fzLoad()}catch(e){fzFehler(e)}};
  nm.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();ab.click()}};return f}
// the folder's overview on the right: its numbers, „Umbenennen“, „Symbol“, „Alle aktualisieren“, „Löschen“ and its systems
function fzOrdnerDetail(box,o){const gs=(FZ.d.geraete||[]).filter(g=>fzOrdnerVon(g)===o.id),on=gs.filter(g=>g.online).length,nz=gs.filter(g=>g.notiz).length;
  const bk=fzEl('button','fzback','‹ '+t('Alle Systeme','All systems'));bk.type='button';bk.onclick=()=>{FZ.auf=false;FZ.ordner='';fzShow()};box.appendChild(bk);
  const hd=fzEl('div','fzdkopf fzokopf'),ht=fzEl('div','fzdtext');hd.appendChild(fzEl('span','fzosymgross',o.symbol||'📁'));
  ht.append(fzEl('div','fzdname',''),fzEl('div','mut',[t(`${gs.length} Systeme`,`${gs.length} systems`),t(`${on} online`,`${on} online`),nz?t(`${nz} mit Notiz`,`${nz} with a note`):''].filter(Boolean).join(' · ')));
  ht.firstChild.appendChild(fzEl('b','',o.name));hd.appendChild(ht);box.appendChild(hd);
  if(FZ.ordnerEdit){box.appendChild(fzOrdnerForm(o));setTimeout(()=>{const i=$('fzoname');if(i&&document.activeElement!==i&&document.activeElement!==$('fzosymbol'))i.focus()},30)}
  const kn=fzEl('div','fzknoepfe');const um=fzBtn(t('Umbenennen','Rename'),'fzk',()=>{FZ.ordnerEdit=true;fzShow()});um.id='fzoumbenennen';
  const sy=fzBtn(t('Symbol','Symbol'),'fzk',()=>{FZ.ordnerEdit=true;fzShow();setTimeout(()=>{const i=$('fzosymbol');if(i){i.focus();i.select()}},40)});
  const akt=fzAktBereit(gs),ak=fzBtn(t('Alle aktualisieren','Update all')+(akt.length?' ('+akt.length+')':''),'fzk',()=>fzAktualisieren(akt.map(g=>g.id)));ak.disabled=!akt.length;ak.id='fzoakt';
  const del=fzBtn(t('Löschen …','Delete …'),'danger',async()=>{if(!confirm(t(`Ordner „${o.name}“ löschen? Seine ${gs.length} Systeme kommen nach „Ohne Ordner“; kein System wird gelöscht.`,`Delete the folder "${o.name}"? Its ${gs.length} systems go to "No folder"; no system is deleted.`)))return;
    try{await api(`/api/admin/fernzugang/ordner/${o.id}`,{method:'DELETE'});FZ.ordner='';FZ.auf=false;fzLoad()}catch(e){fzFehler(e)}});del.id='fzoloeschen';
  kn.append(um,sy,ak,fzEl('span','fzfill'),del);box.appendChild(kn);
  const grid=fzEl('div','fzokarten');for(const g of gs){const [lvl,word]=fzStand(g),k=fzEl('button','fzokarte');k.type='button';
    const tx=fzEl('span','fzrtext');tx.append(fzEl('b','',g.name),fzEl('small','',[word,g.anker?t('Anker ','anchor ')+g.anker:''].filter(Boolean).join(' · ')));
    k.append(fzIcon(g),tx,fzEl('span','fzdot '+lvl));k.onclick=()=>{FZ.sel=g.id;FZ.ordner='';FZ.auf=true;fzShow()};grid.appendChild(k)}
  if(!gs.length)grid.appendChild(fzEl('div','mut',t('Noch kein System in diesem Ordner.','No system in this folder yet.')));box.appendChild(grid)}
// „Koppeln“: the folder the new system lands in (only while folders are on and there is one)
function fzKoppelnOrdner(){const s=$('fzkordner');if(!s)return;const ord=FZ.d&&FZ.d.ordner_an?FZ.d.ordner||[]:[];$('fzkordnerrow').hidden=!ord.length;
  const was=s.value||FZ.ordner||'';s.textContent='';const leer=document.createElement('option');leer.value='';leer.textContent=t('Ohne Ordner','No folder');s.appendChild(leer);
  for(const o of ord){const x=document.createElement('option');x.value=o.id;x.textContent=(o.symbol?o.symbol+' ':'')+o.name;s.appendChild(x)}
  s.value=ord.some(o=>o.id===was)?was:''}
