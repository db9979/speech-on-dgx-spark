// „Weiche abstimmen“ (weiche_abstimmen.py, plan opencode-werkstatt point 1) on Funktionen → Weiche: one run asks the
// language model for words, the panel keeps only those its fixed measure lets through; „Übernehmen“ saves them with the
// Weiche's own save (Rückgängig as always). Words and numbers only, through textContent.
const WT={timer:0};
function wtEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function wtZahl(m){return (m.richtig+m.geschuetzt)+t(' von ',' of ')+m.n+t(' gut',' fine')+' · '+m.falsch+t(' falsch',' wrong')}
function wtShow(d){const box=$('wtbox');if(!box)return;box.hidden=!d.an;if(!d.an)return;
  $('wtgo').disabled=d.laeuft;
  $('wtmsg').textContent=d.laeuft?t('Läuft … Gruppe ','Running … group ')+(d.stand||'-'):d.fehler==='modell'?t('Das Sprachmodell hat keine Wörter geliefert.','The language model gave no words.'):d.fehler?t('Fehler beim Abstimmen.','Error while tuning.'):'';
  const res=$('wtres');res.textContent='';const v=d.vorschlag;if(!v)return;
  res.appendChild(wtEl('div','fh',t('Übungshälfte: ','Practice half: ')+wtZahl(v.vorher.uebung)+' → '+wtZahl(v.nachher.uebung)));
  res.appendChild(wtEl('div','fh',t('Prüfhälfte: ','Check half: ')+wtZahl(v.vorher.pruef)+' → '+wtZahl(v.nachher.pruef)));
  res.appendChild(wtEl('div','mut',v.gruppen+t(' Gruppen gefragt, ',' groups asked, ')+v.probiert+t(' Wörter gemessen, ',' words measured, ')+v.woerter.length+t(' behalten',' kept')));
  if(!v.woerter.length)return;
  const ul=wtEl('ul');v.woerter.forEach(w=>ul.appendChild(wtEl('li','',w.label+': '+w.wort+' (+'+w.plus+')')));res.appendChild(ul);
  const row=wtEl('div','row'),ok=wtEl('button','b p',t('Übernehmen','Apply')),no=wtEl('button','b',t('Verwerfen','Discard'));ok.type=no.type='button';
  ok.onclick=async()=>{try{WH.d=await (await api('/api/admin/weiche/abstimmen/uebernehmen'+(L==='en'?'?lang=en':''),{method:'POST'})).json();WH.edit=null;whRender();wtLoad()}catch(e){$('wtmsg').textContent=e.message}};
  no.onclick=async()=>{try{wtShow(await (await api('/api/admin/weiche/abstimmen',{method:'DELETE'})).json())}catch(e){$('wtmsg').textContent=e.message}};
  row.append(ok,no);res.appendChild(row)}
async function wtLoad(){clearTimeout(WT.timer);if(!$('wtbox'))return;
  try{const d=await (await api('/api/admin/weiche/abstimmen')).json();wtShow(d);if(d.laeuft)WT.timer=setTimeout(wtLoad,3000)}catch{}}
if($('wtgo'))$('wtgo').onclick=async()=>{$('wtgo').disabled=true;
  try{wtShow(await (await api('/api/admin/weiche/abstimmen',{method:'POST'})).json());WT.timer=setTimeout(wtLoad,3000)}catch(e){$('wtmsg').textContent=e.message;$('wtgo').disabled=false}};
window.wtLoad=wtLoad;
