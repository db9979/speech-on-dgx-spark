// Room mode (see room.py): the assistant listens to the conversation in the room for a while and helps
// in a pause. Per device and per switch-on; what it hears stays on the Spark for a few minutes only.
let ROOM_ON=false,RV_ON=false,RHA_ON=false,RFAR_ON=false;
// the name this page has in the list of listening devices: set under Ich → Raum-Modus, else from the browser
function roomDevName(){const u=navigator.userAgent||'',dev=/iPad/.test(u)?'iPad':/iPhone/.test(u)?'iPhone':/Android/.test(u)?'Android':/Mac/.test(u)?'Mac':/Windows/.test(u)?'PC':'Browser';
  const br=/Edg\//.test(u)?'Edge':/Firefox\//.test(u)?'Firefox':/Chrome\//.test(u)?'Chrome':/Safari\//.test(u)?'Safari':'';return br?dev+' · '+br:dev}
// while this page listens: "● Raum" in the tab title and a red dot on the tab icon, seen from across the room
const ROOM_TITLE=document.title,ROOM_ICON=(document.querySelector('link[rel=icon]')||{}).href||'';
function roomMark(on){const want=on?'● '+t('Raum','Room')+' · '+ROOM_TITLE:ROOM_TITLE;if(document.title!==want)document.title=want;
  const l=document.querySelector('link[rel=icon]');if(!l)return;
  const dot="data:image/svg+xml,"+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#5b5bf0"/><circle cx="24" cy="8" r="7" fill="#ef4444" stroke="#fff" stroke-width="2"/></svg>');
  const href=on?dot:ROOM_ICON;if(l.getAttribute('href')!==href&&(on||ROOM_ICON))l.setAttribute('href',href)}
window.room={on:false,speaking:false,id:'',key:'',until:0,lastAlive:0,lastPing:0,quiet:false,queue:Promise.resolve(),lastSpeech:0,wait:false,need:2.5,asking:false,
  cfg(){let o={};try{o=JSON.parse(localStorage.getItem('room')||'{}')}catch{}
    return {mins:30,level:'hints',text:false,area:'',tone:true,detect:false,summary:true,voices:'all',probe:true,name:'',ping:false,...o,kinds:{q:true,cal:true,ha:true,shop:true,timer:true,remind:true,conv:true,...(o.kinds||{})}}},
  save(o){try{localStorage.setItem('room',JSON.stringify({...this.cfg(),...o}))}catch{}},
  idle(){return !chat.rec&&!chat.ctrl&&!playing()&&!chat.asrBusy},
  show(){$('roomtgl').style.display=ROOM_ON&&PROFILE?'':'none';if(this.on&&!(ROOM_ON&&PROFILE))this.stop();roomLive.poll()},
  async start(){if(!ROOM_ON||!PROFILE)return;
    this.on=true;this.id=[...crypto.getRandomValues(new Uint8Array(8))].map(b=>b.toString(16).padStart(2,'0')).join('');
    this.until=Date.now()+this.cfg().mins*60e3;this.wait=false;this.lastSpeech=Date.now();
    if(!wake.on)await startWake();
    if(!wake.on){this.on=false;$('chatroom').checked=false;return}
    // the Spark lists this page (Ich → Raum-Modus „Gerade aktiv“, the strip on every page, the admin, the app)
    const c=this.cfg();this.lastAlive=this.lastPing=Date.now();this.key='';
    try{const r=await fetch('/api/room/start',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({room:this.id,mins:c.mins,name:c.name||roomDevName(),voices:RV_ON?c.voices:'all',probe:c.probe!==false})});
      if(r.ok){const d=await r.json();this.key=d.key||'';if(d.until)this.until=d.until}}catch{}
    $('chatroom').checked=true;this.badge();roomLive.poll()},
  // why: how it ended, for the profile's history (time, voice, lost or here)
  stop(why){if(!this.on)return;this.on=false;this.wait=false;
    fetch('/api/room/stop',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({room:this.id,why:['time','voice','lost'].includes(why)?why:'here'})})
      .then(r=>r.json()).then(d=>this.recap(d.summary||[])).catch(()=>{});
    if(!$('chatwake').checked)stopWake();$('chatroom').checked=false;this.key='';this.badge();setTimeout(()=>roomLive.poll(),500)},
  badge(){const w=$('wakeind');w.classList.toggle('room',this.on);roomMark(this.on);
    w.querySelector('span').textContent=this.on?t('Raum-Modus: hört zu, noch ','Room mode: listening, ')+Math.max(1,Math.ceil((this.until-Date.now())/60e3))+t(' Min.',' min left'):t('lauscht auf „Hey Spark“','listening for "Hey Spark"');
    if(!this.on&&!wake.on)w.hidden=true},
  enqueue(seg,rate){this.queue=this.queue.then(()=>checkWake(seg,rate)).catch(()=>{})},
  // when it ends: what the assistant said and did, shown once and not kept in the conversation
  recap(items){if(!items.length||!this.cfg().summary)return;
    const b=chatLog('assistant',t('Raum-Modus beendet. Das habe ich gesagt und getan:','Room mode ended. What I said and did:')+'\n'+
      items.map(x=>'• '+new Date(x.t).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'})+' '+x.text).join('\n'));
    b.classList.add('pro','recap')},
  body(o){const c=this.cfg();return JSON.stringify({room:this.id,level:c.level,kinds:c.kinds,area:c.area,detect:!!c.detect,voices:RV_ON?c.voices:'all',probe:c.probe!==false,
    tz:(()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}})(),...o})},
  async heard(text){if(!this.on)return;
    if(this.speaking&&/^\W*(stopp?|halt|ruhe|still|sei still|psst|nicht jetzt|jetzt nicht|schon gut|genug|aufhören|hör auf)\b/i.test(text))stopAnswer();
    try{const r=await fetch('/api/room/heard',{method:'POST',headers:{'Content-Type':'application/json'},body:this.body({text})});if(!r.ok)return;
      const d=await r.json();if(d.stop)stopAnswer();if(d.reminder&&window.rem)rem.event({action:'set',item:d.reminder});if(d.say)this.say(d.say,d.silent);
      if(d.end){this.stop('voice');return}this.wait=!!d.wait;this.need=2.5}catch{}},
  // every minute a sign of life: the Spark keeps the page in its list and says when it was ended elsewhere
  // (Ich → Raum-Modus, the iPhone app, Home Assistant, the admin) or extended
  async alive(){const c=this.cfg();
    try{const r=await fetch('/api/room/alive',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({room:this.id,left:Math.max(60,(this.until-Date.now())/1000),name:c.name||roomDevName(),voices:RV_ON?c.voices:'all',probe:c.probe!==false})});
      if(!r.ok)return;const d=await r.json();if(!this.on)return;
      if(d.end){this.stop();chatLog('assistant',t('Raum-Modus wurde an einem anderen Ort beendet.','Room mode was ended elsewhere.')).classList.add('pro');return}
      if(d.key)this.key=d.key;if(d.until)this.until=d.until;this.quiet=!!d.quiet;this.badge()}catch{}},
  async tick(){if(!this.on)return;if(Date.now()>this.until||this.away()){this.stop(this.away()?'lost':'time');return}this.badge();
    if(Date.now()-this.lastAlive>60e3){this.lastAlive=Date.now();this.alive()}
    // "Erinnerungston": a soft tone every 15 minutes, so nobody forgets that it listens (never in quiet hours)
    if(this.cfg().ping&&!this.quiet&&Date.now()-this.lastPing>15*60e3&&this.idle()&&!this.speaking&&!wake.seg){this.lastPing=Date.now();this.tone()}
    if(!this.wait||this.asking||wake.seg||!this.idle()||Date.now()-this.lastSpeech<this.need*1000)return;
    this.wait=false;this.asking=true;
    try{const r=await fetch('/api/room/pause',{method:'POST',headers:{'Content-Type':'application/json'},body:this.body({quiet:(Date.now()-this.lastSpeech)/1000})});
      const d=r.ok?await r.json():{};if(d.end){this.asking=false;this.stop();return}if(d.again){this.need=d.again;this.wait=true}if(d.say)this.say(d.say,d.silent)}catch{}
    this.asking=false},
  // in the background or with the phone locked the microphone stops: after two minutes room mode ends
  hidden:0,away(){return !!this.hidden&&Date.now()-this.hidden>120e3},
  say(text,silent){if(!this.on)return;const b=chatLog('assistant',text);b.classList.add('pro');
    const m={role:'assistant',content:text};chat.msgs.push(m);deletable(b,m);saveConvo();
    if(silent||this.cfg().text||chat.rec||chat.ctrl||playing())return;   // option: only as text in the conversation
    this.speaking=true;
    (async()=>{if(this.cfg().tone){this.tone();await new Promise(r=>setTimeout(r,450))}
      if(!chat.rec&&!chat.ctrl)await sayText(text)})().finally(()=>{this.speaking=false})},
  // a soft two-note tone before it speaks by itself, so nobody is startled
  tone(){try{const ctx=audioCtx(),g=ctx.createGain();g.connect(ctx.destination);const t0=ctx.currentTime;
    g.gain.setValueAtTime(0.0001,t0);g.gain.exponentialRampToValueAtTime(0.08,t0+0.04);g.gain.exponentialRampToValueAtTime(0.0001,t0+0.42);
    [[523.25,0],[659.25,0.14]].forEach(([f,d])=>{const o=ctx.createOscillator();o.type='sine';o.frequency.value=f;o.connect(g);o.start(t0+d);o.stop(t0+0.42)})}catch{}}};
setInterval(()=>room.tick(),300);
// Where my devices listen right now (roomlive.py): the strip on every page, „Auch … hört zu“ at the face and
// Ich → Raum-Modus „Gerade aktiv“ with +15/+30 min and Beenden. Asked when shown and every 30 s while visible.
const roomHM=ms=>new Date(ms).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
const ROOM_VOICES={all:['hört allen zu','listens to everybody'],tv:['bekannte Stimmen, wenn TV läuft','known voices while the TV is on'],known:['nur bekannte Stimmen','known voices only']};
window.roomLive={rooms:[],waiting:[],busy:false,
  async poll(){if(!PROFILE||!ROOM_ON){this.rooms=[];this.waiting=[];this.show();return}if(document.hidden||this.busy)return;this.busy=true;
    try{const r=await fetch('/api/room/active',{cache:'no-store'});if(r.ok){const d=await r.json();this.rooms=d.rooms||[];this.waiting=d.waiting||[]}}catch{}
    this.busy=false;this.show()},
  name(x){return x.key===room.key&&room.on?t('Dieses Gerät','This device'):x.name},
  show(){const rs=this.rooms,b=$('roomlive');
    if(b){b.hidden=!rs.length;if(rs.length){const sp=b.querySelector('span');
      sp.textContent=rs.length===1?t(`${this.name(rs[0])} hört zu bis ${roomHM(rs[0].until)}`,`${this.name(rs[0])} listens until ${roomHM(rs[0].until)}`)
        :t(`${rs.length} Geräte hören zu: `,`${rs.length} devices listen: `)+rs.map(x=>this.name(x)).join(', ')}}
    const o=$('roomothers'),others=rs.filter(x=>!(room.on&&x.key===room.key));
    if(o){o.hidden=!others.length;o.querySelector('span').textContent=others.length?t('Auch ','Also ')+others.map(x=>x.name).join(', ')+t(' hört gerade zu.',' is listening right now.'):''}
    const n=$('roomnow');if(!n)return;
    const row=x=>`<div class="setrow"><div class="lbl"><b>${esc(this.name(x))} <span class="pill ok">${esc(t('hört zu bis ','until ')+roomHM(x.until))}</span></b><span>${esc([x.kind==='speaker'?t('Lautsprecher','Speaker'):t('Browser','Browser'),t('seit ','since ')+roomHM(x.since),t(...(ROOM_VOICES[x.voices]||ROOM_VOICES.all))].concat(x.probe&&x.voices!=='all'?[t('Probelauf','trial')]:[]).join(' · '))}</span></div>
      <div class="ctl"><button class="b" type="button" data-rext="${esc(x.key)}">+30 ${t('Min.','min')}</button><button class="b" type="button" data-rend="${esc(x.key)}">${t('Beenden','Stop')}</button></div></div>`;
    const wait=x=>`<div class="setrow"><div class="lbl"><b>${esc(x.name)}</b><span>${esc(t('Lautsprecher · startet beim nächsten Weckwort','Speaker · starts at the next wake word'))}</span></div><div class="ctl"><button class="b" type="button" data-rend="${esc(x.key)}">${t('Nicht starten','Do not start')}</button></div></div>`;
    n.innerHTML=rs.map(row).join('')+this.waiting.map(wait).join('')||`<div class="fh">${t('Gerade hört kein Gerät zu.','No device is listening right now.')}</div>`;
    n.querySelectorAll('[data-rend]').forEach(e=>e.onclick=()=>this.end(e.dataset.rend));
    n.querySelectorAll('[data-rext]').forEach(e=>e.onclick=()=>this.extend(e.dataset.rext,30))},
  async end(key){try{await api('/api/room/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})})}catch(e){}
    if(room.on&&key===room.key)room.stop();this.poll()},
  async extend(key,mins){try{const d=await (await api('/api/room/extend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,mins})})).json();
    this.rooms=d.rooms||this.rooms;const me=this.rooms.find(x=>x.key===room.key);if(me&&room.on){room.until=me.until;room.badge()}}catch(e){}this.show()}};
setInterval(()=>roomLive.poll(),30e3);
$('roomlivego').onclick=()=>openMe('roombox');
document.addEventListener('visibilitychange',()=>{if(document.hidden){room.hidden=room.hidden||Date.now();return}
  if(room.on&&room.away())room.stop('lost');room.hidden=0;roomLive.poll()});
addEventListener('pagehide',()=>room.stop());
$('chatroom').onchange=()=>{if($('chatroom').checked)room.start();else room.stop()};
// "Ich" → Raum-Modus: settings of this device
function showRoom(){const box=$('roombox');if(!PROFILE||!ROOM_ON){box.innerHTML='';return}const c=room.cfg();
  const kind=(k,l,h)=>`<div class="setrow"><div class="lbl"><b>${esc(l)}</b><span>${esc(h)}</span></div><label class="tgl"><input type="checkbox" data-rk="${k}"${c.kinds[k]!==false?' checked':''}><i></i></label></div>`;
  box.innerHTML=`<h3 class="sec">${t('Gerade aktiv','Active now')}</h3><div id="roomnow"></div>
    ${xsw('room_tell',t('Mitteilung, wenn ein Lautsprecher zu hören beginnt','Note when a speaker starts listening'),t('Wenn jemand an einem deiner Lautsprecher „Raummodus an“ sagt. Höchstens einmal pro Stunde, nie in Ruhezeiten.','When somebody says "Raummodus an" at one of your speakers. At most once an hour, never in quiet hours.'))}
    ${RFAR_ON?xsw('room_remote',t('Raum-Modus an einem anderen Gerät starten','Start room mode on another device'),t('„Raummodus im Wohnzimmer an“ hier oder an einem anderen Lautsprecher sagen oder schreiben. Nur deine eigenen Lautsprecher, nur wenn sie verbunden sind, und erst nach deinem „Ja“. Der Lautsprecher sagt, von wo er gestartet wurde. Nicht über Telegram oder Siri.','Say or type "Raummodus im Wohnzimmer an" here or at another speaker. Only your own speakers, only while they are connected, and only after your "Ja". The speaker says where it was started from. Not via Telegram or Siri.')):''}
    <h3 class="sec">${t('Dieses Gerät','This device')}</h3><div class="intro">${t('Mit dem Schalter „Raum“ unter dem Gesicht hört der Assistent für eine Weile dem Gespräch im Raum zu und hilft in einer Pause. Das Gehörte bleibt nur wenige Minuten auf dem Spark und wird nie gespeichert; er nutzt dabei weder dein Gedächtnis noch Mails oder frühere Gespräche. Geändert wird nur nach einem „Ja“. Sag allen im Raum, dass er zuhört. Ist die Seite länger als zwei Minuten im Hintergrund oder das Handy gesperrt, geht er aus. Diese Einstellungen gelten nur für dieses Gerät.','With the switch "Room" below the face the assistant listens to the conversation in the room for a while and helps in a pause. What it hears stays on the Spark for a few minutes only and is never stored; it uses neither your memory nor mail or earlier conversations. It changes something only after a "yes". Tell everyone in the room that it is listening. When the page is in the background or the phone locked for more than two minutes, it switches off. These settings apply to this device only.')}</div>
    <div class="two2"><div><label>${t('Hört zu für','Listens for')}</label><select id="roommins">${[15,30,60,120,240].map(n=>`<option value="${n}"${n===c.mins?' selected':''}>${n} ${t('Minuten','minutes')}</option>`).join('')}</select></div>
      <div><label>${t('Wie viel er sagen darf','How much it may say')}</label><select id="roomlevel"><option value="questions"${c.level==='questions'?' selected':''}>${t('nur Fragen beantworten','only answer questions')}</option><option value="hints"${c.level==='hints'?' selected':''}>${t('auch Hinweise (empfohlen)','also hints (recommended)')}</option><option value="all"${c.level==='all'?' selected':''}>${t('auch Kommentare','also comments')}</option></select></div></div>
    <div class="fh">${t('„Auch Kommentare“: in einer kurzen Pause höchstens alle zwei Minuten ein lockerer Satz zum Gespräch (eine passende Tatsache, eine Ergänzung oder Richtigstellung). Am wenigsten zuverlässig.','"Also comments": in a short pause at most every two minutes one casual sentence about the conversation (a fitting fact, an addition or a correction). Least reliable.')}</div>`+
    kind('q',t('Offene Fragen beantworten','Answer open questions'),t('„Wann war nochmal …?“ ohne dass jemand angesprochen ist: kurze Antwort, mit Websuche, wenn sie an ist. Im Zweifel sagt er nichts.','"When was … again?" with nobody addressed: a short answer, with the web search when it is on. In doubt it says nothing.'))+
    kind('cal',t('Termine vorschlagen','Offer appointments'),t('„Freitag um 10 zum Zahnarzt“: „Soll ich das eintragen?“. Eingetragen wird erst nach einem Ja.','"Friday at 10 to the dentist": "Shall I enter it?". Entered only after a yes.'))+
    kind('ha',t('Raumklima und Licht','Room climate and light'),t('„Ist das kalt hier“: die echte Temperatur des Raums unten, dazu das Angebot, die Heizung um ein Grad zu ändern; bei „zu dunkel“ das Licht. Geschaltet wird nur nach Ja (mit Codewort, wenn du eines hast).','"It is cold here": the real temperature of the room below, offering to change the heating by one degree; on "too dark" the light. Switches only after yes (with your code word if you have one).'))+
    kind('shop',t('Einkaufsliste','Shopping list'),t('„Wir brauchen noch Milch“: „Soll ich Milch auf die Einkaufsliste setzen?“ (Home Assistant). Erst nach Ja.','"We still need milk": "Shall I put milk on the shopping list?" (Home Assistant). Only after yes.'))+
    kind('timer',t('Timer','Timers'),t('„Die Pizza braucht noch 12 Minuten“: „Soll ich einen Timer über 12 Minuten stellen?“. Erst nach Ja.','"The pizza needs 12 more minutes": "Shall I set a 12 minute timer?". Only after yes.'))+
    kind('remind',t('Erinnerungen','Reminders'),t('„Ich darf nicht vergessen, Oma anzurufen“: „Soll ich dich um 15:30 Uhr erinnern?“ (zur genannten Uhrzeit, „morgen“ um 8 Uhr, sonst in einer Stunde). Erst nach Ja.','"I must not forget to call grandma": "Shall I remind you at 15:30?" (at the time named, "tomorrow" at 8, else in an hour). Only after yes.'))+
    kind('conv',t('Umrechnen','Unit conversion'),t('„Wie viel sind 180 Grad in Fahrenheit?“, Milliliter in Tassen, Zoll in Zentimeter: ausgerechnet, ohne Modell.','"How much is 180 degrees in Fahrenheit?", millilitres in cups, inches in centimetres: calculated, without the model.'))+
    `<label>${t('Raum dieses Geräts in Home Assistant','Room of this device in Home Assistant')}</label><input id="roomarea" placeholder="${t('z. B. Wohnzimmer','e.g. Living room')}" value="${esc(c.area||'')}" autocomplete="off">`+
    (RV_ON?`<div class="two2"><div><label>${t('Wem er zuhört','Who it listens to')}</label><select id="roomvoices">${[['all',t('allen','everybody')],['tv',t('nur bekannten Stimmen, wenn der Fernseher läuft (empfohlen)','only known voices while the TV is on (recommended)')],['known',t('immer nur bekannten Stimmen','always only known voices')]].map(([v,l])=>`<option value="${v}"${c.voices===v?' selected':''}>${esc(l)}</option>`).join('')}</select></div></div>
    <div class="fh">${t('Bekannt ist jede Stimme, die unter Ich → Sprechererkennung angelernt ist (bei allen Profilen). Ob der Fernseher läuft, fragt er Home Assistant: ein eingeschalteter Mediaplayer im Raum oben, ohne Raum im ganzen Haus. Fremde Sätze vergisst er sofort. Ein Satz, der mit „Spark“ anfängt, zählt immer, ebenso „Stopp“ und „Raummodus aus“. Sehr kurze Sätze erkennt die Sprechererkennung oft nicht.','A voice is known when it was taught under Me → Speaker identification (any profile). Whether the TV is on comes from Home Assistant: a media player on in the room above, without a room anywhere in the home. Foreign sentences are forgotten at once. A sentence starting with "Spark" always counts, as do "Stopp" and "Raummodus aus". Very short sentences are often not recognized.')}</div>
    <div class="setrow"><div class="lbl"><b>${t('Probelauf (nur zählen)','Trial (count only)')}</b><span>${t('Er überhört noch nichts, sondern zählt nur. Am Ende steht da, wie viele Sätze er als fremde Stimme überhört hätte. Wenn das zu deinem Abend passt, schalte den Probelauf aus.','It ignores nothing yet but counts. At the end it says how many sentences it would have ignored as a foreign voice. When that fits your evening, switch the trial off.')}</span></div><label class="tgl"><input type="checkbox" id="roomprobe"${c.probe!==false?' checked':''}><i></i></label></div>`:'')+
    `<div class="fh">${t('Fragen, die sich auf vorher Gesagtes beziehen („Wann ist der gestorben?“), ergänzt er aus den letzten Sätzen, aber nur mit Wörtern, die wirklich gefallen sind. Hast du deine Stimme unter „Stimme“ angelernt und ist die Sprechererkennung an, gilt ein „Ja“ nur von dir.','Questions that point back ("When did he die?") are completed from the last sentences, but only with words that were really said. If you taught your voice under "Voice" and speaker recognition is on, only your "yes" counts.')}</div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Genauer erkennen','Detect more')}</b><span>${t('Das Sprachmodell schaut höchstens alle zwei Minuten nach Fragen, Terminen und Einkäufen, die die festen Regeln übersehen. Zählt nur mit einem wörtlichen Zitat. Kostet Rechenzeit auf der GPU.','The language model looks at most every two minutes for questions, appointments and shopping the fixed rules missed. Counts only with a word-for-word quote. Costs GPU time.')}</span></div><label class="tgl"><input type="checkbox" id="roomdetect"${c.detect?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Ton vorher','Tone first')}</b><span>${t('Ein leiser Ton, bevor er von selbst spricht. „Stopp“ beendet den Satz, „Nicht jetzt“ hält ihn eine Viertelstunde still, „Raummodus aus“ schaltet ihn ganz ab.','A soft tone before it speaks by itself. "Stopp" ends the sentence, "Nicht jetzt" keeps it quiet for a quarter of an hour, "Raummodus aus" switches it off.')}</span></div><label class="tgl"><input type="checkbox" id="roomtone"${c.tone?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Zusammenfassung am Ende','Summary at the end')}</b><span>${t('Beim Ausschalten zeigt er, was er gesagt und getan hat (nicht, was er gehört hat). Wird nicht gespeichert.','When switched off it shows what it said and did (not what it heard). Not stored.')}</span></div><label class="tgl"><input type="checkbox" id="roomsum"${c.summary?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Nur als Text','Text only')}</b><span>${t('Hinweise erscheinen still im Verlauf, statt gesprochen zu werden. In deinen Ruhezeiten (Standard 22 bis 7 Uhr) gilt das immer.','Hints appear silently in the conversation instead of being spoken. In your quiet hours (22 to 7 unless changed) this always applies.')}</span></div><label class="tgl"><input type="checkbox" id="roomtext"${c.text?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Erinnerungston','Reminder tone')}</b><span>${t('Alle 15 Minuten ein leiser Ton, damit niemand vergisst, dass er zuhört. Nie in Ruhezeiten.','A soft tone every 15 minutes, so nobody forgets it listens. Never in quiet hours.')}</span></div><label class="tgl"><input type="checkbox" id="roomping"${c.ping?' checked':''}><i></i></label></div>`+
    `<label>${t('Name dieses Geräts','Name of this device')}</label><input id="roomname" maxlength="40" value="${esc(c.name||'')}" placeholder="${esc(roomDevName())}" autocomplete="off"><div class="fh">${t('So steht es in der Liste „Gerade aktiv“, beim Admin und in der iPhone-App.','This is how it appears under "Active now", for the admin and in the iPhone app.')}</div>`+
    (RHA_ON?`<h3 class="sec">${t('Home Assistant','Home Assistant')}</h3><div id="roomha"></div>`:'')+
    `<h3 class="sec">${t('Zuletzt','Recently')}</h3><ul class="facts small" id="roomhist"></ul>`;
  box.querySelectorAll('input[data-rk]').forEach(e=>e.onchange=()=>room.save({kinds:{...room.cfg().kinds,[e.dataset.rk]:e.checked}}));
  $('roommins').onchange=()=>room.save({mins:Number($('roommins').value)});
  $('roomlevel').onchange=()=>room.save({level:$('roomlevel').value});
  $('roomarea').onchange=()=>room.save({area:$('roomarea').value.trim().slice(0,60)});
  $('roomtext').onchange=()=>room.save({text:$('roomtext').checked});
  $('roomping').onchange=()=>room.save({ping:$('roomping').checked});
  $('roomname').onchange=()=>room.save({name:$('roomname').value.replace(/[\x00-\x1f<>"\\]/g,'').trim().slice(0,40)});
  if(typeof xbind==='function')xbind(box);roomLive.show();roomHist();if(RHA_ON)roomHa();
  $('roomdetect').onchange=()=>room.save({detect:$('roomdetect').checked});
  $('roomtone').onchange=()=>room.save({tone:$('roomtone').checked});
  $('roomsum').onchange=()=>room.save({summary:$('roomsum').checked});
  if(RV_ON){$('roomvoices').onchange=()=>room.save({voices:$('roomvoices').value});$('roomprobe').onchange=()=>room.save({probe:$('roomprobe').checked})}}
// Ich → Raum-Modus → Zuletzt: when and where it listened, how it ended, how many sentences; never what was said
async function roomHist(){const ul=$('roomhist');if(!ul)return;let d={items:[],why:{}};try{d=await (await api('/api/room/history')).json()}catch{}
  const day=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{weekday:'short',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  ul.innerHTML=d.items.map(x=>`<li><span><b>${esc(x.name)}</b> <small class="mut">${esc(day(x.start)+' – '+roomHM(x.end*1000)+' · '+(d.why[x.why]||x.why)+' · '+x.heard+t(' Sätze gehört',' sentences heard')+(x.said?' · '+x.said+t(' gesagt',' said'):'')+(x.ignored?' · '+x.ignored+t(' überhört',' ignored'):''))}</small></span></li>`).join('')
    ||`<li class="mut"><span>${t('In den letzten 14 Tagen nicht benutzt.','Not used in the last 14 days.')}</span></li>`}
// Ich → Raum-Modus → Home Assistant: a key that can only read where room mode listens and end it (chat.room_ha)
async function roomHa(){const box=$('roomha');if(!box)return;let d={keys:[]};try{d=await (await api('/api/profile/room/ha')).json()}catch{}
  const k=d.keys[0];
  box.innerHTML=`<div class="setrow"><div class="lbl"><b>${t('Schlüssel für Home Assistant','Key for Home Assistant')}</b><span>${k?esc(t('Angelegt, zuletzt benutzt: ','Made, last used: ')+(k.last?new Date(k.last*1000).toLocaleString():t('noch nie','never'))):esc(t('Darf nur lesen, wo zugehört wird, und beenden.','May only read where it listens, and end it.'))}</span></div>
    <div class="ctl"><button class="b" type="button" id="roomhanew">${k?t('Neu erstellen','Make new'):t('Erstellen','Make')}</button>${k?`<button class="b" type="button" id="roomhadel">${t('Löschen','Delete')}</button>`:''}</div></div><div id="roomhaout"></div>`;
  $('roomhanew').onclick=async()=>{try{const r=await (await api('/api/profile/room/ha',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    const yaml=`rest:\n  - resource: ${location.origin}/api/room/active\n    headers:\n      X-Speech-Device: ${r.token}\n    scan_interval: 30\n    sensor:\n      - name: Spark Raum-Modus\n        value_template: "{{ value_json.count }}"\n        json_attributes: [first, first_until, rooms]\nrest_command:\n  spark_raummodus_aus:\n    url: ${location.origin}/api/room/end\n    method: POST\n    headers:\n      X-Speech-Device: ${r.token}\n    content_type: application/json\n    payload: '{"all": true}'`;
    $('roomhaout').innerHTML=`<div class="fh">${t('Einmal kopieren und in die configuration.yaml von Home Assistant einfügen; der Schlüssel wird nicht noch einmal gezeigt. Am besten unter secrets.yaml ablegen.','Copy once into Home Assistant\'s configuration.yaml; the key is not shown again. Best kept in secrets.yaml.')}</div><pre class="ullog" style="display:block;user-select:all"></pre>`;
    $('roomhaout').querySelector('pre').textContent=yaml}catch(e){$('roomhaout').innerHTML=`<div class="fh err">${esc(e.message)}</div>`}};
  if($('roomhadel'))$('roomhadel').onclick=async()=>{if(!confirm(t('Schlüssel löschen? Home Assistant sieht den Raum-Modus dann nicht mehr.','Delete the key? Home Assistant no longer sees room mode.')))return;
    try{await api('/api/profile/room/ha',{method:'DELETE'})}catch{}roomHa()}}
