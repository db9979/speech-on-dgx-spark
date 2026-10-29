'use strict';
// Spontanhilfe (spontanhilfe.py, plan spontanhilfe S1): the admin's part of Fernzugang → Spontanhilfe, a tab of the
// unlocked page. „Neue Hilfe“ shows a number and a link; when the person waits, „Annehmen“ opens the admin's socket; her
// screen comes by WebRTC straight from her browser (TURN on tars when „Anrufe von unterwegs“ is on). Chat only as
// text (textContent), „Zeigen“ sends a point 0..1, nothing is recorded or sent to a model. S3 (art „shell“): the person
// ran one line in her terminal; after her „j“ her shell comes into an xterm here (bytes, binary), nothing else.
const SH={d:null,ws:null,pc:null,term:null,timer:0,clock:0,zeig:false,link:'',qr:'',befehl:'',befehlMac:'',gesendet:{}};
const SH_ART={ansehen:['Ansehen','View'],shell:['Shell','Shell'],nummer_verfallen:['Nummer verfallen','Number expired'],nummer_gesperrt:['Nummer gesperrt','Number locked']};
function shArt(a){return SH_ART[a]?t(...SH_ART[a]):a}
function shMsg(text,bad){const m=$('shmsg');if(m){m.textContent=text||'';m.classList.toggle('err',!!bad)}}
async function shLoad(){clearTimeout(SH.timer);if(!$('shmain'))return;
  try{const r=await api('/api/admin/spontanhilfe');SH.d=await r.json()}catch(e){$('shmain').hidden=true;return}
  shShow();if(document.querySelector('section#fern.on'))SH.timer=setTimeout(shLoad,SH.ws?10000:3000)}
function shRest(s){s=Math.max(0,s|0);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
// locked: nothing of a help stays in the page, not even hidden (rule „Bereich entsperren“)
function shLeeren(){for(const id of ['shnummer','shnummerinfo','shlink','shqrbild','shwartetname','shjetztlist','shverlauflist','shverlaufh','shbefehl','shbefehlmac'])$(id).textContent='';SH.link='';SH.qr='';SH.befehl='';SH.befehlMac=''}
function shShow(){const d=SH.d,box=$('shmain');if(!d||!box)return;const aus=!d.on||!!d.notaus||!!d.gesperrt;
  if(aus){box.hidden=true;if(d.gesperrt)shLeeren();$('shbanner').hidden=!(d.gesperrt&&SH.ws);fzTopLine();const war=FZ.tab;fzTabs();if(war!==FZ.tab)fzShow();return}
  box.hidden=!fzTabs();
  const h=d.hilfe,neu=h&&h.stand==='neu',wartet=h&&h.stand==='wartet',offen=h&&h.stand==='offen';
  $('shturn').hidden=!!d.turn;
  $('shgo').hidden=!!h&&!neu;$('shnummerbox').hidden=!neu;
  if(neu){$('shnummer').textContent=h.nummer.slice(0,3)+' '+h.nummer.slice(3);
    $('shnummerinfo').textContent=t(`noch ${shRest(h.nummer_rest)} · einmal · ${h.fehl} von ${h.fehl_max} Fehlversuchen`,`${shRest(h.nummer_rest)} left · once · ${h.fehl} of ${h.fehl_max} wrong tries`);
    $('shmailrow').hidden=!d.mail;$('shmailno').hidden=!!d.mail;$('shlinkrow').hidden=!SH.link;
    $('shbefehl').textContent=SH.befehl;$('shbefehlmac').textContent=SH.befehlMac;$('shbefehlrow').hidden=!SH.befehl}
  else{SH.link='';SH.qr='';SH.befehl='';SH.befehlMac='';$('shqrbild').textContent=''}
  const shell=!!h&&h.art==='shell';
  $('shwartet').hidden=!wartet;if(wartet){$('shwartetname').textContent=t(`„${h.name}“ wartet (${shWo(h)}${shell?' · Shell'+(h.os?', '+h.os:''):''}).`,`"${h.name}" is waiting (${shWo(h)}${shell?' · shell'+(h.os?', '+h.os:''):''}).`);
    $('shwartethin').textContent=shell?t('Nach „Annehmen“ tippt die Person in ihrem Terminal „j“; erst dann kommt ihre Shell.','After "Accept" the person types "j" in her terminal; only then her shell comes.'):t('Nach „Annehmen“ klickt die Person selbst „Bildschirm teilen“.','After "Accept" the person clicks "Share screen" herself.')}
  $('shbanner').hidden=!offen;fzTopLine();$('shuhr').hidden=!offen;$('shchat').hidden=!offen||shell;$('shview').hidden=!offen||shell;$('shterm').hidden=!offen||!shell;$('shtools').hidden=!offen;
  $('shzeig').hidden=shell;$('shvoll').hidden=shell;
  if(offen)shUhr(h.bis,h.kann_verlaengern)
  shJetzt();shVerlauf()}
function shWo(h){return fzWoher(h.herkunft)+(h.ip?' · '+h.ip:'')}
function shUhr(bis,kann){SH.bis=bis;SH.kann=kann;clearInterval(SH.clock);const tick=()=>{const rest=SH.bis-Date.now()/1000;
    $('shuhrtext').textContent=t(`noch ${shRest(rest)} · höchstens ${SH.d?SH.d.max_min:180} Minuten`,`${shRest(rest)} left · at most ${SH.d?SH.d.max_min:180} minutes`);
    const warn=rest<=(SH.d?SH.d.hinweis_s:600);$('shuhr').classList.toggle('warn',warn);$('shplus').hidden=!SH.kann;
    $('shhinweis').hidden=!warn;
    const n=SH.d&&SH.d.hilfe;$('shbtext').textContent=t(`Spontanhilfe aktiv · ${n?n.name:''} · noch ${shRest(rest)}`,`Spontaneous help active · ${n?n.name:''} · ${shRest(rest)} left`)}; tick();SH.clock=setInterval(tick,1000)}
function shJetzt(){const d=SH.d,h=d&&d.hilfe,box=$('shjetzt'),list=$('shjetztlist');if(!box)return;list.textContent='';
  box.hidden=!(h&&h.stand!=='neu');if(box.hidden)return;
  const r=fzEl('div','fzjrow'),tx=fzEl('div');
  tx.append(fzEl('b','',h.admin+' → „'+h.name+'“'),fzEl('div','fh',[shWo(h),h.stand==='offen'?t('seit ','since ')+fzZeit(h.seit):t('wartet','waiting'),
    h.stand==='offen'?shArt(h.art):''].filter(Boolean).join(' · ')));
  r.append(tx,fzBtn(t('Trennen','Disconnect'),'danger',shEnde));list.appendChild(r)}
function shVerlauf(){const d=SH.d,list=$('shverlauflist');if(!d||!list)return;list.textContent='';const v=d.verlauf||[];
  $('shverlaufh').textContent=t(`Die letzten ${d.verlauf_tage||30} Tage: Zeit, Admin, Art, Dauer und von wo. Nie ein Name, nie ein Bild, nie der Chat.`,`The last ${d.verlauf_tage||30} days: time, admin, kind, duration and from where. Never a name, a picture or the chat.`);
  if(!v.length){list.appendChild(fzEl('div','mut',t('Noch keine Hilfe.','No help yet.')));return}
  for(const x of v){const r=fzEl('div','fzvrow'),sitz=x.art==='ansehen'||x.art==='shell';r.append(fzEl('span','',fzZeit(x.t)),fzEl('span','',[shArt(x.art),x.admin].filter(Boolean).join(' · ')),
    fzEl('span','mut',sitz?x.min+' min · '+fzWoher(x.herkunft):x.n+' '+t('Fehlversuche','wrong tries')));list.appendChild(r)}}
async function shNeu(){try{const r=await api('/api/admin/spontanhilfe/neu',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});
    const d=await r.json();SH.gesendet={};shMailFrei();SH.link=d.link||'';SH.qr=d.qr||'';SH.befehl=d.befehl||'';SH.befehlMac=d.befehl_mac||'';$('shlink').textContent=SH.link||t('Ein Link braucht die https-Adresse des Panels.','A link needs the panel\'s https address.');shLoad()}catch(e){shMsg(e.message,true)}}
async function shKopie(){try{await navigator.clipboard.writeText(SH.link);shMsg(t('Link kopiert.','Link copied.'))}catch(e){shMsg(t('Kopieren ging nicht.','Copy failed.'),true)}}
async function shBefehlKopie(x){try{await navigator.clipboard.writeText(x);shMsg(t('Zeile kopiert.','Line copied.'))}catch(e){shMsg(t('Kopieren ging nicht.','Copy failed.'),true)}}
async function shTeilen(){if(!navigator.share){shKopie();return}try{await navigator.share({title:t('Hilfe am Bildschirm','Screen help'),url:SH.link})}catch(e){}}
function shQr(){const b=$('shqrbild');if(b.childElementCount){b.textContent='';return}if(!SH.qr)return;
  const img=document.createElement('img');img.alt=t('QR-Code des Links','QR code of the link');img.src='data:image/svg+xml;base64,'+btoa(SH.qr);b.appendChild(img)}
// one invitation per address and help: the button stays off while sending and after it (a new address frees it);
// the same address again only after 60 s and a confirm (the panel checks both, 409 „Einladung schon gesendet“)
function shMailFrei(){const b=$('shmailgo');if(b){b.disabled=false;b.classList.remove('senden');b.removeAttribute('aria-busy')}}
async function shMail(){const an=$('shan').value.trim(),b=$('shmailgo');if(!an||b.disabled)return;
  const k=an.toLowerCase(),vor=SH.gesendet[k];let nochmal=false;
  if(vor){if(Date.now()-vor<60000){shMsg(t('Einladung schon gesendet.','Invitation already sent.'),true);return}
    if(!confirm(t('Einladung schon gesendet. Nochmal senden?','Invitation already sent. Send again?')))return;nochmal=true}
  b.disabled=true;b.classList.add('senden');b.setAttribute('aria-busy','true');shMsg(t('Einladung wird gesendet …','Sending invitation …'));
  try{await api('/api/admin/spontanhilfe/einladung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({an,link:SH.link,en:$('shmailen').checked,nochmal})});
    SH.gesendet[k]=Date.now();b.classList.remove('senden');b.removeAttribute('aria-busy');
    shMsg(t('Einladung gesendet.','Invitation sent.'));$('shan').value=''}catch(e){shMailFrei();shMsg(e.message,true)}}
async function shEnde(){try{await api('/api/admin/spontanhilfe',{method:'DELETE'})}catch(e){}shZu();shLoad()}
async function shPlus(){try{await api('/api/admin/spontanhilfe/verlaengern',{method:'POST'});shLoad()}catch(e){shMsg(e.message,true)}}
// ---------------------------------------------------------------- the open help
async function shAnnehmen(){let tk;const h=SH.d&&SH.d.hilfe,shell=!!h&&h.art==='shell';
  if(shell)try{await fzLaden()}catch(e){shMsg(e.message,true);return}
  try{const r=await api('/api/admin/spontanhilfe/annehmen',{method:'POST'});tk=(await r.json()).ticket}catch(e){shMsg(e.message,true);return}
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/spontanhilfe/admin?t='+encodeURIComponent(tk));
  ws.binaryType='arraybuffer';SH.ws=ws;$('shchatlist').textContent='';
  ws.onmessage=ev=>{if(ev.data instanceof ArrayBuffer){if(SH.term)SH.term.write(new Uint8Array(ev.data));return}let m;try{m=JSON.parse(ev.data)}catch(e){return}shIn(m)};
  ws.onclose=()=>{if(SH.ws===ws){shZu();shLoad()}}}
function shSend(m){if(SH.ws&&SH.ws.readyState===1)SH.ws.send(JSON.stringify(m))}
async function shIn(m){
  if(m.typ==='stand'){if(m.stand==='offen'){if(m.art==='shell')shTerm();else shPc(m.ice||[]);shUhr(m.bis,m.kann_verlaengern);shLoad()}if(m.stand==='zu'){shMsg(t('Die Hilfe ist beendet.','The help has ended.'));shZu();shLoad()}}
  else if(m.typ==='sdp'&&SH.pc){await SH.pc.setRemoteDescription({type:'offer',sdp:m.sdp});const a=await SH.pc.createAnswer();await SH.pc.setLocalDescription(a);shSend({typ:'sdp',art:'answer',sdp:a.sdp})}
  else if(m.typ==='ice'&&SH.pc){try{await SH.pc.addIceCandidate(m.c||null)}catch(e){}}
  else if(m.typ==='chat')shChat(m.text,false);
  else if(m.typ==='teilt')$('shviewinfo').textContent=m.an?t('Die Person teilt ihren Bildschirm. Nichts wird aufgezeichnet.','The person shares the screen. Nothing is recorded.'):t('Die Person teilt gerade nicht.','The person is not sharing right now.');
  else if(m.typ==='erlaubt'&&SH.term){SH.term.write('\x1b[2m'+t('Erlaubt. Die Shell der Person, mit ihren Rechten; sie sieht alles mit.','Allowed. The person\'s shell, with her rights; she sees everything.')+'\x1b[0m\r\n');shTermGroesse(true);SH.term.focus()}
  else if(m.typ==='zeit'){shUhr(m.bis,true);shLoad()}
  else if(m.typ==='hinweis'){SH.kann=m.kann_verlaengern;shMsg(t('Die Hilfe endet in 10 Minuten. „Verlängern“ gibt 60 Minuten mehr.','The help ends in 10 minutes. "Extend" gives 60 more minutes.'))}}
function shPc(ice){if(SH.pc)return;const pc=new RTCPeerConnection({iceServers:ice});SH.pc=pc;
  pc.onicecandidate=e=>shSend({typ:'ice',c:e.candidate?{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex}:null});
  pc.ontrack=e=>{$('shvideo').srcObject=e.streams[0]||new MediaStream([e.track])}}
// S3: her shell in an xterm (the bytes binary both ways, the size as „groesse“)
function shTerm(){if(SH.term||!window.Terminal)return;const el=$('shterm');el.hidden=false;el.textContent='';
  const term=new window.Terminal({cursorBlink:true,fontSize:14,cols:80,rows:24,scrollback:2000,theme:{background:'#0b1020'}});term.open(el);SH.term=term;
  term.write('\x1b[2m'+t('Warte auf das „j“ der Person in ihrem Terminal …','Waiting for the person\'s "j" in her terminal …')+'\x1b[0m\r\n');
  const enc=new TextEncoder();term.onData(x=>{if(SH.ws&&SH.ws.readyState===1)SH.ws.send(enc.encode(x))});shTermGroesse(true)}
function shTermGroesse(force){const term=SH.term,el=$('shterm');if(!term||!el||el.hidden)return;const w=Math.max(320,el.clientWidth-16),h=Math.max(200,el.clientHeight-12);
  const c=Math.max(20,Math.min(400,Math.floor(w/8.6))),r=Math.max(5,Math.min(200,Math.floor(h/17.5)));if(!force&&c===term.cols&&r===term.rows)return;
  term.resize(c,r);shSend({typ:'groesse',cols:c,rows:r})}
addEventListener('resize',()=>shTermGroesse(false));
function shZu(){const ws=SH.ws;SH.ws=null;if(ws)try{ws.close()}catch(e){}if(SH.pc){try{SH.pc.close()}catch(e){}SH.pc=null}
  if(SH.term){try{SH.term.dispose()}catch(e){}SH.term=null;const el=$('shterm');if(el)el.textContent=''}
  const v=$('shvideo');if(v)v.srcObject=null;clearInterval(SH.clock);SH.zeig=false;const z=$('shzeig');if(z)z.classList.remove('on')}
function shChat(text,mine){const l=$('shchatlist'),b=fzEl('div','shmsg'+(mine?' mine':''),text);l.appendChild(b);l.scrollTop=l.scrollHeight}
function shChatSend(){const i=$('shchatin'),s=i.value.trim().slice(0,500);if(!s)return;shSend({typ:'chat',text:s});shChat(s,true);i.value=''}
function shZeigen(e){if(!SH.zeig)return;const v=$('shvideo'),r=v.getBoundingClientRect();if(!v.videoWidth)return;
  // the picture inside the element (object-fit: contain): only a point on it counts
  const s=Math.min(r.width/v.videoWidth,r.height/v.videoHeight),w=v.videoWidth*s,h=v.videoHeight*s,x0=r.left+(r.width-w)/2,y0=r.top+(r.height-h)/2;
  const x=(e.clientX-x0)/w,y=(e.clientY-y0)/h;if(x<0||x>1||y<0||y>1)return;shSend({typ:'zeig',x,y});
  const dot=$('shzeigdot');dot.style.left=(e.clientX-r.left)+'px';dot.style.top=(e.clientY-r.top)+'px';dot.hidden=false;clearTimeout(SH.dot);SH.dot=setTimeout(()=>dot.hidden=true,2500)}
{const g=$('shgo');if(g){g.onclick=shNeu;$('shweg').onclick=shEnde;$('shkopie').onclick=shKopie;$('shbefehlkopie').onclick=()=>shBefehlKopie(SH.befehl);$('shbefehlmackopie').onclick=()=>shBefehlKopie(SH.befehlMac);$('shteilen').onclick=shTeilen;$('shqr').onclick=shQr;$('shmailgo').onclick=shMail;$('shan').oninput=shMailFrei;
  $('shannehmen').onclick=shAnnehmen;$('shablehnen').onclick=shEnde;$('shende').onclick=shEnde;$('shbende').onclick=shEnde;$('shplus').onclick=shPlus;
  $('shzeig').onclick=()=>{SH.zeig=!SH.zeig;$('shzeig').classList.toggle('on',SH.zeig)};$('shvideo').onclick=shZeigen;
  $('shvoll').onclick=()=>{const v=$('shview');if(v.requestFullscreen)v.requestFullscreen().catch(()=>{})};
  $('shchatin').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();shChatSend()}};$('shchatgo').onclick=shChatSend;
  $('shverlaufweg').onclick=async()=>{if(!confirm(t('Den ganzen Verlauf der Spontanhilfe löschen?','Delete the whole history of spontaneous help?')))return;
    try{await api('/api/admin/spontanhilfe/verlauf',{method:'DELETE'});shLoad()}catch(e){shMsg(e.message,true)}}}}
window.shLoad=shLoad;window.shShow=shShow;
