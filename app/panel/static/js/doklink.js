// Links als Dokument (doklink.py, plan open-notebook Stufe 4): „Link hinzufügen“ under Ich → Dokumente takes up to ten
// addresses (one per line); the Spark fetches each public page or file and keeps it as a document. Waiting and failed
// addresses stand below with their state in fixed words; „Neu abrufen“ in the details of a link document asks the page
// again, only on the click. Addresses are the person's own text: only through esc(), never markup.
const LKD_WORT={angenommen:['angenommen','accepted'],wartet:['wird geholt','being fetched'],ok:['ist ein Dokument','is a document'],
  gleich:['unverändert','unchanged'],neu:['neu gelesen','read again'],adresse:['keine gültige Adresse','not a valid address'],
  zugang:['Adresse mit Zugangsdaten','address with login data'],port:['nur die üblichen Ports','only the usual ports'],
  lang:['Adresse zu lang','address too long'],privat:['keine öffentliche Adresse','not a public address'],
  doppelt:['liegt schon in den Dokumenten oder wartet','already in the documents or waiting'],
  warteschlange:['es warten schon genug','enough are waiting already'],notaus:['der Notaus hält das Internet zu','the Notaus holds the internet off'],
  groesse:['zu groß','too large'],art:['diese Art liest der Spark nicht','the Spark does not read this kind'],
  status:['die Seite antwortet nicht mit Inhalt','the page does not answer with content'],weiter:['zu viele Weiterleitungen','too many redirects'],
  zeit:['zu langsam','too slow'],netz:['nicht erreichbar','not reachable'],speicher:['kein Platz für Dokumente','no room for documents'],
  grenze:['Tagesgrenze erreicht','daily limit reached']};
const lkdWort=w=>LKD_WORT[w]?t(...LKD_WORT[w]):w;
const lkdInfo=()=>DOCINFO&&DOCINFO.link&&DOCINFO.link.on?DOCINFO.link:null;
// the link of a document (Ich → Dokumente details: address, fetched, „Neu abrufen“)
function lkdOf(id){const L=lkdInfo();return L?(L.links||[]).find(x=>x.doc===id)||null:null}
let lkdTimer=null;
function lkdShow(){const box=$('lkdbox');if(!box)return;clearTimeout(lkdTimer);const L=lkdInfo();
  if(!L){box.hidden=true;return}box.hidden=false;
  const open=(L.links||[]).filter(x=>!x.doc);
  $('lkdin').innerHTML=`<p class="fh">${esc(t(`Bis zu ${L.max} Adressen, eine je Zeile. Nur öffentliche Seiten und Dateien (HTML, PDF, Text, Word, ODT) bis ${L.mb} MB; heute ${L.today} von ${L.day} Abrufen.`,
      `Up to ${L.max} addresses, one per line. Public pages and files only (HTML, PDF, text, Word, ODT) up to ${L.mb} MB; ${L.today} of ${L.day} fetches today.`))}</p>`+
    `<textarea id="lkdurls" rows="3" maxlength="22000" placeholder="https://…" aria-label="${esc(t('Adressen','Addresses'))}"></textarea>`+
    `<div class="ld-acts"><button class="b p" type="button" id="lkdgo">${ic('download')} ${esc(t('Holen','Fetch'))}</button></div>`+
    `<div id="lkdmsg" class="mut" aria-live="polite"></div>`+
    (open.length?`<div class="ld-list">`+open.map(x=>`<div class="ld-row"><span class="ld-mid"><b>${esc(x.url)}</b><small>${esc(lkdWort(x.stand==='wartet'?'wartet':x.fehler||x.stand))}</small></span>`+
      `<span class="ld-right"><button class="b" type="button" data-lkddrop="${esc(x.id)}" aria-label="${esc(t('Aus der Liste nehmen','Take out of the list'))}">${ic('x')}</button></span></div>`).join('')+`</div>`:'');
  if(open.some(x=>x.stand==='wartet'))lkdTimer=setTimeout(()=>{if(box.offsetParent!==null&&!document.hidden&&typeof showDocs==='function')showDocs()},5000)}
async function lkdGo(){const urls=$('lkdurls').value.split(/\s+/).map(x=>x.trim()).filter(Boolean),L=lkdInfo();if(!urls.length||!L)return;
  if(urls.length>L.max){$('lkdmsg').innerHTML=`<span class="err">${esc(t(`Höchstens ${L.max} Adressen auf einmal.`,`At most ${L.max} addresses at once.`))}</span>`;return}
  $('lkdgo').disabled=true;
  try{const r=await (await api('/api/profile/docs/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})})).json();
    const n=r.links.filter(x=>x.wort==='angenommen').length;
    $('lkdmsg').textContent=t(`${n} von ${r.links.length} angenommen`,`${n} of ${r.links.length} accepted`)+
      r.links.filter(x=>x.wort!=='angenommen').map(x=>' · '+x.url+': '+lkdWort(x.wort)).join('')}
  catch(x){$('lkdmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}
  $('lkdgo').disabled=false;if(typeof showDocs==='function')showDocs()}
// „Neu abrufen“: the answer says unchanged, read again or why not
async function lkdAgain(doc){try{const r=await (await api('/api/profile/wissen/'+encodeURIComponent(doc)+'/abrufen',{method:'POST'})).json();
    $('docmsg').textContent=t('Neu abrufen: ','Fetch again: ')+lkdWort(r.stand)}
  catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}
  if(typeof showDocs==='function')showDocs()}
document.addEventListener('click',async e=>{if(e.target.closest('#lkdgo')){lkdGo();return}
  const d=e.target.closest('[data-lkddrop]');if(!d)return;
  try{await api('/api/profile/docs/link/'+encodeURIComponent(d.dataset.lkddrop),{method:'DELETE'})}catch(x){$('lkdmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}
  if(typeof showDocs==='function')showDocs()});
