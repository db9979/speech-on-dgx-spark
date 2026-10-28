// Fernzugang (fernzugang.py, plan ssh-vermittlung stage 1): Fernzugang → Fern-Server. Servers elsewhere call the panel
// through their anchor (anker/spark-anker.py); an admin opens their shell here. Every name and number goes through
// textContent; xterm.js (MIT, pinned in fernzugang.XTERM) loads from the panel only when a shell opens. „Shell“ and
// „Koppeln (Code)“ ask for a fresh code or passkey (stufen „Schutz ändern“). The chips beside the terminal are fixed
// commands: a tap puts one into the line, Enter is always the person's own. The shell's output never leaves the page.
// „Herauslösen“ moves the open shell into its own window (the panel page with #fernfenster): that window asks this one
// for its own one-time ticket over postMessage (same origin only), never in its address; „Zurückholen“ takes it back.
// In the terminal the browser's own shortcuts are held back (fzFang); „Alle Tasten“ adds full screen and the Keyboard
// Lock API (Chrome, Edge), so even Strg+W or Esc go to the shell; Esc held for 2 s leaves.
const FZ={d:null,sel:'',timer:0,ws:null,term:null,sitz:null,code:null,ctrl:false,alt:false,sid:'',pop:null,weg:null};
const FZ_FENSTER=location.hash==='#fernfenster'&&!!window.opener;
function fzEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function fzBtn(txt,cls,fn){const b=fzEl('button','b'+(cls?' '+cls:''),txt);b.type='button';b.onclick=fn;return b}
function fzZeit(s){if(!s)return'–';const d=new Date(s*1000),h=new Date();
  const uhr=d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===h.toDateString()?uhr:d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'numeric'})+' '+uhr}
function fzMin(s){const m=Math.max(0,Math.round((Date.now()/1000-s)/60));return m<60?m+' min':Math.floor(m/60)+' h '+(m%60)+' min'}
function fzMsg(text,bad){const m=$('fzmsg');if(m){m.textContent=text||'';m.classList.toggle('err',!!bad)}}
function fzStand(g){return g.stand==='abbau'?['warn',t('wird beim nächsten Kontakt abgebaut','removed at next contact')]
  :g.hostkey_falsch?['bad',t('Host-Schlüssel falsch','host key wrong')]:!g.erlaubt?['warn',t('gesperrt','blocked')]
  :g.online?['ok',t('online','online')]:['',t('offline','offline')]}
async function fzLoad(){clearTimeout(FZ.timer);const box=$('fzbox');if(!box||document.body.classList.contains('mgr')||FZ_FENSTER)return;
  try{const r=await api('/api/admin/fernzugang');FZ.d=await r.json();
    if(FZ.weg&&!(FZ.d.offen||[]).some(x=>x.id===FZ.weg.sid)){FZ.weg=null;FZ.pop=null;FZ.sitz=null;fzBanner();fzWegZeigen()}
    fzShow();fzJetzt();fzVerlauf()}catch(e){fzMsg(e.message,true)}
  if(document.querySelector('section#fern.on'))FZ.timer=setTimeout(fzLoad,FZ.ws?15000:10000)}
function fzShow(){const d=FZ.d,box=$('fzmain');if(!d||!box)return;$('fzoff').hidden=!!d.on;$('fznotaus').hidden=!d.notaus;box.hidden=!d.on||!!FZ.ws||!!FZ.weg;
  if(!d.on)return;const c=d.counts||{};
  const tiles=$('fztiles');tiles.textContent='';
  for(const [n,de,en,warn] of [[c.online,'Systeme verbunden','systems connected'],[c.gekoppelt,'gekoppelt','paired'],
    [(c.sitzungen||0)+' / '+d.max,'Sitzungen offen','sessions open',c.sitzungen>0],[d.leerlauf+' min','Leerlauf trennt','idle ends']]){
    const x=fzEl('div','fztile'+(warn?' warn':''));x.append(fzEl('b','',String(n??0)),fzEl('small','',t(de,en)));tiles.appendChild(x)}
  const list=$('fzlist');list.textContent='';
  if(!d.geraete.length)list.appendChild(fzEl('div','mut',t('Noch kein Server gekoppelt. „Neues System koppeln“ zeigt den Befehl für den Server.','No server paired yet. "Pair a new system" shows the command for the server.')));
  if(FZ.sel&&!d.geraete.some(g=>g.id===FZ.sel))FZ.sel='';
  if(!FZ.sel&&d.geraete[0]&&!NARROW())FZ.sel=d.geraete[0].id;
  for(const g of d.geraete){const [lvl,word]=fzStand(g),card=fzEl('div','card fzcard'+(g.id===FZ.sel?' on':''));card.dataset.id=g.id;
    const hd=fzEl('div','fzhead'),dot=fzEl('span','fzdot '+lvl);hd.append(dot,fzEl('b','',g.name));
    if(g.sitzungen)hd.appendChild(fzEl('span','pill warn',g.sitzungen+t(' Sitzung',' session')));
    hd.appendChild(fzEl('span','pill '+lvl,word));card.appendChild(hd);
    card.appendChild(fzEl('div','mut small',[g.online?t('online seit ','online since ')+fzZeit(g.online_seit):g.weg?t('offline seit ','offline since ')+fzZeit(g.weg):'',
      g.os,g.anker?t('Anker ','anchor ')+g.anker:'',g.zuletzt?t('letzte Sitzung ','last session ')+fzZeit(g.zuletzt):''].filter(Boolean).join(' · ')));
    const row=fzEl('div','row');const sh=fzBtn(t('Shell','Shell'),'p',e=>{e.stopPropagation();fzOpen(g)});
    sh.disabled=!g.online||g.hostkey_falsch||!g.erlaubt||g.stand==='abbau'||(c.sitzungen||0)>=d.max;codeLock(sh,'protect');
    const bs=fzBtn(t('Bildschirm','Screen'),'',()=>{});bs.disabled=true;bs.appendChild(fzEl('small','mut',' '+t('später','later')));
    row.append(sh,bs);card.appendChild(row);card.onclick=()=>{FZ.sel=g.id;fzShow()};list.appendChild(card)}
  fzDetail();fzKoppelnZeigen();fzProtokoll()}
function fzDetail(){const box=$('fzdetail'),g=(FZ.d.geraete||[]).find(x=>x.id===FZ.sel);box.textContent='';box.hidden=!g;if(!g)return;
  const [lvl,word]=fzStand(g);const hd=fzEl('div','fzhead');hd.append(fzEl('span','fzdot '+lvl),fzEl('b','',g.name),fzEl('span','pill '+lvl,word));box.appendChild(hd);
  const dl=fzEl('dl','fzfacts');
  for(const [k,v] of [[t('Online seit','Online since'),g.online?fzZeit(g.online_seit)+' ('+fzMin(g.online_seit)+')':'–'],[t('Letzte Sitzung','Last session'),fzZeit(g.zuletzt)],
    [t('Host-Schlüssel','Host key'),g.fp?g.fp+t(' · bei der Kopplung festgelegt',' · pinned at pairing'):'–'],[t('Anmeldung','Sign-in'),t('ed25519 aus dem Tresor · Benutzer ','ed25519 from the vault · user ')+'spark'],
    [t('Anker','Anchor'),(g.anker||'–')+(g.os?' · '+g.os:'')],[t('Gekoppelt','Paired'),fzZeit(g.seit)]]){dl.append(fzEl('dt','',k),fzEl('dd','',v))}
  box.appendChild(dl);
  if(g.hostkey_falsch)box.appendChild(fzEl('div','note err',t('Der Server zeigt einen anderen Host-Schlüssel als bei der Kopplung: keine Verbindung. War das eine Neuinstallation, „Entfernen“ und neu koppeln.','The server shows another host key than at pairing: no connection. If it was reinstalled, "Remove" and pair again.')));
  const row=fzEl('div','row');const sh=fzBtn(t('Sitzung öffnen','Open session'),'p',()=>fzOpen(g));sh.disabled=!g.online||g.hostkey_falsch||!g.erlaubt||g.stand==='abbau';codeLock(sh,'protect');
  const cut=fzBtn(t('Trennen','Disconnect'),'danger',async()=>{try{await api(`/api/admin/fernzugang/geraete/${g.id}/trennen`,{method:'POST'});fzMsg(t('Getrennt. Der Anker kommt nach seiner Pause wieder, solange er sich verbinden darf.','Disconnected. The anchor comes back after its pause while it may connect.'));fzLoad()}catch(e){fzMsg(e.message,true)}});
  const rm=fzBtn(t('Entfernen','Remove'),'danger',()=>fzRemove(g));codeLock(rm,'confirm');row.append(sh,cut,rm);box.appendChild(row);
  box.appendChild(fzEl('div','fh',t('„Sitzung öffnen“ fragt jedes Mal frisch nach Code oder Passkey (Schutz ändern).','"Open session" asks for a code or passkey every time (Change protection).')));
  const sw=fzEl('div','setrow');const lb=fzEl('div','lbl');lb.append(fzEl('b','',t('Darf sich verbinden','May connect')),fzEl('span','',t('Aus: der Anker wird abgewiesen, bis du es wieder erlaubst.','Off: the anchor is refused until you allow it again.')));
  const tg=fzEl('label','tgl'),inp=document.createElement('input');inp.type='checkbox';inp.checked=!!g.erlaubt;inp.disabled=g.stand==='abbau';tg.append(inp,fzEl('i'));
  inp.onchange=async()=>{try{await api(`/api/admin/fernzugang/geraete/${g.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({erlaubt:inp.checked})});fzLoad()}catch(e){inp.checked=!inp.checked;fzMsg(e.message,true)}};
  sw.append(lb,tg);box.appendChild(sw)}
async function fzRemove(g){if(!confirm(t(`„${g.name}“ entfernen? Der Schlüssel gilt sofort nicht mehr; der Anker baut auf dem Server alles ab, was er eingerichtet hat (jetzt oder beim nächsten Kontakt).`,`Remove "${g.name}"? The key stops at once; the anchor removes everything it set up on the server (now or at its next contact).`)))return;
  try{const r=await api(`/api/admin/fernzugang/geraete/${g.id}`,{method:'DELETE'});const d=await r.json();
    fzMsg(d.stand==='abbau'?t('Entfernt. Der Anker baut sich ab; ist er offline, beim nächsten Kontakt. Von Hand auf dem Server: sudo spark-anker entfernen','Removed. The anchor removes itself; when offline, at its next contact. By hand on the server: sudo spark-anker entfernen'):'');FZ.sel='';fzLoad()}catch(e){fzMsg(e.message,true)}}
// „Neues System koppeln“: a name, then a fresh code; the code is shown once, the one command to paste on the server
async function fzKoppeln(){const name=$('fzname').value.trim();if(!name){$('fzname').focus();return}
  try{const r=await api('/api/admin/fernzugang/koppeln',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,origin:location.origin})});
    FZ.code=Object.assign(await r.json(),{name,bis:Date.now()/1000+0});FZ.code.bis+=FZ.code.gilt_s;$('fzname').value='';fzKoppelnZeigen()}catch(e){fzMsg(e.message,true)}}
function fzKoppelnZeigen(){const box=$('fzcode');if(!box)return;box.textContent='';const k=FZ.code;
  if(!k||Date.now()/1000>k.bis){FZ.code=null;box.appendChild(fzEl('div','fh',t('Ein Name für den Server, dann „Koppeln (Code)“: der Code steht nur hier und gilt 10 Minuten.','A name for the server, then "Pair (code)": the code only shows here and counts 10 minutes.')));return}
  box.appendChild(fzEl('div','',t(`Einmal-Code für „${k.name}“. Er wird nur jetzt gezeigt und gilt bis `,`One-time code for "${k.name}". It is shown only now and counts until `)+fzZeit(k.bis)+'.'));
  box.appendChild(fzEl('div','fzbig',k.code));
  box.appendChild(fzEl('div','fh',t('Auf dem Server (Debian, Ubuntu, Raspberry Pi OS; sshd läuft) diese eine Zeile einfügen. Sie fragt dann im Terminal nach dem Code; er steht nie im Befehl.','On the server (Debian, Ubuntu, Raspberry Pi OS; sshd running) paste this one line. It then asks for the code in the terminal; it is never in the command.')));
  const pre=fzEl('pre','fzcmd',k.befehl);box.appendChild(pre);
  const row=fzEl('div','row');row.appendChild(fzBtn(t('Kopieren','Copy'),'',e=>copyString(k.befehl,e.target)));box.appendChild(row);
  const pr=fzEl('details','fzpruef');pr.appendChild(fzEl('summary','',t('Prüfen (freiwillig)','Check (optional)')));
  pr.appendChild(fzEl('div','fh',t('SHA-256 des Programms, wie es das Panel ausliefert; auf dem Server mit curl -fsSL …/fernzugang/anker | sha256sum vergleichen:','SHA-256 of the program as the panel hands it out; compare on the server with curl -fsSL …/fernzugang/anker | sha256sum:')));
  pr.appendChild(fzEl('code','fzsha',(k.anker||{}).sha256||''));if(k.fp)pr.appendChild(fzEl('div','fh',t('Zertifikat des Panels (festgelegt): ','Panel certificate (pinned): ')+k.fp));
  box.appendChild(pr)}
// „Gerade verbunden“: who has a session open, from where (Zuhause or Internet, the address shortened) and with what
const FZ_CLIENT={browser:['Browser','Browser'],iphone:['iPhone','iPhone'],android:['Android','Android'],fenster:['Fenster','Window']};
function fzWoher(h){return h==='internet'?t('Internet','Internet'):t('Zuhause','Home')}
function fzJetzt(){const d=FZ.d,box=$('fzjetzt'),list=$('fzjetztlist');if(!d||!box)return;const o=d.on?d.offen||[]:[];box.hidden=!o.length;list.textContent='';
  const name=id=>((d.geraete||[]).find(g=>g.id===id)||{}).name||'';
  for(const x of o){const r=fzEl('div','fzjrow'),tx=fzEl('div');tx.append(fzEl('b','',name(x.geraet)+' · '+(x.art==='shell'?t('Shell','Shell'):x.art)),
      fzEl('div','fh',[x.admin,t(...(FZ_CLIENT[x.client]||FZ_CLIENT.browser)),fzWoher(x.herkunft)+(x.ip?' ('+x.ip+')':''),t('seit ','since ')+fzZeit(x.seit)].join(' · ')));
    r.append(tx,fzBtn(t('Trennen','Disconnect'),'danger',async()=>{try{await api(`/api/admin/fernzugang/sitzung/${x.id}/trennen`,{method:'POST'});fzLoad()}catch(e){fzMsg(e.message,true)}}));list.appendChild(r)}}
// „Verlauf“: the sessions of the last days, no content
function fzVerlauf(){const d=FZ.d,list=$('fzverlauflist');if(!d||!list)return;list.textContent='';const v=d.verlauf||[];
  $('fzverlaufh').textContent=t(`Die Sitzungen der letzten ${d.verlauf_tage||30} Tage: Zeit, System, Admin, Art, Dauer und von wo. Nie eine Adresse, nie was lief.`,`The sessions of the last ${d.verlauf_tage||30} days: time, system, admin, kind, duration and from where. Never an address, never what ran.`);
  if(!v.length){list.appendChild(fzEl('div','mut',t('Noch keine Sitzung.','No session yet.')));return}
  for(const x of v){const r=fzEl('div','fzvrow');r.append(fzEl('span','',fzZeit(x.t)),fzEl('span','',[x.system,x.admin,x.art==='shell'?t('Shell','Shell'):x.art].join(' · ')),
    fzEl('span','mut',x.min+' min · '+fzWoher(x.herkunft)));list.appendChild(r)}}
async function fzVerlaufWeg(){if(!confirm(t('Den ganzen Verlauf des Fernzugangs löschen?','Delete the whole remote access history?')))return;
  try{await api('/api/admin/fernzugang/verlauf',{method:'DELETE'});fzLoad()}catch(e){fzMsg(e.message,true)}}
function fzProtokoll(){const p=$('fzlog');if(!p)return;p.textContent='fernzugang: anker_auf | ok | 1\nfernzugang: sitzung_auf | admin | 1\nfernzugang: sitzung_zu | leerlauf | 15\nfernzugang: koppeln_code | admin | 1'}
// ---------------------------------------------------------------- the terminal
function fzLaden(){if(window.Terminal)return Promise.resolve();
  return new Promise((ok,bad)=>{const l=document.createElement('link');l.rel='stylesheet';l.href='/static/xterm/xterm.css?v='+encodeURIComponent(SPARK_VER);document.head.appendChild(l);
    const s=document.createElement('script');s.src='/static/xterm/xterm.js?v='+encodeURIComponent(SPARK_VER);s.onload=()=>ok();s.onerror=()=>bad(new Error(t('xterm.js fehlt','xterm.js missing')));document.head.appendChild(s)})}
function fzGroesse(){const el=$('fzterm');const w=Math.max(320,el.clientWidth-16),h=Math.max(200,el.clientHeight-16);
  return [Math.max(20,Math.min(400,Math.floor(w/8.6))),Math.max(5,Math.min(200,Math.floor(h/17.5)))]}
async function fzOpen(g){if(FZ.ws||FZ.weg){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}
  try{await fzLaden()}catch(e){fzMsg(e.message,true);return}
  $('fzview').hidden=false;$('fzmain').hidden=true;const [cols,rows]=fzGroesse();let tk;
  try{const r=await api('/api/admin/fernzugang/sitzung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraet:g.id,cols,rows})});tk=(await r.json()).ticket}
  catch(e){fzZu(e.message);return}
  fzTerm(tk,{name:g.name,gid:g.id,seit:Date.now()/1000,max:FZ.d.max,leer:FZ.d.leerlauf},cols,rows)}
// the terminal for one ticket: a new session, or one this window takes over (its own window, or back into the tab)
function fzTerm(tk,sitz,cols,rows){
  const term=new window.Terminal({cursorBlink:true,fontSize:14,cols,rows,scrollback:2000,theme:{background:'#0b1020'}});
  $('fzterm').textContent='';term.open($('fzterm'));term.attachCustomKeyEventHandler(fzFang);term.focus();FZ.term=term;
  FZ.sitz=sitz;fzBanner();fzInfo('');
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/fernzugang/terminal?t='+encodeURIComponent(tk));
  ws.binaryType='arraybuffer';FZ.ws=ws;const enc=new TextEncoder();
  term.write(t('Verbinde mit ','Connecting to ')+sitz.name+' …\r\n');
  term.onData(x=>{if(ws.readyState!==1)return;if(FZ.ctrl&&x.length===1){const c=x.toUpperCase().charCodeAt(0);if(c>=64&&c<96)x=String.fromCharCode(c-64);FZ.ctrl=false;fzKeys()}
    if(FZ.alt&&x.length===1){x='\x1b'+x;FZ.alt=false;fzKeys()}fzZeile(x);ws.send(enc.encode(x))});
  ws.onmessage=ev=>{if(ev.data instanceof ArrayBuffer){term.write(new Uint8Array(ev.data));return}let m;try{m=JSON.parse(ev.data)}catch{return}
    if(m.typ==='stand'&&m.stand==='offen'){FZ.sid=m.id||'';fzResize();term.write('\x1b[2m'+t('Verbunden · SSH · Host-Schlüssel ','Connected · SSH · host key ')+m.fp+t(' geprüft',' checked')+'\x1b[0m\r\n');fzInfo(m.fp)}
    if(m.typ==='fehler'||m.typ==='zu')FZ.grund=m.grund;if(m.typ==='weg')FZ.grund='weg'};
  ws.onclose=()=>{if(FZ.ws!==ws)return;if(FZ.grund==='weg'){fzWeg();return}if(FZ_FENSTER){window.close();return}fzZu(fzGrund(FZ.grund))};
  window.addEventListener('resize',fzResize)}
const FZ_GRUND={leerlauf:['Leerlauf: die Sitzung ist zu.','Idle: the session is closed.'],notaus:['Notaus: alle Sitzungen sind zu.','Emergency stop: every session is closed.'],
  hostkey:['Der Host-Schlüssel passt nicht zur Kopplung: keine Verbindung.','The host key does not match the pairing: no connection.'],ssh:['SSH-Anmeldung ging nicht (Benutzer spark, Schlüssel des Panels).','SSH sign-in failed (user spark, the panel key).'],
  zu_gross:['Zu viel auf einmal eingefügt (höchstens 64 KB).','Too much pasted at once (64 KB at most).'],sshd:['Auf dem Server hört kein sshd auf 127.0.0.1:22.','No sshd listens on 127.0.0.1:22 on the server.'],
  anker:['Der Anker hat nicht geantwortet.','The anchor did not answer.'],server:['Der Server hat die Sitzung beendet.','The server ended the session.'],getrennt:['Getrennt.','Disconnected.'],alle:['Alle getrennt.','All disconnected.']};
function fzGrund(g){return g&&FZ_GRUND[g]?t(...FZ_GRUND[g]):t('Sitzung beendet.','Session ended.')}
function fzResize(){if(!FZ.term||!FZ.ws||FZ.ws.readyState!==1)return;const [c,r]=fzGroesse();if(c===FZ.term.cols&&r===FZ.term.rows)return;FZ.term.resize(c,r);FZ.ws.send(JSON.stringify({typ:'groesse',cols:c,rows:r}))}
function fzBanner(){const b=$('fzbanner');if(!FZ.sitz){b.hidden=true;document.body.classList.remove('fzaktiv');return}b.hidden=false;document.body.classList.add('fzaktiv');
  $('fzbtext').textContent=t('Fernsitzung aktiv · ','Remote session active · ')+FZ.sitz.name+' · '+fzMin(FZ.sitz.seit)+t(' · Notaus trennt sofort',' · emergency stop ends it at once');
  clearTimeout(FZ.bt);FZ.bt=setTimeout(fzBanner,30000)}
function fzInfo(fp){const dl=$('fzinfo');dl.textContent='';const s=FZ.sitz||{};
  for(const [k,v] of [[t('System','System'),s.name||''],[t('Host-Schlüssel','Host key'),fp||'…'],[t('Leerlauf trennt','Idle ends'),t('nach ','after ')+s.leer+' min'],
    [t('Sitzungen','Sessions'),t('höchstens ','at most ')+s.max],[t('Anmeldung','Sign-in'),t('frischer Code oder Passkey','fresh code or passkey')],[t('Aufgezeichnet','Recorded'),t('nichts','nothing')]])dl.append(fzEl('dt','',k),fzEl('dd','',v))}
// the chips after the person's own last command line (FZ.zeile: only that line, only in this page, never the output,
// never sent anywhere): fernzugang.FOLGE's fixed rules, {1} = the own first argument, shell-quoted; else the fixed CHIPS
function fzQuote(a){return /^[A-Za-z0-9@%_+=:,.\/-]+$/.test(a)?a:"'"+a.replace(/'/g,"'\\''")+"'"}
function fzFolge(line){const w=String(line||'').trim().split(/\s+/).filter(Boolean);if(w[0]==='sudo')w.shift();
  for(const [words,next] of (FZ.d&&FZ.d.folge)||[]){if(!Array.isArray(words)||!Array.isArray(next)||words.length>w.length||!words.every((x,i)=>x===w[i]))continue;
    const arg=w[words.length];const out=next.filter(c=>typeof c==='string'&&(!c.includes('{1}')||arg)).map(c=>c.split('{1}').join(arg?fzQuote(arg):''));
    if(out.length)return out.slice(0,4)}
  return null}
function fzZeile(x){if(x==='\r'){FZ.zeile=FZ.buf||'';FZ.buf='';fzChips();return}
  if(x==='\x7f'){FZ.buf=(FZ.buf||'').slice(0,-1);return}
  if(/[\x00-\x1f]/.test(x)){if(x.endsWith('\r')&&!/[\x00-\x0c\x0e-\x1f]/.test(x)){FZ.buf=(FZ.buf||'')+x.slice(0,-1);fzZeile('\r')}else FZ.buf='';return}
  FZ.buf=((FZ.buf||'')+x).slice(-500)}
function fzChips(){const w=$('fzchips');w.textContent='';const f=fzFolge(FZ.zeile);$('fzchipwas').hidden=!f;
  for(const c of f||(FZ.d&&FZ.d.chips)||[]){const b=fzEl('button','fzchip');b.type='button';b.append(fzEl('code','',c),fzEl('small','',t('Einfügen','Insert')));
  b.onclick=()=>{if(FZ.term){FZ.term.paste(c);FZ.term.focus()}};w.appendChild(b)}}
const FZ_KEYS=[['Esc','\x1b'],['Tab','\t'],['Strg',''],['Alt',''],['↑','\x1b[A'],['↓','\x1b[B'],['←','\x1b[D'],['→','\x1b[C'],['⏎','\r'],
  ['F1','\x1bOP'],['F2','\x1bOQ'],['F3','\x1bOR'],['F4','\x1bOS'],['F5','\x1b[15~'],['F6','\x1b[17~'],['F7','\x1b[18~'],['F8','\x1b[19~'],
  ['F9','\x1b[20~'],['F10','\x1b[21~'],['F11','\x1b[23~'],['F12','\x1b[24~']];
function fzKeys(){const w=$('fzkeys');w.textContent='';for(const [l,seq] of FZ_KEYS){const b=fzEl('button','b'+((l==='Strg'&&FZ.ctrl)||(l==='Alt'&&FZ.alt)?' on':''),l==='Strg'?t('Strg','Ctrl'):l);b.type='button';
  b.onclick=()=>{if(l==='Strg'){FZ.ctrl=!FZ.ctrl;fzKeys();FZ.term&&FZ.term.focus();return}if(l==='Alt'){FZ.alt=!FZ.alt;fzKeys();FZ.term&&FZ.term.focus();return}
    if(FZ.ws&&FZ.ws.readyState===1)FZ.ws.send(new TextEncoder().encode(seq));FZ.term&&FZ.term.focus()};w.appendChild(b)}}
// the browser's own shortcuts the page may take stay in the shell: F1–F12, Tab, Alt and Strg combinations (not Strg+C
// with a selection, Strg+V and Strg+Shift+C/V: copy and paste); xterm then sends the key on as usual
function fzFang(e){if(e.type!=='keydown')return true;const k=(e.key||'').toLowerCase();
  const copy=(e.ctrlKey&&e.shiftKey&&(k==='c'||k==='v'))||(e.ctrlKey&&!e.shiftKey&&k==='v')||(e.ctrlKey&&k==='c'&&FZ.term&&FZ.term.hasSelection());
  if(!copy&&(/^f([1-9]|1[0-2])$/.test(k)||k==='tab'||e.altKey||e.ctrlKey))e.preventDefault();return true}
// „Alle Tasten“: full screen plus the Keyboard Lock API (Chromium); elsewhere a hint, the normal capture stays
async function fzAlleTasten(){const kb=navigator.keyboard;
  if(!kb||typeof kb.lock!=='function'){fzMsg(t('Alle Tasten nur in Chrome oder Edge; sonst das Panel als App installieren. Die üblichen Tastenkürzel gehen auch so an die Shell.','All keys only in Chrome or Edge; otherwise install the panel as an app. The usual shortcuts go to the shell anyway.'),true);return}
  try{if(!document.fullscreenElement)await $('fzview').requestFullscreen();await kb.lock();
    fzMsg(t('Alle Tasten gehen an die Shell. Zum Verlassen Esc 2 Sekunden halten.','All keys go to the shell. To leave, hold Esc for 2 seconds.'));FZ.term&&FZ.term.focus()}catch(e){fzMsg(e.message,true)}}
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&navigator.keyboard&&typeof navigator.keyboard.unlock==='function')navigator.keyboard.unlock()});
// „Herauslösen“: the panel page in its own window; it asks here for its own ticket (fz-bereit), this tab shows „läuft im
// eigenen Fenster“ once the server moved the session (weg)
function fzHeraus(){if(!FZ.ws||!FZ.sid||!FZ.sitz)return;const w=window.open('/#fernfenster','fz'+FZ.sid,'popup,width=1100,height=720');
  if(!w){fzMsg(t('Der Browser hat das Fenster blockiert: Pop-ups für das Panel erlauben.','The browser blocked the window: allow pop-ups for the panel.'),true);return}
  FZ.pop={w,sid:FZ.sid,sitz:FZ.sitz}}
async function fzFensterTicket(sid,fenster){const r=await api(`/api/admin/fernzugang/sitzung/${sid}/fenster`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fenster})});return (await r.json()).ticket}
addEventListener('message',async e=>{if(e.origin!==location.origin||!e.data||typeof e.data!=='object')return;
  if(e.data.typ==='fz-bereit'&&FZ.pop&&e.source===FZ.pop.w){const p=FZ.pop;let tk;try{tk=await fzFensterTicket(p.sid,true)}catch(x){fzMsg(x.message,true);return}
    p.w.postMessage({typ:'fz-ticket',ticket:tk,sitz:p.sitz,chips:(FZ.d&&FZ.d.chips)||[],folge:(FZ.d&&FZ.d.folge)||[]},location.origin)}
  else if(e.data.typ==='fz-ticket'&&FZ_FENSTER&&e.source===window.opener&&!FZ.ws&&typeof e.data.ticket==='string'){
    FZ.d={chips:Array.isArray(e.data.chips)?e.data.chips.filter(x=>typeof x==='string'):[],folge:Array.isArray(e.data.folge)?e.data.folge:[]};const sitz=e.data.sitz||{};
    try{await fzLaden()}catch(x){fzMsg(x.message,true);return}
    document.title=String(sitz.name||'')+' · '+t('Fernzugang','Remote access');fzChips();const [c,r]=fzGroesse();
    fzTerm(e.data.ticket,{name:String(sitz.name||''),gid:String(sitz.gid||''),seit:Number(sitz.seit)||Date.now()/1000,max:Number(sitz.max)||1,leer:Number(sitz.leer)||15},c,r)}});
function fzWeg(){const ws=FZ.ws,sitz=FZ.sitz;FZ.ws=null;FZ.grund='';FZ.zeile=FZ.buf='';if(FZ.term){FZ.term.dispose();FZ.term=null}window.removeEventListener('resize',fzResize);
  if(FZ_FENSTER){window.close();return}
  FZ.weg={sid:FZ.sid,sitz};FZ.sitz=sitz;fzBanner();$('fzview').hidden=true;fzWegZeigen();if(ws&&ws.readyState<2)ws.close()}
function fzWegZeigen(){const b=$('fzweg');if(!b)return;b.hidden=!FZ.weg;if(FZ.weg)$('fzwegname').textContent=FZ.weg.sitz?FZ.weg.sitz.name:'';if(!FZ.weg&&FZ.d)fzShow()}
async function fzZurueck(){const w=FZ.weg;if(!w)return;let tk;try{await fzLaden();tk=await fzFensterTicket(w.sid,false)}catch(e){fzMsg(e.message,true);return}
  FZ.weg=null;fzWegZeigen();$('fzview').hidden=false;$('fzmain').hidden=true;const [c,r]=fzGroesse();fzTerm(tk,w.sitz,c,r)}
async function fzWegTrennen(){const w=FZ.weg,p=FZ.pop;if(p&&p.w&&!p.w.closed){p.w.close();return}
  if(w&&w.sitz&&w.sitz.gid){try{await api(`/api/admin/fernzugang/geraete/${w.sitz.gid}/trennen`,{method:'POST'})}catch(e){fzMsg(e.message,true)}}FZ.weg=null;FZ.sitz=null;fzBanner();fzWegZeigen();fzLoad()}
function fzTrennen(){if(FZ.ws)FZ.ws.close();else if(FZ.weg)fzWegTrennen()}
function fzZu(text){const ws=FZ.ws;FZ.ws=null;FZ.grund='';FZ.zeile=FZ.buf='';if(ws&&ws.readyState<2)ws.close();if(FZ.term){FZ.term.dispose();FZ.term=null}FZ.sitz=null;fzBanner();
  window.removeEventListener('resize',fzResize);$('fzview').hidden=true;$('fzmain').hidden=false;if(text)fzMsg(text,true);fzLoad()}
async function fzAlle(){if(!confirm(t('Jede Sitzung und jeden Anker jetzt trennen?','Disconnect every session and anchor now?')))return;
  try{const r=await api('/api/admin/fernzugang/alle-trennen',{method:'POST'});const d=await r.json();fzMsg(t('Getrennt: ','Disconnected: ')+d.n);if(FZ.ws)fzTrennen();fzLoad()}catch(e){fzMsg(e.message,true)}}
{const k=$('fzgo');if(k){$('fzheraus').onclick=fzHeraus;$('fzverlaufweg').onclick=fzVerlaufWeg;$('fzalletasten').onclick=fzAlleTasten;$('fzzurueck').onclick=fzZurueck;$('fzwegstop').onclick=fzWegTrennen;
  if(!(navigator.keyboard&&typeof navigator.keyboard.lock==='function'))$('fzalletasten').title=t('Nur in Chrome oder Edge','Only in Chrome or Edge');k.onclick=fzKoppeln;codeLock(k,'protect');$('fzalle').onclick=fzAlle;$('fzbtrennen').onclick=fzTrennen;$('fzstop').onclick=fzTrennen;$('fzalle2').onclick=fzAlle;
  $('fzname').onkeydown=e=>{if(e.key==='Enter')fzKoppeln()};fzKeys();new MutationObserver(()=>{if(FZ.d)fzChips()}).observe($('fzview'),{attributes:true,attributeFilter:['hidden']})}}
window.fzLoad=fzLoad;
// the menu entry Fernzugang: only for an admin (never the Verwalter) while Funktionen → Fernzugang zu Servern is on (whoami)
window.fzStart=who=>{const on=!!(who&&who.fernzugang);document.querySelectorAll('nav button[data-s=fern]').forEach(b=>b.hidden=!on)};
// the own window: only the terminal, over the whole page; it tells its opener it is ready and waits for the ticket
if(FZ_FENSTER&&$('fzview')){document.body.classList.add('fzfenster');$('fzview').hidden=false;window.opener.postMessage({typ:'fz-bereit'},location.origin)}
