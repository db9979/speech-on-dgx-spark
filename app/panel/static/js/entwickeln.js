// Entwickeln (entwickelnseite.py, plan opencode-pi, package 3, Dominik 2026-11-03 „3a“): Zustand → Werkstatt → part
// „Entwickeln“ beside „Prüfen und reparieren“. Übersicht: on the left the local changes, the branches on GitHub and the
// settings, on the right one of them with the tiles (runs as, internet, GitHub), the local commits, the buttons
// (Lokal einspielen, An GitHub geben, Zurück, Verwerfen: the server asks the code and update.sh checks everything
// again) and the Ablauf. Terminal: a shell as spark-dev (own sub-switch, a fresh code each session) with xterm.js of
// the Fernzugang (fzLaden, one source). Commit titles and the terminal are data from spark-dev: textContent only.
const DV={d:null,gh:null,ca:null,sel:'lokal',such:'',timer:0,ansicht:'ueber',term:null,ws:null,grund:'',thema:false,ctrl:false,alt:false};
function dvEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function dvT(p){return L==='en'?p[1]:p[0]}
function dvBtn(txt,cls,fn){const b=dvEl('button','b'+(cls?' '+cls:''),txt);b.type='button';b.onclick=fn;return b}
function dvZeit(s){if(!s)return'';const d=new Date(s*1000);return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'numeric'})+' '+d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'})}
// GitHub's "Tests" of a branch (entwickeln.GH_TESTS) and the internet (entwickelnseite.seite): fixed words
const DV_TESTS={gruen:[['grün','green'],'ok'],laeuft:[['laufen','running'],'read'],rot:[['rot','red'],'err'],unbekannt:[['unbekannt','unknown'],'off']};
const DV_NETZ={da:[['da','there'],'ok'],weg:[['weg','gone'],'bad'],unbekannt:[['nicht geprüft','not checked'],'']};
const DV_ENDE={leerlauf:['Leerlauf: die Sitzung ist zu.','Idle: the session is closed.'],grenze:['Die längste Sitzung ist um.','The longest session is over.'],
  notaus:['Notaus: das Terminal ist zu.','Emergency stop: the terminal is closed.'],aus:['Terminal im Browser ist aus.','Terminal in the browser is off.'],
  zu_gross:['Zu viel auf einmal eingefügt (höchstens 64 KB).','Too much pasted at once (64 KB at most).'],beendet:['Sitzung beendet.','Session ended.'],
  fenster:['Getrennt.','Disconnected.'],abmelden:['Abgemeldet: die Sitzung ist zu.','Signed out: the session is closed.'],
  start:['Das Terminal konnte nicht starten (sudo ./install.sh --entwickeln einmal neu).','The terminal could not start (sudo ./install.sh --entwickeln once again).'],
  voll:['Es ist schon ein Terminal offen.','A terminal is open already.'],ticket:['Die Freigabe ist abgelaufen: noch einmal öffnen.','The permit expired: open again.']};
// the way of a change, from the order to GitHub (the picture „Ablauf“): fixed steps
const DV_ABLAUF=[[['Auftrag','Order'],['im Terminal mit OpenCode','in the terminal with OpenCode']],[['Commit auf lokal','Commit on lokal'],['OpenCode oder du, als spark-dev','OpenCode or you, as spark-dev']],
  [['Schnelltest offline','Quick test offline'],['betroffene Tests und Wächter, ohne Netz und Browser','affected tests and guards, no network, no browser']],
  [['Lokal einspielen','Install locally'],['„+lokal“, die alte Version bleibt zum Zurückgehen','"+lokal", the old version stays to go back']],
  [['An GitHub geben','Hand to GitHub'],['Zweig opencode/…, Claude prüft, dann main','branch opencode/…, Claude reviews, then main']]];
function werkTab(k,still){document.querySelectorAll('#werktabs button').forEach(b=>b.classList.toggle('on',b.dataset.wt===k));
  $('wkbox').hidden=k!=='werk';$('dvbox').hidden=k!=='dev';if(!still)try{localStorage.setItem('werktab',k)}catch{}
  if(k!=='dev'&&window.leisteSetzen)leisteSetzen(null);
  if(k==='dev')dvLoad();else if(window.wkLoad)wkLoad()}
function dvOpen(){let k='werk';try{k=localStorage.getItem('werktab')||'werk'}catch{}werkTab(k==='dev'?'dev':'werk',true)}
document.querySelectorAll('#werktabs button').forEach(b=>b.onclick=()=>werkTab(b.dataset.wt));
document.querySelectorAll('#dvseg button').forEach(b=>b.onclick=()=>dvAnsicht(b.dataset.dv));
// ⓘ beside the title: the page's sentence (.pintro) as its title; in the terminal, where the sentence is folded away, a click shows it
$('dvinfo').onclick=()=>{const b=$('dvbox'),an=!b.classList.contains('dvintro');b.classList.toggle('dvintro',an);$('dvinfo').setAttribute('aria-expanded',an?'true':'false');dvHoehe();dvGroesseSenden()};
$('dvinfo').title=document.querySelector('#dvbox>.pintro').textContent;
function dvAnsicht(k){DV.ansicht=k;document.querySelectorAll('#dvseg button').forEach(b=>b.classList.toggle('on',b.dataset.dv===k));
  $('dvueber').hidden=k!=='ueber';$('dvterm').hidden=k!=='term';$('dvbox').classList.toggle('dvtermansicht',k==='term');
  $('dvbox').classList.toggle('ld-sel',k==='ueber'&&!$('dvdetail').hidden);   // on the phone .ld-sel would hide the terminal (Dominik 2026-11-04)
  if(DV.d)dvShow();else if(k==='term')dvTermSeite();if(k!=='term'&&window.leisteSetzen)leisteSetzen(null);if(k==='term'&&DV.term)setTimeout(dvGroesseSenden,50)}
async function dvLoad(){clearTimeout(DV.timer);const box=$('dvbox');if(!box||document.body.classList.contains('mgr'))return;
  if(box.offsetParent){try{const d=await (await api('/api/admin/entwickeln')).json();
      DV.gh=d.an&&d.github_an?await (await api('/api/admin/entwickeln/github')).json():null;
      DV.ca=d.an&&d.auftrag_an?await (await api('/api/admin/entwickeln/auftraege')).json():null;DV.d=d;dvShow();$('dvmsg').textContent=''}
    catch(e){$('dvmsg').textContent=e.message}}
  DV.timer=setTimeout(dvLoad,DV.d&&DV.d.update?5000:30000)}
function dvChip(txt,cls){const c=dvEl('span','dvchip'+(cls?' '+cls:''));if(cls==='ok'||cls==='bad')c.appendChild(dvEl('i'));c.appendChild(document.createTextNode(txt));return c}
function dvShow(){const d=DV.d;if(!d)return;$('dvoff').hidden=!!d.an;
  const ch=$('dvchips');ch.textContent='';const n=DV_NETZ[d.internet]||DV_NETZ.unbekannt;
  ch.appendChild(dvChip(t('Internet: ','Internet: ')+dvT(n[0]),n[1]));if(d.version)ch.appendChild(dvChip(d.version,'ver'));
  ch.appendChild(dvChip(t('Admin-Schalter: ','Admin switch: ')+(d.an?t('an','on'):t('aus','off'))));
  if(DV.ansicht!=='ueber')return dvTermSeite();
  dvList();dvDetail()}
// the left side: what can be chosen, filtered by the search
function dvZeilen(){const d=DV.d,g=DV.gh,z=[];
  z.push({grp:t('Lokale Änderungen','Local changes'),n:d.anzahl||0,id:'lokal',ic:'dev',b:t('Zweig lokal · ','Branch lokal · ')+(d.anzahl||0)+t(' Commits',' commits'),
    s:d.anzahl?t('läuft als ','runs as ')+(d.version||'+lokal'):t('nichts eingespielt','nothing installed'),
    badge:d.offen?[d.offen+t(' neu im Klon',' new in the clone'),'due']:d.anzahl?['+lokal','read']:null});
  if(g)for(const x of g.zweige||[]){const ts=DV_TESTS[x.tests]||DV_TESTS.unbekannt;
    z.push({grp:t('Zweige auf GitHub','Branches on GitHub'),n:(g.zweige||[]).length,id:'gh:'+x.zweig,ic:'up',b:x.zweig,s:t('GitHub-Tests ','GitHub tests ')+dvT(ts[0])+' · '+dvZeit(x.t),badge:[dvT(ts[0]),ts[1]]})}
  const ca=(DV.ca&&DV.ca.auftraege)||[];
  for(const x of ca){const st=DV_CA[x.zustand]||DV_CA.abgelehnt;
    z.push({grp:t('Code-Aufträge','Code orders'),n:ca.length,id:'ca:'+x.id,ic:'llm',b:x.ziel||x.zweig,s:x.zweig+' · '+dvZeit(x.t),badge:[dvT(st[0]),st[1]]})}
  const an=w=>w?t('an','on'):t('aus','off');
  [['set:an','gear',t('Entwickeln auf dem Pi','Develop on the Pi'),t('Admin-Schalter · nur Admins','Admin switch · admins only'),an(d.an)],
   ['set:github','up',t('An GitHub geben','Hand to GitHub'),t('nur Zweige opencode/…, nie main','only branches opencode/…, never main'),an(d.github_an)],
   ['set:terminal','dev',t('Terminal im Browser','Terminal in the browser'),t('Shell als spark-dev, frischer Code','shell as spark-dev, fresh code'),an(d.terminal_an)],
   ['set:auftrag','llm',t('Code-Auftrag im Chat','Code order in the chat'),t('nur Admin, nur getippt','admins only, typed only'),an(d.auftrag_an)],
   ['set:modell','llm',t('Modell und Grenzen','Model and limits'),t('eigenes Sprachmodell · Stufe hinten','own language model · stage last'),'OpenCode '+(d.opencode_version||'')],
   ['set:zugang','key',t('Zugang spark-dev','Access spark-dev'),t('kein Passwort, kein sudo, Netz nur zum LLM-Tor','no password, no sudo, network only to the LLM-Tor'),'']].forEach(([id,ic,b,s,r])=>
    z.push({grp:t('Einstellungen','Settings'),n:6,id,ic,b,s,right:r}));
  return z}
function dvList(){const box=$('dvlist');box.textContent='';
  const q=dvEl('input');q.type='search';q.className='dvsuche';q.placeholder=t('Änderungen und Zweige suchen …','Search changes and branches …');q.setAttribute('aria-label',q.placeholder);q.value=DV.such;
  q.oninput=()=>{DV.such=q.value;dvRows(rows)};box.appendChild(q);const rows=dvEl('div');box.appendChild(rows);dvRows(rows)}
function dvRows(box){box.textContent='';const f=DV.such.trim().toLocaleLowerCase();let grp='';
  for(const z of dvZeilen()){if(f&&!(z.b+' '+z.s).toLocaleLowerCase().includes(f))continue;
    if(z.grp!==grp){grp=z.grp;const h=dvEl('div','ld-grp');h.appendChild(dvEl('span','',z.grp));h.appendChild(dvEl('span','',String(z.n)));box.appendChild(h)}
    const r=dvEl('div','ld-row'+(DV.sel===z.id?' on':''));r.tabIndex=0;r.dataset.id=z.id;const ik=dvEl('span','ld-ico');ik.appendChild(icNode(z.ic));r.appendChild(ik);
    const m=dvEl('div','ld-mid');m.appendChild(dvEl('b','',z.b));m.appendChild(dvEl('small','',z.s));r.appendChild(m);
    const rt=dvEl('div','ld-right');if(z.badge)rt.appendChild(dvEl('span','ld-badge '+z.badge[1],z.badge[0]));else if(z.right)rt.appendChild(dvEl('span','ld-when',z.right));r.appendChild(rt);
    r.onclick=()=>dvPick(z.id);r.onkeydown=e=>{if(e.key==='Enter')dvPick(z.id)};box.appendChild(r)}
  if(!box.childElementCount)box.appendChild(dvEl('div','mut ld-empty',t('Nichts gefunden.','Nothing found.')))}
function dvPick(id){DV.sel=id;DV.thema=false;dvList();dvDetail();if(NARROW())window.scrollTo(0,0)}
function dvZurueck(){DV.sel='';$('dvdetail').hidden=true;$('dvbox').classList.remove('ld-sel');dvList()}
function dvKopf(det,titel,unter){if(NARROW())det.appendChild(dvBtn('‹ '+t('Entwickeln','Develop'),'ld-back',dvZurueck));
  det.appendChild(dvEl('h3','',titel));if(unter)det.appendChild(dvEl('div','mut wkunter',unter))}
function dvErkl(det,teile,cls){const e=dvEl('div','wkerkl'+(cls?' '+cls:''));e.appendChild(dvEl('b','',teile[0]+' '));e.appendChild(document.createTextNode(teile[1]));det.appendChild(e)}
function dvDetail(){const det=$('dvdetail'),box=$('dvbox'),d=DV.d;if(!det||!d)return;
  if(!DV.sel&&!NARROW())DV.sel='lokal';
  det.hidden=!DV.sel;box.classList.toggle('ld-sel',!det.hidden);det.textContent='';if(det.hidden)return;
  if(DV.sel==='lokal')return dvLokal(det);
  if(DV.sel.startsWith('gh:'))return dvZweig(det,DV.sel.slice(3));
  if(DV.sel.startsWith('ca:'))return dvAuftrag(det,DV.sel.slice(3));
  return dvEinst(det,DV.sel.slice(4))}
function dvKachel(kopf,wert,unter,cls,extra,clip){const k=dvEl('div','dvtile');k.appendChild(dvEl('span','dvtk',kopf));const w=dvEl('b','dvtw'+(cls?' '+cls:''));
  if(cls==='ok'||cls==='bad'||cls==='warn')w.appendChild(dvEl('i'));w.appendChild(dvEl('span','dvtv',wert));if(extra)w.appendChild(dvEl('span','ld-badge read',extra));k.appendChild(w);
  k.appendChild(dvEl('small',clip?'dvtclip':'',unter));return k}
function dvLokal(det){const d=DV.d,g=DV.gh,ver=(d.version||'').replace(/\+lokal$/,'');
  dvKopf(det,t('Lokale Änderungen','Local changes'),t('Commits auf dem Zweig lokal im Klon von spark-dev. Eingespielt laufen sie auf dem Pi, auf GitHub sind sie erst nach „An GitHub geben“.','Commits on the branch lokal in spark-dev\'s clone. Installed they run on the Pi; they reach GitHub only after "Hand to GitHub".'));
  const k=dvEl('div','dvtiles'),n=DV_NETZ[d.internet]||DV_NETZ.unbekannt,z0=g&&(g.zweige||[])[0];
  k.appendChild(dvKachel(t('Läuft als','Runs as'),ver||'–',d.vorher?t('die vorige Fassung bleibt zum Zurückgehen','the previous state stays to go back'):d.anzahl?t('ohne vorige lokale Fassung','no previous local state'):t('ohne lokale Änderungen','without local changes'),'',d.anzahl?'+lokal':''));
  k.appendChild(dvKachel(t('Internet','Internet'),dvT(n[0]),t('Einspielen geht ohne, An GitHub geben braucht es','Installing works without, handing to GitHub needs it'),n[1]));
  const ts=z0?DV_TESTS[z0.tests]||DV_TESTS.unbekannt:null;
  k.appendChild(dvKachel('GitHub',z0?dvT(ts[0]):d.github_an?t('nichts gegeben','nothing handed'):t('aus','off'),z0?z0.zweig:t('Ein Claude-Thread prüft Zweige opencode/…','A Claude thread reviews branches opencode/…'),z0?{ok:'ok',err:'bad',read:'warn'}[ts[1]]||'':'',null,!!z0));
  det.appendChild(k);
  const lz=d.letzter;
  if(lz&&lz.ergebnis!=='ok'&&lz.text)dvErkl(det,[t('Zuletzt abgelehnt:','Last refused:'),dvT(lz.text)+((lz.rot||[]).length?t(' Rot: ',' Red: ')+lz.rot.slice(0,5).join(', '):'')],'bad');
  else if(lz&&lz.ergebnis==='ok')dvErkl(det,[t('Zuletzt:','Last:'),{einspielen:t('eingespielt','installed'),zurueck:t('zurückgegangen','went back'),verwerfen:t('verworfen','dropped'),aufsetzen:t('mit dem Update aufgesetzt','rebased with the update')}[lz.art]+' · '+dvZeit(lz.t)+(lz.module?' · '+lz.module+t(' Testmodule grün',' test modules green'):'')],'ok');
  if(d.offen)dvErkl(det,[d.offen===1?t('1 neuer Commit im Klon.','1 new commit in the clone.'):d.offen+t(' neue Commits im Klon.',' new commits in the clone.'),t('Noch nicht eingespielt: „Lokal einspielen“ prüft und testet sie zuerst.','Not installed yet: "Install locally" checks and tests them first.')]);
  det.appendChild(dvEl('div','wkh',t('Commits auf lokal','Commits on lokal')+' ('+(d.anzahl||0)+')'));
  const cs=d.commits||[];
  if(!cs.length)det.appendChild(dvEl('div','mut',d.anzahl?t('Die Liste kommt mit dem nächsten Einspielen oder sudo speech-spark lokal status.','The list comes with the next install or sudo speech-spark lokal status.'):t('Keine lokalen Änderungen eingespielt.','No local changes installed.')));
  else{const l=dvEl('div','dvcommits');for(const c of cs){const r=dvEl('div','dvcommit');r.appendChild(dvEl('code','',c.kurz));const m=dvEl('div','ld-mid');
      m.appendChild(dvEl('b','',c.titel||t('(ohne Titel)','(no title)')));const s=dvEl('small');s.appendChild(document.createTextNode(c.dateien+(c.dateien===1?t(' Datei ',' file '):t(' Dateien ',' files '))));
      s.appendChild(dvEl('span','wkplus','+'+c.plus));s.appendChild(document.createTextNode(' '));s.appendChild(dvEl('span','wkminus','−'+c.minus));m.appendChild(s);r.appendChild(m);l.appendChild(r)}
    det.appendChild(l)}
  const acts=dvEl('div','ld-acts'),aus=!d.an||d.update;
  const ein=dvBtn(t('Lokal einspielen','Install locally'),'p',e=>dvWunsch('einspielen',e.currentTarget));ein.disabled=aus||d.offen===0;codeLock(ein,'protect');acts.appendChild(ein);
  if(d.github_an){const gb=dvBtn(t('An GitHub geben','Hand to GitHub'),'',()=>{DV.thema=!DV.thema;dvDetail()});gb.disabled=aus;acts.appendChild(gb)}
  const zu=dvBtn(t('Zurück zur alten Version','Back to the old version'),'',e=>dvWunsch('zurueck',e.currentTarget));zu.disabled=aus||!d.vorher;codeLock(zu,'confirm');acts.appendChild(zu);
  const vw=dvBtn(t('Verwerfen …','Drop …'),'danger',e=>dvWunsch('verwerfen',e.currentTarget));vw.disabled=aus||!d.anzahl;codeLock(vw,'confirm');acts.appendChild(vw);
  det.appendChild(acts);
  if(DV.thema)dvThema(det);
  det.appendChild(dvEl('div','mut wkunter',d.update?t('Ein Update läuft gerade; die Knöpfe warten darauf.','An update is running; the buttons wait for it.')
    :t('Einspielen, Zurück und Verwerfen laufen wie ein kleines Update: Sicherung zuerst, dann startet meist nur das Panel neu. Das Modell schlägt nur vor; einspielen entscheidest du.','Install, back and drop run like a small update: a backup first, then mostly only the panel restarts. The model only proposes; you decide what is installed.')));
  dvAblauf(det)}
function dvThema(det){const f=dvEl('div','dvthema');const lb=dvEl('label','',t('Thema des Zweigs (a-z, 0-9, Bindestrich)','Topic of the branch (a-z, 0-9, hyphen)'));lb.htmlFor='dvthema';
  const i=dvEl('input');i.id='dvthema';i.maxLength=40;i.autocomplete='off';i.placeholder=t('z. B. hilfe-wetter','e.g. help-weather');f.appendChild(lb);f.appendChild(i);
  const go=dvBtn(t('Weitergeben','Hand over'),'p',e=>dvGithub(i.value,e.currentTarget));codeLock(go,'protect');f.appendChild(go);
  f.appendChild(dvEl('div','mut wkunter',t('Der Zweig geht als opencode/<thema> an GitHub, nie an main. Ohne Internet wartet er und geht von selbst, sobald GitHub erreichbar ist.','The branch goes to GitHub as opencode/<topic>, never to main. Without the internet it waits and goes by itself once GitHub answers.')));
  det.appendChild(f);if(!NARROW())i.focus()}
function dvAblauf(det){det.appendChild(dvEl('div','wkh',t('Ablauf','How it goes')));const a=dvEl('ol','dvablauf');
  DV_ABLAUF.forEach(([h,s],i)=>{const li=dvEl('li','dvschritt'+(i===4?' net':''));li.appendChild(dvEl('span','dvnr',String(i+1)));li.appendChild(dvEl('b','',dvT(h)));li.appendChild(dvEl('small','',dvT(s)));a.appendChild(li)});
  det.appendChild(a);det.appendChild(dvEl('div','mut wkunter',t('Schritte 1 bis 4 gehen ohne Internet, Schritt 5 braucht es. Kommt vorher ein Update, setzt es die lokalen Commits auf die neue Version; passen sie nicht, bleibt die laufende Version und oben im Panel steht ein Hinweis.','Steps 1 to 4 work without the internet, step 5 needs it. If an update comes first, it puts the local commits on the new version; if they do not fit, the running version stays and a note shows on top of the panel.')))}
function dvZweig(det,zweig){const g=DV.gh||{},x=(g.zweige||[]).find(z=>z.zweig===zweig);if(!x){DV.sel='lokal';return dvLokal(det)}
  const ts=DV_TESTS[x.tests]||DV_TESTS.unbekannt;dvKopf(det,x.zweig,t('an GitHub gegeben ','handed to GitHub ')+dvZeit(x.t));
  const dl=dvEl('dl','ld-facts');[[t('Commit','Commit'),x.kopf],[t('Commits','Commits'),String(x.anzahl)],[t('GitHub-Tests','GitHub tests'),dvT(ts[0])]].forEach(([k,v])=>{dl.appendChild(dvEl('dt','',k));dl.appendChild(dvEl('dd','',v))});det.appendChild(dl);
  const h=t('Gib den Zweig ','Give the branch ')+x.zweig+t(' einem Claude-Thread zum Prüfen',' to a Claude thread to review')+(x.link?': '+x.link:'');
  dvErkl(det,[t('Wie weiter:','What next:'),t('Ein Claude-Thread prüft den Zweig gegen Richtlinie und Sicherheits-Checkliste und bringt ihn auf main. Kommt danach ein Update, fallen die eingespielten lokalen Commits, die schon drin sind, von selbst weg.','A Claude thread reviews the branch against the guideline and the security checklist and brings it onto main. When an update comes afterwards, installed local commits that are part of it drop out by themselves.')]);
  const acts=dvEl('div','ld-acts');acts.appendChild(dvBtn(t('Hinweis für Claude kopieren','Copy the note for Claude'),'p',e=>copyString(h,e.currentTarget)));
  if(x.link){const a=dvEl('a','b',t('Auf GitHub ansehen','View on GitHub'));a.href=x.link;a.target='_blank';a.rel='noopener noreferrer';acts.appendChild(a)}
  det.appendChild(acts)}
function dvEinst(det,k){const d=DV.d,a=w=>w?t('an','on'):t('aus','off');
  const T={an:[t('Entwickeln auf dem Pi','Develop on the Pi'),[t('Admin-Schalter: ','Admin switch: ')+a(d.an)+'.',t('Ein- und ausschalten unter Funktionen → Entwickeln auf dem Pi. Aus heißt: der Schlüssel von spark-dev gilt am LLM-Tor nicht mehr, einspielen geht nicht; eingespielte Änderungen laufen weiter, bis du sie verwirfst.','Switch on and off under Features → Develop on the Pi. Off means: spark-dev\'s key no longer works at the LLM-Tor, installing does not work; installed changes keep running until you drop them.')]],
    github:[t('An GitHub geben','Hand to GitHub'),[t('Schalter: ','Switch: ')+a(d.github_an)+'.',t('Unter Funktionen → Entwickeln auf dem Pi → An GitHub geben. Root schiebt den Zweig mit einem eigenen Deploy-Schlüssel nur nach opencode/…, nie nach main; spark-dev selbst bekommt nie Internet.','Under Features → Develop on the Pi → Hand to GitHub. Root pushes the branch with a deploy key of its own only to opencode/…, never to main; spark-dev itself never gets the internet.')]],
    terminal:[t('Terminal im Browser','Terminal in the browser'),[t('Schalter: ','Switch: ')+a(d.terminal_an)+'.',t('Unter Funktionen → Entwickeln auf dem Pi → Terminal im Browser. Eine Shell als spark-dev hier auf der Seite (Reiter Terminal), jede Sitzung mit frischem Code; sie endet nach '+(d.leerlauf_min||60)+' Minuten ohne Tastendruck und Ausgabe.','Under Features → Develop on the Pi → Terminal in the browser. A shell as spark-dev right on this page (tab Terminal), a fresh code for every session; it ends after '+(d.leerlauf_min||60)+' minutes without a key or output.')]],
    auftrag:[t('Code-Auftrag im Chat','Code order in the chat'),[t('Schalter: ','Switch: ')+a(d.auftrag_an)+'.',t('Unter Funktionen → Entwickeln auf dem Pi → Code-Auftrag im Chat. Ein Admin tippt im Assistenten im Panel oder in der App, was sich ändern soll („Code-Auftrag: …“); OpenCode arbeitet einmal als spark-dev auf einem eigenen Zweig, die Karte und diese Seite zeigen den Vorschlag. Nie über Lautsprecher, Auto, Telegram oder Gäste.','Under Features → Develop on the Pi → Code order in the chat. An admin types in the assistant in the panel or the app what should change ("Code order: …"); OpenCode works once as spark-dev on a branch of its own, the card and this page show the proposal. Never over speakers, the car, Telegram or guests.')]],
    modell:[t('Modell und Grenzen','Model and limits'),[t('OpenCode ','OpenCode ')+(d.opencode_version||'')+(d.opencode?'':t(' fehlt',' missing'))+'.',t('OpenCode fragt das eigene Sprachmodell über das LLM-Tor mit eigenem Schlüssel, immer ganz hinten in der Reihe: wer spricht, geht vor. Welches Modell läuft, steht unter Zustand → Modelle.','OpenCode asks the own language model through the LLM-Tor with its own key, always last in line: whoever speaks goes first. Which model runs shows under Status → Models.')]],
    zugang:[t('Zugang spark-dev','Access spark-dev'),[t('Eigener Nutzer.','Its own user.'),t('spark-dev hat kein Passwort und kein sudo, sieht weder Tresor noch Profile noch /var/lib/speech-spark und erreicht nur das LLM-Tor. Per SSH: deinen öffentlichen Schlüssel nach /home/spark-dev/.ssh/authorized_keys, dann ssh spark-dev@<Panel-Rechner> und spark-opencode. Die Anleitung steht unter Funktionen → Entwickeln auf dem Pi.','spark-dev has no password and no sudo, sees neither vault nor profiles nor /var/lib/speech-spark and reaches only the LLM-Tor. Over SSH: your public key into /home/spark-dev/.ssh/authorized_keys, then ssh spark-dev@<panel computer> and spark-opencode. The guide is under Features → Develop on the Pi.')]]}[k];
  if(!T){DV.sel='lokal';return dvLokal(det)}dvKopf(det,T[0]);dvErkl(det,T[1])}
async function dvWunsch(art,btn){const frage={einspielen:t('Die neuen Commits von spark-dev prüfen, im Sandkasten testen und wie ein Update einspielen?','Check the new commits of spark-dev, test them in the sandbox and install them like an update?'),
    zurueck:t('Zurück zu der Fassung vor dem letzten lokalen Einspielen?','Back to the state before the last local install?'),
    verwerfen:t('Die eingespielten lokalen Änderungen verwerfen? Danach läuft die Version ohne sie; die Commits bleiben im Klon von spark-dev.','Drop the installed local changes? Afterwards the version runs without them; the commits stay in spark-dev\'s clone.')}[art];
  if(!confirm(frage))return;btn.disabled=true;$('dvmsg').textContent=t('Einen Moment …','One moment …');
  try{await api('/api/admin/entwickeln/'+art,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    $('dvmsg').textContent=t('Gestartet: Fortschritt unter Einstellungen → Update.','Started: progress under Settings → Update.');dvLoad()}
  catch(e){$('dvmsg').textContent=e.message;btn.disabled=false}}
async function dvGithub(thema,btn){btn.disabled=true;$('dvmsg').textContent=t('Einen Moment …','One moment …');
  try{const r=await (await api('/api/admin/entwickeln/github',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({thema})})).json();
    DV.thema=false;$('dvmsg').textContent=t('Gestartet: ','Started: ')+r.zweig;dvLoad()}
  catch(e){$('dvmsg').textContent=e.message;btn.disabled=false}}
// ---------------------------------------------------------------- a Code-Auftrag from the chat (codeauftrag.py)
const DV_CA={laeuft:[['läuft','running'],'read'],fertig:[['Vorschlag','proposal'],'due'],leer:[['nichts geändert','nothing changed'],'off'],
  abgelehnt:[['nicht gemacht','not done'],'err'],lokal:[['auf lokal','on lokal'],'ok'],verworfen:[['verworfen','dropped'],'off']};
function dvAuftrag(det,aid){const x=((DV.ca&&DV.ca.auftraege)||[]).find(y=>y.id===aid);if(!x){DV.sel='lokal';return dvLokal(det)}
  const st=DV_CA[x.zustand]||DV_CA.abgelehnt;
  dvKopf(det,t('Code-Auftrag (OpenCode)','Code order (OpenCode)'),t('OpenCode hat als spark-dev auf dem eigenen Zweig ','OpenCode worked as spark-dev on its own branch ')+x.zweig+t(' gearbeitet. Das Modell schlägt nur vor. Einspielen entscheidest du.','. The model only proposes. You decide what is installed.'));
  dvErkl(det,[t('Ziel:','Goal:'),x.ziel]);
  const k=dvEl('div','dvtiles');k.appendChild(dvKachel(t('Stand','State'),dvT(st[0]),x.grund?'':dvZeit(x.t),{ok:'ok',err:'bad',due:'warn'}[st[1]]||''));
  k.appendChild(dvKachel(t('Dateien','Files'),String(x.dateien||0),'+'+(x.plus||0)+' −'+(x.minus||0)));
  k.appendChild(dvKachel(t('Zweig','Branch'),'opencode/…',x.zweig,'',null,true));det.appendChild(k);
  if(x.grund&&DV_CA_GRUND[x.grund])dvErkl(det,[t('Grund:','Reason:'),dvT(DV_CA_GRUND[x.grund])],'bad');
  if(x.diff){det.appendChild(dvEl('div','wkh',t('Änderung','Change')+(x.gekuerzt?t(' (gekürzt)',' (cut)'):'')));det.appendChild(dvEl('pre','dvdiff',x.diff))}
  const acts=dvEl('div','ld-acts'),fertig=x.zustand==='fertig';
  const ein=dvBtn(t('Lokal einspielen','Install locally'),'p',e=>dvCa('lokal',x,e.currentTarget));ein.disabled=!fertig;codeLock(ein,'protect');acts.appendChild(ein);
  if(DV.d.github_an){const gh=dvBtn(t('An GitHub geben','Hand to GitHub'),'',e=>dvGithub(x.zweig.slice(9),e.currentTarget));gh.disabled=!fertig;codeLock(gh,'protect');acts.appendChild(gh)}
  const weg=dvBtn(t('Verwerfen …','Drop …'),'danger',e=>dvCa('verwerfen',x,e.currentTarget));weg.disabled=!fertig;codeLock(weg,'confirm');acts.appendChild(weg);
  if(DV.d.terminal_an)acts.appendChild(dvBtn(t('Im Terminal weitermachen','Go on in the terminal'),'',()=>dvAnsicht('term')));
  det.appendChild(acts);
  det.appendChild(dvEl('div','mut wkunter',t('Lokal einspielen setzt lokal auf diesen Zweig und spielt dann wie gewohnt ein (Schnelltest, wie ein Update). An GitHub geben schickt den Zweig ','Install locally moves lokal onto this branch and then installs as usual (quick test, like an update). Hand to GitHub sends the branch ')+x.zweig+t(' an GitHub, nie an main.',' to GitHub, never to main.')))}
const DV_CA_GRUND={aus:['Code-Auftrag ist aus.','The code order is off.'],laeuft:['Es lief schon ein Code-Auftrag.','A code order was running already.'],
  klon:['Der Klon von spark-dev fehlt oder hat keinen Zweig lokal.','spark-dev\'s clone or its branch lokal is missing.'],opencode:['OpenCode lief nicht durch (Sprachmodell erreichbar?).','OpenCode did not finish (language model reachable?).'],
  zeit:['OpenCode brauchte zu lange.','OpenCode took too long.'],leer:['OpenCode hat nichts geändert.','OpenCode changed nothing.'],
  konflikt:['Passt nicht mehr auf lokal.','No longer fits onto lokal.'],weg:['Den Zweig gibt es nicht mehr.','The branch is gone.'],fehler:['Ging schief (sudo speech-spark logs entwickeln).','Failed (sudo speech-spark logs entwickeln).']};
async function dvCa(art,x,btn){const frage={lokal:t('Diesen Vorschlag auf lokal übernehmen, im Sandkasten testen und wie ein Update einspielen?','Take this proposal onto lokal, test it in the sandbox and install it like an update?'),
    verwerfen:t('Den Zweig dieses Vorschlags löschen? Eingespielt war nichts.','Delete this proposal\'s branch? Nothing was installed.')}[art];
  if(!confirm(frage))return;btn.disabled=true;$('dvmsg').textContent=t('Einen Moment …','One moment …');
  try{await api('/api/admin/entwickeln/auftrag/'+art,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id})});
    $('dvmsg').textContent=art==='lokal'?t('Gestartet: Fortschritt unter Einstellungen → Update.','Started: progress under Settings → Update.'):t('Wird verworfen.','Being dropped.');dvLoad()}
  catch(e){$('dvmsg').textContent=e.message;btn.disabled=false}}
// ---------------------------------------------------------------- the terminal (entwickelnseite.terminal_ws)
// Compact (Dominik 2026-11-04 „nimmt alles zu viel Platz ein“): one bar is the terminal's head: what runs and where,
// the pills of the page's alerts and code (leisteSetzen, admin.js), „Fertig?“ (a popover with the session's facts),
// full screen and „Sitzung beenden“. The terminal fills the window's remaining height (dvHoehe) and OpenCode starts in
// it at once (entwickeln.TERM_START); quitting OpenCode leaves the shell. On the phone a row of keys (FZ_KEYS).
function dvTermSeite(){const box=$('dvterm');if(!box)return;
  if(!box.firstChild){const tb=dvEl('div','dvtermbox');tb.id='dvtermbox';tb.dataset.lpop='1';const bar=dvEl('div','dvleiste');
    const nm=dvEl('span','dvlname');nm.id='dvlname';const fakt=dvEl('span','dvlfakt');fakt.id='dvlfakt';const pills=dvEl('span','dvlpills');pills.id='dvlpills';
    const fertig=dvEl('button','lpill',t('Fertig?','Done?'));fertig.type='button';fertig.id='dvfertig';fertig.setAttribute('aria-haspopup','dialog');fertig.onclick=()=>leistePop(fertig,dvFertig);
    const voll=dvEl('button','dvlknopf');voll.type='button';voll.id='dvvoll';voll.appendChild(icNode('expand'));voll.onclick=dvVoll;
    const ende=dvEl('button','dvlende');ende.type='button';ende.id='dvende';ende.onclick=dvTermBeenden;
    bar.append(nm,fakt,pills,fertig,voll,ende);const x=dvEl('div','dvxterm');x.id='dvxterm';const k=dvEl('div','dvtasten');k.id='dvtasten';
    tb.append(bar,x,k);box.appendChild(tb);addEventListener('resize',()=>{dvHoehe();dvGroesseSenden()});document.addEventListener('fullscreenchange',dvVollGeaendert)}
  if(!DV.term)dvTermLeer();dvLeiste()}
function dvLeiste(){const d=DV.d||{};if(!$('dvlname'))return;
  leisteSetzen(!$('dvterm').hidden&&!$('dvbox').hidden&&document.querySelector('section#werk.on')?$('dvlpills'):null);
  $('dvlname').textContent='';const pk=dvEl('i');pk.classList.toggle('an',!!DV.term);$('dvlname').append(pk,DV.term?dvEl('span','lplang',t('OpenCode · eigenes Modell','OpenCode · own model')):'Terminal',DV.term?dvEl('span','lpkurz','OpenCode'):'');
  $('dvlfakt').textContent=[t('Panel-Rechner','panel computer'),'spark-dev',t('Zweig ','branch ')+(d.zweig||'lokal')+(d.offen?' · '+d.offen+t(' neu',' new'):''),t('Modell Stufe hinten','model stage last'),t('Leerlauf ','idle ')+(d.leerlauf_min||60)+' min'].join(' · ');
  const offen=!DV.term&&d.terminal&&d.terminal.offen;$('dvende').hidden=!DV.term&&!offen;const el=$('dvende'),lang=offen?t('Offene Sitzung beenden','End the open session'):t('Sitzung beenden','End the session');el.textContent='';el.append(dvEl('span','lplang',lang),dvEl('span','lpkurz',t('Ende','End')));el.title=lang;
  const v=t('Vollbild','Full screen');$('dvvoll').hidden=!DV.term||!document.fullscreenEnabled||NARROW();$('dvvoll').title=v;$('dvvoll').setAttribute('aria-label',v);
  $('dvinfo').title=document.querySelector('#dvbox>.pintro').textContent;dvTasten();dvHoehe()}
// „Fertig?“: what to do next and where this shell stands (the old side column), the hint without sudo
function dvFertig(p){const d=DV.d||{};p.appendChild(dvEl('h4','',t('Fertig?','Done?')));
  p.appendChild(dvEl('p','',t('Committe in OpenCode oder mit git commit. Danach steht der Commit im Reiter Übersicht bei den lokalen Änderungen, mit „Lokal einspielen“.','Commit in OpenCode or with git commit. Then the commit shows in the tab Overview with the local changes, with "Install locally".')));
  const dl=dvEl('dl','ld-facts');[[t('Rechner','Computer'),t('Panel-Rechner','panel computer')],[t('Nutzer','User'),t('spark-dev, nie der Panel-Nutzer','spark-dev, never the panel user')],[t('Ordner','Folder'),'~/speech-on-dgx-spark'],
    [t('Zweig','Branch'),d.zweig||'lokal'],[t('Modell','Model'),t('eigenes Sprachmodell · Stufe hinten','own language model · stage last')],[t('Netz','Network'),t('nur LLM-Tor','LLM-Tor only')],
    [t('Befehle','Commands'),t('OpenCode fragt vorher','OpenCode asks first')],[t('Neu starten','Start again'),'opencode']].forEach(([k,v])=>{dl.appendChild(dvEl('dt','',k));dl.appendChild(dvEl('dd','',v))});
  p.appendChild(dl);const s=dvEl('p','mut',t('Kein sudo hier: Update und Installation als dein Admin-Nutzer per SSH oder unter ','No sudo here: updates and installing as your admin user over SSH or under '));
  s.appendChild(wayEl(t('Fernzugang','Remote access'),t('Fernzugang','Remote access')));s.appendChild(document.createTextNode(t('. Kein Zugriff auf Tresor, Profile und /var/lib/speech-spark; der Assistent sieht nie, was hier läuft.','. No access to the vault, profiles and /var/lib/speech-spark; the assistant never sees what runs here.')));p.appendChild(s)}
// the terminal as high as the window allows (like the Fernzugang's fzLayout): the page itself never scrolls
function dvHoehe(){const x=$('dvxterm');if(!x)return;if($('dvterm').hidden||!document.querySelector('section#werk.on')){x.style.removeProperty('--dvh');return}
  if(document.fullscreenElement===$('dvtermbox')){x.style.setProperty('--dvh',Math.max(200,innerHeight-x.getBoundingClientRect().top-$('dvtasten').offsetHeight)+'px');return}
  const unten=NARROW()?(($('aptabs')&&$('aptabs').offsetHeight)||0)+8:12,min=NARROW()?240:300;document.documentElement.style.setProperty('--leiste-unten',unten+'px');
  let h=Math.max(min,Math.floor(innerHeight-x.getBoundingClientRect().top-$('dvtasten').offsetHeight-unten));x.style.setProperty('--dvh',h+'px');
  const over=document.documentElement.scrollHeight-innerHeight;if(over>0){h=Math.max(min,h-over);x.style.setProperty('--dvh',h+'px')}}
// full screen: the terminal box alone (Esc stays with OpenCode where the browser lets the page keep it)
async function dvVoll(){const b=$('dvtermbox');try{if(document.fullscreenElement){await document.exitFullscreen();return}await b.requestFullscreen();
  if(navigator.keyboard&&navigator.keyboard.lock)navigator.keyboard.lock(['Escape']).catch(()=>{})}catch(e){$('dvmsg').textContent=e.message}}
function dvVollGeaendert(){const an=document.fullscreenElement===$('dvtermbox'),v=an?t('Vollbild beenden','Leave full screen'):t('Vollbild','Full screen');
  if(!an&&navigator.keyboard&&navigator.keyboard.unlock)navigator.keyboard.unlock();$('dvvoll').textContent='';$('dvvoll').appendChild(icNode(an?'x':'expand'));$('dvvoll').title=v;$('dvvoll').setAttribute('aria-label',v);
  setTimeout(()=>{dvHoehe();dvGroesseSenden();DV.term&&DV.term.focus()},60)}
// the phone's keys: Esc, Tab, Strg, Alt and the arrows of the Fernzugang (FZ_KEYS, one source)
function dvTasten(){const w=$('dvtasten');if(!w)return;w.textContent='';w.hidden=!DV.term||!NARROW();if(w.hidden)return;
  for(const [l,seq] of FZ_KEYS.slice(0,8)){const b=dvEl('button','b'+((l==='Strg'&&DV.ctrl)||(l==='Alt'&&DV.alt)?' on':''),l==='Strg'?t('Strg','Ctrl'):l);b.type='button';
    b.onclick=()=>{if(l==='Strg')DV.ctrl=!DV.ctrl;else if(l==='Alt')DV.alt=!DV.alt;else if(DV.ws&&DV.ws.readyState===1)DV.ws.send(new TextEncoder().encode(seq));
      if(l==='Strg'||l==='Alt')dvTasten();DV.term&&DV.term.focus()};w.appendChild(b)}}
function dvTermLeer(){const x=$('dvxterm'),d=DV.d||{};x.textContent='';const m=dvEl('div','dvtleer');
  if(!d.an||!d.terminal_an){m.appendChild(dvEl('p','',!d.an?t('Entwickeln auf dem Pi ist aus. Einschalten unter Funktionen → Entwickeln auf dem Pi.','Develop on the Pi is off. Switch it on under Features → Develop on the Pi.')
      :t('Terminal im Browser ist aus. Einschalten unter Funktionen → Entwickeln auf dem Pi → Terminal im Browser. Per SSH geht es auch so: ssh spark-dev@<Panel-Rechner>, dann opencode.','Terminal in the browser is off. Switch it on under Features → Develop on the Pi → Terminal in the browser. Over SSH it works anyway: ssh spark-dev@<panel computer>, then opencode.')))}
  else{if(DV.grund)m.appendChild(dvEl('p','dvtgrund',dvT(DV_ENDE[DV.grund]||DV_ENDE.fenster)));
    m.appendChild(dvEl('p','',t('OpenCode startet sofort, mit dem eigenen Sprachmodell als spark-dev im eigenen Klon. Beendest du es, bleibt eine Shell; opencode startet es neu. Jede Sitzung fragt nach deinem Code.','OpenCode starts at once, with the own language model as spark-dev in its own clone. When you quit it, a shell stays; opencode starts it again. Every session asks for your code.')));
    const b=dvBtn(t('Terminal öffnen','Open the terminal'),'p',()=>dvTermAuf(b));codeLock(b,'protect');m.appendChild(b)}
  x.appendChild(m)}
function dvGroesse(){const el=$('dvxterm');const w=Math.max(320,el.clientWidth-16),h=Math.max(200,el.clientHeight-16);return [Math.max(20,Math.min(400,Math.floor(w/7.9))),Math.max(5,Math.min(200,Math.floor(h/16.5)))]}
// after xterm drew: its real cell size, so the rows fill the box to its foot
function dvZellen(){const sc=DV.term&&$('dvxterm').querySelector('.xterm-screen'),r=sc&&$('dvxterm').querySelector('.xterm-rows>div');if(!r||!DV.term.cols)return null;
  const cw=sc.getBoundingClientRect().width/DV.term.cols,ch=r.getBoundingClientRect().height,el=$('dvxterm');if(!(cw>0&&ch>0))return null;
  return [Math.max(20,Math.min(400,Math.floor((el.clientWidth-16)/cw))),Math.max(5,Math.min(200,Math.floor((el.clientHeight-16)/ch)))]}
function dvGroesseSenden(){if(!DV.term||$('dvterm').hidden)return;const [c,r]=dvZellen()||dvGroesse();if(c===DV.term.cols&&r===DV.term.rows)return;DV.term.resize(c,r);
  if(DV.ws&&DV.ws.readyState===1)DV.ws.send(JSON.stringify({typ:'groesse',cols:c,rows:r}))}
async function dvTermAuf(btn){if(DV.ws)return;btn.disabled=true;$('dvmsg').textContent='';
  try{await fzLaden()}catch(e){$('dvmsg').textContent=e.message;btn.disabled=false;return}
  const [cols,rows]=dvGroesse();let tk;
  try{tk=(await (await api('/api/admin/entwickeln/terminal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cols,rows})})).json()).ticket}
  catch(e){$('dvmsg').textContent=e.message;btn.disabled=false;return}
  const x=$('dvxterm');x.textContent='';DV.grund='';const bg=getComputedStyle(document.documentElement).getPropertyValue('--term').trim();
  const term=new window.Terminal({cursorBlink:true,fontSize:13,cols,rows,scrollback:3000,theme:bg?{background:bg}:undefined});DV.term=term;term.open(x);term.focus();
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/entwickeln/terminal?t='+encodeURIComponent(tk));ws.binaryType='arraybuffer';DV.ws=ws;
  const enc=new TextEncoder();term.onData(s=>{if(ws.readyState!==1)return;if(DV.ctrl&&s.length===1){const c=s.toUpperCase().charCodeAt(0);if(c>=64&&c<96)s=String.fromCharCode(c-64);DV.ctrl=false;dvTasten()}
    if(DV.alt&&s.length===1){s='\x1b'+s;DV.alt=false;dvTasten()}ws.send(enc.encode(s))});
  ws.onmessage=ev=>{if(ev.data instanceof ArrayBuffer){term.write(new Uint8Array(ev.data));return}let m;try{m=JSON.parse(ev.data)}catch{return}
    if(m.typ==='stand'){term.write('\x1b[2m'+t('Verbunden als spark-dev · endet nach ','Connected as spark-dev · ends after ')+m.leerlauf+t(' min Leerlauf',' min idle')+'\x1b[0m\r\n'+
      t('OpenCode startet … (beenden mit ctrl+c, dann Shell; neu starten: opencode)','OpenCode starts … (quit with ctrl+c, then a shell; start again: opencode)')+'\r\n');dvGroesseSenden()}
    if(m.typ==='zu')DV.grund=String(m.grund||'')};
  ws.onclose=ev=>{if(DV.ws!==ws)return;if(!DV.grund)DV.grund=ev.code===4429?'voll':ev.code===4502?'start':ev.code===4503?'notaus':ev.code===4404?'aus':ev.code===4403?'ticket':'fenster';dvTermZu()};
  dvLeiste();setTimeout(dvGroesseSenden,80)}
function dvTermZu(){if(DV.term){DV.term.dispose();DV.term=null}DV.ws=null;DV.ctrl=DV.alt=false;if(document.fullscreenElement===$('dvtermbox'))document.exitFullscreen().catch(()=>{});dvTermLeer();dvLeiste();dvLoad()}
async function dvTermBeenden(){if(DV.ws&&DV.ws.readyState===1){DV.grund='beendet';DV.ws.send(JSON.stringify({typ:'ende'}));DV.ws.close(1000);return}
  try{await api('/api/admin/entwickeln/terminal/beenden',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});dvLoad()}catch(e){$('dvmsg').textContent=e.message}}
window.dvOpen=dvOpen;window.dvLoad=dvLoad;
