// Einladungen aus Mails (einladung.py, Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3): a mail with an
// invitation (.ics) shows a bar under its subject: what, when, where, who invites, the own answer so far, the calendar
// it goes into; „Zusagen“, „Vielleicht“, „Absagen“ like Apple Mail, with „Mails senden“ also to the organiser.
// Only the Spark decides; the bar shows what it says. post.js calls einShow(subject element, mail id, folder).
const EIN={id:'',d:null,busy:false,msg:'',cal:'',reply:true};
const EIN_WORD={accepted:['Zugesagt','Accepted'],tentative:['Vielleicht','Maybe'],declined:['Abgesagt','Declined']};
function einWhen(d){const loc=kalLoc(),s=new Date(d.start*1000),e=new Date((d.end||d.start)*1000);
  if(d.allday){const last=new Date(e.getTime()-1000),day={weekday:'short',day:'numeric',month:'long',year:'numeric'};
    return s.toDateString()===last.toDateString()||!d.end?s.toLocaleDateString(loc,day):s.toLocaleDateString(loc,{day:'numeric',month:'short'})+' – '+last.toLocaleDateString(loc,day)}
  const hm={hour:'2-digit',minute:'2-digit'};
  return s.toLocaleDateString(loc,{weekday:'short',day:'numeric',month:'long',year:'numeric'})+', '+s.toLocaleTimeString(loc,hm)+
    (d.end?' – '+(e.toDateString()===s.toDateString()?e.toLocaleTimeString(loc,hm):e.toLocaleString(loc,{day:'numeric',month:'short',...hm})):'')}
async function einShow(after,id,folder){if(!after)return;
  let bar=after.parentNode.querySelector('.einbar');if(!bar){bar=document.createElement('div');bar.className='einbar';bar.setAttribute('aria-live','polite');after.after(bar)}
  if(EIN.id!==id+'|'+folder){Object.assign(EIN,{id:id+'|'+folder,d:null,msg:'',cal:'',reply:true});
    bar.innerHTML=`<div class="mut">${esc(t('Einladung wird gelesen …','Reading the invitation …'))}</div>`;
    const {r,d}=await apiTry('/api/profile/mail/invite?'+new URLSearchParams({id,folder}).toString());
    if(EIN.id!==id+'|'+folder||!bar.isConnected)return;
    if(!r.ok){bar.innerHTML=`<div class="note warn">${esc(errSay(r.status,d.detail,t('Die Einladung lässt sich nicht lesen.','The invitation cannot be read.')))}</div>`;return}
    EIN.d=d}
  einPaint(bar,id,folder)}
function einPaint(bar,id,folder){const d=EIN.d;if(!d)return;const cancel=d.method==='cancel';
  const org=d.organizer.name||d.organizer.addr,mine=EIN_WORD[d.mine];
  const btn=(k,lbl,cls)=>`<button type="button" class="b${cls?' '+cls:''}" data-ein="${k}"${EIN.busy?' disabled':''}>${esc(lbl)}</button>`;
  bar.innerHTML=`<div class="einhead">${postIc('cal')}<div class="ld-mid"><b>${esc(d.title||t('(ohne Titel)','(no title)'))}</b>`+
    `<small>${esc(einWhen(d))}${d.repeats?' · '+esc(t('wiederholt sich','repeats')):''}</small>`+(d.place?`<small>${esc(d.place)}</small>`:'')+
    (org?`<small>${esc((cancel?t('Abgesagt von ','Cancelled by '):t('Einladung von ','Invitation from '))+org)}${d.people>1?' · '+esc(d.people+t(' Personen',' people')):''}</small>`:'')+`</div></div>`+
    (cancel?`<div class="einstate">${esc(d.in?t('Abgesagt. Steht noch im Kalender „','Cancelled. Still in the calendar "')+d.in+t('“.','".'):t('Abgesagt. Steht in keinem Kalender.','Cancelled. In no calendar.'))}</div>`+(d.in?`<div class="einacts">${btn('remove',t('Aus dem Kalender entfernen','Remove from calendar'),'bad')}</div>`:'')
      :`<div class="einstate">${esc(d.in?t('Im Kalender „','In the calendar "')+d.in+t('“','"')+(mine?' · '+mine[L==='en'?1:0]:''):mine?mine[L==='en'?1:0]:t('Noch nicht im Kalender','Not in the calendar yet'))}</div>`+
      (!d.in&&d.calendars.length>1?`<label class="einpick">${esc(t('Kalender','Calendar'))}<select data-ein="cal">${d.calendars.map(c=>`<option value="${esc(c.id)}"${c.id===EIN.cal?' selected':''}>${esc(c.name)}</option>`).join('')}</select></label>`:'')+
      (!d.calendars.length?`<div class="note warn">${esc(t('Kein Kalender, in den der Spark schreiben darf: Kalender → Einstellungen.','No calendar the Spark may write into: Calendar → Settings.'))}</div>`:'')+
      (d.reply?`<label class="chk einreply"><input type="checkbox" data-ein="reply"${EIN.reply?' checked':''}> ${esc(t('Antwort an ','Answer to ')+d.organizer.addr+t(' senden',''))}</label>`:'')+
      `<div class="einacts">${d.method==='publish'?btn('accept',t('In den Kalender','Add to calendar'),'p')
        :btn('accept',t('Zusagen','Accept'),'p')+btn('tentative',t('Vielleicht','Maybe'))+btn('decline',t('Absagen','Decline'))}</div>`)+
    `<div class="fh${EIN.msg&&EIN.msg.err?' err':''}">${esc(EIN.msg?EIN.msg.text:'')}</div>`;
  const sel=bar.querySelector('select[data-ein=cal]');if(sel){if(!EIN.cal)EIN.cal=sel.value;sel.onchange=()=>EIN.cal=sel.value}
  const rp=bar.querySelector('input[data-ein=reply]');if(rp)rp.onchange=()=>EIN.reply=rp.checked;
  bar.querySelectorAll('button[data-ein]').forEach(b=>b.onclick=()=>einTake(bar,id,folder,b.dataset.ein))}
async function einTake(bar,id,folder,answer){const d=EIN.d;if(!d||EIN.busy)return;
  if(answer==='remove'&&!confirm(t('Den abgesagten Termin aus dem Kalender entfernen?','Remove the cancelled appointment from the calendar?')))return;
  EIN.busy=true;EIN.msg='';einPaint(bar,id,folder);
  const {r,d:x}=await apiTry('/api/profile/mail/invite',xjson('POST',{id,folder,answer,calendar:EIN.cal||'',reply:!!(d.reply&&EIN.reply)}));
  EIN.busy=false;
  if(!r.ok){EIN.msg={err:true,text:errSay(r.status,x.detail,'')};einPaint(bar,id,folder);return}
  const word={accept:'accepted',tentative:'tentative',decline:'declined'}[answer];
  Object.assign(d,{in:x.in,mine:word||d.mine});
  EIN.msg={text:(answer==='remove'?t('Aus dem Kalender entfernt.','Removed from the calendar.'):x.in?t('Im Kalender „','In the calendar "')+x.in+t('“.','".'):t('Nicht im Kalender.','Not in the calendar.'))+
    (x.replied?' '+t('Antwort gesendet.','Answer sent.'):'')};
  einPaint(bar,id,folder)}
