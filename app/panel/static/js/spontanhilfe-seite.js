'use strict';
// The person's page of the Spontanhilfe (/hilfe, spontanhilfe.py): no login, no panel, no model. The number (or the
// link's key behind "#", taken from the address at once) and a first name; then her browser shares the screen by
// WebRTC only after her own click. Messages from the panel are data: shown with textContent, nothing else.
(()=>{
const EN=!/^de\b/i.test(navigator.language||'de');
const L={titel:['Hilfe am Bildschirm','Screen help'],intro:['Geben Sie die Nummer ein, die man Ihnen am Telefon gesagt hat.','Enter the number you were told on the phone.'],
  link:['Ihr Link ist erkannt.','Your link is recognised.'],weiter:['Weiter','Continue'],
  nichts:['Nichts wird installiert. Man sieht erst etwas, wenn Sie „Bildschirm teilen“ wählen.','Nothing is installed. Nothing is seen until you choose "Share screen".'],
  warten:['Einen Moment bitte','One moment please'],teilen:['Bildschirm teilen','Share screen'],
  prev:['So sieht man Ihren Bildschirm. Der gelbe Kreis zeigt, wohin man Sie bittet zu schauen.','This is how your screen is seen. The yellow circle shows where you are asked to look.'],
  senden:['Senden','Send'],beenden:['Beenden','End'],schliessen:['Oder einfach dieses Fenster schließen.','Or just close this window.'],
  zu:['Die Hilfe ist beendet','The help has ended'],zutext:['Es bleibt nichts zurück. Sie können dieses Fenster schließen.','Nothing is left behind. You can close this window.'],
  name:['Ihr Vorname','Your first name'],nummer:['Nummer','Number'],msg:['Nachricht schreiben …','Write a message …']};
const tr=k=>L[k][EN?1:0],$=id=>document.getElementById(id);
document.documentElement.lang=EN?'en':'de';document.title=tr('titel');
document.querySelectorAll('[data-t]').forEach(e=>{e.textContent=tr(e.dataset.t)});
$('name').placeholder=tr('name');$('name').setAttribute('aria-label',tr('name'));$('nummer').setAttribute('aria-label',tr('nummer'));$('chatin').placeholder=tr('msg');
// the link's key: only from the part behind "#", never sent in an address; the address bar forgets it at once
let link='';const h=location.hash.slice(1);
if(/^[A-Za-z0-9_-]{20,30}$/.test(h)){link=h;$('nummer').hidden=true;$('linkda').hidden=false}
if(location.hash)history.replaceState(null,'',location.pathname);
const S={ws:null,pc:null,stream:null,admin:'',bis:0,clock:0};
const show=id=>['s-start','s-warten','s-offen','s-zu'].forEach(x=>$(x).hidden=x!==id);
$('name').focus();
$('f-start').onsubmit=async e=>{e.preventDefault();$('fehler').textContent='';
  const body={name:$('name').value.trim()};if(link)body.link=link;else body.nummer=$('nummer').value.replace(/\s/g,'');
  let r;try{r=await /*raw: the person's page loads without base.js*/fetch('/api/hilfe/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'omit'})}
  catch(err){$('fehler').textContent=EN?'No connection.':'Keine Verbindung.';return}
  if(!r.ok){let d={};try{d=await r.json()}catch(x){}
    $('fehler').textContent=r.status===403?(EN?'Number not valid.':'Nummer nicht gültig.'):r.status===429?(EN?'Too many tries, please wait a minute.':'Zu viele Versuche, bitte eine Minute warten.'):String(d.detail||r.status);
    if(link&&r.status===403){link='';$('nummer').hidden=false;$('linkda').hidden=true}return}
  const d=await r.json();S.admin=String(d.admin||'');link='';connect(d.tok)};
function connect(tok){show('s-warten');$('wartentext').textContent=EN?`${S.admin} will accept in a moment.`:`${S.admin} nimmt gleich an.`;
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/hilfe/ws');S.ws=ws;
  ws.onopen=()=>ws.send(JSON.stringify({typ:'hallo',tok}));
  ws.onmessage=ev=>{let m;try{m=JSON.parse(ev.data)}catch(e){return}onMsg(m)};
  ws.onclose=()=>zu()}
function send(m){if(S.ws&&S.ws.readyState===1)S.ws.send(JSON.stringify(m))}
async function onMsg(m){
  if(m.typ==='stand'){if(m.stand==='offen'){S.bis=m.bis;show('s-offen');bar(false);pc(m.ice||[])}if(m.stand==='zu')zu()}
  else if(m.typ==='sdp'&&S.pc&&m.art==='answer'){try{await S.pc.setRemoteDescription({type:'answer',sdp:m.sdp})}catch(e){}}
  else if(m.typ==='ice'&&S.pc){try{await S.pc.addIceCandidate(m.c||null)}catch(e){}}
  else if(m.typ==='chat')chat(String(m.text||''),false);
  else if(m.typ==='zeig')zeig(m.x,m.y);
  else if(m.typ==='zeit'){S.bis=m.bis;bar(!!S.stream)}}
function bar(sieht){$('bartext').textContent=sieht?(EN?`${S.admin} sees your screen`:`${S.admin} sieht Ihren Bildschirm`):(EN?`${S.admin} is ready. Nothing is seen yet.`:`${S.admin} ist bereit. Noch sieht man nichts.`);
  clearInterval(S.clock);const tick=()=>{const m=Math.max(0,Math.ceil((S.bis-Date.now()/1000)/60));$('baruhr').textContent=EN?`ends after ${m} min at the latest`:`endet spätestens in ${m} min`};tick();S.clock=setInterval(tick,15000)}
function pc(ice){if(S.pc)return;const p=new RTCPeerConnection({iceServers:ice});S.pc=p;
  p.onicecandidate=e=>send({typ:'ice',c:e.candidate?{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex}:null})}
$('teilen').onclick=async()=>{if(!navigator.mediaDevices||!navigator.mediaDevices.getDisplayMedia){chat(EN?'This browser cannot share the screen. Please use Chrome, Edge, Firefox or Safari.':'Dieser Browser kann den Bildschirm nicht teilen. Bitte Chrome, Edge, Firefox oder Safari nehmen.',false);return}
  let st;try{st=await navigator.mediaDevices.getDisplayMedia({video:true,audio:false})}catch(e){return}
  S.stream=st;const tr0=st.getVideoTracks()[0];
  for(const s of S.pc.getSenders())if(s.track)S.pc.removeTrack(s);
  S.pc.addTrack(tr0,st);$('eigen').srcObject=st;$('prev').hidden=false;$('prevtext').hidden=false;$('teilen').hidden=true;
  tr0.onended=()=>{S.stream=null;$('prev').hidden=true;$('prevtext').hidden=true;$('teilen').hidden=false;send({typ:'teilt',an:false});bar(false)};
  const o=await S.pc.createOffer();await S.pc.setLocalDescription(o);send({typ:'sdp',art:'offer',sdp:o.sdp});send({typ:'teilt',an:true});bar(true)};
function chat(text,mine){const b=document.createElement('div');b.className='msg'+(mine?' mine':'');b.textContent=text;$('chat').appendChild(b);$('chat').scrollTop=$('chat').scrollHeight}
$('f-chat').onsubmit=e=>{e.preventDefault();const s=$('chatin').value.trim().slice(0,500);if(!s)return;send({typ:'chat',text:s});chat(s,true);$('chatin').value=''};
function zeig(x,y){if(typeof x!=='number'||typeof y!=='number'||x<0||x>1||y<0||y>1)return;const v=$('eigen'),d=$('dot');if($('prev').hidden)return;
  d.style.left=(x*v.clientWidth)+'px';d.style.top=(y*v.clientHeight)+'px';d.hidden=false;clearTimeout(S.dot);S.dot=setTimeout(()=>d.hidden=true,4000)}
$('ende').onclick=()=>{send({typ:'ende'});zu()};
function zu(){if(S.stream)S.stream.getTracks().forEach(t=>t.stop());S.stream=null;if(S.pc){try{S.pc.close()}catch(e){}S.pc=null}
  const ws=S.ws;S.ws=null;if(ws){ws.onclose=null;try{ws.close()}catch(e){}}clearInterval(S.clock);
  if(!$('s-start').hidden)return;show('s-zu')}
addEventListener('pagehide',()=>{send({typ:'ende'})});
})();
