// Fernzugang (fernzugang.py, plan ssh-vermittlung stage 1): Funktionen → Fernzugang. Servers elsewhere call the panel
// through their anchor (anker/spark-anker.py); an admin opens their shell here. Every name and number goes through
// textContent; xterm.js (MIT, pinned in fernzugang.XTERM) loads from the panel only when a shell opens. „Shell“ and
// „Koppeln (Code)“ ask for a fresh code or passkey (stufen „Schutz ändern“). The chips beside the terminal are fixed
// commands: a tap puts one into the line, Enter is always the person's own. The shell's output never leaves the page.
const FZ={d:null,sel:'',timer:0,ws:null,term:null,sitz:null,code:null,ctrl:false};
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
async function fzLoad(){clearTimeout(FZ.timer);const box=$('fzbox');if(!box||document.body.classList.contains('mgr'))return;
  try{const r=await api('/api/admin/fernzugang');FZ.d=await r.json();fzShow()}catch(e){fzMsg(e.message,true)}
  if(document.querySelector('section#fern.on'))FZ.timer=setTimeout(fzLoad,FZ.ws?15000:10000)}
function fzShow(){const d=FZ.d,box=$('fzmain');if(!d||!box)return;$('fzoff').hidden=!!d.on;$('fznotaus').hidden=!d.notaus;box.hidden=!d.on;
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
function fzProtokoll(){const p=$('fzlog');if(!p)return;p.textContent='fernzugang: anker_auf | ok | 1\nfernzugang: sitzung_auf | admin | 1\nfernzugang: sitzung_zu | leerlauf | 15\nfernzugang: koppeln_code | admin | 1'}
// ---------------------------------------------------------------- the terminal
function fzLaden(){if(window.Terminal)return Promise.resolve();
  return new Promise((ok,bad)=>{const l=document.createElement('link');l.rel='stylesheet';l.href='/static/xterm/xterm.css?v='+encodeURIComponent(SPARK_VER);document.head.appendChild(l);
    const s=document.createElement('script');s.src='/static/xterm/xterm.js?v='+encodeURIComponent(SPARK_VER);s.onload=()=>ok();s.onerror=()=>bad(new Error(t('xterm.js fehlt','xterm.js missing')));document.head.appendChild(s)})}
function fzGroesse(){const el=$('fzterm');const w=Math.max(320,el.clientWidth-16),h=Math.max(200,el.clientHeight-16);
  return [Math.max(20,Math.min(400,Math.floor(w/8.6))),Math.max(5,Math.min(200,Math.floor(h/17.5)))]}
async function fzOpen(g){if(FZ.ws){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}
  try{await fzLaden()}catch(e){fzMsg(e.message,true);return}
  $('fzview').hidden=false;$('fzmain').hidden=true;const [cols,rows]=fzGroesse();let tk;
  try{const r=await api('/api/admin/fernzugang/sitzung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraet:g.id,cols,rows})});tk=(await r.json()).ticket}
  catch(e){fzZu(e.message);return}
  const term=new window.Terminal({cursorBlink:true,fontSize:14,cols,rows,scrollback:2000,theme:{background:'#0b1020'}});
  $('fzterm').textContent='';term.open($('fzterm'));term.focus();FZ.term=term;
  FZ.sitz={name:g.name,seit:Date.now()/1000,max:FZ.d.max,leer:FZ.d.leerlauf};fzBanner();fzInfo('');
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/fernzugang/terminal?t='+encodeURIComponent(tk));
  ws.binaryType='arraybuffer';FZ.ws=ws;const enc=new TextEncoder();
  term.write(t('Verbinde mit ','Connecting to ')+g.name+' …\r\n');
  term.onData(x=>{if(ws.readyState!==1)return;if(FZ.ctrl&&x.length===1){const c=x.toUpperCase().charCodeAt(0);if(c>=64&&c<96)x=String.fromCharCode(c-64);FZ.ctrl=false;fzKeys()}ws.send(enc.encode(x))});
  ws.onmessage=ev=>{if(ev.data instanceof ArrayBuffer){term.write(new Uint8Array(ev.data));return}let m;try{m=JSON.parse(ev.data)}catch{return}
    if(m.typ==='stand'&&m.stand==='offen'){term.write('\x1b[2m'+t('Verbunden · SSH · Host-Schlüssel ','Connected · SSH · host key ')+m.fp+t(' geprüft',' checked')+'\x1b[0m\r\n');fzInfo(m.fp)}
    if(m.typ==='fehler'||m.typ==='zu')FZ.grund=m.grund};
  ws.onclose=()=>fzZu(fzGrund(FZ.grund));
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
function fzChips(){const w=$('fzchips');w.textContent='';for(const c of (FZ.d&&FZ.d.chips)||[]){const b=fzEl('button','fzchip');b.type='button';b.append(fzEl('code','',c),fzEl('small','',t('Einfügen','Insert')));
  b.onclick=()=>{if(FZ.term){FZ.term.paste(c);FZ.term.focus()}};w.appendChild(b)}}
const FZ_KEYS=[['Esc','\x1b'],['Tab','\t'],['Strg',''],['↑','\x1b[A'],['↓','\x1b[B'],['←','\x1b[D'],['→','\x1b[C'],['⏎','\r']];
function fzKeys(){const w=$('fzkeys');w.textContent='';for(const [l,seq] of FZ_KEYS){const b=fzEl('button','b'+(l==='Strg'&&FZ.ctrl?' on':''),l==='Strg'?t('Strg','Ctrl'):l);b.type='button';
  b.onclick=()=>{if(l==='Strg'){FZ.ctrl=!FZ.ctrl;fzKeys();FZ.term&&FZ.term.focus();return}if(FZ.ws&&FZ.ws.readyState===1)FZ.ws.send(new TextEncoder().encode(seq));FZ.term&&FZ.term.focus()};w.appendChild(b)}}
function fzTrennen(){if(FZ.ws)FZ.ws.close()}
function fzZu(text){const ws=FZ.ws;FZ.ws=null;FZ.grund='';if(ws&&ws.readyState<2)ws.close();if(FZ.term){FZ.term.dispose();FZ.term=null}FZ.sitz=null;fzBanner();
  window.removeEventListener('resize',fzResize);$('fzview').hidden=true;$('fzmain').hidden=false;if(text)fzMsg(text,true);fzLoad()}
async function fzAlle(){if(!confirm(t('Jede Sitzung und jeden Anker jetzt trennen?','Disconnect every session and anchor now?')))return;
  try{const r=await api('/api/admin/fernzugang/alle-trennen',{method:'POST'});const d=await r.json();fzMsg(t('Getrennt: ','Disconnected: ')+d.n);if(FZ.ws)fzTrennen();fzLoad()}catch(e){fzMsg(e.message,true)}}
{const k=$('fzgo');if(k){k.onclick=fzKoppeln;codeLock(k,'protect');$('fzalle').onclick=fzAlle;$('fzbtrennen').onclick=fzTrennen;$('fzstop').onclick=fzTrennen;$('fzalle2').onclick=fzAlle;
  $('fzname').onkeydown=e=>{if(e.key==='Enter')fzKoppeln()};fzKeys();new MutationObserver(()=>{if(FZ.d)fzChips()}).observe($('fzview'),{attributes:true,attributeFilter:['hidden']})}}
window.fzLoad=fzLoad;
