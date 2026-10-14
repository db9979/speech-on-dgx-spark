// "Ich" → E-Mail, part "Mein Mailstil" (mailstil.py): how the profile writes mails, learned from its own sent mails.
// Only the summary is kept, never a mail. Every field can be changed; changed fields stay when the Spark learns again.
let MSTIL_ON=false,MSTIL=null;
const MSTIL_FIELDS=[['anrede',t('Anrede','Form of address')],['gruss_anfang',t('Begrüßung','Greeting')],['gruss_ende',t('Gruß','Sign-off')],
  ['laenge',t('Länge','Length')],['ton',t('Ton','Tone')],['wendungen',t('Typische Wendungen','Typical phrases')],['eigenheiten',t('Eigenheiten','Habits')]];
const MSTIL_SAY={du:'du',Sie:'Sie',gemischt:t('gemischt','mixed'),kurz:t('kurz','short'),mittel:t('mittel','medium'),lang:t('lang','long'),
  locker:t('locker','casual'),freundlich:t('freundlich','friendly'),sachlich:t('sachlich','matter-of-fact'),foermlich:t('förmlich','formal')};
const MSTIL_WHY={postfach:t('Das Postfach war nicht erreichbar.','The mailbox could not be reached.'),zeitlimit:t('Das Lesen hat zu lange gedauert.','Reading took too long.'),
  kein_gesendet_ordner:t('Kein Ordner „Gesendet“ gefunden.','No "Sent" folder found.'),zu_wenig_mails:t('Zu wenige gesendete Mails (mindestens drei je Gruppe).','Too few sent mails (at least three per group).'),
  modell:t('Das Sprachmodell hat keinen brauchbaren Stil geliefert.','The language model gave no usable style.')};
const mstilMsg=(x,err)=>{const m=$('mstilmsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
async function mstilCall(path,body,method){let r;
  try{r=await api('/api/profile/mailstil'+path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined})}catch(e){mstilMsg(e.message,true);return null}
  const d=await r.json().catch(()=>null);if(d){MSTIL=d;mstilRender()}return d}
async function showMailStil(){const box=$('mailstil');if(!box)return;if(!PROFILE||!MSTIL_ON){box.textContent='';return}
  try{MSTIL=await (await api('/api/profile/mailstil')).json()}catch{box.textContent='';return}mstilRender()}
function mstilValue(s,k){const v=s[k];if(Array.isArray(v))return v.join(' · ');if(k==='laenge'&&v)return MSTIL_SAY[v]+(s.woerter?t(` · etwa ${s.woerter} Wörter`,` · about ${s.woerter} words`):'');
  return MSTIL_SAY[v]||v||'–'}
// one group: its fields as rows (read), "Ändern" opens the same fields as a small form
function mstilGroup(g){const E=icEl,s=MSTIL.groups[g]||{},fest=new Set(s.fest||[]),wrap=E('div'),list=E('div','ic-list');wrap.appendChild(list);
  for(const [k,label] of MSTIL_FIELDS){const meta=mstilValue(s,k)+(fest.has(k)?' ✎ '+t('von dir','by you'):'');list.appendChild(icRow(label,meta,[],null))}
  if(s.mails)wrap.appendChild(E('div','fh',t(`Gelernt aus ${s.mails} Mails dieser Gruppe.`,`Learned from ${s.mails} mails of this group.`)));
  const edit=E('button','b',t('Ändern','Change'));edit.type='button';edit.style.marginTop='8px';edit.dataset.mstilEdit=g;
  edit.onclick=()=>{edit.replaceWith(mstilForm(g,s))};wrap.appendChild(edit);return wrap}
function mstilSel(id,opts,val){const x=icEl('select');x.id=id;for(const o of opts){const op=icEl('option','',MSTIL_SAY[o]||o);op.value=o;if(o===val)op.selected=true;x.appendChild(op)}return x}
function mstilForm(g,s){const E=icEl,f=E('div','ic-form'),fields={};
  const add=(k,label,ctl)=>{const l=E('label','',label);l.htmlFor=ctl.id;f.append(l,ctl);fields[k]=ctl};
  add('anrede',t('Anrede','Form of address'),mstilSel('mst-anrede-'+g,MSTIL.anrede,s.anrede));
  const ga=E('input');ga.id='mst-ga-'+g;ga.maxLength=40;ga.value=s.gruss_anfang||'';ga.placeholder=t('Hallo {Name},','Hello {Name},');add('gruss_anfang',t('Begrüßung ({Name} steht für den Namen)','Greeting ({Name} stands for the name)'),ga);
  const ge=E('textarea');ge.id='mst-ge-'+g;ge.rows=2;ge.maxLength=80;ge.value=s.gruss_ende||'';add('gruss_ende',t('Gruß','Sign-off'),ge);
  add('laenge',t('Länge','Length'),mstilSel('mst-len-'+g,MSTIL.lengths,s.laenge));
  add('ton',t('Ton','Tone'),mstilSel('mst-ton-'+g,MSTIL.tones,s.ton));
  const wd=E('textarea');wd.id='mst-wd-'+g;wd.rows=4;wd.value=(s.wendungen||[]).join('\n');add('wendungen',t('Typische Wendungen (eine pro Zeile, höchstens acht)','Typical phrases (one per line, at most eight)'),wd);
  const ei=E('textarea');ei.id='mst-ei-'+g;ei.rows=3;ei.value=(s.eigenheiten||[]).join('\n');add('eigenheiten',t('Eigenheiten (eine pro Zeile, höchstens vier)','Habits (one per line, at most four)'),ei);
  const ok=E('button','b p',t('Speichern','Save')),no=E('button','b',t('Abbrechen','Cancel'));ok.type=no.type='button';ok.dataset.mstilSave=g;
  no.onclick=()=>mstilRender();
  ok.onclick=async()=>{const lines=x=>x.value.split('\n').map(v=>v.trim()).filter(Boolean),ch={};
    for(const [k,c] of Object.entries(fields)){const v=(k==='wendungen'||k==='eigenheiten')?lines(c):c.value.trim();
      const was=s[k]===undefined?(Array.isArray(v)?[]:''):s[k];if(JSON.stringify(v)!==JSON.stringify(was)&&!(v===''||(Array.isArray(v)&&!v.length&&!was.length)))ch[k]=v}
    if(!Object.keys(ch).length){mstilRender();return}
    ok.disabled=true;if(await mstilCall('',{groups:{[g]:ch}},'PUT'))mstilMsg(t('Gespeichert. Deine Änderungen bleiben beim nächsten Lernen stehen.','Saved. Your changes stay when the Spark learns again.'));else ok.disabled=false};
  const row=E('div','row');row.append(ok,no);f.appendChild(row);return f}
function mstilRender(){const d=MSTIL,box=$('mailstil'),E=icEl;if(!box||!d)return;box.textContent='';
  if(!d.on){return}
  box.appendChild(E('h3','sec',t('Mein Mailstil','My mail style')));
  box.appendChild(E('div','intro',t('Der Spark liest deine gesendeten Mails nur lesend und merkt sich, wie du schreibst: Anrede, Gruß, Länge, Ton und typische Wendungen. Damit klingen Antwort-Entwürfe nach dir, per Sprache und im Begleiter („Antwort entwerfen“). Gespeichert wird nur diese Zusammenfassung, keine Mail. Nur für dein Profil, nie im Log.',
    'The Spark reads your sent mails read-only and remembers how you write: form of address, greeting, length, tone and typical phrases. That way reply drafts sound like you, by voice and in the Begleiter ("Draft a reply"). Only this summary is kept, never a mail. Only for your profile, never in a log.')));
  const has=Object.keys(d.groups).length,parts=[];
  if(d.running)parts.push(t('lernt gerade …','learning …'));
  else if(has&&d.learned)parts.push(t('gelernt am ','learned on ')+new Date(d.learned*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE')+t(` aus ${d.mails} Mails`,` from ${d.mails} mails`));
  else parts.push(t('noch nicht gelernt','not learned yet'));
  if(d.state==='fehler')parts.push('⚠ '+(MSTIL_WHY[d.why]||t('Nicht gelernt.','Not learned.')));
  const learn=E('button','b p',has?t('Neu lernen','Learn again'):t('Stil lernen','Learn style'));learn.type='button';learn.id='mstillearn';
  learn.disabled=!d.boxes.length||d.running;
  learn.onclick=async()=>{learn.disabled=true;mstilMsg(t('Lese gesendete Mails und lerne … das dauert ein bis zwei Minuten.','Reading sent mails and learning … this takes a minute or two.'));
    const r=await mstilCall('/learn',{},'POST');if(r)mstilMsg(r.state==='ok'?t('Fertig.','Done.'):'⚠ '+(MSTIL_WHY[r.why]||''),r.state!=='ok');learn.disabled=false};
  const menu=has?[{label:t('Mailstil löschen','Delete mail style'),danger:true,act:async()=>{if(!confirm(t('Den gelernten Mailstil löschen? Deine eigenen Änderungen gehen mit.','Delete the learned mail style? Your own changes go too.')))return;
    if(await mstilCall('',null,'DELETE'))mstilMsg(t('Gelöscht.','Deleted.'))}}]:[];
  box.appendChild(icCard('mail',t('Mein Mailstil','My mail style'),parts.join(' · '),[learn],menu));
  if(!d.boxes.length)box.appendChild(E('div','fh',t('Erst oben ein Postfach verbinden.','Connect a mailbox above first.')));
  const m=E('div','fh');m.id='mstilmsg';box.appendChild(m);
  if(has){const items=d.names.filter(n=>d.groups[n.id]).map(n=>({k:n.id,label:L==='en'?n.en:n.de,n:'',body:()=>mstilGroup(n.id)}));
    box.appendChild(icTabs('mailstil',items))}}
