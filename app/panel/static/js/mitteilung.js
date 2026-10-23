// Mitteilung antippen öffnet genau diese Meldung (mitteilungen.py, Dominik 2026-10-23): a tapped notification of the
// browser (sw.js) or the Android app (#meldung=<number>) opens the conversation and shows the note there as a card
// above it, with its full text and the one button the Spark picked by fixed rules (ziel: Offen, Chat, Mail, Code,
// Weg). Only the number comes in; the text is fetched for the own profile. Everything through textContent (icEl),
// never as HTML; a way in the text becomes a Sprung-Link by itself (way.js).
const MT_ID=/^[0-9a-f]{16}$/;
async function mtOpen(id){if(!MT_ID.test(id||'')||typeof PROFILE==='undefined'||!PROFILE)return;
  const {r,d}=await apiTry('/api/profile/mitteilung?id='+id);
  if(typeof goSec==='function')goSec('chat');
  mtCard(r.ok?d:null)}
function mtWhen(s){const d=new Date(s*1000),n=new Date(),hm=d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===n.toDateString()?t('heute ','today ')+hm:d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{weekday:'short',day:'numeric',month:'numeric'})+' '+hm}
// the card above the conversation; null: the note is older than a day or was for another profile
function mtCard(x){const log=$('chatlog');if(!log)return;const old=$('mtcard');if(old)old.remove();
  const el=icEl,c=el('div','vk mtcard');c.id='mtcard';c.setAttribute('role','region');c.setAttribute('aria-label',t('Mitteilung','Notification'));
  const k=el('div','vk-k'),sym=el('span','vk-sym');sym.appendChild(icSvg('bell',14));k.append(sym,el('b','',t('Mitteilung','Notification')));
  if(x)k.appendChild(el('span','mt-wann',mtWhen(x.t)));
  const zu=el('button','mt-zu');zu.type='button';zu.setAttribute('aria-label',t('Schließen','Close'));zu.appendChild(icSvg('x',14));zu.onclick=()=>c.remove();
  k.appendChild(zu);c.appendChild(k);
  if(!x){c.appendChild(el('div','vk-z',t('Diese Mitteilung ist nicht mehr da (älter als ein Tag oder nach einem Neustart des Spark).',
    'This notification is gone (older than a day, or the Spark restarted).')));log.before(c);return}
  c.append(el('b','vk-t',x.title),el('div','vk-z mt-text',x.body));
  const z=x.ziel||{},bar=el('div','vk-b'),go=(de,en,act)=>{const b=el('button','b'+(bar.childElementCount?'':' p'),t(de,en));b.type='button';b.onclick=()=>act(b);bar.appendChild(b)};
  if(z.art==='vorgang'&&typeof vgShow==='function'&&typeof VG_ON!=='undefined'&&VG_ON)go('Ansehen und erledigen','View and handle',()=>vgShow(z.vg));
  if(z.art==='chat'&&typeof cxOpen==='function')go('Chat öffnen','Open chat',()=>{goSec('chats');cxOpen(z.chat)});
  if(z.art==='mail'&&typeof postRead==='function')go('Mail lesen','Read mail',()=>{icTabSet('post','show');goSec('post');postRead(z.ref)});
  if(z.art==='code'&&z.code)go('Code kopieren','Copy code',b=>copyString(z.code,b));
  if(z.weg&&typeof wayGo==='function')go('Öffnen: '+z.weg,'Open: '+z.weg,()=>wayGo(z.weg));
  if(bar.childElementCount)c.appendChild(bar);
  if(z.vg&&typeof nahe!=='undefined')nahe.opened(z.vg);   // a note about a Vorgang counts as seen (zustellung.py)
  log.before(c);c.scrollIntoView({block:'nearest'})}
// #meldung=<number>: from the Android app, a new window of a tapped browser notification or the Begleiter on the Mac
function mtHash(){const m=/^#meldung=([0-9a-f]{16})$/.exec(location.hash);if(!m)return;
  history.replaceState(null,'',location.pathname+location.search);mtOpen(m[1])}
addEventListener('hashchange',()=>{if(location.hash.startsWith('#meldung='))mtHash()});
if(navigator.serviceWorker)navigator.serviceWorker.addEventListener('message',e=>{const m=e.data&&e.data.meldung;if(typeof m==='string')mtOpen(m)});
