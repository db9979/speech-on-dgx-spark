'use strict';
// Fernzugang → Bildschirm (fernbild.py, plan ssh-vermittlung stage 4): the screen of a paired system in this page,
// Guacamole.Client (guacamole-common-js, vendored in /static/guac, loaded only when a screen opens). It first only
// shows: the mouse goes to the panel always (it counts as activity there, the panel passes it only while „Steuern“ is
// on), keys only while „Steuern“ is on. „spark-steuern“ tells the panel; „spark-rate“ is the panel's rate (KB/s).
// On a Mac the macOS user and password are asked here for each session and sent once with the ticket, never kept.
const FB={c:null,tunnel:null,kb:null,mouse:null,g:null,steuern:false,rate:[],grund:''};
const FB_GRUND={guacd:['Der Bildschirm-Dienst (guacd) startet nicht: auf dem Spark „journalctl -u speech-spark-guacd“ zeigt warum.','The screen service (guacd) does not start: "journalctl -u speech-spark-guacd" on the Spark shows why.'],
  sshd:['Das System zeigt keinen Bildschirm: dort „sudo spark-anker bildschirm“.','The system shows no screen: run "sudo spark-anker bildschirm" there.'],
  anker:['Der Anker ist nicht verbunden.','The anchor is not connected.'],voll:['Schon so viele Sitzungen offen, wie erlaubt sind.','As many sessions open as allowed.'],
  zu_gross:['Eine Nachricht der Seite war zu groß: der Bildschirm ist zu.','A message of the page was too big: the screen is closed.'],
  ticket:['Die Freigabe ist abgelaufen. Noch einmal „Bildschirm“.','The permission expired. "Screen" once more.'],
  aus:['Der Bildschirm ist ausgeschaltet worden.','The screen was switched off.']};
function fbGrund(w){if(w==='guacd'){const x=fzBildDienst(FZ.d);if(x)return x}return FB_GRUND[w]?t(...FB_GRUND[w]):fzGrund(w)}
function fbLaden(){if(window.Guacamole)return Promise.resolve();
  return new Promise((ok,bad)=>{window.module={exports:{}};const s=document.createElement('script');s.src='/static/guac/guacamole-common.min.js?v='+encodeURIComponent(SPARK_VER);
    s.onload=()=>{delete window.module;window.Guacamole?ok():bad(new Error(t('Der Bildschirm-Baustein fehlt.','The screen component is missing.')))};
    s.onerror=()=>{delete window.module;bad(new Error(t('Der Bildschirm-Baustein fehlt.','The screen component is missing.')))};document.head.appendChild(s)})}
function fbSparsam(){try{return localStorage.getItem('fbsparsam')==='1'}catch{return false}}
async function fbOpen(g){if(FZ.ws||FZ.weg||FZ.fs||FZ.fb){fzMsg(t('Erst die offene Sitzung trennen.','Disconnect the open session first.'),true);return}
  $('fbsparsam').checked=fbSparsam();$('fbmacrow').hidden=g.bild!=='mac';$('fbmacuser').value='';$('fbmacpw').value='';FB.g=g;
  $('fbname').textContent=g.name;$('fbmodal').style.display='grid';setTimeout(()=>(g.bild==='mac'?$('fbmacuser'):$('fbgo')).focus(),50)}
function fbModalZu(){$('fbmodal').style.display='none';$('fbmacpw').value=''}
async function fbStart(){const g=FB.g;if(!g)return;const sp=$('fbsparsam').checked,body={geraet:g.id,sparsam:sp};
  try{localStorage.setItem('fbsparsam',sp?'1':'0')}catch{}
  if(g.bild==='mac'){body.benutzer=$('fbmacuser').value.trim();body.passwort=$('fbmacpw').value;if(!body.benutzer||!body.passwort){(body.benutzer?$('fbmacpw'):$('fbmacuser')).focus();return}}
  fbModalZu();$('fzmain').hidden=true;$('fzstatus').hidden=true;$('fzbild').hidden=false;
  const box=$('fbschirm');body.breite=Math.max(320,Math.round(box.clientWidth||1280));body.hoehe=Math.max(200,Math.round(box.clientHeight||800));
  let tk;try{await fbLaden();const r=await api('/api/admin/fernzugang/bildschirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});tk=(await r.json()).ticket}
  catch(e){body.passwort='';$('fzbild').hidden=true;$('fzmain').hidden=false;fzFehler(e);return}
  body.passwort='';
  FZ.fb=FB;FZ.sitz={name:g.name,seit:Date.now()/1000,max:FZ.d.max,leer:FZ.d.leerlauf,art:'bildschirm'};fzBanner();fzMsg('');FB.rate=[];FB.grund='';
  $('fblangsam').hidden=true;$('fbrate').textContent='';fbSteuern(false,true);
  const tunnel=new Guacamole.WebSocketTunnel((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/fernzugang/bildschirm');
  const c=new Guacamole.Client(tunnel),inner=tunnel.oninstruction;FB.c=c;FB.tunnel=tunnel;
  tunnel.oninstruction=(op,args)=>{if(op==='spark-rate'){fbRate(Number(args[0])||0);return}if(inner)inner(op,args)};
  const el=c.getDisplay().getElement();box.textContent='';box.appendChild(el);c.getDisplay().onresize=fbScale;
  c.onerror=st=>{FB.grund=st&&st.message?String(st.message):''};
  c.onstatechange=s=>{if(s===5)fbZu(FB.grund?fbGrund(FB.grund):'')};
  c.onclipboard=(stream,mime)=>{if(!FZ.d.zwischenablage||mime!=='text/plain'){stream.sendAck('no',0x0100);return}let x='';const r=new Guacamole.StringReader(stream);
    r.ontext=s=>{x+=s};r.onend=()=>{if(navigator.clipboard)navigator.clipboard.writeText(x.slice(0,65536)).catch(()=>{})}};
  const m=new Guacamole.Mouse(el);FB.mouse=m;m.onEach(['mousedown','mouseup','mousemove'],e=>{if(FB.c)FB.c.sendMouseState(e.state,true)});
  const kb=new Guacamole.Keyboard(box);FB.kb=kb;kb.onkeydown=k=>{if(!FB.steuern||!FB.c)return true;FB.c.sendKeyEvent(1,k);return false};kb.onkeyup=k=>{if(FB.steuern&&FB.c)FB.c.sendKeyEvent(0,k)};
  c.connect('t='+encodeURIComponent(tk));tk='';box.focus();fbScale()}
// „Zwischenablage senden“ (only with Funktionen → … → Zwischenablage and while „Steuern“ is on; the panel checks both)
async function fbAblage(){if(!FB.c||!FB.steuern)return;let x='';try{x=await navigator.clipboard.readText()}catch(e){fzMsg(t('Der Browser gibt die Zwischenablage nicht her.','The browser does not give the clipboard.'),true);return}
  if(!x)return;const w=new Guacamole.StringWriter(FB.c.createClipboardStream('text/plain'));w.sendText(x.slice(0,65536));w.sendEnd();$('fbschirm').focus()}
// „Steuern“: only now mouse and keys reach the system (the panel checks it); „Ansehen“ at any time
function fbSteuern(on,still){FB.steuern=!!on;const b=$('fbsteuern');b.setAttribute('aria-pressed',on?'true':'false');b.textContent=on?t('Nur ansehen','View only'):t('Steuern','Control');
  $('fbstand').textContent=on?t('Steuern: Maus und Tasten gehen zum System.','Control: mouse and keys go to the system.'):t('Nur ansehen: Maus und Tasten gehen nicht zum System.','View only: mouse and keys do not go to the system.');
  $('fzbild').classList.toggle('fbsteuert',FB.steuern);$('fbablage').hidden=!(on&&FZ.d&&FZ.d.zwischenablage);if(!on&&FB.kb)FB.kb.reset();if(!still&&FB.tunnel)FB.tunnel.sendMessage('spark-steuern',on?'1':'0');if(on)$('fbschirm').focus()}
// the panel sends its rate every few seconds: shown, and below bild_langsam a hint (the proxy is slow, „Sparsam“ helps)
function fbRate(kb){FB.rate=FB.rate.concat([kb]).slice(-3);$('fbrate').textContent=kb+' KB/s';
  const lahm=FB.rate.length>=2&&FB.rate.every(x=>x<((FZ.d&&FZ.d.bild_langsam)||100));$('fblangsam').hidden=!lahm}
function fbScale(){const c=FB.c,box=$('fbschirm');if(!c||!box)return;const d=c.getDisplay(),w=d.getWidth(),h=d.getHeight();if(!w||!h)return;
  d.scale(Math.min(box.clientWidth/w,box.clientHeight/h))}
function fbGroesse(){fbScale();const box=$('fbschirm');if(FB.c&&box.clientWidth>=320&&box.clientHeight>=200)FB.c.sendSize(Math.round(box.clientWidth),Math.round(box.clientHeight))}
function fbTrennen(text){fbZu(typeof text==='string'?text:'')}   // fbZu leaves FZ.fb first: the client's own „disconnected“ finds nothing to do
function fbZu(text){if(!FZ.fb)return;FZ.fb=null;const c=FB.c;FB.c=null;FB.tunnel=null;if(FB.kb){FB.kb.reset();FB.kb.onkeydown=FB.kb.onkeyup=null;FB.kb=null}FB.mouse=null;FB.steuern=false;
  if(c)try{c.disconnect()}catch{}if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});$('fbschirm').textContent='';$('fzbild').hidden=true;$('fzmain').hidden=false;
  FZ.sitz=null;fzBanner();if(text)fzMsg(text,true);fzLoad()}
{const b=$('fbsteuern');if(b){b.onclick=()=>fbSteuern(!FB.steuern);$('fbtrennen').onclick=()=>fbTrennen();$('fbvoll').onclick=()=>{const v=$('fzbild');if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});else if(v.requestFullscreen)v.requestFullscreen().catch(()=>{})};
  $('fbgo').onclick=fbStart;$('fbab').onclick=fbModalZu;const m=$('fbmodal');m.addEventListener('click',e=>{if(e.target===m)fbModalZu()});m.addEventListener('keydown',e=>{if(e.key==='Escape')fbModalZu();if(e.key==='Enter'&&e.target.tagName==='INPUT'&&e.target.type!=='checkbox')fbStart()});
  $('fbablage').onclick=fbAblage;
  if(window.ResizeObserver)new ResizeObserver(()=>{clearTimeout(FB.rt);FB.rt=setTimeout(fbGroesse,150)}).observe($('fbschirm'))}}
