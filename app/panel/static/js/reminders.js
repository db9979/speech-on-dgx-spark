// Timers and reminders that ring while the page is open.
// ---------------------------------------------------------------- timers and reminders
// The assistant sets them with a tool; profiles keep them on the Spark (the first device of the
// profile that plays one takes it, the others stay silent). Guests have none (only questions and answers). A due reminder
// chimes, shows a bubble and is spoken; a notification appears when the page is in the background.
let REM_ON=true;
// Reminders set by a recognized speaker other than this browser's profile live on that profile
// and also ring here ("local": kept in this browser only, not deleted on the Spark).
const rem={list:[],rung:new Set(),
  key(){return 'reminders:'+(PROFILE?PROFILE.id:'')},
  stored(){try{return JSON.parse(localStorage.getItem(this.key())||'[]')}catch{return []}},
  async load(){try{localStorage.removeItem('reminders')}catch{}   // what guests kept here before they lost every tool
    if(PROFILE){let l=[];try{l=await this.fetchList()}catch{}this.list=[...l,...this.stored()].sort((a,b)=>a.due-b.due)}
    else this.list=[];this.show()},
  keep(){if(PROFILE)try{localStorage.setItem(this.key(),JSON.stringify(this.list.filter(x=>x.local)))}catch{}this.show()},
  event(ev){if(ev.action==='set'){const it={...ev.item,...(ev.foreign&&PROFILE?{local:true}:{})};
      this.list=[...this.list.filter(x=>x.id!==it.id),it].sort((a,b)=>a.due-b.due);
      try{if(window.Notification&&Notification.permission==='default')Notification.requestPermission()}catch{}}
    else this.list=this.list.filter(x=>!ev.ids.includes(x.id));this.keep()},
  drop(id){const x=this.list.find(y=>y.id===id);this.list=this.list.filter(y=>y.id!==id);if(PROFILE&&x&&!x.local)api('/api/profile/reminders/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{});this.keep()},
  when(due){const d=new Date(due),n=new Date(),o={hour:'2-digit',minute:'2-digit'};
    if(d.toDateString()!==n.toDateString())Object.assign(o,{day:'2-digit',month:'2-digit'});
    return d.toLocaleString(L==='en'?'en-GB':'de-DE',o)},
  show(){const el=$('remlist');el.hidden=!REM_ON||!this.list.length;
    el.innerHTML=this.list.map(x=>`<span class="rem" title="${esc(x.text)}">⏰ <b>${this.when(x.due)}</b><span>${esc(x.text)}</span><button type="button" data-id="${esc(x.id)}" title="${t('Löschen','Cancel')}">✕</button></span>`).join('');
    el.querySelectorAll('button').forEach(b=>b.onclick=()=>this.drop(b.dataset.id))},
  // A profile's reminder rings on one device only: the first that plays it takes it on the Spark
  // (/api/profile/reminders/played); every other page, the iPhone app and push then stay silent.
  async take(x){if(!PROFILE||x.local){this.drop(x.id);return true}
    let play=true;
    try{const r=await api('/api/profile/reminders/played',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id})});
      if(r.ok){const d=await r.json();play=!!d.play;x.vg=d.vg||''}}catch{}   // vg: its card of Offen is in today's conversation    // the Spark unreachable: rather ring once too often than never
    this.list=this.list.filter(y=>y.id!==x.id);this.keep();return play},
  async ring(x){this.rung.add(x.id);if(!await this.take(x))return;
    const card=x.vg&&window.vgLive;
    if(Date.now()-x.due>10*60e3){   // long missed (page was closed): shown quietly, not chimed or said
      if(card)vgLive(x.vg,x.text);else chatLog('assistant','⏰ '+t('Verpasst ','Missed ')+'('+this.when(x.due)+'): '+x.text);return}
    const line=t('Erinnerung: ','Reminder: ')+x.text;
    chime();setTimeout(chime,350);if(card)vgLive(x.vg,line);else chatLog('assistant','⏰ '+line).classList.add('alarm');
    if(document.hidden)try{if(window.Notification&&Notification.permission==='granted')new Notification('⏰ '+x.text,{body:t('Erinnerung','Reminder'),tag:x.id})}catch{}
    if(chat.rec||chat.ctrl||playing())return;   // a conversation is running: the bubble and the chime suffice
    if(typeof voiceOn==='function'&&!voiceOn())return;   // Vorlesen off: the bubble and the chime suffice
    sayText(line)},
  // this browser's push subscription, short (push.sub_id): notes go to the device used last, once
  async pushId(){try{const r=await navigator.serviceWorker.getRegistration();const s=r&&await r.pushManager.getSubscription();
    if(!s||!crypto.subtle)return '';const h=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s.endpoint));
    return [...new Uint8Array(h)].slice(0,8).map(b=>b.toString(16).padStart(2,'0')).join('')}catch{return ''}},
  async fetchList(){return (await api('/api/profile/reminders?page=1&push_id='+await this.pushId())).json()},
  tick(){const now=Date.now();
    for(const x of this.list)if(x.due<=now&&!this.rung.has(x.id)){
      if(now-x.due>6*3600e3){this.drop(x.id);continue}   // long overdue (page was closed): drop quietly
      this.ring(x)}
    if(PROFILE&&!document.hidden&&now-(this.synced||0)>60e3){this.synced=now;    // pick up reminders set on other devices
      this.fetchList().then(l=>{if(PROFILE){this.list=[...l,...this.list.filter(x=>x.local)].filter(x=>!this.rung.has(x.id)).sort((a,b)=>a.due-b.due);this.show()}}).catch(()=>{})}}};
setInterval(()=>rem.tick(),2000);
// Meldung ans genutzte Gerät (zustellung.py): this page says how long ago it was last touched (only that, never what):
// every 60 s while in front, at once on the first touch after a pause, "weg" when it goes to the background. With the
// switch off the Spark says so, and the page asks again only every 5 minutes.
// stage 2: a tapped note about a Vorgang says "gesehen"; "zu" are the Vorgänge done elsewhere, their notifications go
const nahe={input:Date.now(),said:0,on:true,seen:[],
  async say(weg){if(!PROFILE)return;this.said=Date.now();const seen=this.seen.splice(0,5);
    try{const r=await api('/api/zustellung/da',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({idle:Math.round((Date.now()-this.input)/1000),weg:!!weg,id:await rem.pushId(),...(seen.length?{gesehen:seen}:{})})});
      if(r.ok){const d=await r.json();this.on=!!d.on;if(d.zu&&d.zu.length)this.close(d.zu)}}catch{}},
  async close(zu){try{const reg=await navigator.serviceWorker.getRegistration();if(!reg)return;
    for(const n of await reg.getNotifications())if(n.data&&zu.includes(n.data.vg))n.close()}catch{}},
  opened(vg){if(/^v[0-9a-f]{10}$/.test(vg||'')&&!this.seen.includes(vg)){this.seen.push(vg);this.say()}},
  touch(){const n=Date.now(),pause=n-this.input;this.input=n;if(this.on&&pause>30e3&&n-this.said>5e3&&!document.hidden)this.say()},
  tick(){if(!document.hidden&&Date.now()-this.said>(this.on?60e3:300e3))this.say()}};
['pointerdown','keydown','wheel','touchstart'].forEach(e=>addEventListener(e,()=>nahe.touch(),{passive:true,capture:true}));
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(nahe.on&&PROFILE)nahe.say(true)}else nahe.touch()});
setInterval(()=>nahe.tick(),5000);
if(navigator.serviceWorker)navigator.serviceWorker.addEventListener('message',e=>nahe.opened(e.data&&e.data.vg));
{const q=new URLSearchParams(location.search),vg=q.get('vg');if(vg){q.delete('vg');
  history.replaceState(null,'',location.pathname+(q.toString()?'?'+q:'')+location.hash);setTimeout(()=>nahe.opened(vg),1500)}}
