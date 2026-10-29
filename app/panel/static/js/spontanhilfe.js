'use strict';
// Spontanhilfe (spontanhilfe.py, plan spontanhilfe S1): the admin's part of Fernzugang → Spontanhilfe, a tab of the
// unlocked page. „Neue Hilfe“ shows a number and a link; when the person waits, „Annehmen“ opens the admin's socket; her
// screen comes by WebRTC straight from her browser (TURN on tars when „Anrufe von unterwegs“ is on). Chat only as
// text (textContent), „Zeigen“ sends a point 0..1, nothing is recorded or sent to a model.
const SH={d:null,ws:null,pc:null,timer:0,clock:0,zeig:false,link:'',qr:''};
function shMsg(text,bad){const m=$('shmsg');if(m){m.textContent=text||'';m.classList.toggle('err',!!bad)}}
async function shLoad(){clearTimeout(SH.timer);if(!$('shmain'))return;
  try{const r=await api('/api/admin/spontanhilfe');SH.d=await r.json()}catch(e){$('shmain').hidden=true;return}
  shShow();if(document.querySelector('section#fern.on'))SH.timer=setTimeout(shLoad,SH.ws?10000:3000)}
function shRest(s){s=Math.max(0,s|0);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
// locked: nothing of a help stays in the page, not even hidden (rule „Bereich entsperren“)
function shLeeren(){for(const id of ['shnummer','shnummerinfo','shlink','shqrbild','shwartetname','shjetztlist','shverlauflist','shverlaufh'])$(id).textContent='';SH.link='';SH.qr=''}
function shShow(){const d=SH.d,box=$('shmain');if(!d||!box)return;const aus=!d.on||!!d.notaus||!!d.gesperrt;
  if(aus){box.hidden=true;if(d.gesperrt)shLeeren();$('shbanner').hidden=!(d.gesperrt&&SH.ws);fzTopLine();const war=FZ.tab;fzTabs();if(war!==FZ.tab)fzShow();return}
  box.hidden=!fzTabs();
  const h=d.hilfe,neu=h&&h.stand==='neu',wartet=h&&h.stand==='wartet',offen=h&&h.stand==='offen';
  $('shturn').hidden=!!d.turn;
  $('shgo').hidden=!!h&&!neu;$('shnummerbox').hidden=!neu;
  if(neu){$('shnummer').textContent=h.nummer.slice(0,3)+' '+h.nummer.slice(3);
    $('shnummerinfo').textContent=t(`noch ${shRest(h.nummer_rest)} · einmal · ${h.fehl} von ${h.fehl_max} Fehlversuchen`,`${shRest(h.nummer_rest)} left · once · ${h.fehl} of ${h.fehl_max} wrong tries`);
    $('shmailrow').hidden=!d.mail;$('shmailno').hidden=!!d.mail;$('shlinkrow').hidden=!SH.link}
  else{SH.link='';SH.qr='';$('shqrbild').textContent=''}
  $('shwartet').hidden=!wartet;if(wartet)$('shwartetname').textContent=t(`„${h.name}“ wartet (${shWo(h)}).`,`"${h.name}" is waiting (${shWo(h)}).`);
  $('shbanner').hidden=!offen;fzTopLine();$('shuhr').hidden=!offen;$('shchat').hidden=!offen;$('shview').hidden=!offen;$('shtools').hidden=!offen;
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
    h.stand==='offen'?t('Ansehen','View'):''].filter(Boolean).join(' · ')));
  r.append(tx,fzBtn(t('Trennen','Disconnect'),'danger',shEnde));list.appendChild(r)}
function shVerlauf(){const d=SH.d,list=$('shverlauflist');if(!d||!list)return;list.textContent='';const v=d.verlauf||[];
  $('shverlaufh').textContent=t(`Die letzten ${d.verlauf_tage||30} Tage: Zeit, Admin, Art, Dauer und von wo. Nie ein Name, nie ein Bild, nie der Chat.`,`The last ${d.verlauf_tage||30} days: time, admin, kind, duration and from where. Never a name, a picture or the chat.`);
  if(!v.length){list.appendChild(fzEl('div','mut',t('Noch keine Hilfe.','No help yet.')));return}
  const art={ansehen:t('Ansehen','View'),nummer_verfallen:t('Nummer verfallen','Number expired'),nummer_gesperrt:t('Nummer gesperrt','Number locked')};
  for(const x of v){const r=fzEl('div','fzvrow');r.append(fzEl('span','',fzZeit(x.t)),fzEl('span','',[art[x.art]||x.art,x.admin].filter(Boolean).join(' · ')),
    fzEl('span','mut',x.art==='ansehen'?x.min+' min · '+fzWoher(x.herkunft):x.n+' '+t('Fehlversuche','wrong tries')));list.appendChild(r)}}
async function shNeu(){try{const r=await api('/api/admin/spontanhilfe/neu',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});
    const d=await r.json();SH.link=d.link||'';SH.qr=d.qr||'';$('shlink').textContent=SH.link||t('Ein Link braucht die https-Adresse des Panels.','A link needs the panel\'s https address.');shLoad()}catch(e){shMsg(e.message,true)}}
async function shKopie(){try{await navigator.clipboard.writeText(SH.link);shMsg(t('Link kopiert.','Link copied.'))}catch(e){shMsg(t('Kopieren ging nicht.','Copy failed.'),true)}}
async function shTeilen(){if(!navigator.share){shKopie();return}try{await navigator.share({title:t('Hilfe am Bildschirm','Screen help'),url:SH.link})}catch(e){}}
function shQr(){const b=$('shqrbild');if(b.childElementCount){b.textContent='';return}if(!SH.qr)return;
  const img=document.createElement('img');img.alt=t('QR-Code des Links','QR code of the link');img.src='data:image/svg+xml;base64,'+btoa(SH.qr);b.appendChild(img)}
async function shMail(){const an=$('shan').value.trim();if(!an)return;
  try{await api('/api/admin/spontanhilfe/einladung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({an,link:SH.link,en:$('shmailen').checked})});
    shMsg(t('Einladung gesendet.','Invitation sent.'));$('shan').value=''}catch(e){shMsg(e.message,true)}}
async function shEnde(){try{await api('/api/admin/spontanhilfe',{method:'DELETE'})}catch(e){}shZu();shLoad()}
async function shPlus(){try{await api('/api/admin/spontanhilfe/verlaengern',{method:'POST'});shLoad()}catch(e){shMsg(e.message,true)}}
// ---------------------------------------------------------------- the open help
async function shAnnehmen(){let tk;
  try{const r=await api('/api/admin/spontanhilfe/annehmen',{method:'POST'});tk=(await r.json()).ticket}catch(e){shMsg(e.message,true);return}
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/spontanhilfe/admin?t='+encodeURIComponent(tk));
  SH.ws=ws;$('shchatlist').textContent='';
  ws.onmessage=ev=>{let m;try{m=JSON.parse(ev.data)}catch(e){return}shIn(m)};
  ws.onclose=()=>{if(SH.ws===ws){shZu();shLoad()}}}
function shSend(m){if(SH.ws&&SH.ws.readyState===1)SH.ws.send(JSON.stringify(m))}
async function shIn(m){
  if(m.typ==='stand'){if(m.stand==='offen'){shPc(m.ice||[]);shUhr(m.bis,m.kann_verlaengern);shLoad()}if(m.stand==='zu'){shMsg(t('Die Hilfe ist beendet.','The help has ended.'));shZu();shLoad()}}
  else if(m.typ==='sdp'&&SH.pc){await SH.pc.setRemoteDescription({type:'offer',sdp:m.sdp});const a=await SH.pc.createAnswer();await SH.pc.setLocalDescription(a);shSend({typ:'sdp',art:'answer',sdp:a.sdp})}
  else if(m.typ==='ice'&&SH.pc){try{await SH.pc.addIceCandidate(m.c||null)}catch(e){}}
  else if(m.typ==='chat')shChat(m.text,false);
  else if(m.typ==='teilt')$('shviewinfo').textContent=m.an?t('Die Person teilt ihren Bildschirm. Nichts wird aufgezeichnet.','The person shares the screen. Nothing is recorded.'):t('Die Person teilt gerade nicht.','The person is not sharing right now.');
  else if(m.typ==='zeit'){shUhr(m.bis,true);shLoad()}
  else if(m.typ==='hinweis'){SH.kann=m.kann_verlaengern;shMsg(t('Die Hilfe endet in 10 Minuten. „Verlängern“ gibt 60 Minuten mehr.','The help ends in 10 minutes. "Extend" gives 60 more minutes.'))}}
function shPc(ice){if(SH.pc)return;const pc=new RTCPeerConnection({iceServers:ice});SH.pc=pc;
  pc.onicecandidate=e=>shSend({typ:'ice',c:e.candidate?{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex}:null});
  pc.ontrack=e=>{$('shvideo').srcObject=e.streams[0]||new MediaStream([e.track])}}
function shZu(){const ws=SH.ws;SH.ws=null;if(ws)try{ws.close()}catch(e){}if(SH.pc){try{SH.pc.close()}catch(e){}SH.pc=null}
  const v=$('shvideo');if(v)v.srcObject=null;clearInterval(SH.clock);SH.zeig=false;const z=$('shzeig');if(z)z.classList.remove('on')}
function shChat(text,mine){const l=$('shchatlist'),b=fzEl('div','shmsg'+(mine?' mine':''),text);l.appendChild(b);l.scrollTop=l.scrollHeight}
function shChatSend(){const i=$('shchatin'),s=i.value.trim().slice(0,500);if(!s)return;shSend({typ:'chat',text:s});shChat(s,true);i.value=''}
function shZeigen(e){if(!SH.zeig)return;const v=$('shvideo'),r=v.getBoundingClientRect();if(!v.videoWidth)return;
  // the picture inside the element (object-fit: contain): only a point on it counts
  const s=Math.min(r.width/v.videoWidth,r.height/v.videoHeight),w=v.videoWidth*s,h=v.videoHeight*s,x0=r.left+(r.width-w)/2,y0=r.top+(r.height-h)/2;
  const x=(e.clientX-x0)/w,y=(e.clientY-y0)/h;if(x<0||x>1||y<0||y>1)return;shSend({typ:'zeig',x,y});
  const dot=$('shzeigdot');dot.style.left=(e.clientX-r.left)+'px';dot.style.top=(e.clientY-r.top)+'px';dot.hidden=false;clearTimeout(SH.dot);SH.dot=setTimeout(()=>dot.hidden=true,2500)}
{const g=$('shgo');if(g){g.onclick=shNeu;$('shweg').onclick=shEnde;$('shkopie').onclick=shKopie;$('shteilen').onclick=shTeilen;$('shqr').onclick=shQr;$('shmailgo').onclick=shMail;
  $('shannehmen').onclick=shAnnehmen;$('shablehnen').onclick=shEnde;$('shende').onclick=shEnde;$('shbende').onclick=shEnde;$('shplus').onclick=shPlus;
  $('shzeig').onclick=()=>{SH.zeig=!SH.zeig;$('shzeig').classList.toggle('on',SH.zeig)};$('shvideo').onclick=shZeigen;
  $('shvoll').onclick=()=>{const v=$('shview');if(v.requestFullscreen)v.requestFullscreen().catch(()=>{})};
  $('shchatin').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();shChatSend()}};$('shchatgo').onclick=shChatSend;
  $('shverlaufweg').onclick=async()=>{if(!confirm(t('Den ganzen Verlauf der Spontanhilfe löschen?','Delete the whole history of spontaneous help?')))return;
    try{await api('/api/admin/spontanhilfe/verlauf',{method:'DELETE'});shLoad()}catch(e){shMsg(e.message,true)}}}}
window.shLoad=shLoad;window.shShow=shShow;
