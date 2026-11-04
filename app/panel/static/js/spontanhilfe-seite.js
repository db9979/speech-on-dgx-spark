'use strict';
// The person's page of the Spontanhilfe (/hilfe, spontanhilfe.py): no login, no panel, no model. The number (or the
// link's key behind "#", taken from the address at once) and a first name; then her browser shares the screen by
// WebRTC only after her own click. Messages from the panel are data: shown with textContent, nothing else.
// Look (Dominik 2026-11-04, spontanhilfe/seite2/vorschlag-schlicht.png): a white header with the state and „Sitzung
// beenden“, boxes „Bildschirm teilen“ / „Anfrage“ and a small „Vorschau“ left, „Nachrichten“ right with the field on top.
(()=>{
const EN=!/^de\b/i.test(navigator.language||'de');
const L={titel:['Hilfe am Bildschirm','Screen help'],marke:['Spark Fernhilfe','Spark remote help'],intro:['Geben Sie die Nummer ein, die man Ihnen am Telefon gesagt hat.','Enter the number you were told on the phone.'],
  link:['Ihr Link ist erkannt.','Your link is recognised.'],weiter:['Weiter','Continue'],
  nichts:['Nichts wird installiert. Man sieht erst etwas, wenn Sie „Bildschirm teilen“ wählen.','Nothing is installed. Nothing is seen until you choose "Share screen".'],
  warten:['Einen Moment bitte','One moment please'],teilen:['Bildschirm teilen','Share screen'],
  teiltext:['{a} sieht noch nichts. Erst wenn Sie hier tippen und den Bildschirm wählen, sieht {a} ihn.','{a} sees nothing yet. Only when you tap here and choose your screen does {a} see it.'],
  prev:['So sieht {a} Ihren Bildschirm. Ein Kreis zeigt, wohin {a} Sie bittet zu schauen.','This is how {a} sees your screen. A circle shows where {a} asks you to look.'],
  vorschau:['Vorschau','Preview'],ausblenden:['ausblenden','hide'],einblenden:['einblenden','show'],
  anfrage:['Anfrage','Request'],nachrichten:['Nachrichten','Messages'],sie:['Sie','You'],
  senden:['Senden','Send'],beenden:['Sitzung beenden','End session'],
  zu:['Die Hilfe ist beendet','The help has ended'],zutext:['Es bleibt nichts zurück. Sie können dieses Fenster schließen.','Nothing is left behind. You can close this window.'],
  name:['Ihr Vorname','Your first name'],nummer:['Nummer','Number'],msg:['Nachricht an {a} …','Message to {a} …'],
  bereit:['{a} ist bereit, noch sieht man nichts','{a} is ready, nothing is seen yet'],geteilt:['Bildschirm wird geteilt','Screen is shared'],
  uhr:['mit {a} · endet spätestens in {n} min','with {a} · ends after {n} min at the latest'],
  fuss:['Verbindung verschlüsselt · Es wird nichts aufgezeichnet','Connection encrypted · Nothing is recorded'],fusslan:['Es wird nichts aufgezeichnet','Nothing is recorded'],
  laden:['Programm laden','Load program'],nein:['Nur ansehen lassen','View only'],pruefk:['Prüfsumme','Checksum'],
  wunsch:['{a} möchte Ihren Computer steuern','{a} would like to control your computer'],
  wintext:['Dafür ist ein kleines Programm nötig. Es fragt vor dem Start noch einmal nach; Sie können jederzeit beenden.','This needs a small program. It asks you once more before it starts; you can end at any time.'],
  winsch:[['Programm laden','Die geladene Datei öffnen','Im Programm „Erlauben“ wählen'],['Load the program','Open the downloaded file','Choose "Allow" in the program']],
  lintext:['Dafür läuft ein kleines Programm im Terminal. Es fragt vor dem Start noch einmal nach; Sie können jederzeit beenden. Unter Wayland geht nur Ansehen.','This runs a small program in a terminal. It asks you once more before it starts; you can end at any time. Under Wayland only viewing works.'],
  linsch:[['Befehl zeigen und kopieren','In ein Terminal einfügen (Strg+Umschalt+V) und Enter drücken','Fragt das Terminal nach dem Schlüssel: „Schlüssel kopieren“, dort einfügen und Enter; dann „Erlauben“ wählen'],['Show and copy the command','Paste it into a terminal (Ctrl+Shift+V) and press Enter','When the terminal asks for the key: "Copy key", paste it there and press Enter; then choose "Allow"']],
  macsch:[['Programm laden','Die Datei SparkHilfe aus den Downloads öffnen, dann das Programm „SparkHilfe-…“ öffnen (beim ersten Mal: „Öffnen“)','Den Freigaben „Bildschirmaufnahme“ und „Bedienungshilfen“ folgen und im Programm „Erlauben“ wählen'],['Load the program','Open the file SparkHilfe from your downloads, then open the program "SparkHilfe-…" (the first time: "Open")','Follow the permissions "Screen Recording" and "Accessibility" and choose "Allow" in the program']],
  nurwin:['Steuern geht bisher nur unter Windows, macOS und Linux (X11). Ansehen läuft weiter.','Control works only on Windows, macOS and Linux (X11) so far. Viewing goes on.'],
  startmac:['Die Datei SparkHilfe aus den Downloads öffnen (Safari packt sie selbst aus) und das Programm „SparkHilfe-…“ öffnen; beim ersten Mal fragt macOS, ob Sie es öffnen möchten: „Öffnen“. SparkHilfe führt Sie dann zu den Freigaben „Bildschirmaufnahme“ und „Bedienungshilfen“ und fragt Sie, bevor jemand steuern darf.','Open the file SparkHilfe from your downloads (Safari unpacks it by itself) and open the program "SparkHilfe-…"; the first time macOS asks whether you want to open it: "Open". SparkHilfe then leads you to the permissions "Screen Recording" and "Accessibility" and asks you before anyone may control.'],
  apple:['Von Apple beglaubigt (notarisiert); macOS prüft das beim Öffnen.','Notarized by Apple; macOS checks this when it opens.'],
  zeilelad:['Befehl zeigen','Show command'],kopieren:['Befehl kopieren','Copy command'],schluessel:['Schlüssel kopieren','Copy key'],
  kopiert:['Kopiert. Jetzt im Terminal einfügen (Strg+Umschalt+V) und Enter drücken.','Copied. Now paste it into the terminal (Ctrl+Shift+V) and press Enter.'],
  sohne:['Kopieren geht hier nicht; den Schlüssel bitte abtippen:','Copying does not work here; please type the key:'],
  linux:['Der Schlüssel gilt einmal und 10 Minuten. Das Programm fragt Sie, bevor jemand steuern darf.','The key works once and for 10 minutes. The program asks you before anyone may control.'],
  start:['Die Datei SparkHilfe aus den Downloads öffnen. Windows warnt vielleicht einmal („Weitere Informationen“ → „Trotzdem ausführen“). Das Programm fragt Sie, bevor jemand steuern darf.','Open the file SparkHilfe from your downloads. Windows may warn once ("More info" → "Run anyway"). The program asks you before anyone may control.'],
  verbunden:['Das Programm ist verbunden','The program is connected'],verbundentext:['Es fragt Sie jetzt, ob {a} steuern darf.','It now asks you whether {a} may control.'],
  aktiv:['Steuerung erlaubt','Control allowed'],aktivtext:['Beenden im Programm oder oben mit „Sitzung beenden“.','End in the program or above with "End session".'],
  nuran:['Nur ansehen','View only'],nurantext:['Im Programm ist nur Ansehen gewählt.','View only is chosen in the program.'],
  ohnetext:['Es wird nicht gesteuert. Ansehen läuft weiter.','There is no control. Viewing goes on.'],
  neu:['Bitte die Seite neu laden.','Please reload the page.'],
  warte:['Bitte einen Moment warten, dann noch einmal tippen (noch {n} s).','Please wait a moment, then tap again ({n} s left).'],
  ungueltig:['Nummer nicht gültig.','Number not valid.'],vorname:['Bitte den Vornamen eingeben (Buchstaben, bis 30).','Please enter your first name (letters, up to 30).'],
  fehlt:['Für dieses System gibt es das Programm gerade nicht. Ansehen läuft weiter.','There is no program for this system right now. Viewing goes on.'],
  nicht:['Gerade nicht möglich.','Not possible right now.'],anders:['Das ging gerade nicht. Bitte noch einmal tippen.','That did not work. Please tap again.'],
  keine:['Keine Verbindung.','No connection.'],
  browser:['Dieser Browser kann den Bildschirm nicht teilen. Bitte Chrome, Edge, Firefox oder Safari nehmen.','This browser cannot share the screen. Please use Chrome, Edge, Firefox or Safari.']};
const S={ws:null,pc:null,stream:null,admin:'',bis:0,clock:0,tok:'',art:'',key:''};
const tr=(k,n)=>{const t=L[k][EN?1:0];return typeof t==='string'?t.replace(/\{a\}/g,S.admin).replace('{n}',n):t},$=id=>document.getElementById(id);
document.documentElement.lang=EN?'en':'de';document.title=tr('marke');
document.querySelectorAll('[data-t]').forEach(e=>{e.textContent=tr(e.dataset.t)});
$('name').placeholder=tr('name');$('name').setAttribute('aria-label',tr('name'));$('nummer').setAttribute('aria-label',tr('nummer'));
$('fuss').textContent=tr(location.protocol==='https:'?'fuss':'fusslan');
// the server's own words never show here: every refusal by its status as a fixed text (the panel's texts are German
// and some English); a 429 waits out its Retry-After with the button off and the reason on it
function why(st,start){return st===403?tr(start?'ungueltig':'neu'):st===400?tr('vorname'):st===404&&!start?tr('fehlt'):st===503||st===404?tr('nicht'):tr('anders')}
function hint(out,t){out.textContent=t;out.hidden=!t}
function warte(r,btn,out){let n=parseInt(r.headers.get('Retry-After')||'',10);if(!(n>0&&n<=120))n=30;clearInterval(btn._warte);
  const tick=()=>{if(n<=0){clearInterval(btn._warte);if(out.textContent===btn.title)hint(out,'');btn.disabled=false;btn.title='';return}
    btn.disabled=true;btn.title=tr('warte',n);hint(out,btn.title);n--};tick();btn._warte=setInterval(tick,1000)}
function nein(r,btn,out,start){if(r.status===429)return warte(r,btn,out);hint(out,why(r.status,start))}
// the link's key: only from the part behind "#", never sent in an address; the address bar forgets it at once
let link='';const h=location.hash.slice(1);
if(/^[A-Za-z0-9_-]{20,30}$/.test(h)){link=h;$('nummer').hidden=true;$('linkda').hidden=false}
if(location.hash)history.replaceState(null,'',location.pathname);
const show=id=>{['s-start','s-warten','s-offen','s-zu'].forEach(x=>$(x).hidden=x!==id);$('ende').hidden=id==='s-start'||id==='s-zu';if(id!=='s-offen')$('state').hidden=true};
(link?$('name'):$('nummer')).focus();
$('f-start').onsubmit=async e=>{e.preventDefault();hint($('fehler'),'');
  const body={name:$('name').value.trim()};if(link)body.link=link;else body.nummer=$('nummer').value.replace(/\s/g,'');
  let r;try{r=await /*raw: the person's page loads without base.js*/fetch('/api/hilfe/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'omit'})}
  catch(err){hint($('fehler'),tr('keine'));return}
  if(!r.ok){nein(r,$('f-start').querySelector('button'),$('fehler'),true);
    if(link&&r.status===403){link='';$('nummer').hidden=false;$('linkda').hidden=true}return}
  const d=await r.json();S.admin=String(d.admin||'').slice(0,60);link='';connect(d.tok)};
function connect(tok){S.tok=tok;show('s-warten');$('wartentext').textContent=EN?`${S.admin} will accept in a moment.`:`${S.admin} nimmt gleich an.`;
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/hilfe/ws');S.ws=ws;
  ws.onopen=()=>ws.send(JSON.stringify({typ:'hallo',tok}));
  ws.onmessage=ev=>{let m;try{m=JSON.parse(ev.data)}catch(e){return}onMsg(m)};
  ws.onclose=()=>zu()}
function send(m){if(S.ws&&S.ws.readyState===1)S.ws.send(JSON.stringify(m))}
function offen(){show('s-offen');$('teiltext').textContent=tr('teiltext');$('prevtext').textContent=tr('prev');$('chatin').placeholder=tr('msg');$('chatin').setAttribute('aria-label',tr('msg'));bar(!!S.stream)}
async function onMsg(m){
  if(m.typ==='stand'){if(m.stand==='offen'){S.bis=m.bis;offen();pc(m.ice||[])}if(m.stand==='zu')zu()}
  else if(m.typ==='sdp'&&S.pc&&m.art==='answer'){try{await S.pc.setRemoteDescription({type:'answer',sdp:m.sdp})}catch(e){}}
  else if(m.typ==='ice'&&S.pc){try{await S.pc.addIceCandidate(m.c||null)}catch(e){}}
  else if(m.typ==='chat')chat(String(m.text||''),false);
  else if(m.typ==='zeig')zeig(m.x,m.y);
  else if(m.typ==='zeit'){S.bis=m.bis;bar(!!S.stream)}
  else if(m.typ==='steuern')steuern(m)}
// S2 Steuern (spontansteuern.py): only after the admin asked; the program comes as a blob by POST with her session key,
// its one-time key goes only into the file name (never into an address); the program asks her once more.
// S2d Linux X11: no file, one line for her terminal (the key only in its variable SPARKHILFE_SCHLUESSEL)
// S2c Mac: a zip the Spark packs per help; the key only in the app's name inside (an iPad says "Macintosh" too: touch)
async function osArt(){const ua=navigator.userAgent||'';
  if(/Linux/i.test(ua)&&!/Android|CrOS/i.test(ua))return 'linux-x11';
  if(/Macintosh/i.test(ua))return (navigator.maxTouchPoints||0)>1?'':'mac';
  if(!/Windows/i.test(ua))return '';
  try{const d=navigator.userAgentData&&await navigator.userAgentData.getHighEntropyValues(['architecture']);if(d&&d.architecture==='arm')return 'windows-arm64'}catch(e){}
  return 'windows-x64'}
function schritte(list){const ol=$('schritte');ol.textContent='';(list||[]).forEach(t=>{const li=document.createElement('li');li.textContent=t;ol.appendChild(li)});ol.hidden=!list}
function stText(k,text){$('steuern').hidden=false;$('steuerntitel').textContent=tr(k);$('steuerntext').textContent=tr(text);schritte(null)}
function knoepfeWeg(){$('laden').hidden=$('nein').hidden=$('pruefknopf').hidden=$('pruef').hidden=true;$('pruef').textContent='';hint($('hinweis'),'');zeileWeg()}
async function steuern(m){
  if(m.stand==='angefragt'){S.art=await osArt();const lin=S.art==='linux-x11',mac=S.art==='mac',sha=lin?'':String(((m.programme||{})[S.art])||'').replace(/[^0-9a-f]/g,''),da=lin?m.zeile===true:!!sha;
    knoepfeWeg();$('laden').hidden=$('nein').hidden=!da;$('laden').textContent=tr(lin?'zeilelad':'laden');
    $('pruef').textContent=mac&&da?tr('apple'):sha;$('pruef').hidden=!(mac&&da);$('pruefknopf').hidden=!sha||mac;$('pruefknopf').setAttribute('aria-expanded','false');   // Mac: Apple's notarization in words
    $('steuern').hidden=false;$('steuerntitel').textContent=tr('wunsch');$('steuerntext').textContent=tr(!da?(S.art?'fehlt':'nurwin'):lin?'lintext':'wintext');schritte(da?tr(lin?'linsch':mac?'macsch':'winsch'):null)}
  else if(m.stand==='programm'){knoepfeWeg();stText('verbunden','verbundentext')}
  else if(m.stand==='control')stText('aktiv','aktivtext');
  else if(m.stand==='view')stText('nuran','nurantext');
  else{knoepfeWeg();stText('nuran','ohnetext')}}
function zeileWeg(){$('zeile').textContent=$('skey').textContent='';S.key='';$('zeile').hidden=$('kopieren').hidden=$('kopkey').hidden=$('skey').hidden=true}
async function laden(){let r;const lin=S.art==='linux-x11',mac=S.art==='mac',out=$('hinweis');hint(out,'');
  try{r=await /*raw: the person's page loads without base.js*/fetch('/api/hilfe/programm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lin||mac?{tok:S.tok,art:S.art,origin:location.origin}:{tok:S.tok,art:S.art}),credentials:'omit'})}
  catch(e){hint(out,tr('keine'));return}
  if(!r.ok)return nein(r,$('laden'),out,false);
  if(lin){let d={};try{d=await r.json()}catch(x){}const b=String(d.befehl||''),k=String(d.schluessel||'');
    if(!/^curl [\x20-\x7e]{10,600}$/.test(b)||!/^[A-Za-z0-9_-]{22}$/.test(k)){hint(out,tr('neu'));return}
    S.key=k;$('zeile').textContent=b;$('zeile').hidden=$('kopieren').hidden=$('kopkey').hidden=false;$('steuerntext').textContent=tr('linux');return}
  if(mac){const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');   // the key is inside, in the app's name
    a.href=url;a.download='SparkHilfe.zip';document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);$('steuerntext').textContent=tr('startmac');return}
  const key=r.headers.get('X-Spark-Schluessel')||'';if(!/^[A-Za-z0-9_-]{22}$/.test(key)){hint(out,tr('neu'));return}
  const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');
  a.href=url;a.download='SparkHilfe-'+location.host.replace(/[^A-Za-z0-9.-]/g,'_')+'-'+key+'.exe';document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),60000);$('steuerntext').textContent=tr('start')}
$('laden').onclick=laden;
$('pruefknopf').onclick=()=>{const p=$('pruef');p.hidden=!p.hidden;$('pruefknopf').setAttribute('aria-expanded',String(!p.hidden))};
$('kopieren').onclick=async()=>{try{await navigator.clipboard.writeText($('zeile').textContent);$('steuerntext').textContent=tr('kopiert')}catch(e){}};
// the key only to the clipboard (shown only when copying does not work); never in an address, never in the line
$('kopkey').onclick=async()=>{if(!S.key)return;try{await navigator.clipboard.writeText(S.key);$('steuerntext').textContent=tr('kopiert')}
  catch(e){$('steuerntext').textContent=tr('sohne');$('skey').textContent=S.key;$('skey').hidden=false}};
$('nein').onclick=()=>{send({typ:'steuern_nein'});knoepfeWeg();stText('nuran','ohnetext')};
function bar(sieht){$('state').hidden=false;$('state').classList.toggle('on',sieht);$('bartext').textContent=tr(sieht?'geteilt':'bereit');
  clearInterval(S.clock);const tick=()=>{$('baruhr').textContent=tr('uhr',Math.max(0,Math.ceil((S.bis-Date.now()/1000)/60)))};tick();S.clock=setInterval(tick,15000)}
function pc(ice){if(S.pc)return;const p=new RTCPeerConnection({iceServers:ice});S.pc=p;
  p.onicecandidate=e=>send({typ:'ice',c:e.candidate?{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex}:null})}
$('teilen').onclick=async()=>{if(!navigator.mediaDevices||!navigator.mediaDevices.getDisplayMedia){chat(tr('browser'),false);return}
  let st;try{st=await navigator.mediaDevices.getDisplayMedia({video:true,audio:false})}catch(e){return}
  S.stream=st;const tr0=st.getVideoTracks()[0];
  for(const s of S.pc.getSenders())if(s.track)S.pc.removeTrack(s);
  S.pc.addTrack(tr0,st);$('eigen').srcObject=st;$('prev').hidden=false;$('teilbox').hidden=true;
  tr0.onended=()=>{S.stream=null;$('prev').hidden=true;$('teilbox').hidden=false;send({typ:'teilt',an:false});bar(false)};
  const o=await S.pc.createOffer();await S.pc.setLocalDescription(o);send({typ:'sdp',art:'offer',sdp:o.sdp});send({typ:'teilt',an:true});bar(true)};
// the small preview can be hidden; the circle keeps working once it is shown again
$('prevweg').onclick=()=>{const r=$('pvrow');r.hidden=!r.hidden;$('prevweg').textContent=tr(r.hidden?'einblenden':'ausblenden')};
function chat(text,mine){const b=document.createElement('div'),w=document.createElement('b'),t=document.createElement('time'),x=document.createElement('div');
  b.className='msg'+(mine?' mine':'');w.className='who';w.textContent=mine?tr('sie'):S.admin;
  t.textContent=new Date().toLocaleTimeString(EN?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});x.textContent=text;
  b.append(w,t,x);$('chat').appendChild(b);$('chat').scrollTop=$('chat').scrollHeight}
$('f-chat').onsubmit=e=>{e.preventDefault();const s=$('chatin').value.trim().slice(0,500);if(!s)return;send({typ:'chat',text:s});chat(s,true);$('chatin').value=''};
function zeig(x,y){if(typeof x!=='number'||typeof y!=='number'||x<0||x>1||y<0||y>1)return;const v=$('eigen'),d=$('dot');if($('prev').hidden||$('pvrow').hidden)return;
  d.style.left=(x*v.clientWidth)+'px';d.style.top=(y*v.clientHeight)+'px';d.hidden=false;clearTimeout(S.dot);S.dot=setTimeout(()=>d.hidden=true,4000)}
$('ende').onclick=()=>{send({typ:'ende'});zu()};
function zu(){if(S.stream)S.stream.getTracks().forEach(t=>t.stop());S.stream=null;if(S.pc){try{S.pc.close()}catch(e){}S.pc=null}
  const ws=S.ws;S.ws=null;if(ws){ws.onclose=null;try{ws.close()}catch(e){}}clearInterval(S.clock);
  if(!$('s-start').hidden)return;show('s-zu')}
addEventListener('pagehide',()=>{send({typ:'ende'})});
})();
