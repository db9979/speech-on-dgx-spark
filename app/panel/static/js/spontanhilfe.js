'use strict';
// Spontanhilfe (spontanhilfe.py, plan spontanhilfe S1): the admin's part of Fernzugang → Spontanhilfe, a tab of the
// unlocked page. „Neue Hilfe“ shows a number and a link; when the person waits, „Annehmen“ opens the admin's socket; her
// screen comes by WebRTC straight from her browser (TURN on tars when „Anrufe von unterwegs“ is on). Chat only as
// text (textContent), „Zeigen“ sends a point 0..1, nothing is recorded or sent to a model. S3 (art „shell“): the person
// ran one line in her terminal; after her „j“ her shell comes into an xterm here (bytes, binary), nothing else.
const SH={d:null,ws:null,pc:null,term:null,timer:0,clock:0,ntick:0,zeig:false,link:'',qr:'',befehl:'',befehlMac:'',gesendet:{},
  weg:'link',os:'linux',mailEn:false,alle:false,neuId:'',abgelaufen:false,nbis:0,lbis:0,teilt:false};
const SH_ART={ansehen:['Ansehen','View'],shell:['Shell','Shell'],nummer_verfallen:['Nummer verfallen','Number expired'],nummer_gesperrt:['Nummer gesperrt','Number locked']};
function shArt(a){return SH_ART[a]?t(...SH_ART[a]):a}
// messages come as a short toast (sayToast), never as a line under the page
function shMsg(text,bad){fzMsg(text,bad)}
async function shLoad(){clearTimeout(SH.timer);if(!$('shmain'))return;
  try{const r=await api('/api/admin/spontanhilfe');SH.d=await r.json()}catch(e){$('shmain').hidden=true;return}
  shShow();if(document.querySelector('section#fern.on'))SH.timer=setTimeout(shLoad,SH.ws?10000:3000)}
function shRest(s){s=Math.max(0,s|0);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
// locked: nothing of a help stays in the page, not even hidden (rule „Bereich entsperren“)
function shLeeren(){for(const id of ['shnummer','shnummerinfo','shringtext','shlink','shqrbild','shwartetname','shlaeuft','shverlauflist','shbefehl','shvstand'])$(id).textContent='';
  SH.link='';SH.qr='';SH.befehl='';SH.befehlMac='';SH.neuId='';SH.abgelaufen=false;clearInterval(SH.ntick)}
function shShow(){const d=SH.d,box=$('shmain');if(!d||!box)return;const aus=!d.on||!!d.notaus||!!d.gesperrt;
  if(aus){box.hidden=true;$('shgo').hidden=true;if(d.gesperrt)shLeeren();$('shbanner').hidden=!(d.gesperrt&&SH.ws);fzTopLine();const war=FZ.tab;fzTabs();if(war!==FZ.tab)fzShow();return}
  box.hidden=!fzTabs();
  const h=d.hilfe,neu=h&&h.stand==='neu',wartet=h&&h.stand==='wartet',offen=h&&h.stand==='offen',shell=!!h&&h.art==='shell';
  if(neu){if(SH.neuId!==h.id){SH.neuId=h.id;SH.abgelaufen=false}SH.nbis=Date.now()/1000+h.nummer_rest;SH.lbis=Date.now()/1000+h.link_rest}
  else if(!h&&SH.neuId&&!SH.abgelaufen){SH.abgelaufen=true;SH.nbis=SH.lbis=0}    // ran out unused: the panel moved it to the history
  else if(h){SH.neuId='';SH.abgelaufen=false}
  $('shgo').hidden=box.hidden||(!!h&&!neu);$('shturn').hidden=!!d.turn;
  $('shleer').hidden=!!h||SH.abgelaufen;
  // the four steps: created → invite → connected → shared (only until the picture fills the right side)
  const schritt=neu||SH.abgelaufen?2:wartet?3:0,st=$('shschritte');st.hidden=!schritt;
  for(const li of st.children){const n=+li.dataset.s;li.className=n<schritt?'fertig':n===schritt?'jetzt':''}
  $('shnummerbox').hidden=!(neu||SH.abgelaufen);
  if(neu){$('shnummer').textContent=h.nummer.slice(0,3)+' '+h.nummer.slice(3);
    $('shfehl').textContent=t(`${h.fehl} von ${h.fehl_max} Fehlversuchen`,`${h.fehl} of ${h.fehl_max} wrong tries`);
    $('shmailrow').hidden=!d.mail;$('shmailno').hidden=!!d.mail}
  if(!neu){SH.link='';SH.qr='';SH.befehl='';SH.befehlMac='';$('shqrbild').textContent=''}
  shNummerUhr();shWege();
  $('shwartet').hidden=!wartet;if(wartet){$('shwartetname').textContent=t(`„${h.name}“ wartet (${shWo(h)}${shell?' · Shell'+(h.os?', '+h.os:''):''}).`,`"${h.name}" is waiting (${shWo(h)}${shell?' · shell'+(h.os?', '+h.os:''):''}).`);
    $('shwartethin').textContent=shell?t('Nach „Annehmen“ tippt die Person in ihrem Terminal „j“; erst dann kommt ihre Shell.','After "Accept" the person types "j" in her terminal; only then her shell comes.'):t('Nach „Annehmen“ klickt die Person selbst „Bildschirm teilen“.','After "Accept" the person clicks "Share screen" herself.')}
  if(offen&&typeof h.teilt==='boolean')SH.teilt=h.teilt;
  $('shbanner').hidden=!offen;fzTopLine();$('shoffen').hidden=!offen;$('shview').hidden=!offen||shell;$('shterm').hidden=!offen||!shell;
  $('shchatbtn').hidden=shell;if(shell||!offen)$('shchat').hidden=true;shTeiltZeigen();
  if(offen)shUhr(h.bis,h.kann_verlaengern);else clearInterval(SH.clock);
  shListe();shVerlauf()}
// viewer controls only while the person really shares (Zeigepfeil, Vollbild); Chat and Beenden while the help is open
function shTeiltZeigen(){const h=SH.d&&SH.d.hilfe,shell=!!h&&h.art==='shell',an=!!h&&h.stand==='offen'&&!shell&&SH.teilt;
  $('shzeig').hidden=!an;$('shvoll').hidden=!an;$('shviewinfo').hidden=an||shell;
  $('shviewinfo').textContent=t('Die Person teilt gerade nicht. Sobald sie „Bildschirm teilen“ klickt, steht ihr Bild hier.','The person is not sharing right now. As soon as she clicks "Share screen", her picture shows here.');
  if(!an&&SH.zeig){SH.zeig=false;$('shzeig').classList.remove('on')}}
// the number's ring counts down; at 0 the number goes and „Abgelaufen – Neue Nummer“ comes (the link may hold on)
function shNummerUhr(){clearInterval(SH.ntick);const d=SH.d||{},tick=()=>{const now=Date.now()/1000,rest=SH.nbis-now,lrest=SH.lbis-now,weg=SH.abgelaufen||rest<=0;
    $('shringtext').textContent=shRest(rest);$('shring').style.setProperty('--p',Math.max(0,Math.min(100,rest/(d.nummer_s||600)*100)).toFixed(1)+'%');
    $('shnummerinfo').textContent=t(`Nummer gilt noch ${shRest(rest)} min, einmal`,`Number valid for ${shRest(rest)} min, once`);
    for(const id of ['shring','shnummer'])$(id).hidden=weg;$('shnummerinfo').hidden=weg;$('shabgelaufen').hidden=!weg;
    $('shabgelaufeninfo').textContent=lrest>0&&!SH.abgelaufen&&SH.link?t(` – die Nummer gilt nicht mehr; der Link noch ${shRest(lrest)}.`,` – the number no longer works; the link for another ${shRest(lrest)}.`):t(' – Nummer und Link gelten nicht mehr.',' – number and link no longer work.');
    const offen=!SH.abgelaufen&&(rest>0||(lrest>0&&!!SH.link));$('shwtabsbox').hidden=!offen;
    if(SH.abgelaufen||(rest<=0&&lrest<=0)){clearInterval(SH.ntick);if(!SH.abgelaufen&&SH.neuId)shLoad()}};
  if(!$('shnummerbox').hidden){tick();SH.ntick=setInterval(tick,1000)}}
// the three ways as tabs: Link, E-Mail (Deutsch/English), Shell (Linux/macOS, one line)
function shWege(){const shellOk=!!SH.befehl&&SH.nbis-Date.now()/1000>0;$('shwshell').hidden=!shellOk;if(SH.weg==='shell'&&!shellOk)SH.weg='link';
  for(const b of document.querySelectorAll('#shwtabs button')){const on=b.dataset.w===SH.weg;b.classList.toggle('on',on);b.setAttribute('aria-selected',on?'true':'false')}
  $('shplink').hidden=SH.weg!=='link';$('shpmail').hidden=SH.weg!=='mail';$('shpshell').hidden=SH.weg!=='shell';
  $('shlink').textContent=SH.link||t('Link und Zeile stehen nur direkt nach „Neue Hilfe“ in diesem Browser; „Neue Nummer“ macht neue.','Link and line show only right after "New help" in this browser; "New number" makes new ones.');
  for(const id of ['shkopie','shteilen','shqr'])$(id).disabled=!SH.link;$('shmailgo').disabled=$('shmailgo').disabled||!SH.link;
  $('shmailde').classList.toggle('on',!SH.mailEn);$('shmailen').classList.toggle('on',SH.mailEn);
  $('shoslinux').classList.toggle('on',SH.os!=='mac');$('shosmac').classList.toggle('on',SH.os==='mac');
  $('shbefehl').textContent=SH.os==='mac'?SH.befehlMac:SH.befehl}
function shWo(h){return fzWoher(h.herkunft)+(h.ip?' · '+h.ip:'')}
function shUhr(bis,kann){SH.bis=bis;SH.kann=kann;clearInterval(SH.clock);const tick=()=>{const rest=SH.bis-Date.now()/1000,d=SH.d||{},h=d.hilfe;
    const warn=rest<=(d.hinweis_s||600);$('shplus').hidden=!(SH.kann&&warn);
    const bald=rest>0&&rest<=120;$('shbanner').classList.toggle('fzwarn',bald);$('shbplus').hidden=!(bald&&SH.kann);
    const name=h&&h.name?h.name:'',min=h&&h.seit?Math.max(0,Math.round((Date.now()/1000-h.seit)/60)):0,shell=!!h&&h.art==='shell';
    $('shvstand').textContent='● '+(shell?t(`${name} · Shell · ${min} min · noch ${shRest(rest)}`,`${name} · shell · ${min} min · ${shRest(rest)} left`)
      :SH.teilt?t(`${name} teilt · ${min} min · noch ${shRest(rest)}`,`${name} shares · ${min} min · ${shRest(rest)} left`)
      :t(`${name} · wartet aufs Teilen · noch ${shRest(rest)}`,`${name} · waiting for the share · ${shRest(rest)} left`));
    $('shvstand').classList.toggle('warn',warn);
    $('shbtext').textContent=bald?t(`Spontanhilfe endet in ${shRest(rest)}`,`Spontaneous help ends in ${shRest(rest)}`):t(`Spontanhilfe aktiv · ${name} · noch ${shRest(rest)}`,`Spontaneous help active · ${name} · ${shRest(rest)} left`)}; tick();SH.clock=setInterval(tick,1000)}
// left: „Läuft“ (the one help) like „Systeme“, then the history of the last days
function shZeile(ic,farbe,titel,pill,pillCls,rest,on){const r=fzEl('div','fzrow shrow'+(on?' on':'')),i=fzEl('span','fzos shic',ic);i.style.background=farbe;
  const tx=fzEl('span','fzrtext'),sm=fzEl('small');sm.append(fzEl('span','shpill '+pillCls,pill),document.createTextNode(rest?' · '+rest:''));
  tx.append(fzEl('b','',titel),sm);r.append(i,tx);return r}
function shListe(){const d=SH.d,h=d&&d.hilfe,l=$('shlaeuft');if(!l)return;l.textContent='';$('shlaeufth').textContent=t('Läuft · ','Running · ')+(h?1:0);
  if(!h){l.appendChild(fzEl('div','mut fzleer',t('Gerade keine Hilfe.','No help right now.')));return}
  const now=Date.now()/1000;
  if(h.stand==='neu')l.appendChild(shZeile('?','var(--acc)',t('Hilfe ','Help ')+h.nummer.slice(0,3)+' '+h.nummer.slice(3),t('wartet auf Person','waiting for the person'),'warn',t('noch ','')+shRest(SH.nbis-now)+t('',' left'),true));
  else{const shell=h.art==='shell',offen=h.stand==='offen';
    l.appendChild(shZeile((h.name||'?').slice(0,1).toUpperCase(),offen?'var(--ok)':'var(--warn)',h.name||'',
      offen?(shell?t('Shell','Shell'):SH.teilt?t('teilt Bildschirm','sharing the screen'):t('verbunden','connected')):t('wartet auf dich','waiting for you'),offen?'ok':'warn',
      [offen&&h.seit?fzMin(h.seit):'',fzWoher(h.herkunft)].filter(Boolean).join(' · '),true))}}
function shVerlauf(){const d=SH.d,list=$('shverlauflist');if(!d||!list)return;list.textContent='';const v=d.verlauf||[];
  $('shverlaufh').textContent=t(`Verlauf · ${d.verlauf_tage||30} Tage`,`History · ${d.verlauf_tage||30} days`);
  $('shverlaufweg').hidden=!v.length;$('shalle').hidden=v.length<=5;$('shalle').textContent=SH.alle?t('Weniger ‹','Less ‹'):t('Alle anzeigen ›','Show all ›');
  if(!v.length){list.appendChild(fzEl('div','mut fzleer',t('Noch keine Hilfe.','No help yet.')));return}
  for(const x of SH.alle?v:v.slice(0,5)){const sitz=x.art==='ansehen'||x.art==='shell';
    list.appendChild(shZeile(sitz?'✓':'–','#9aa3b5',[shArt(x.art),x.admin].filter(Boolean).join(' · '),
      sitz?t('beendet','ended'):x.art==='nummer_gesperrt'?t('gesperrt','locked'):t('abgelaufen','expired'),'',
      [fzZeit(x.t),sitz?x.min+' min · '+fzWoher(x.herkunft):x.n+' '+t('Fehlversuche','wrong tries')].join(' · '),false))}}
async function shNeu(){try{const r=await api('/api/admin/spontanhilfe/neu',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});
    const d=await r.json();SH.gesendet={};shMailFrei();SH.link=d.link||'';SH.qr=d.qr||'';SH.befehl=d.befehl||'';SH.befehlMac=d.befehl_mac||'';SH.abgelaufen=false;SH.neuId='';$('shqrbild').textContent='';
    if(!SH.link)shMsg(t('Ein Link braucht die https-Adresse des Panels.','A link needs the panel\'s https address.'),true);shLoad()}catch(e){shMsg(e.message,true)}}
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
  try{await api('/api/admin/spontanhilfe/einladung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({an,link:SH.link,en:SH.mailEn,nochmal})});
    SH.gesendet[k]=Date.now();b.classList.remove('senden');b.removeAttribute('aria-busy');
    shMsg(t('Einladung gesendet.','Invitation sent.'));$('shan').value=''}catch(e){shMailFrei();shMsg(e.message,true)}}
async function shEnde(){SH.neuId='';SH.abgelaufen=false;try{await api('/api/admin/spontanhilfe',{method:'DELETE'})}catch(e){}shZu();shLoad()}
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
  else if(m.typ==='chat'){shChat(m.text,false);if($('shchat').hidden){$('shchat').hidden=false;$('shchatbtn').setAttribute('aria-expanded','true')}}
  else if(m.typ==='teilt'){SH.teilt=!!m.an;shTeiltZeigen();shListe()}
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
  const v=$('shvideo');if(v)v.srcObject=null;clearInterval(SH.clock);SH.zeig=false;SH.teilt=false;const z=$('shzeig');if(z)z.classList.remove('on')}
function shChat(text,mine){const l=$('shchatlist'),b=fzEl('div','shmsg'+(mine?' mine':''),text);l.appendChild(b);l.scrollTop=l.scrollHeight}
function shChatSend(){const i=$('shchatin'),s=i.value.trim().slice(0,500);if(!s)return;shSend({typ:'chat',text:s});shChat(s,true);i.value=''}
function shZeigen(e){if(!SH.zeig)return;const v=$('shvideo'),r=v.getBoundingClientRect();if(!v.videoWidth)return;
  // the picture inside the element (object-fit: contain): only a point on it counts
  const s=Math.min(r.width/v.videoWidth,r.height/v.videoHeight),w=v.videoWidth*s,h=v.videoHeight*s,x0=r.left+(r.width-w)/2,y0=r.top+(r.height-h)/2;
  const x=(e.clientX-x0)/w,y=(e.clientY-y0)/h;if(x<0||x>1||y<0||y>1)return;shSend({typ:'zeig',x,y});
  const dot=$('shzeigdot');dot.style.left=(e.clientX-r.left)+'px';dot.style.top=(e.clientY-r.top)+'px';dot.hidden=false;clearTimeout(SH.dot);SH.dot=setTimeout(()=>dot.hidden=true,2500)}
{const g=$('shgo');if(g){g.onclick=shNeu;$('shgo2').onclick=shNeu;$('shneunr').onclick=shNeu;$('shneunr2').onclick=shNeu;$('shweg').onclick=shEnde;$('shkopie').onclick=shKopie;
  $('shbefehlkopie').onclick=()=>shBefehlKopie(SH.os==='mac'?SH.befehlMac:SH.befehl);$('shteilen').onclick=shTeilen;$('shqr').onclick=shQr;$('shmailgo').onclick=shMail;$('shan').oninput=shMailFrei;
  for(const b of $('shwtabs').querySelectorAll('button'))b.onclick=()=>{SH.weg=b.dataset.w;shWege()};
  $('shmailde').onclick=()=>{SH.mailEn=false;shWege()};$('shmailen').onclick=()=>{SH.mailEn=true;shWege()};
  $('shoslinux').onclick=()=>{SH.os='linux';shWege()};$('shosmac').onclick=()=>{SH.os='mac';shWege()};
  $('shalle').onclick=()=>{SH.alle=!SH.alle;shVerlauf()};
  $('shannehmen').onclick=shAnnehmen;$('shablehnen').onclick=shEnde;$('shende').onclick=shEnde;$('shbende').onclick=shEnde;$('shbplus').onclick=shPlus;$('shplus').onclick=shPlus;
  $('shzeig').onclick=()=>{SH.zeig=!SH.zeig;$('shzeig').classList.toggle('on',SH.zeig)};$('shvideo').onclick=shZeigen;
  $('shchatbtn').onclick=()=>{const c=$('shchat');c.hidden=!c.hidden;$('shchatbtn').setAttribute('aria-expanded',c.hidden?'false':'true');if(!c.hidden)$('shchatin').focus()};
  $('shvoll').onclick=()=>{const v=$('shview');if(v.requestFullscreen)v.requestFullscreen().catch(()=>{})};
  $('shchatin').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();shChatSend()}};$('shchatgo').onclick=shChatSend;
  $('shverlaufweg').onclick=async()=>{if(!confirm(t('Den ganzen Verlauf der Spontanhilfe löschen?','Delete the whole history of spontaneous help?')))return;
    try{await api('/api/admin/spontanhilfe/verlauf',{method:'DELETE'});shLoad()}catch(e){shMsg(e.message,true)}}}}
window.shLoad=shLoad;window.shShow=shShow;
