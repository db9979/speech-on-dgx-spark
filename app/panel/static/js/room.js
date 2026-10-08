// Room mode (see room.py): the assistant listens to the conversation in the room for a while and helps
// in a pause. Per device and per switch-on; what it hears stays on the Spark for a few minutes only.
let ROOM_ON=false;
window.room={on:false,speaking:false,id:'',until:0,queue:Promise.resolve(),lastSpeech:0,wait:false,need:2.5,asking:false,
  cfg(){let o={};try{o=JSON.parse(localStorage.getItem('room')||'{}')}catch{}
    return {mins:30,level:'hints',text:false,area:'',tone:true,detect:false,summary:true,...o,kinds:{q:true,cal:true,ha:true,shop:true,timer:true,remind:true,conv:true,...(o.kinds||{})}}},
  save(o){try{localStorage.setItem('room',JSON.stringify({...this.cfg(),...o}))}catch{}},
  idle(){return !chat.rec&&!chat.ctrl&&!playing()&&!chat.asrBusy},
  show(){$('roomtgl').style.display=ROOM_ON&&PROFILE?'':'none';if(this.on&&!(ROOM_ON&&PROFILE))this.stop()},
  async start(){if(!ROOM_ON||!PROFILE)return;
    this.on=true;this.id=[...crypto.getRandomValues(new Uint8Array(8))].map(b=>b.toString(16).padStart(2,'0')).join('');
    this.until=Date.now()+this.cfg().mins*60e3;this.wait=false;this.lastSpeech=Date.now();
    if(!wake.on)await startWake();
    if(!wake.on){this.on=false;$('chatroom').checked=false;return}
    $('chatroom').checked=true;this.badge()},
  stop(){if(!this.on)return;this.on=false;this.wait=false;
    fetch('/api/room/stop',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({room:this.id})})
      .then(r=>r.json()).then(d=>this.recap(d.summary||[])).catch(()=>{});
    if(!$('chatwake').checked)stopWake();$('chatroom').checked=false;this.badge()},
  badge(){const w=$('wakeind');w.classList.toggle('room',this.on);
    w.querySelector('span').textContent=this.on?t('Raum-Modus: hört zu, noch ','Room mode: listening, ')+Math.max(1,Math.ceil((this.until-Date.now())/60e3))+t(' Min.',' min left'):t('lauscht auf „Hey Spark“','listening for "Hey Spark"');
    if(!this.on&&!wake.on)w.hidden=true},
  enqueue(seg,rate){this.queue=this.queue.then(()=>checkWake(seg,rate)).catch(()=>{})},
  // when it ends: what the assistant said and did, shown once and not kept in the conversation
  recap(items){if(!items.length||!this.cfg().summary)return;
    const b=chatLog('assistant',t('Raum-Modus beendet. Das habe ich gesagt und getan:','Room mode ended. What I said and did:')+'\n'+
      items.map(x=>'• '+new Date(x.t).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'})+' '+x.text).join('\n'));
    b.classList.add('pro','recap')},
  body(o){const c=this.cfg();return JSON.stringify({room:this.id,level:c.level,kinds:c.kinds,area:c.area,detect:!!c.detect,
    tz:(()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}})(),...o})},
  async heard(text){if(!this.on)return;
    if(this.speaking&&/^\W*(stopp?|halt|ruhe|still|sei still|psst|nicht jetzt|jetzt nicht|schon gut|genug|aufhören|hör auf)\b/i.test(text))stopAnswer();
    try{const r=await fetch('/api/room/heard',{method:'POST',headers:{'Content-Type':'application/json'},body:this.body({text})});if(!r.ok)return;
      const d=await r.json();if(d.stop)stopAnswer();if(d.reminder&&window.rem)rem.event({action:'set',item:d.reminder});if(d.say)this.say(d.say,d.silent);
      if(d.end){this.stop();return}this.wait=!!d.wait;this.need=2.5}catch{}},
  async tick(){if(!this.on)return;if(Date.now()>this.until||this.away()){this.stop();return}this.badge();
    if(!this.wait||this.asking||wake.seg||!this.idle()||Date.now()-this.lastSpeech<this.need*1000)return;
    this.wait=false;this.asking=true;
    try{const r=await fetch('/api/room/pause',{method:'POST',headers:{'Content-Type':'application/json'},body:this.body({quiet:(Date.now()-this.lastSpeech)/1000})});
      const d=r.ok?await r.json():{};if(d.again){this.need=d.again;this.wait=true}if(d.say)this.say(d.say,d.silent)}catch{}
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
document.addEventListener('visibilitychange',()=>{if(document.hidden){room.hidden=room.hidden||Date.now();return}
  if(room.on&&room.away())room.stop();room.hidden=0});
addEventListener('pagehide',()=>room.stop());
$('chatroom').onchange=()=>{if($('chatroom').checked)room.start();else room.stop()};
// "Ich" → Raum-Modus: settings of this device
function showRoom(){const box=$('roombox');if(!PROFILE||!ROOM_ON){box.innerHTML='';return}const c=room.cfg();
  const kind=(k,l,h)=>`<div class="setrow"><div class="lbl"><b>${esc(l)}</b><span>${esc(h)}</span></div><label class="tgl"><input type="checkbox" data-rk="${k}"${c.kinds[k]!==false?' checked':''}><i></i></label></div>`;
  box.innerHTML=`<div class="intro">${t('Mit dem Schalter „Raum“ unter dem Gesicht hört der Assistent für eine Weile dem Gespräch im Raum zu und hilft in einer Pause. Das Gehörte bleibt nur wenige Minuten auf dem Spark und wird nie gespeichert; er nutzt dabei weder dein Gedächtnis noch Mails oder frühere Gespräche. Geändert wird nur nach einem „Ja“. Sag allen im Raum, dass er zuhört. Ist die Seite länger als zwei Minuten im Hintergrund oder das Handy gesperrt, geht er aus. Diese Einstellungen gelten nur für dieses Gerät.','With the switch "Room" below the face the assistant listens to the conversation in the room for a while and helps in a pause. What it hears stays on the Spark for a few minutes only and is never stored; it uses neither your memory nor mail or earlier conversations. It changes something only after a "yes". Tell everyone in the room that it is listening. When the page is in the background or the phone locked for more than two minutes, it switches off. These settings apply to this device only.')}</div>
    <div class="two2"><div><label>${t('Hört zu für','Listens for')}</label><select id="roommins">${[15,30,60,120,240].map(n=>`<option value="${n}"${n===c.mins?' selected':''}>${n} ${t('Minuten','minutes')}</option>`).join('')}</select></div>
      <div><label>${t('Wie viel er sagen darf','How much it may say')}</label><select id="roomlevel"><option value="questions"${c.level==='questions'?' selected':''}>${t('nur Fragen beantworten','only answer questions')}</option><option value="hints"${c.level==='hints'?' selected':''}>${t('auch Hinweise (empfohlen)','also hints (recommended)')}</option><option value="all"${c.level==='all'?' selected':''}>${t('auch Kommentare','also comments')}</option></select></div></div>
    <div class="fh">${t('„Auch Kommentare“: nach längerer Stille höchstens alle zehn Minuten ein kurzer Satz, wenn das Modell etwas sicher Hilfreiches weiß. Am wenigsten zuverlässig.','"Also comments": after a longer silence, at most every ten minutes one short sentence when the model knows something surely helpful. Least reliable.')}</div>`+
    kind('q',t('Offene Fragen beantworten','Answer open questions'),t('„Wann war nochmal …?“ ohne dass jemand angesprochen ist: kurze Antwort, mit Websuche, wenn sie an ist. Im Zweifel sagt er nichts.','"When was … again?" with nobody addressed: a short answer, with the web search when it is on. In doubt it says nothing.'))+
    kind('cal',t('Termine vorschlagen','Offer appointments'),t('„Freitag um 10 zum Zahnarzt“: „Soll ich das eintragen?“. Eingetragen wird erst nach einem Ja.','"Friday at 10 to the dentist": "Shall I enter it?". Entered only after a yes.'))+
    kind('ha',t('Raumklima und Licht','Room climate and light'),t('„Ist das kalt hier“: die echte Temperatur des Raums unten, dazu das Angebot, die Heizung um ein Grad zu ändern; bei „zu dunkel“ das Licht. Geschaltet wird nur nach Ja (mit Codewort, wenn du eines hast).','"It is cold here": the real temperature of the room below, offering to change the heating by one degree; on "too dark" the light. Switches only after yes (with your code word if you have one).'))+
    kind('shop',t('Einkaufsliste','Shopping list'),t('„Wir brauchen noch Milch“: „Soll ich Milch auf die Einkaufsliste setzen?“ (Home Assistant). Erst nach Ja.','"We still need milk": "Shall I put milk on the shopping list?" (Home Assistant). Only after yes.'))+
    kind('timer',t('Timer','Timers'),t('„Die Pizza braucht noch 12 Minuten“: „Soll ich einen Timer über 12 Minuten stellen?“. Erst nach Ja.','"The pizza needs 12 more minutes": "Shall I set a 12 minute timer?". Only after yes.'))+
    kind('remind',t('Erinnerungen','Reminders'),t('„Ich darf nicht vergessen, Oma anzurufen“: „Soll ich dich um 15:30 Uhr erinnern?“ (zur genannten Uhrzeit, „morgen“ um 8 Uhr, sonst in einer Stunde). Erst nach Ja.','"I must not forget to call grandma": "Shall I remind you at 15:30?" (at the time named, "tomorrow" at 8, else in an hour). Only after yes.'))+
    kind('conv',t('Umrechnen','Unit conversion'),t('„Wie viel sind 180 Grad in Fahrenheit?“, Milliliter in Tassen, Zoll in Zentimeter: ausgerechnet, ohne Modell.','"How much is 180 degrees in Fahrenheit?", millilitres in cups, inches in centimetres: calculated, without the model.'))+
    `<label>${t('Raum dieses Geräts in Home Assistant','Room of this device in Home Assistant')}</label><input id="roomarea" placeholder="${t('z. B. Wohnzimmer','e.g. Living room')}" value="${esc(c.area||'')}" autocomplete="off">`+
    `<div class="fh">${t('Fragen, die sich auf vorher Gesagtes beziehen („Wann ist der gestorben?“), ergänzt er aus den letzten Sätzen, aber nur mit Wörtern, die wirklich gefallen sind. Hast du deine Stimme unter „Stimme“ angelernt und ist die Sprechererkennung an, gilt ein „Ja“ nur von dir.','Questions that point back ("When did he die?") are completed from the last sentences, but only with words that were really said. If you taught your voice under "Voice" and speaker recognition is on, only your "yes" counts.')}</div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Genauer erkennen','Detect more')}</b><span>${t('Das Sprachmodell schaut höchstens alle zwei Minuten nach Fragen, Terminen und Einkäufen, die die festen Regeln übersehen. Zählt nur mit einem wörtlichen Zitat. Kostet Rechenzeit auf der GPU.','The language model looks at most every two minutes for questions, appointments and shopping the fixed rules missed. Counts only with a word-for-word quote. Costs GPU time.')}</span></div><label class="tgl"><input type="checkbox" id="roomdetect"${c.detect?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Ton vorher','Tone first')}</b><span>${t('Ein leiser Ton, bevor er von selbst spricht. „Stopp“ beendet den Satz, „Nicht jetzt“ hält ihn eine Viertelstunde still, „Raummodus aus“ schaltet ihn ganz ab.','A soft tone before it speaks by itself. "Stopp" ends the sentence, "Nicht jetzt" keeps it quiet for a quarter of an hour, "Raummodus aus" switches it off.')}</span></div><label class="tgl"><input type="checkbox" id="roomtone"${c.tone?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Zusammenfassung am Ende','Summary at the end')}</b><span>${t('Beim Ausschalten zeigt er, was er gesagt und getan hat (nicht, was er gehört hat). Wird nicht gespeichert.','When switched off it shows what it said and did (not what it heard). Not stored.')}</span></div><label class="tgl"><input type="checkbox" id="roomsum"${c.summary?' checked':''}><i></i></label></div>`+
    `<div class="setrow"><div class="lbl"><b>${t('Nur als Text','Text only')}</b><span>${t('Hinweise erscheinen still im Verlauf, statt gesprochen zu werden. In deinen Ruhezeiten (Standard 22 bis 7 Uhr) gilt das immer.','Hints appear silently in the conversation instead of being spoken. In your quiet hours (22 to 7 unless changed) this always applies.')}</span></div><label class="tgl"><input type="checkbox" id="roomtext"${c.text?' checked':''}><i></i></label></div>`;
  box.querySelectorAll('input[data-rk]').forEach(e=>e.onchange=()=>room.save({kinds:{...room.cfg().kinds,[e.dataset.rk]:e.checked}}));
  $('roommins').onchange=()=>room.save({mins:Number($('roommins').value)});
  $('roomlevel').onchange=()=>room.save({level:$('roomlevel').value});
  $('roomarea').onchange=()=>room.save({area:$('roomarea').value.trim().slice(0,60)});
  $('roomtext').onchange=()=>room.save({text:$('roomtext').checked});
  $('roomdetect').onchange=()=>room.save({detect:$('roomdetect').checked});
  $('roomtone').onchange=()=>room.save({tone:$('roomtone').checked});
  $('roomsum').onchange=()=>room.save({summary:$('roomsum').checked})}
