// Timers and reminders that ring while the page is open.
// ---------------------------------------------------------------- timers and reminders
// The assistant sets them with a tool; profiles keep them on the Spark (the first device of the
// profile that plays one takes it, the others stay silent), guests in this browser. A due reminder
// chimes, shows a bubble and is spoken; a notification appears when the page is in the background.
let REM_ON=true;
// Reminders set by a recognized speaker other than this browser's profile live on that profile
// and also ring here ("local": kept in this browser only, not deleted on the Spark).
const rem={list:[],rung:new Set(),
  key(){return PROFILE?'reminders:'+PROFILE.id:'reminders'},
  stored(){try{return JSON.parse(localStorage.getItem(this.key())||'[]')}catch{return []}},
  async load(){if(PROFILE){let l=[];try{l=await (await api('/api/profile/reminders?page=1')).json()}catch{}this.list=[...l,...this.stored()].sort((a,b)=>a.due-b.due)}
    else this.list=this.stored();this.show()},
  keep(){try{localStorage.setItem(this.key(),JSON.stringify(PROFILE?this.list.filter(x=>x.local):this.list))}catch{}this.show()},
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
      if(r.ok)play=!!(await r.json()).play}catch{}    // the Spark unreachable: rather ring once too often than never
    this.list=this.list.filter(y=>y.id!==x.id);this.keep();return play},
  async ring(x){this.rung.add(x.id);if(!await this.take(x))return;
    if(Date.now()-x.due>10*60e3){   // long missed (page was closed): shown quietly, not chimed or said
      chatLog('assistant','⏰ '+t('Verpasst ','Missed ')+'('+this.when(x.due)+'): '+x.text);return}
    const line=t('Erinnerung: ','Reminder: ')+x.text;
    chime();setTimeout(chime,350);const b=chatLog('assistant','⏰ '+line);b.classList.add('alarm');
    if(document.hidden)try{if(window.Notification&&Notification.permission==='granted')new Notification('⏰ '+x.text,{body:t('Erinnerung','Reminder'),tag:x.id})}catch{}
    if(chat.rec||chat.ctrl||playing())return;   // a conversation is running: the bubble and the chime suffice
    sayText(line)},
  tick(){const now=Date.now();
    for(const x of this.list)if(x.due<=now&&!this.rung.has(x.id)){
      if(now-x.due>6*3600e3){this.drop(x.id);continue}   // long overdue (page was closed): drop quietly
      this.ring(x)}
    if(PROFILE&&!document.hidden&&now-(this.synced||0)>60e3){this.synced=now;    // pick up reminders set on other devices
      api('/api/profile/reminders?page=1').then(r=>r.json()).then(l=>{if(PROFILE){this.list=[...l,...this.list.filter(x=>x.local)].filter(x=>!this.rung.has(x.id)).sort((a,b)=>a.due-b.due);this.show()}}).catch(()=>{})}}};
setInterval(()=>rem.tick(),2000);
