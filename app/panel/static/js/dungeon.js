// KI-Dungeon-Master (dungeon.py, plan dungeon-master/plan.md): a page of its own in the menu. „Runden“ lists the own
// rounds and starts a new one; an open round is the table: the group on the left, the story in the middle, the round
// and the own hero on the right (a phone shows them one below the other). „Helden“ holds the kept heroes. A seat link
// (#spiel=<code>) opens the same table in a window, for a guest without a profile through /api/dungeon/*, for a
// signed-in profile with „Mit meinem Profil“. Every value comes from the panel; names, actions and the narration are
// only ever text (esc), never markup. Funktionen → KI-Dungeon-Master, button „Regeln anpassen“, is the admin's rules editor.
const DM={on:false,data:null,rid:'',v:null,seq:0,busy:false,msg:'',err:false,made:null,at:0,ende:false,form:{},edit:'',kap:false};
const DG={code:'',v:null,info:null,busy:false,msg:'',err:false,at:0,figur:'',konto:{tok:'',v:null,step:'',adr:'',msg:'',err:false,gebunden:false}};
// read aloud (the last turn's WAV, the host's device plays it by itself) and the microphone of a seat
const DMA={gtab:'',handy:'geschichte',hzug:{p:-1,g:-1},p:{el:null,url:''},g:{el:null,url:''},rec:null,parts:[],mode:'',t0:0,voll:false,hilfe:null,modus:'',aendern:{p:0,g:0},rf:null,albseite:'',gesendet:0,mut:{p:0,g:0},kopf:false,app:false,gauf:{},ro:null,feedk:{p:'',g:''}};
// the short guide for players at the table, the basics first (Punkt 6 of the table review of 2026-10-24): a small card
// opens by itself once on this device, the pages by its button
const DMHILFE=[['Was du schreibst','What you write','Was deine Figur tut oder sagt, in ein, zwei Sätzen: „Ich schleiche zur Tür und lausche.“ Der Dungeon-Master erzählt, was daraus wird.','What your character does or says, in a sentence or two: "I sneak to the door and listen." The Dungeon Master tells what comes of it.'],
  ['Wann es weitergeht','When it goes on','Alle schreiben gleichzeitig. Haben alle gehandelt oder ist die Zugzeit um, erzählt der Dungeon-Master. „Warten auf“ zeigt, wer noch fehlt; bis dahin kannst du deine Aktion ändern. Kommt jemand mitten im Kampf dazu, wartet er am Rand, bis der Kampf vorbei ist; im ersten Zug am Tisch gibt er noch niemandem etwas. Jedes Gerät hat einen Platz.','Everyone writes at the same time. Once all have acted or the turn time is up, the Dungeon Master narrates. "Waiting for" shows who is still missing; until then you can change your action. Whoever joins during a fight waits at the edge until it is over; in their first turn at the table they give nobody anything yet. Every device has one seat.'],
  ['Das kann ich','What I can do','Dein Bogen zeigt unter „Das kann ich“ deine Fähigkeiten und die Zauber deiner Klasse. Zaubertricks gehen beliebig oft, höhere Zauber brauchen eine Ladung, die Ladungen füllen sich mit jeder Runde und jedem Kapitel. Antippen schreibt es in deine Aktion. Was dein Held noch nicht kann, gelingt nicht: dann steht eine kleine Zeile nur für dich da.','Your sheet shows your abilities and your class\'s spells under "What I can do". Cantrips work any time, higher spells need a charge, the charges fill up with every round and chapter. A tap writes it into your action. What your hero cannot do yet does not work: then a small line just for you says so.'],
  ['Würfeln und Kampf','Dice and fights','Würfeln musst du nicht, das macht das Panel: ein W20 plus der Bonus deines Werts (16 gibt +3) gegen eine Schwierigkeit. Bei Vorteil würfelt es zweimal und nimmt den besseren Wurf, bei Nachteil den schlechteren. Kommt deine Probe, tippst du auf den großen Würfel oder schüttelst das Handy: er rollt auf die Zahl des Panels, die Leiste zeigt, wie knapp es war. Trefft ihr auf Gegner, wählt das Panel sie passend zu eurer Gruppe aus dem Bestiarium, die Karte „Begegnung“ zeigt sie; ein Tipp auf einen Gegner zeigt seine Werte. Greifst du an, würfelt das Panel: W20 + Wert-Bonus + Übungsbonus gegen die Rüstungsklasse (RK) des Gegners, eine 20 trifft immer doppelt, eine 1 nie. Schaden kommt von deiner Waffe oder deinem Zauber. Danach greift jeder Gegner, der noch steht, an; die Leiste über der Geschichte zeigt ihr Leben. Am Ende gibt es die Erfahrung aus dem Bestiarium, geteilt durch die Helden.','You never roll yourself, the panel does: a d20 plus your value\'s bonus (16 gives +3) against a difficulty. With advantage it rolls twice and keeps the better roll, with disadvantage the worse. When your check comes, tap the big die or shake your phone: it rolls onto the panel\'s number, the bar shows how close it was. When you meet foes, the panel picks them from the bestiary to fit your group, the card „Encounter“ shows them; a tap on a foe shows its values. When you attack, the panel rolls: d20 + value bonus + proficiency bonus against the foe\'s armour class (AC), a 20 always hits double, a 1 never hits. Damage comes from your weapon or spell. Then every foe still standing attacks; the bar above the story shows their life. At the end you get the experience of the bestiary, divided among the heroes.'],
  ['Karte und Gewölbe','Map and vaults','Die Karte zeigt, wo ihr seid, und wächst mit, je mehr ihr entdeckt. Tippe unter „Von hier aus“ einen Weg an, dann steht er in deinem Feld. In Gewölben würfelt das Panel Fallen; die Antwort auf ein Rätsel schreibst du einfach in deine Aktion.','The map shows where you are and grows as you explore. Tap a way under "From here" to put it in your field. In vaults the panel rolls the traps; just write the answer to a riddle into your action.'],
  ['Am Boden und gefallen','Down and fallen','Bei 0 Leben liegt dein Held am Boden und kann nichts tun. Ein Freund gibt ihm mit „🧪 Heiltrank geben“ einen Trank, heilt ihn oder hilft ihm in seiner Aktion auf. Ab dem nächsten erzählten Zug würfelt das Panel für ihn jeden Zug einen Rettungswurf mit dem W20: ab 10 gelingt er, eine 1 zählt doppelt. Drei gelungene oder eine 20 und er steht mit 1 Leben wieder auf, drei misslungene und er ist gefallen: für immer, seine Dinge und sein Gold liegen unter „Liegt hier“ für die anderen. Ist er der einzige lebende Held am Tisch, fällt er nicht: ein Fremder bringt ihn in Sicherheit, er erwacht mit 1 Leben, der Kampf endet ohne EP, und er verliert die Hälfte seines Goldes und ein Ding aus der Tasche. Am Kindertisch ist er nur ohnmächtig und wacht im nächsten Kapitel ohne Gold wieder auf. Vor jedem neuen Tisch rasten die Lebenden: volles Leben, volle Ladungen.','At 0 life your hero is down and cannot do anything. A friend gives them a potion with "🧪 Give a healing potion", heals them or helps them up in their action. From the next told turn the panel rolls a death save with the d20 for them each turn: 10 or more succeeds, a 1 counts twice. Three successes or a 20 and they get up with 1 life, three failures and they have fallen: for good, their things and gold lie under "Lying here" for the others. If they are the only living hero at the table they do not fall: a stranger brings them to safety, they wake with 1 life, the fight ends without XP, and they lose half their gold and one thing from the bag. At the children\'s table they are only unconscious and wake in the next chapter without gold. Before every new table the living rest: full life, full charges.'],
  ['Schadensarten','Damage kinds','Jeder Treffer hat eine Art: 🗡️ Hieb, 🏹 Stich, 🔨 Wucht, 🔥 Feuer, ❄️ Kälte, ⚡ Blitz und mehr. Zauber treffen mit ihrer eigenen Art, Zauber ohne Schaden wie Schild greifen nicht an. Gegen eine Schwäche zählt ein Treffer doppelt, gegen Widerstand halb, gegen Immunität gar nicht; eine magische Waffe (+1 oder besser) geht durch Widerstand gegen Hieb, Stich und Wucht. Was ein Gegner verträgt, zeigt seine Karte erst nach einem Treffer oder einer gelungenen Intelligenz-Probe im Kampf. Ringe, Rüstung und Tränke mit Widerstand halbieren Treffer ihrer Art bei dir. Ein Öl aus der Tasche kommt mit „Auf die Waffe“ auf deine Waffe: drei Treffer mit seiner Art obendrauf.','Every hit has a kind: 🗡️ slashing, 🏹 piercing, 🔨 bludgeoning, 🔥 fire, ❄️ cold, ⚡ lightning and more. Spells hit with their own kind, spells without damage such as Shield do not attack. Against a weakness a hit counts double, against a resistance half, against an immunity not at all; a magic weapon (+1 or better) goes through a resistance to slashing, piercing and bludgeoning. What a foe takes its card shows only after a hit or a passed Intelligence check in a fight. Rings, armour and potions with a resistance halve hits of their kind on you. An oil from the bag goes on your weapon with "On the weapon": three hits with its kind on top.'],
  ['Kräfte und Erfahrung','Powers and experience','Manche Fähigkeiten setzt das Panel selbst um: Eisenhaut nimmt jedem Treffer 1 ab und „wirkt immer“, Schildwall fängt 1× je Szene den Treffer eines Freundes ab, Kampfschrei gibt der Gruppe +1 auf die Proben des Zugs. Nenne sie in deiner Aktion („Ich setze Schildwall ein“). Erfahrung sammelt sich am Tisch („+X EP noch am Tisch“) und zählt am Ende der Runde oder des Kapitels.','Some abilities the panel carries out itself: Iron skin takes 1 off every hit and "always works", Shield wall takes a friend\'s hit once a scene, Battle cry gives the group +1 on the turn\'s checks. Name them in your action ("I use Shield wall"). Experience gathers at the table ("+X XP still at the table") and counts at the end of the round or chapter.'],
  ['Leben, Beute, Tauschen','Life, loot, trading','Der Balken zeigt dein Leben. Beute landet in deiner Tasche (bis 12 Plätze, gleiche Tränke stapeln sich); Tränke und Zauber nutzt du dort. Tauschen geht per Angebot: erst wenn der andere annimmt, tauscht das Panel.','The bar shows your life. Loot lands in your bag (up to 12 places, the same potions stack); you use potions and spells from there. Trading works by offer: only when the other one accepts does the panel swap.'],
  ['Ausrüstung und Gewicht','Equipment and weight','„📜 Heldenbogen“ in der Seitenspalte öffnet deinen Bogen groß, ein Tipp auf ein Ding zeigt Bild, Beschreibung und Werte. Neun Plätze wie bei D&D: Ziehe ein Ding aus der Tasche auf seinen Platz oder tippe „Anlegen“. Du trägst Stärke mal 3,75 kg; ab drei Vierteln bist du belastet und würfelst Geschick mit Nachteil. Was nicht mehr passt, bleibt unter „Liegt hier“ am Boden.','"📜 Hero sheet" in the side column opens your sheet large, a tap on a thing shows its picture, description and values. Nine places as in D&D: drag a thing from the bag onto its place or tap "Equip". You carry strength times 3.75 kg; from three quarters you are burdened and roll dexterity with disadvantage. What no longer fits stays on the ground under "Lying here".'],
  ['Händler','Merchants','In Siedlungen bietet ein Händler Waren an, „⚖ Händler“ zeigt sie groß. Die Preise macht das Panel, Charisma gibt bis 20 % Rabatt; Verkaufen bringt die Hälfte. Sehr seltene Magie ist erst unerkannt: Eine Rolle des Erkennens oder der Händler nennt, was sie kann.','In settlements a merchant offers goods, "⚖ Merchant" shows them large. The panel sets the prices, Charisma gives up to 20 % off; selling fetches half. Very rare magic is unknown at first: a scroll of knowing or the merchant names what it does.'],
  ['Werte, Dinge und Werkzeuge','Values, things and tools','Tippe auf einen Wert, auf Leben, Stufe oder Rüstungsklasse: darunter steht, was es ist und wofür es zählt. Ein getragenes Ding öffnet sein Fenster mit Bild. Nennst du in deiner Aktion ein Werkzeug wie Seil oder Dietrich und passt die Probe, gibt es +2; bei einer 1 kann es zerbrechen.','Tap a value, life, level or armour class: below it says what it is and what it counts for. A worn thing opens its window with the picture. If your action names a tool like a rope or lockpick and the check fits, you get +2; on a 1 it can break.'],
  ['Warten und Tischgespräch','Waiting and table talk','Während der Dungeon-Master erzählt, zeigt der Tisch die Würfe schon vorab, dazu Wissenskarten der Welt. Im „💬 Tischgespräch“ unter dem Feld redet ihr miteinander; der Dungeon-Master liest das nie.','While the Dungeon Master narrates, the table already shows the rolls, plus lore cards of the world. In the "💬 Table talk" below the field you talk to each other; the Dungeon Master never reads it.'],
  ['Grenzen und X-Karte','Lines and X-card','Unter „🛡 Grenzen“ legst du fest, was nie vorkommt und was nur angedeutet wird; der Tisch sieht die Wörter, nie, von wem sie sind. War eine Szene zu viel, tippe auf „✖ X-Karte“: ohne Begründung und ohne Namen wird sie ruhiger neu erzählt.','Under "🛡 Lines" you set what never appears and what is only hinted at; the table sees the words, never whose they are. Was a scene too much, tap "✖ X-card": without a reason and without a name it is told again more calmly.'],
  ['Hören und Sprechen','Listen and speak','Ist Vorlesen an, tippst du einmal auf „🔊 Ton an“, danach liest jedes Gerät die Erzählung Satz für Satz von selbst vor und markiert den Satz, der gerade gesprochen wird. Was jemand wörtlich sagt, spricht die Figur, nie der Erzähler; dein Held bekommt eine eigene Stimme vorgeschlagen. Die Uhr startet erst nach dem Vorlesen. 🔈/🔇 schaltet es nur auf diesem Gerät an oder aus, „🔊 Nochmal hören“ liest den letzten Zug noch einmal. Mit 🎤 sprichst du deine Aktion; der Text landet im Feld, abgeschickt wird mit „Handeln“.','With reading aloud on, tap "🔊 Sound on" once; after that every device reads the narration sentence by sentence by itself and marks the sentence being spoken. What someone says word for word is spoken by the character, never the narrator; your hero gets a voice of its own proposed. The clock starts only after the reading. 🔈/🔇 switches it on or off on this device only, "🔊 Listen again" reads the last turn once more. With 🎤 you speak your action; the text lands in the field, "Act" sends it.'],
  ['Als Gast','As a guest','Am Ende bekommst du einen Figur-Code. Damit spielt dein Held beim nächsten Mal weiter, auch in einem eigenen Profil. Schreib ihn dir auf.','At the end you get a hero code. With it your hero plays on next time, also in a profile of your own. Write it down.']];
// the guide is a window with one page per part (Punkt 9 of the review of 2026-10-24): ‹ › or the dots page, ✕, Esc or a tap beside it closes;
// the first time on a device only a small card „So geht's“ in three sentences with „Mehr“ (Punkt 6 of the table review)
function dmHilfe(){if(DMA.hilfe===null){let seen=false;try{seen=localStorage.getItem('dm-hilfe')==='1';localStorage.setItem('dm-hilfe','1')}catch(e){}DMA.hilfe=seen?false:'kurz'}
  if(DMA.hilfe===false)return '';
  if(DMA.hilfe==='kurz')return `<div class="dm-hkurz" role="note"><div class="dm-hkurz-k"><b>❔ ${esc(t('So geht\'s','How it works'))}</b><button type="button" class="ic-ib" data-dmhilfe="zu" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>
    <p>${esc(t('Schreib ins Feld, was dein Held tut oder sagt, in ein, zwei Sätzen. Haben alle gehandelt oder ist die Zeit um, erzählt der Dungeon-Master, wie es weitergeht. Würfeln musst du nicht, das macht das Panel.','Write into the field what your hero does or says, in a sentence or two. Once everyone has acted or the time is up, the Dungeon Master tells what happens next. You do not roll dice, the panel does.'))}</p>
    <button type="button" class="b" data-dmhilfe="0">${esc(t('Mehr','More'))} ›</button></div>`;const n=DMHILFE.length,i=Math.max(0,Math.min(n-1,+DMA.hilfe||0)),x=DMHILFE[i],titel='❔ '+t('So spielst du','How to play');
  return `<div class="dm-fen dm-fen-hilfe" data-dmfenbg="hilfe"><div class="dm-fen-box" role="dialog" aria-modal="true" aria-label="${esc(titel)}">
    <div class="dm-fen-kopf"><h3>${esc(titel)}</h3><button type="button" class="ic-ib" data-dmhilfe="zu" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>
    <div class="dm-fen-body dm-hseite"><small class="mut">${esc(t('Seite '+(i+1)+' von '+n,'Page '+(i+1)+' of '+n))}</small><h4>${esc(t(x[0],x[1]))}</h4><p>${esc(t(x[2],x[3]))}</p></div>
    <div class="dm-hnav"><button type="button" class="b" data-dmhilfe="${i-1}"${i?'':' disabled'}>‹ ${esc(t('Zurück','Back'))}</button><span class="dm-hpunkte">${DMHILFE.map((y,k)=>`<button type="button" class="${k===i?'on':''}" data-dmhilfe="${k}" title="${esc(t(y[0],y[1]))}" aria-label="${esc(t(y[0],y[1]))}"></button>`).join('')}</span><button type="button" class="b p" data-dmhilfe="${i<n-1?i+1:'zu'}">${esc(i<n-1?t('Weiter','Next')+' ›':t('Fertig','Done'))}</button></div></div></div>`}
const dmHilfeAuf=w=>DMA.hilfe=w==='zu'?false:Math.max(0,Math.min(DMHILFE.length-1,+w||0));
// the table alone, filling the screen (the button again, Esc or leaving the browser's full screen ends it; without the browser's full screen, as on the iPhone, it fills the window)
function dmVoll(on){DMA.voll=on;const f=document.querySelector('[data-dmvoll]'),w=f&&f.closest('.dm');if(w)w.classList.toggle('dm-voll',on);
  try{if(on&&w&&w.requestFullscreen&&!document.fullscreenElement)w.requestFullscreen().catch(()=>{});if(!on&&document.fullscreenElement)document.exitFullscreen()}catch(e){}
  document.querySelectorAll('.dm [data-dmvoll]').forEach(b=>b.outerHTML=dmVollKnopf())}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&DMA.voll)dmVoll(false)});
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&DMA.voll)dmVoll(false)});
const dmWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const dmLang=()=>L==='en'?'en':'de';
// the look of the whole game page (Dominik 2026-10-23): the dark vault or the light parchment, in the colours of the world;
// the device's or the panel's setting first, a choice by the button kept on this device
function dmHell(){let m=DMA.modus;if(!m)try{m=localStorage.getItem('dm-modus')||''}catch(e){}if(m)return m==='hell';
  const th=document.documentElement.dataset.theme;return th?th==='light':!(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)}
function dmLook(w,farben){if(!w)return;w.classList.add('dm-tisch');w.classList.toggle('dm-hell',dmHell());
  w.style.cssText=Object.entries(farben||{}).filter(([k,x])=>/^#[0-9a-fA-F]{6}$/.test(x)).map(([k,x])=>`--w-${k}:${x}`).join(';')}
const dmModus=()=>`<button type="button" class="b dm-modus" data-dmmodus="1" title="${esc(t('Hell oder dunkel, dieses Gerät merkt es sich','Light or dark, this device keeps it'))}">${esc(dmHell()?'☾ '+t('Dunkel','Dark'):'☀ '+t('Hell','Light'))}</button>`;
document.body.addEventListener('click',e=>{if(!e.target.closest('[data-dmmodus]'))return;DMA.modus=dmHell()?'dunkel':'hell';try{localStorage.setItem('dm-modus',DMA.modus)}catch(x){}
  document.querySelectorAll('.dm.dm-tisch').forEach(w=>w.classList.toggle('dm-hell',DMA.modus==='hell'));document.querySelectorAll('[data-dmmodus]').forEach(b=>b.outerHTML=dmModus())});
const dmWelt=(w,id)=>(w&&w.welten||[]).find(x=>x.id===id)||(w&&w.welten||[])[0]||{};
const dmTop=sub=>`<div class="dm-head dm-top"><div class="dm-htitle"><h3>⚔ ${esc(t('Dungeon-Master','Dungeon Master'))}</h3><small class="mut">${esc(sub)}</small></div>${dmModus()}${dmVollKnopf()}</div>`;
// „⛶ Vollbild“ on the overview too, not only at the table (Dominik 2026-10-24 „ebenso fehlt hier bereits der fullscreen modus“)
const dmVollKnopf=()=>`<button type="button" class="b dm-full" data-dmvoll="${DMA.voll?0:1}">${esc(DMA.voll?'✕ '+t('Vollbild aus','Exit full screen'):'⛶ '+t('Vollbild','Full screen'))}</button>`;
// a card to choose (world, story, tone, people, class): picture, name, one line
const dmCard=(attr,on,ic,name,sub)=>`<button type="button" class="dm-card${on?' on':''}" ${attr}><span class="dm-ic" aria-hidden="true">${esc(ic||'')}</span><b>${esc(name)}</b>${sub?`<small>${esc(sub)}</small>`:''}</button>`;
// a world's card on the new round's form: its title picture (landscape, Dominik 2026-10-24 „3“) once painted, else the sign
const dmWCard=(x,on)=>x.bild?`<button type="button" class="dm-card dm-wcard${on?' on':''}" data-dmseg="${esc(x.id)}">${dmPic(x.bild,x.name,'dm-wpic',x.zeichen)}<b>${esc(x.name)}</b>${x.satz?`<small>${esc(x.satz)}</small>`:''}</button>`
  :dmCard(`data-dmseg="${esc(x.id)}"`,on,x.zeichen,x.name,x.satz);
// the colour of a rarity (app.css), named here in full so every class is found
const DMSEL={gewoehnlich:'dm-s0',selten:'dm-s1',rar:'dm-s2',episch:'dm-s3',legendaer:'dm-s4'};
// the menu entry only for a signed-in profile the admin released the game for (start.js, like the Wissensbuch)
window.dmStart=who=>{DM.on=!!(who&&who.profile&&who.dungeon);
  document.querySelectorAll('nav button[data-s=dungeon]').forEach(b=>b.hidden=!DM.on)};
function dmOpen(){if(!PROFILE)return;const root=$('dmroot'),box=$('dmbox');if(box){box.hidden=true;$('dungeon').appendChild(box)}root.textContent='';
  const body=k=>()=>{const w=document.createElement('div');w.className='dm';w.id='dmview';w.dataset.tab=k;dmPaint(w);return w};
  root.appendChild(icTabs('dungeon',[{k:'runden',label:OWN_PAGES.dmbox[2],body:body('runden')},{k:'helden',label:t('Helden','Heroes'),body:body('helden')},...(ADMIN?[{k:'regeln',label:t('Regeln','Rules'),body:dmRulesBox}]:[])]));
  dmLoad()}
window.dmOpen=dmOpen;
async function dmLoad(){if(!DM.on)return;const seq=++DM.seq;const {r,d}=await apiTry('/api/profile/dungeon?lang='+dmLang());if(seq!==DM.seq)return;
  if(r.ok){DM.data=d;DM.err=false;DM.msg=''}else{DM.msg=dmErr(r.status,d.detail);DM.err=true}
  if(DM.rid&&!(DM.data&&DM.data.runden||[]).some(x=>x.rid===DM.rid)){DM.rid='';DM.v=null}
  if(DM.rid)await dmRound();else dmDraw()}
async function dmRound(){if(!DM.rid)return;const seq=++DM.seq;const {r,d}=await apiTry('/api/profile/dungeon/'+DM.rid);if(seq!==DM.seq)return;
  if(r.ok){DM.v=d;DM.at=Date.now()}else{DM.rid='';DM.v=null;DM.msg=dmErr(r.status,d.detail);DM.err=true}dmDraw();
  if(!r.ok){const m=document.querySelector('#dmview .dmmsg');if(m)m.scrollIntoView({block:'center',behavior:'smooth'})}}
function dmDraw(){const w=$('dmview');if(w)dmPaint(w)}
function dmPaint(w){const D=DM.data;w.classList.toggle('dm-voll',!!DMA.voll);w.classList.remove('dm-amtisch');delete w.dataset.welt;dmLook(w,D&&dmWelt(D.wahl,DM.welt).farben);
  if(!D){w.innerHTML=`<div class="ld-empty mut">${esc(DM.err?DM.msg:t('Lade den Dungeon-Master …','Loading the Dungeon Master …'))}</div>`;return}
  if(w.dataset.tab==='helden'){w.innerHTML=`<div class="dm-mitte">${dmTop(t('Deine Helden','Your heroes'))+dmHeroes(D)+dmMsg(DM)}</div>`;return}
  if(DM.v){dmTable(w,DM.v,'p');return}
  w.innerHTML=`<div class="dm-mitte">${dmTop(t('Runden, Kampagnen und eine neue Runde','Rounds, campaigns and a new round'))+dmRounds(D)+dmCampaigns(D)+dmNew(D)+dmMsg(DM)}</div>`;dmDingFill(w,'p')}
const dmMsg=S=>`<div class="dmmsg ${S.err?'err':'mut'}" role="status">${esc(S.msg)}</div>`;
// a refusal of the panel as a sentence with what to do: the reason word of the rule (dungeon._http, one per raise in
// dungeon*.py, test_dungeon checks every one has its sentence) or the coarse word
// the host hides a line of table talk or an action (Punkt 13 of 2026-10-24); only on the own page, a guest never hosts
const dmHide=(v,art,n,pid)=>v.gastgeber?`<button type="button" class="ic-ib dm-hide" data-dmhide="${art}" data-n="${n}"${pid?` data-pid="${esc(pid)}"`:''} title="${esc(t('Für alle ausblenden','Hide for everyone'))}" aria-label="${esc(t('Für alle ausblenden','Hide for everyone'))}">⊘</button>`:'';
const DMGRUND={
  'heiler':['Der Heiler findet keine Wunde mit einer Folge, die er nehmen könnte.','The healer finds no wound with a consequence to take.'],
  'gefaehrte':['Diesen Gefährten gibt es hier nicht oder er ist schon dabei.','This companion is not here or already with you.'],
  'gefaehrten':['Die Gruppe ist voll: höchstens zwei Gefährten und vier zusammen.','The group is full: at most two companions and four together.'],
  'personen aus':['Der Personen-Katalog ist auf diesem Spark aus.','The people catalog is off on this Spark.'],
  'wunsch aus':['Herzenswünsche sind auf diesem Spark aus.','Heart\'s wishes are off on this Spark.'],
  'wunsch':['Der Wunsch passt so nicht: einer aus der Liste oder eigene Worte mit 3 bis 160 Zeichen.','The wish does not fit like that: one of the list or own words of 3 to 160 characters.'],
  'fluestern aus':['Flüstern ist auf diesem Spark aus.','Whispering is off on this Spark.'],
  'fluestern auto':['Aus dem Auto wird nicht geflüstert.','No whispering from the car.'],
  'fluestern oft':['In diesem Zug hast du schon geflüstert. Im nächsten Zug wieder.','You already whispered this turn. Again next turn.'],
  'figur':['Diese Figur ist gerade nicht in der Szene.','This person is not in the scene right now.'],
  'stumm figur':['Die Figur schweigt. Versuch es im nächsten Zug noch einmal.','The person stays silent. Try again next turn.'],
  'chronik aus':['Das Chronikbuch ist auf diesem Spark aus.','The chronicle is off on this Spark.'],
  'seite':['Diese Seite der Chronik gibt es nicht mehr.','This page of the chronicle no longer exists.'],
  'pdf':['Für das PDF fehlt auf diesem Spark die PDF-Bibliothek (fpdf2).','The PDF library (fpdf2) is missing on this Spark.'],
  'rast aus':['Die Rast ist auf diesem Spark aus.','Resting is off on this Spark.'],
  'rune':['Diese Rune hast du nicht oder das Ding gehört nicht dir.','You do not have this rune or the thing is not yours.'],
  'rune aus':['Runen und Sockel sind auf diesem Spark gerade aus.','Runes and sockets are switched off on this Spark right now.'],
  'rune kampf':['Erst der Kampf: Solange er läuft, setzt niemand eine Rune ein.','First the fight: nobody sets a rune while it runs.'],
  'rune sockel':['Das passt dort nicht: ein Ding mit freiem Sockel, an dem diese Rune wirkt.','That does not fit there: a thing with a free socket where this rune works.'],
  'rune voll':['Jeder Sockel dieses Dings ist schon belegt.','Every socket of this thing is taken already.'],
  'rune deckel':['Zu stark: Mit dieser Rune wäre das Ding stärker als „episch“ oder über einem Deckel. Die Vorschau sagt, welcher.','Too strong: with this rune the thing would be stronger than "epic" or above a cap. The preview says which.'],
  'markt kampf':['Erst der Kampf: Solange er läuft, gibt es keinen Markt, kein Kaufen und kein Verkaufen.','First the fight: while it runs there is no market, no buying and no selling.'],
  'rast kampf':['Mitten im Kampf rastet niemand.','Nobody rests in the middle of a fight.'],
  'rast schon':['Die Gruppe rastet schon; der nächste Zug erzählt das Lager.','The group is resting already; the next turn tells the camp.'],
  'rast kurz':['Zwei kurze Rasten sind vorbei; erst nach einer langen Rast wieder.','Two short rests are used; only again after a long rest.'],
  'rast lang':['Die letzte lange Rast ist noch nicht lange genug her.','The last long rest was not long enough ago.'],
  'platz falsch':['Das passt dort nicht hin: Jedes Ding gehört an seinen Körperteil (Gürtel an den Gürtel, Waffe in die Haupthand, Amulett an den Hals). Beim Ziehen leuchten die passenden Felder.','That does not go there: every item belongs on its body part (a belt at the belt, a weapon in the main hand, an amulet at the neck). While you drag, the fitting places light up.'],
  'wortliste':['Das geht an diesem Tisch nicht: Ein Wort steht auf der Wortliste der Runde (Ton, „nie“, Tabus der Geschichte oder Grenzen am Tisch). Formuliere es anders.','That does not work at this table: a word is on the round\'s word list (tone, "never", the story\'s taboos or the table\'s lines). Put it another way.'],
  'grenzen':['Die Grenzen passen so nicht: kurze Wörter, mit Komma getrennt.','The lines do not fit like that: short words, separated by commas.'],
  'zufall':['Eine Zufallsregel passt so nicht: Name, Chance von 1 bis 100, Zahl im Bereich der Wirkung, ein Hinweis braucht einen Satz.','A random rule does not fit like that: name, chance from 1 to 100, number in the effect\'s range, a hint needs a sentence.'],
  'fraktion':['Eine Fraktion passt so nicht: Name mit 2 bis 30 Zeichen, Felder 4, 6 oder 8, ein Schritt vor oder zurück.','A faction does not fit like that: a name of 2 to 30 characters, 4, 6 or 8 segments, one step forward or back.'],
  'quest':['Das geht mit diesem Ding nicht: geben nur, was du trägst, an einen Helden am Tisch; aufheben nur, was hier liegt.','That does not work with this thing: give only what you carry, to a hero at the table; pick up only what lies here.'],
  'quest voll':['Die Runde hat schon zwölf besondere Dinge.','The round already has twelve special things.'],
  'quest aus':['Quest-Gegenstände sind auf diesem Spark gerade aus.','Quest items are switched off on this Spark right now.'],
  'fraktionen aus':['Fraktionen sind auf diesem Spark gerade aus.','Factions are switched off on this Spark right now.'],
  'fraktionen voll':['Es gibt schon sechs Fraktionen; nimm erst eine heraus.','There are six factions already; take one out first.'],
  'zufall aus':['Zufallsregeln sind auf diesem Spark gerade aus.','Random rules are switched off on this Spark right now.'],
  'orakel':['So fragt das Orakel nicht: eine Frage oder bis zu drei Tabellen, das Chaos von 1 bis 9.','The oracle does not take that: a question or up to three tables, the chaos from 1 to 9.'],
  'orakel aus':['Das Orakel ist auf diesem Spark gerade aus.','The oracle is switched off on this Spark right now.'],
  'orakel oft':['Das Orakel hat in diesem Zug genug gesagt. Im nächsten Zug wieder.','The oracle has said enough this turn. Again next turn.'],
  'grenzen aus':['Grenzen und X-Karte sind auf diesem Spark gerade aus.','Lines and the X-card are switched off on this Spark right now.'],
  'xkarte wartet':['Die X-Karte geht gleich wieder: der Dungeon-Master erzählt gerade.','The X-card works again in a moment: the Dungeon Master is telling right now.'],
  'xkarte oft':['Die X-Karte wurde eben erst gelegt. In einer Minute geht sie wieder.','The X-card was laid just now. It works again in a minute.'],
  'rand':['Dein Held wartet am Rand, bis der Kampf vorbei ist. Danach kommt er an den Tisch und kann handeln.','Your hero waits at the edge until the fight is over. Then they come to the table and can act.'],
  'neu':['Im ersten Zug am Tisch kann dein Held noch niemandem etwas geben, keinen Trank für andere und keinen Tausch. Ab dem nächsten Zug geht es.','In their first turn at the table your hero cannot give anyone anything yet, no potion for others and no trade. From the next turn on it works.'],
  'geraet':['Auf diesem Gerät spielt schon ein Held in dieser Runde. Jedes Gerät hat einen Platz.','A hero of this round already plays on this device. Every device has one seat.'],
  'weiter':['Dieser Mail-Link galt nur einmal und nur kurz. Öffne deinen Platz-Link oder warte auf die nächste Mail.','This mail link was valid only once and only for a while. Open your seat link or wait for the next mail.'],
  'boden':['Dein Held liegt am Boden und kann gerade nichts tun. Ein Freund kann ihm einen Heiltrank geben oder ihm aufhelfen.','Your hero is down and cannot do anything right now. A friend can give them a healing potion or help them up.'],
  'ohnmacht':['Dein Held ist ohnmächtig und wacht am nächsten Tisch wieder auf, im nächsten Kapitel.','Your hero is unconscious and wakes at the next table, in the next chapter.'],
  'tot':['Dieser Held ist gefallen und spielt nicht mehr. Wähle einen anderen Helden.','This hero has fallen and plays no more. Pick another hero.'],
  'stumm':['Der Gastgeber hat dich im Tischgespräch stummgeschaltet. Deine Aktionen gehen weiter.','The host muted you in the table talk. Your actions go on.'],
  'zeile':['Diese Zeile gibt es nicht mehr.','This line is gone.'],
  'eintrag':['Diesen Eintrag gibt es nicht mehr. Lade die Liste neu.','This entry is gone. Reload the list.'],
  'adresse':['Diese E-Mail-Adresse passt nicht. Prüfe sie, beim Einschalten der Zug-Mails muss es die Adresse deines Gast-Kontos sein.','This e-mail address does not fit. Check it; for turn mails it must be the address of your guest account.'],
  'code':['Der Code passt nicht oder ist abgelaufen. Fordere einen neuen an.','The code does not fit or has expired. Ask for a new one.'],
  'konto':['Dein Gast-Konto ist auf diesem Gerät nicht mehr angemeldet. Melde dich mit deiner Adresse neu an.','Your guest account is no longer signed in on this device. Sign in again with your address.'],
  'codes':['Für diese Adresse kamen in der letzten Stunde schon genug Codes. Nimm den letzten oder warte eine Stunde.','Enough codes went to this address in the last hour. Use the last one or wait an hour.'],
  'mails':['Der Spark hat heute schon so viele Mails fürs Spiel geschickt, wie gehen. Morgen klappt es wieder.','The Spark has sent as many game mails today as allowed. It works again tomorrow.'],
  'konten':['Auf diesem Spark gibt es schon so viele Gast-Konten, wie gehen.','This Spark already has as many guest accounts as allowed.'],
  'postfach':['Für Gast-Mails ist noch kein Postfach gewählt. Bitte den Gastgeber, das beim Admin einzurichten.','No mailbox is chosen for guest mails yet. Ask the host to have the admin set it up.'],
  'mail':['Die Mail ging gerade nicht raus. Probiere es gleich noch einmal.','The mail did not go out right now. Try again shortly.'],
  'notaus':['Der Spark hält gerade alle Aktionen an (Notaus).','The Spark holds every action right now (emergency stop).'],
  'profil':['Du spielst mit deinem Profil, deine Helden bleiben dort.','You play with your profile, your heroes stay there.'],
  'aus':['Gast-Konten sind auf diesem Spark gerade aus.','Guest accounts are switched off on this Spark right now.'],
  'held spielt':['Dieser Held spielt gerade in einer anderen Runde. Beende sie dort oder wähle einen anderen Helden.','This hero is playing in another round right now. End it there or pick another hero.'],
  'mehrzeit':['Du hast in diesem Zug schon eine Minute mehr bekommen.','You already got one more minute this turn.'],
  'besetzt':['Dieser Platz ist schon besetzt, oder du sitzt schon an diesem Tisch.','This seat is taken already, or you already sit at this table.'],
  'runden':['Du hast schon so viele offene Runden, wie gehen. Beende eine alte Runde, dann klappt es.','You already have as many open rounds as allowed. End an old round, then it works.'],
  'helden':['Deine Heldenliste ist voll. Lösche einen alten Helden oder spiele mit einem vorhandenen.','Your hero list is full. Delete an old hero or play with one you have.'],
  'kampagnen':['Du hast schon so viele Kampagnen, wie gehen. Lösche eine alte Kampagne.','You already have as many campaigns as allowed. Delete an old campaign.'],
  'geschichten':['Die Liste der Geschichten ist voll. Lösche zuerst eine.','The list of stories is full. Delete one first.'],
  'figuren':['Gerade warten zu viele Figur-Codes. Probiere es später noch einmal.','Too many hero codes are waiting right now. Try again later.'],
  'voll':['Alle Plätze dieser Runde sind belegt.','All seats of this round are taken.'],
  'fall':['Diesen Erzähler-Fehler gibt es nicht mehr; lade die Seite neu.','This narrator error no longer exists; reload the page.'],
  'angebote':['Es warten schon genug Tauschangebote. Warte, bis eines angenommen oder abgelehnt ist.','Enough trade offers are waiting already. Wait until one is accepted or declined.'],
  'runde':['Diese Runde gibt es nicht mehr oder sie ist vorbei.','This round is gone or over.'],
  'held':['Diesen Helden gibt es nicht, oder Name, Volk oder Klasse fehlen.','This hero does not exist, or name, people or class are missing.'],
  'gastgeber':['Das darf nur der Gastgeber der Runde.','Only the host of the round may do this.'],
  'platz':['Du sitzt nicht an diesem Tisch.','You do not sit at this table.'],
  'geschichte':['Diese Geschichte gibt es nicht mehr oder sie ist nicht fertig.','This story is gone or not finished.'],
  'kampagne':['Diese Kampagne gibt es nicht mehr.','This campaign is gone.'],
  'kapitel laeuft':['Das nächste Kapitel läuft schon. Öffne es aus deinen Runden.','The next chapter is running already. Open it from your rounds.'],
  'name':['Diesen Namen hat schon jemand am Tisch. Nimm einen anderen.','Someone at the table has this name already. Pick another one.'],
  'name doppelt':['Diesen Namen hat schon jemand am Tisch. Nimm einen anderen.','Someone at the table has this name already. Pick another one.'],
  'zug':['Der Zug ist gerade zu, der Dungeon-Master erzählt. Gleich bist du wieder dran.','The turn is closed, the Dungeon Master is narrating. Your turn comes back shortly.'],
  'alter zug':['Der Zug ist gerade zu. Gleich geht es weiter.','The turn is closed right now. It goes on shortly.'],
  'pause':['Das Sprachmodell oder die Musik ist gerade pausiert. Probiere es später noch einmal.','The language model or the music is paused right now. Try again later.'],
  'wartung':['Bilder sind gerade pausiert. Probiere es später noch einmal.','Pictures are paused right now. Try again later.'],
  'zeit':['Das Bild hat zu lange gedauert. Probiere es noch einmal.','The picture took too long. Try again.'],
  'bisher':['Die Zusammenfassung wird gerade geschrieben oder passt nicht. Einen Moment, dann noch einmal.','The summary is being written or does not fit. Wait a moment, then try again.'],
  'vorschlag':['Das Modell hat keinen brauchbaren Vorschlag geliefert. Bitte noch einmal.','The model gave no usable proposal. Please try again.'],
  'figur':['Der Figur-Code passt nicht oder wurde schon benutzt.','The hero code does not fit or was used already.'],
  'figur-code':['Der Figur-Code passt nicht oder wurde schon benutzt.','The hero code does not fit or was used already.'],
  'leer':['Da steht noch nichts. Schreib erst etwas hinein.','There is nothing yet. Write something first.'],
  'keine aktion':['Schreib erst, was dein Held tut.','First write what your hero does.'],
  'tasche voll':['Deine Tasche ist voll. Leg erst etwas ab oder verkaufe es.','Your bag is full. Put something down or sell it first.'],
  'passt nicht':['Das passt nicht zu deiner Klasse oder an diesen Platz.','That does not fit your class or this place.'],
  'an':['Der andere Held kann das gerade nicht nehmen, seine Tasche ist voll oder zu schwer.','The other hero cannot take it right now, the bag is full or too heavy.'],
  'kaufen':['Dafür reicht dein Gold nicht, oder der Händler hat es nicht mehr.','You do not have enough gold, or the merchant no longer has it.'],
  'verkaufen':['Das kauft der Händler nicht.','The merchant does not buy that.'],
  'verbessern':['Das kann der Schmied nicht besser machen: nur Waffen und Rüstung ohne feste Seltenheit, höchstens bis episch.','The smith cannot make that better: only weapons and armour without a fixed rarity, at most up to epic.'],
  'kasse':['So viel Gold hat der Händler nicht mehr. Kauf erst etwas bei ihm oder komm am nächsten Ort wieder.','The merchant has no more gold for that. Buy something from them first or come back at the next place.'],
  'erkennen':['Das kann der Händler gerade nicht erkennen, oder dein Gold reicht nicht.','The merchant cannot identify this right now, or your gold is not enough.'],
  'haendler':['Gerade ist kein Händler da.','There is no merchant here right now.'],
  'kein trank':['Das ist kein Trank.','That is no potion.'],
  'kein oel':['Das ist kein Öl für eine Waffe.','That is no oil for a weapon.'],
  'keine waffe':['Dafür braucht dein Held eine Waffe in der Haupthand.','Your hero needs a weapon in the main hand for that.'],
  'kein zauber':['Das ist kein Zauber.','That is no spell.'],
  'punkt':['Dafür hast du keinen Wertpunkt frei, oder der Wert ist schon ganz oben.','You have no value point for that, or the value is at the top already.'],
  'faehigkeit':['Diese Fähigkeit steht gerade nicht zur Wahl.','This ability is not on offer right now.'],
  'fallen':['Das kannst du hier nicht ablegen.','You cannot put that down here.'],
  'aufheben':['Das liegt nicht mehr hier, oder deine Tasche ist voll.','That is no longer here, or your bag is full.'],
  'ablegen':['An diesem Platz trägst du nichts.','You wear nothing in this place.'],
  'tausch':['Dieser Tausch geht so nicht.','This trade does not work like that.'],
  'angebot':['Dieses Tauschangebot passt nicht mehr: einer hat die Dinge oder das Gold nicht mehr.','This trade offer no longer fits: someone no longer has the things or the gold.'],
  'stimme':['Diese Stimme gibt es nicht, oder die Sprachausgabe kann sie nicht machen.','This voice does not exist, or the speech output cannot make it.'],
  'geschlecht':['Bitte männlich, weiblich oder divers wählen.','Please pick male, female or non-binary.'],
  'ton':['Diese Aufnahme gibt es nicht mehr.','This recording is gone.'],
  'bild':['Dieses Bild gibt es nicht mehr.','This picture is gone.'],
  'stueck':['Dieses Musikstück gibt es nicht mehr.','This piece of music is gone.'],
  'erzaehlung':['Diese Erzählung gibt es nicht mehr.','This narration is gone.'],
  'termin':['Dieser Termin passt nicht: er muss in der Zukunft liegen.','This date does not fit: it must lie in the future.'],
  'daumen':['Das ging nicht.','That did not work.'],
  'aktion':['Diese Aktion gibt es nicht mehr zum 👍, nur die der letzten drei Züge.','This action can no longer get a 👍, only those of the last three turns.'],
  'heldenmut':['Heldenmut ist gerade aus.','Heroic courage is off right now.'],
  'gold':['Dafür reicht dein Gold nicht, oder „Gold mit Zweck“ ist gerade aus.','Your gold is not enough for that, or "Gold with a purpose" is off right now.'],
  'dienst':['Dieses Angebot gibt es hier nicht.','That offer is not here.'],
  'siedlung':['Das gibt es nur in einer Siedlung oder beim Händler, nicht im Kampf.','Only in a settlement or at a merchant, not in a fight.'],
  'nacht':['Nachts haben die Läden zu. Das Gasthaus ist offen.','At night the shops are shut. The inn is open.'],
  'gasthaus':['Heute habt ihr schon im Gasthaus geruht.','You have rested at the inn today already.'],
  'schmied':['Der Schmied kann das nicht flicken, oder deine Tasche ist voll.','The smith cannot mend that, or your bag is full.'],
  'lehre':['Diese Lehrstunde hast du schon.','You have that lesson already.'],
  'geruecht':['Hier gibt es kein neues Gerücht.','No new rumour here.'],
  'was':['Das ging nicht.','That did not work.'],
  'eingabe':['Die Eingabe passt nicht. Prüfe die Felder.','The input does not fit. Check the fields.'],
  'nicht da':['Das gibt es nicht mehr.','That is gone.']};
const dmErr=(status,d)=>typeof d==='string'&&DMGRUND[d]?t(...DMGRUND[d]):errSay(status,d,'');
function dmSay(S,x,err){S.msg=String(x||'').slice(0,300);S.err=!!err;document.querySelectorAll(S===DM?'#dmview .dmmsg':'#dgcard .dmmsg').forEach(m=>{m.className='dmmsg '+(err?'err':'mut');m.textContent=S.msg})}
function dmRounds(D){const st={laeuft:t('läuft','running'),ende:t('beendet','ended')};
  if(!D.runden.length)return `<div class="ic-empty">${esc(t('Noch keine Runde. Leg unten eine an und lade bis zu vier Mitspieler ein, auch Leute ohne Profil.','No round yet. Start one below and invite up to four players, also people without a profile.'))}</div>`;
  return `<h3 class="sec">${esc(t('Deine Runden','Your rounds'))}</h3><div class="ic-list">${D.runden.map(x=>`<div class="ic-row"><span class="dm-ic" aria-hidden="true">${esc(dmWelt(D.wahl,x.welt).zeichen||'')}</span><div class="ic-rmid"><span class="ic-t">${esc(x.titel)}</span><small class="ic-meta">${x.pause?`<b class="dm-pausepill">⏸ ${esc(t('Pause','paused'))}</b>`:esc(st[x.status]||x.status)} · ${esc(t('Zug','Turn'))} ${x.zug} · ${x.spieler} ${esc(t('Spieler','players'))}${x.held?' · '+esc(x.held):''}${x.gastgeber?' · '+esc(t('du leitest','you host')):''}${(x.ehrungen||[]).length?`<span class="dm-ehrz">🏅 ${x.ehrungen.map(e=>esc(e.titel+': '+e.name)).join(' · ')}</span>`:''}</small></div><button type="button" class="b p" data-dmopen="${esc(x.rid)}">${esc(t('Öffnen','Open'))}</button>${dmRowWeg(x)}</div>`).join('')}</div>`}
// every round of the list can end or go (Dominik 2026-10-25 „runden sollen immer löschbar bzw. beendbar sein. mit nachfrage
// wirklich.“): the host ends a running round or deletes it at once, deletes an ended one; a player hides an ended one.
// The first tap asks „Wirklich …?“, the second does it.
const DMWEG={ende:['Beenden','End','Wirklich beenden?','Really end?'],loeschen:['Löschen','Delete','Wirklich löschen?','Really delete?'],weg:['Ausblenden','Hide','Wirklich ausblenden?','Really hide?']};
function dmRowWeg(x){const w=x.status==='ende'?[x.gastgeber?'loeschen':'weg']:x.gastgeber?['ende','loeschen']:[];
  return w.map(k=>{const q=DM.del===x.rid+'|'+k,L=DMWEG[k];return `<button type="button" class="b${k==='ende'?'':' danger'}${q?' on':''}" data-dmdel="${esc(x.rid)}" data-was="${k}">${esc(q?t(L[2],L[3]):t(L[0],L[1]))}</button>`}).join('')}
// an ended round: the host deletes it, a player takes it off the own list (second tap confirms)
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmkann]');if(!b)return;const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
  ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+b.dataset.dmkann;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmdel]');if(!b)return;const rid=b.dataset.dmdel,k=rid+'|'+(b.dataset.was||'');
  if(DM.del!==k){DM.del=k;dmDraw();return}DM.del='';const x=await dmSend(`/api/profile/dungeon/${rid}`+(b.dataset.was==='loeschen'?'?loeschen=1':''),null,DM);if(x)DM.data=x;dmDraw()});
// campaigns (Stufe 2): a chapter closed keeps „Bisher geschah“, the heroes and the guests' heroes for the next one
function dmCampaigns(D){const ks=D.kampagnen||[];if(!ks.length)return '';
  return `<h3 class="sec">${esc(t('Kampagnen','Campaigns'))} · ${ks.length}/${D.kampagnen_max}</h3><div class="dm-kamp">${ks.map(k=>{const ed=DM.edit===k.kid;
    const who=[...k.helden,...k.gaeste.map(n=>n+' ('+t('Gast','guest')+')')].join(', ');
    const cov=(k.titelbilder||[]).slice(-1)[0];
    return `<div class="dm-k">${cov?`<img class="dm-kbild" alt="" loading="lazy" src="/api/profile/dungeon/kampagne/${esc(k.kid)}/bild/${cov}">`:''}<div class="dm-khead"><div><b>${esc(k.titel)}</b><small class="mut">${esc(k.welt)} · ${esc(t('Kapitel','Chapter'))} ${k.kapitel}${who?' · '+esc(who):''}</small></div></div>
    ${(k.orte||[]).length?`<small class="mut dm-korte">${esc(t('Karte: ','Map: ')+k.orte.join(' → '))}</small>`:''}
    <div class="lbl">${esc(t('Bisher geschah','The story so far'))}${k.entwurf&&!k.schreibt?' · '+esc(t('Entwurf','draft')):''}</div>
    ${k.schreibt?`<p class="mut dm-bisher">${esc(t('Der Dungeon-Master schreibt die Zusammenfassung …','The Dungeon Master is writing the summary …'))}</p>`
      :ed?`<textarea class="dm-kedit" rows="5" maxlength="${D.bisher_max}" aria-label="${esc(t('Bisher geschah','The story so far'))}">${esc(k.bisher)}</textarea>`
      :`<p class="dm-bisher">${esc(k.bisher)}</p>`}
    <div class="dm-hostb">${ed?`<button type="button" class="b p" data-dmksave="${esc(k.kid)}">${esc(t('Speichern','Save'))}</button><button type="button" class="b" data-dmkedit="">${esc(t('Abbrechen','Cancel'))}</button>`
      :`<button type="button" class="b p" data-dmkweiter="${esc(k.kid)}"${k.schreibt?' disabled':''}>▶ ${esc(t('Kapitel '+(k.kapitel+1)+' beginnen','Start chapter '+(k.kapitel+1)))}</button><button type="button" class="b" data-dmkedit="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmkneu="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Neu schreiben lassen','Write it again'))}</button>${k.buch?`<button type="button" class="b" data-dmkbuch="${esc(k.kid)}">📖 ${esc(t('Chronik','Chronicle'))} · ${k.buch}</button>`:''}<button type="button" class="b danger" data-dmkdel="${esc(k.kid)}">${esc(t('Löschen','Delete'))}</button>`}</div>${DM.buch&&DM.buch.kid===k.kid?dmBuch(DM.buch):''}</div>`}).join('')}</div>`}
// Chronikbuch (D&D idea 11, dungeon_chronik): one page per chapter to turn, the PDF made on the Spark, a page away
function dmBuch(B){const s=B.d.seiten||[],i=Math.max(0,Math.min(B.i,s.length-1)),x=s[i];if(!x)return `<p class="mut">${esc(t('Die Chronik ist leer.','The chronicle is empty.'))}</p>`;
  return `<div class="dm-buch"><div class="dm-buchkopf"><button type="button" class="b" data-dmkblatt="-1"${i?'':' disabled'} aria-label="${esc(t('Seite zurück','Page back'))}">‹</button><b>${esc(t('Kapitel','Chapter'))} ${x.kapitel} · ${esc(x.titel)}</b><small class="mut">${i+1}/${s.length}</small><button type="button" class="b" data-dmkblatt="1"${i<s.length-1?'':' disabled'} aria-label="${esc(t('Seite vor','Page forward'))}">›</button></div>
  ${x.bild?`<img class="dm-kbild" alt="" loading="lazy" src="${esc(x.bild)}">`:''}<small class="mut">${x.zuege} ${esc(t('Züge','turns'))}</small>
  ${x.bisher?`<div class="lbl">${esc(t('Bisher geschah','The story so far'))}</div><p>${esc(x.bisher)}</p>`:''}
  <div class="lbl">${esc(t('Helden','Heroes'))}</div>${x.helden.map(h=>`<p>${esc(h.name)} · ${esc(h.volk)} ${esc(h.klasse)}, ${esc(t('Stufe','level'))} ${h.stufe}${h.narben.length?' · 🩸 '+esc(h.narben.join(', ')):''}</p>`).join('')}
  ${x.ehrungen.length?`<div class="lbl">${esc(t('Ehrungen des Abends','Honours of the evening'))}</div>${x.ehrungen.map(e=>`<p>🏅 ${esc(e.titel)}: ${esc(e.name)}</p>`).join('')}`:''}
  ${x.schrift.map(w=>`<div class="lbl">📜 ${esc(w.titel)}</div><p class="dm-buchschrift">${esc(w.text)}</p>`).join('')}
  ${x.orte.length?`<small class="mut">${esc(t('Orte: ','Places: ')+x.orte.join(' → '))}</small>`:''}
  <div class="dm-hostb"><a class="b" href="/api/profile/dungeon/kampagne/${esc(B.kid)}/chronik.pdf?lang=${dmLang()}" download>${esc(t('Als PDF','As PDF'))}</a><button type="button" class="b danger" data-dmkseite="${x.kapitel}">${esc(t('Seite löschen','Delete page'))}</button><button type="button" class="b" data-dmkbuch="">${esc(t('Schließen','Close'))}</button></div></div>`}
// people and class of a new hero as cards (the hidden field keeps the choice), their values as chips that never break
// (Dominik 2026-10-24 „die werte anzeige ist nicht cool gelöst“, „1“): the people's bonus; the class's best values,
// life and what it can do from level 1
const dmKurz=(w,id)=>(w.werte.find(x=>x.id===id)||{}).kurz||id;
function dmVolkSub(w,x){const e=Object.entries(x.werte||{});
  return e.length===w.werte.length&&e.every(([k,v])=>v===e[0][1])?[[t('Alle Werte +','All values +')+e[0][1],'up']]:e.map(([k,v])=>[dmKurz(w,k)+' +'+v,'up'])}
function dmKlasseSub(w,x){const st=x.start||{f:[],z:[]},f=st.f.length,z=st.z.length;
  return [...x.reihe.slice(0,2).map(k=>[dmKurz(w,k),'']),['❤ '+x.leben,'leben'],...(f?[['✦ '+f+' '+t(f===1?'Kraft':'Kräfte',f===1?'power':'powers'),'kraft']]:[]),
    ...(z?[['✨ '+z+' '+t('Zauber',z===1?'spell':'spells'),'kraft']]:[])]}
// painted pictures for peoples, classes and powers (Dominik 2026-10-24 „bilder keine icons“, dungeon_dingbild.hero_prompt):
// the picture once it is painted, a calm colour of its own until then, never an emoji
// until a picture is painted a calm placeholder (Punkt 7 of 2026-10-24): the thing's sign on parchment, large ones say
// „Noch kein Bild“; the painted picture covers it once it loads
const DMZ={angriff:'⚔',heilen:'✚',schutz:'🛡',sonst:'✦'};
function dmPic(bild,id,cls,zeichen){const z=zeichen||String(id||'?').trim().slice(0,1).toUpperCase();
  return `<span class="dm-pic${cls?' '+cls:''}" aria-hidden="true"><span class="dm-pz">${esc(z)}${/gross/.test(cls||'')?`<small>${esc(t('Noch kein Bild','No picture yet'))}</small>`:''}</span>${bild?`<img alt="" loading="lazy" data-dmdbild="${esc(bild)}">`:''}</span>`}
// the hero form's picture of a people, class or power in the style of the world chosen (Punkt 8a of 2026-10-24): the
// new round's form gets each world's (bilder), a seat's form only its round's (bild)
const DMBW={w:''},dmHB=x=>(x.bilder&&x.bilder[DMBW.w])||x.bild;
function dmHBSwap(f){const w=DM.data&&DM.data.wahl;if(!f||!w)return;
  f.querySelectorAll('.dmf-neu .dm-vk [data-dmvk]').forEach(c=>{const a=c.closest('.dm-vk').dataset.dmvkk==='volk'?w.voelker:w.klassen,x=a.find(y=>y.id===c.dataset.dmvk),p=c.querySelector('.dm-pic');
    if(x&&p)p.outerHTML=dmPic(dmHB(x),x.name)});
  const det=f.querySelector('.dmf-kdet');if(det)det.innerHTML=dmKlasseDet(w,(f.querySelector('.dmf-klasse')||{}).value);dmDingFill(f,'p')}
// sub is a line of text or, for peoples and classes, a list of chips [text, kind] that never break inside
const dmPChips=a=>`<span class="dm-pchips">${a.map(([x,k])=>`<span class="dm-pchip${k?' '+k:''}">${esc(x)}</span>`).join('')}</span>`;
const dmPCard=(attr,on,x,sub)=>`<button type="button" class="dm-card dm-pcard${on?' on':''}" ${attr}>${dmPic(dmHB(x),x.name)}<b>${esc(x.name)}</b>${Array.isArray(sub)?dmPChips(sub):sub?`<small>${dmFx(sub)}</small>`:''}</button>`;
// a power as a picture tile (class detail, „Das kann ich“): the colour on top is its kind, a tap explains it
// the colour of a kind (app.css), named here in full so every class is found
const DMKK={angriff:'k-angriff',heilen:'k-heilen',schutz:'k-schutz',sonst:'k-sonst'};
const DMKART=()=>({angriff:t('Angriff','Attack'),heilen:t('Heilen','Healing'),schutz:t('Schutz','Protection'),sonst:t('Sonstiges','Other')});
const dmKtSub=x=>x.grad===undefined?(x.wert?x.wert+' +'+x.bonus:''):x.grad&&x.rest!==undefined&&x.rest!==null?t('noch '+x.rest+' von '+x.voll,x.rest+' of '+x.voll+' left'):x.satz||'';
function dmKt(x,key,on,off){return `<button type="button" class="dm-kt ${DMKK[x.art]||DMKK.sonst}${on?' on':''}${off?' aus':''}${x.immer?' immer':''}" data-dmkt="${esc(key)}" aria-expanded="${!!on}">${dmPic(dmHB(x),x.name,'',DMZ[x.art]||DMZ.sonst)}${x.grad?`<em>${esc(t('Grad '+x.grad,'Grade '+x.grad))}</em>`:''}<b>${esc(x.name)}</b><small>${dmFx(dmKtSub(x))}</small></button>`}
// what the panel does for an ability (faehigkeiten[].wirkung, Punkt 3 of 2026-10-24); one that always works has no „Einsetzen“
const DMWIRK=()=>({weniger_schaden:t('das Panel zieht je Treffer 1 ab','the panel takes 1 off every hit'),schaden_plus:t('das Panel gibt jedem Waffentreffer +1 Schaden','the panel adds 1 damage to every weapon hit'),leben_je_stufe:t('das Panel gibt dir +3 Leben je Stufe','the panel gives you 3 more life per level'),heilen:t('das Panel heilt 1× je Szene einen Freund um 1W6+2','the panel heals a friend by 1d6+2 once a scene'),wiederbeleben:t('das Panel holt 1× je Szene einen Freund vom Boden mit 3 Leben zurück','the panel brings a friend down back with 3 life once a scene'),abfangen:t('das Panel gibt dir 1× je Szene den Treffer eines Freundes','the panel gives you a friend\'s hit once a scene'),gruppe_probe:t('das Panel gibt der Gruppe +1 auf die Proben dieses Zugs','the panel gives the group +1 on this turn\'s checks')});
// what a power is: picture, kind, sentence, explanation and its values; „✨ Wirken“ writes it into the own action field
function dmKtDet(x,say){const zt=x.grad===undefined?t('Fähigkeit','Ability'):x.grad?t('Zauber Grad '+x.grad,'Spell grade '+x.grad):t('Zaubertrick','Cantrip');
  const chips=[DMKART()[x.art]||'',x.wert?`🎲 ${esc(x.wert)} ${dmBo(x.bonus)}${x.grad===undefined&&!x.immer?' '+esc(t('beim Einsetzen','when used')):''}`:'',x.grad?esc(x.rest===undefined||x.rest===null?t('Ladungen je Stufe','charges per level'):t('noch '+x.rest+' von '+x.voll+' Ladungen',x.rest+' of '+x.voll+' charges left')):x.grad===0?esc(t('beliebig oft','any time')):'',
    x.immer?esc(t('wirkt immer','always works')):'',x.wirkung?esc(DMWIRK()[x.wirkung]||''):''].filter(Boolean);
  return `<div class="dm-ktd ${DMKK[x.art]||DMKK.sonst}">${dmPic(dmHB(x),x.name,'gross',DMZ[x.art]||DMZ.sonst)}<div><b class="dm-ktd-n">${esc(x.name)}</b> <small class="mut">· ${esc(zt)}</small>
    ${x.satz?`<p>${dmFx(x.satz)}</p>`:''}${x.info?`<p class="mut">${dmFx(x.info)}</p>`:''}<div class="dm-ktchips">${chips.map((c,i)=>`<span class="dm-chip${i?'':' dm-kart'}">${i?c:esc(c)}</span>`).join('')}</div>
    ${say&&!x.immer?`<div class="dm-iacts"><button type="button" class="b p" data-dmkann="${esc(say)}" data-dmfenzu="alle">✨ ${esc(x.grad===undefined?t('Einsetzen','Use'):t('Wirken','Cast'))}</button></div>`:''}</div></div>`}
// the chosen class large (Dominik 2026-10-24 „alles“): picture, sentence, values, the powers of level 1 as tiles by grade
const DMKT={k:'',x:''};
function dmKlasseDet(w,kid){const x=w.klassen.find(k=>k.id===kid)||w.klassen[0];if(!x)return '';const st=x.start||{f:[],z:[]},gr={};
  st.z.forEach((z,i)=>(gr[z.grad]=gr[z.grad]||[]).push([z,i]));if(DMKT.k!==x.id)DMKT.x='';DMKT.k=x.id;
  const sel=DMKT.x,pick=sel?(sel[0]==='f'?st.f[+sel.slice(2)]:st.z[+sel.slice(2)]):null;
  const tiles=a=>`<div class="dm-kts">${a.map(([y,k])=>dmKt(y,k,k===sel)).join('')}</div>`;
  const vn=k=>(w.werte.find(v=>v.id===k)||{}).name||k;
  return `<div class="dm-kdet">${dmPic(dmHB(x),x.name,'gross')}<div class="dm-kdet-t"><b class="dm-kdet-n">${esc(x.name)}</b>
    <small class="mut">${esc(t('Hauptwerte ','Main values ')+x.reihe.slice(0,2).map(vn).join(t(' und ',' and ')))} · ${esc(t('Leben','Life'))} ${x.leben}${x.leben_plus?` (${dmBo(x.leben_plus)} ${esc(t('je Stufe','per level'))})`:''}</small>
    ${x.satz?`<p>${esc(x.satz)}</p>`:''}
    <h5>${esc(t('Startkräfte','Starting powers'))}</h5>${st.f.length?tiles(st.f.map((y,i)=>[y,'f:'+i])):`<small class="mut">${esc(t('keine','none'))}</small>`}
    ${Object.keys(gr).sort((a,b)=>a-b).map(g=>`<h5>${esc(+g?t('Zauber Grad '+g,'Spells grade '+g):t('Zaubertricks','Cantrips'))}${+g?'':' · '+esc(t('beliebig oft','any time'))}</h5>${tiles(gr[g].map(([y,i])=>[y,'z:'+i]))}`).join('')}
    ${pick?dmKtDet(pick):''}</div></div>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm-neu .dm-kdet [data-dmkt]');if(!b)return;const f=b.closest('.dm-neu'),det=f.querySelector('.dmf-kdet,.dgf-kdet');
  DMKT.x=DMKT.x===b.dataset.dmkt?'':b.dataset.dmkt;det.innerHTML=dmKlasseDet(dmVertWahl(f),(f.querySelector('.dmf-klasse,.dgf-klasse')||{}).value);dmDingFill(det,f.closest('#dgcard')?'g':'p')});
// „Das kann ich“ (Dominik 2026-10-23 „1-3“, as picture tiles 2026-10-24 „alles“): abilities, cantrips and the spells by
// grade with the charges left in this chapter, filtered by kind; a tap opens the power's window, „✨ Wirken“ there puts it
// into the own action field, the panel checks what was typed (dungeon.check_powers)
const DMKF={f:''};
const dmKannSay=(x,spell)=>spell?t('Ich wirke '+x.name+'.','I cast '+x.name+'.'):t('Ich setze '+x.name+' ein.','I use '+x.name+'.');
function dmKann(h){const k=h.kann||{faehigkeiten:[],zauber:[],dinge:[]},all=[...k.faehigkeiten,...k.zauber];
  if(!all.length&&!k.dinge.length)return `<small class="mut">${esc(t('Noch nichts.','Nothing yet.'))}</small>`;
  const f=all.some(x=>x.art===DMKF.f)?DMKF.f:'',n=a=>all.filter(x=>x.art===a).length,show=x=>!f||x.art===f;
  const tiles=a=>`<div class="dm-kts">${a.filter(show).map(x=>dmKt(x,(x.grad===undefined?'kf:':'kz:')+x.id,false,x.rest===0)).join('')}</div>`;
  const gr={};k.zauber.forEach(z=>(gr[z.grad]=gr[z.grad]||[]).push(z));
  const dots=z=>'●'.repeat(z.rest)+'○'.repeat(Math.max(0,z.voll-z.rest));
  const sec=(title,sub,a)=>a.some(show)?`<h5>${esc(title)}${sub?` <small class="dm-ksub">${esc(sub)}</small>`:''}</h5>${tiles(a)}`:'';
  return `<div class="dm-kfilter" role="group" aria-label="${esc(t('Nach Art','By kind'))}">${['',...Object.keys(DMKART())].filter(a=>!a||n(a)).map(a=>`<button type="button" class="dm-kf${a?' '+DMKK[a]:''}${f===a?' on':''}" data-dmkf="${a}" aria-pressed="${f===a}">${esc(a?DMKART()[a]:t('Alle','All'))} ${a?n(a):all.length}</button>`).join('')}</div>
    ${sec(t('Fähigkeiten','Abilities'),t('immer verfügbar','always there'),k.faehigkeiten)}
    ${Object.keys(gr).sort((a,b)=>a-b).map(g=>{const z=gr[g][0];return sec(+g?t('Grad '+g,'Grade '+g):t('Zaubertricks','Cantrips'),+g?dots(z)+' '+(z.rest?t(z.rest+' von '+z.voll+' Ladungen',z.rest+' of '+z.voll+' charges'):t('keine Ladung mehr, kommt mit dem nächsten Kapitel','no charge left, it comes back with the next chapter')):t('beliebig oft','any time'),gr[g])}).join('')}
    ${k.dinge.length?`<div class="dm-pills"><small class="mut">${esc(t('Aus der Tasche:','From the bag:'))}</small> ${k.dinge.map(n=>`<span class="pill">${esc(n)}</span>`).join(' ')}</div>`:''}`}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmkf]');if(!b)return;DMKF.f=b.dataset.dmkf;b.closest('#dgcard')?dgDraw():dmDraw()});
// the hero's gender (Dominik 2026-10-26): three buttons, at creation and on the hero sheet (sheet: posts at once)
const DMSEX=()=>[['maennlich',t('männlich','male')],['weiblich',t('weiblich','female')],['divers',t('divers','non-binary')]];
// Review 27.10. Z12: the hero's voices grouped by gender, the hero's own gender first (divers and unset: female first)
function dmVoiceGroups(h,v){const vw=new Set(v.stimmen_w||[]),all=[...new Set([h.stimme,...(v.stimmen||[])].filter(Boolean))];
  const opt=x=>`<option${x===h.stimme?' selected':''}>${esc(x)}</option>`,grp=(l,xs)=>xs.length?`<optgroup label="${esc(l)}">${xs.map(opt).join('')}</optgroup>`:'';
  const w=[t('Weibliche Stimmen','Female voices'),all.filter(x=>vw.has(x))],m=[t('Männliche Stimmen','Male voices'),all.filter(x=>!vw.has(x))];
  return (h.geschlecht==='maennlich'?[m,w]:[w,m]).map(([l,xs])=>grp(l,xs)).join('')}
function dmSex(cur,sheet){return `<div class="dm-kfilter dm-sex" role="group" aria-label="${esc(t('Geschlecht','Gender'))}"${sheet?' data-dmsexsheet="1"':''}>${DMSEX().map(([k,n])=>`<button type="button" class="dm-kf${k===cur?' on':''}" data-dmsex="${k}" aria-pressed="${k===cur}">${esc(n)}</button>`).join('')}</div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('.dm [data-dmsex]');if(!b)return;const box=b.closest('.dm-sex');
  box.querySelectorAll('[data-dmsex]').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)});
  if(!box.dataset.dmsexsheet){const inp=box.previousElementSibling;if(inp)inp.value=b.dataset.dmsex;return}
  const body={was:'geschlecht',geschlecht:b.dataset.dmsex};
  if(b.closest('#dmview')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
  else await dgAct('/api/dungeon/held',body)});
function dmHeroForm(w,heroes,pre){const vk=(k,a,sub)=>`<input type="hidden" class="${pre}${k}" value="${esc(a[0].id)}"><div class="dm-cards dm-klein dm-vk" data-dmvkk="${k}">${a.map((x,i)=>dmPCard(`data-dmvk="${esc(x.id)}"`,i===0,x,sub(w,x))).join('')}</div>`;
  return `${heroes&&heroes.length?`<label>${esc(t('Held','Hero'))}</label><select class="${pre}held"><option value="">${esc(t('Neuer Held …','New hero …'))}</option>${heroes.map(h=>`<option value="${esc(h.hid)}"${h.zustand==='tot'?' disabled':''}>${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}${h.zustand==='tot'?' · '+esc(t('gefallen','fallen')):''}</option>`).join('')}</select>`:''}
    <div class="${pre}neu dm-neu"><label>${esc(t('Name deiner Figur','Name of your character'))}</label><input class="${pre}name" maxlength="24" autocomplete="off">
    <label>${esc(t('Geschlecht','Gender'))}</label><input type="hidden" class="${pre}geschlecht" value="">${dmSex('',false)}
    <label>${esc(t('Volk','People'))}</label>${vk('volk',w.voelker,dmVolkSub)}<label>${esc(t('Klasse','Class'))}</label>${vk('klasse',w.klassen,dmKlasseSub)}<div class="${pre}kdet">${dmKlasseDet(w,w.klassen[0].id)}</div>
    <label>${esc(t('Werte','Values'))}</label><small class="mut">${esc(t('Die Zahlen 15, 14, 13, 12, 10 und 8 verteilen: ziehen oder zwei antippen tauscht sie. Dahinter das Volk, der Wert und der Bonus für Würfe.','Lay out 15, 14, 13, 12, 10 and 8: drag, or tap two to swap them. After it the people\'s bonus, the value and the bonus for rolls.'))}</small>
    <div class="${pre}vert dm-vert">${w.verteilung?dmVert(w,w.klassen[0].id,w.voelker[0].id):''}</div>
    <label>${esc(t('Ein Satz zu deiner Figur (frei)','One sentence about your character (optional)'))}</label><input class="${pre}satz" maxlength="120" autocomplete="off">
    ${w.bilder_an?`<label class="dm-check"><input type="checkbox" class="${pre}portraet"> ${esc(t('Porträt malen lassen (aus Volk, Klasse und deinem Satz)','Have a portrait painted (from people, class and your sentence)'))}</label>`:''}</div>`}
function dmHeroBody(box,pre){const sel=box.querySelector('.'+pre+'held');if(sel&&sel.value)return sel.value;
  const v=c=>(box.querySelector('.'+pre+c)||{}).value||'';const vt=box.querySelector('.'+pre+'vert');return {name:v('name').trim(),geschlecht:v('geschlecht'),volk:v('volk'),klasse:v('klasse'),satz:v('satz').trim(),verteilung:vt?dmVertOf(vt):undefined}}
// the six values of a new hero: the fixed row (15 14 13 12 10 8) laid out by the class, the player drags or taps two numbers to swap them
const dmSign=m=>(m<0?'−':'+')+Math.abs(m);
// dice and bonuses stand out everywhere in the game (Dominik 2026-10-24 „Würfel und Bonis … gehen im fließtext unter“):
// dmBo a bonus as a coloured chip, dmFx a text escaped with every die („1W6+2“, „W20“, „2d8“) and signed number marked
// a check as a card (Dominik 2026-10-24 „für was die Würfelprobe gerade gemacht wird … geht ein bisschen unter“): what it
// is for large (wofuer: the model's few words or the start of the action), who rolls which value above, the sum below
function dmPK(v,x,die,cls,attr){const W=v.werte||{},hat='w' in x;
  return `<div class="dm-wurf dm-pk ${hat?(x.ok?'ok':'bad'):''}${cls||''}"${attr||''}>${die}<div class="dm-pkt"><small class="dm-pkwer">${esc(x.name)} ${esc(t('würfelt','rolls'))} ${esc(W[x.wert]||x.wert)}</small>${x.wofuer?`<b class="dm-pkwas">${esc(x.wofuer)}</b>`:''}
    <small class="dm-pkr">${hat?`${dmVt(x)}${dmTool(x)}${x.schrei?`<span class="dm-vt">${esc(t('Kampfschrei +1','Battle cry +1'))}</span> `:''}${x.mut?`<span class="dm-vt dm-mutw">⭐ ${esc(t('Heldenmut: neu gewürfelt','Heroic courage: rolled again'))}</span> `:''}${x.glueck?`<span class="dm-vt">🍀 ${esc(t('Glück: die 1 neu gewürfelt','Luck: the 1 rolled again'))}</span> `:''}${x.w} ${dmBo(x.bonus)} = <b>${x.gesamt}</b> `:''}${esc(t('gegen Schwierigkeit','vs difficulty'))} ${x.schwer}</small></div>${hat?`<span class="dm-pke">${esc(x.ok?t('geschafft','success'):t('nicht geschafft','failed'))}</span>`:''}</div>`}
const dmBo=m=>`<span class="dm-bo ${m>0?'up':m<0?'dn':'nu'}">${dmSign(m)}</span>`;
const DMFX=/(?<![\p{L}\d])(\d*[WDd]\d+)((?:\s?[+−-]\s?\d+)?)(?![\p{L}\d])|(?<![\p{L}\d])([+−]\d+)(?![\d])/gu;
const dmFx=s=>esc(s).replace(DMFX,(m,w,p,b)=>w?`<span class="dm-wf">${w}${p}</span>`:`<span class="dm-bo ${b[0]==='+'&&b!=='+0'?'up':b==='+0'?'nu':'dn'}">${b}</span>`);
function dmVert(w,kid,vid,cur){const k=w.klassen.find(x=>x.id===kid)||w.klassen[0],vo=w.voelker.find(x=>x.id===vid)||w.voelker[0];
  const val=cur||Object.fromEntries(k.reihe.map((id,i)=>[id,w.verteilung[i]])),md=s=>dmSign(Math.floor((s-10)/2));
  return w.werte.map(x=>{const v=val[x.id],b=(vo.werte||{})[x.id]||0;
    return `<div class="dm-vslot" data-w="${esc(x.id)}" title="${esc(x.name)}"><small>${esc(x.kurz)}</small><button type="button" class="dm-vchip" draggable="true" data-dmv="${esc(x.id)}" aria-label="${esc(x.name+' '+v)}">${v}</button><small class="dm-vsum">${b?'+'+b+' ':''}= <b>${v+b}</b> · ${md(v+b)}</small></div>`}).join('')}
function dmVertOf(box){const o={};box.querySelectorAll('.dm-vchip').forEach(c=>o[c.dataset.dmv]=+c.textContent);return o}
function dmVertWahl(box){return box.closest('#dgcard')?DG.info&&DG.info.wahl:DM.data&&DM.data.wahl}
function dmVertDraw(f,keep){const w=dmVertWahl(f),pre=f.querySelector('.dmf-vert')?'dmf-':'dgf-',v=f.querySelector('.'+pre+'vert');if(!w||!v)return;
  v.innerHTML=dmVert(w,(f.querySelector('.'+pre+'klasse')||{}).value,(f.querySelector('.'+pre+'volk')||{}).value,keep?dmVertOf(v):null)}
function dmVertSwap(v,a,b){if(a===b)return;const o=dmVertOf(v);[o[a],o[b]]=[o[b],o[a]];const f=v.closest('.dm-neu');
  v.innerHTML=dmVert(dmVertWahl(v),(f.querySelector('.dmf-klasse,.dgf-klasse')||{}).value,(f.querySelector('.dmf-volk,.dgf-volk')||{}).value,o);
  const c=v.querySelector(`[data-dmv="${CSS.escape(b)}"]`);if(c)c.focus({preventScroll:true})}
document.body.addEventListener('click',e=>{const c=e.target.closest('.dm-neu [data-dmvk]');if(!c)return;const g=c.closest('.dm-vk'),f=c.closest('.dm-neu'),k=g.dataset.dmvkk;
  g.querySelectorAll('.dm-card').forEach(x=>x.classList.toggle('on',x===c));const inp=f.querySelector(`.dmf-${k},.dgf-${k}`);if(inp)inp.value=c.dataset.dmvk;dmVertDraw(f,k==='volk');
  const det=f.querySelector('.dmf-kdet,.dgf-kdet');if(k==='klasse'&&det){det.innerHTML=dmKlasseDet(dmVertWahl(f),c.dataset.dmvk);dmDingFill(det,f.closest('#dgcard')?'g':'p')}});
document.body.addEventListener('click',e=>{const c=e.target.closest('.dm-vchip');if(!c)return;const v=c.closest('.dm-vert'),on=v.querySelector('.dm-vchip.on');
  if(on&&on!==c){dmVertSwap(v,on.dataset.dmv,c.dataset.dmv);return}c.classList.toggle('on')});
document.body.addEventListener('dragstart',e=>{const c=e.target.closest&&e.target.closest('.dm-vchip');if(c){e.dataTransfer.setData('text/plain',c.dataset.dmv);e.dataTransfer.effectAllowed='move'}});
document.body.addEventListener('dragover',e=>{if(e.target.closest&&e.target.closest('.dm-vslot'))e.preventDefault()});
document.body.addEventListener('drop',e=>{const s=e.target.closest&&e.target.closest('.dm-vslot');if(!s)return;e.preventDefault();
  const a=e.dataTransfer.getData('text/plain');if(a)dmVertSwap(s.closest('.dm-vert'),a,s.dataset.w)});
// a new round (Dominik 2026-10-23): world, story, tone, people and class as cards with pictures; the stories of the chosen
// world are the admin's and the ten that come with the Spark, a story sets its tone
function dmStories(w,welt){const ton=id=>w.toene.find(x=>x.id===id)||{},E=w.eigene,VON={eigen:t('deine','yours'),admin:t('vom Admin','by the admin')};
  const card=g=>`<button type="button" class="dm-card dm-gcard" data-dmgs="${esc(g.gid)}"><b>${esc(g.titel)}</b><small class="dm-gidee">${esc(g.idee)}</small><small class="dm-gmeta">${esc((ton(g.ton).zeichen||'')+' '+(ton(g.ton).name||''))} · ${g.akte} ${esc(t('Akte','acts'))}${VON[g.von]?' · '+esc(VON[g.von]):''}</small></button>`;
  // Eigene Geschichten (dungeon_geschichten): „⋯“ beside every card, Löschen of a story not the host's own only hides it
  const mehr=g=>`<span class="ic-menu dm-gmehr"><button type="button" class="b" data-dmgmehr="1" aria-haspopup="true" aria-label="${esc(t('Mehr zu „'+g.titel+'“','More on “'+g.titel+'”'))}">⋯</button><div class="ic-pop" hidden>${[['bearbeiten',t('Bearbeiten','Edit')],['kopieren',t('Kopieren','Copy')],['loeschen',g.von==='eigen'?t('Löschen','Delete'):t('Ausblenden','Hide')]].map(([k,l])=>`<button type="button"${k==='loeschen'?' class="danger"':''} data-dmgwas="${k}" data-gid="${esc(g.gid)}">${esc(l)}</button>`).join('')}</div></span>`;
  return (E?`<button type="button" class="dm-card dm-gcard dm-gneu" data-dmgneu="1"><b>＋ ${esc(t('Neue Geschichte','New story'))}</b><small class="dm-gidee">${esc(t('Ton wählen, Stichworte nach Wunsch: das Sprachmodell schreibt sie.','Pick a tone, keywords if you like: the language model writes it.'))}</small></button>`:'')
    +dmCard('data-dmgs=""',true,'✒',t('Frei erzählen','Tell freely'),t('Der Dungeon-Master erfindet die Geschichte aus dem Einstieg.','The Dungeon Master makes up the story from the opening.'))
    +(w.geschichten||[]).filter(g=>g.welt===welt).map(g=>E?`<div class="dm-gwrap">${card(g)}${mehr(g)}</div>`:card(g)).join('')
    +(E&&E.aus?`<button type="button" class="b dm-gzeigen" data-dmgzeigen="1">${esc(t(`${E.aus} ausgeblendete wieder zeigen`,`Show ${E.aus} hidden again`))}</button>`:'')}
function dmWorld(w,id){const f=w.querySelector('.dm-form'),D=DM.data;if(!f||!D)return;DM.welt=id;DMBW.w=id;dmLook(w,dmWelt(D.wahl,id).farben);dmHBSwap(f);
  f.querySelector('.dmf-gesch').innerHTML=dmStories(D.wahl,id);dmStory(w,f.querySelector('.dmf-gesch [data-dmgs=""]'))}
function dmStory(w,b){const f=w.querySelector('.dm-form'),D=DM.data;if(!f||!D||!b)return;
  f.querySelectorAll('.dmf-gesch .dm-card').forEach(x=>x.classList.toggle('on',x===b));
  const g=(D.wahl.geschichten||[]).find(x=>x.gid===b.dataset.dmgs),ti=f.querySelector('.dmf-titel');
  f.querySelectorAll('.dmf-ton .dm-card').forEach(x=>{x.disabled=!!g&&x.dataset.dmseg!==String(g.ton);if(g)x.classList.toggle('on',x.dataset.dmseg===String(g.ton))});
  if(ti&&(!ti.value.trim()||ti.value===ti.dataset.auto)){ti.value=g?g.titel:'';ti.dataset.auto=ti.value}}
function dmNew(D){const w=D.wahl;if(D.runden.filter(x=>x.gastgeber&&x.status!=='ende').length>=D.runden_max)return `<div class="ic-note"><div class="ic-mid"><b>${esc(t('Du leitest schon '+D.runden_max+' Runden.','You host '+D.runden_max+' rounds already.'))}</b><span>${esc(t('Beende eine, um eine neue anzulegen.','End one to start a new one.'))}</span></div></div>`;
  const min=s=>s>=3600?Math.round(s/3600)+' h':s>=60?Math.round(s/60)+' min':s+' s',welt=DMBW.w=dmWelt(w,DM.welt).id,step=(n,x)=>`<h4 class="dm-step"><span>${n}</span>${esc(x)}</h4>`;
  return `<h3 class="sec">${esc(t('Neue Runde','New round'))}</h3><div class="dm-form">
    ${step(1,t('Welt','World'))}<div class="dm-cards dmf-welt">${w.welten.map(x=>dmWCard(x,x.id===welt)).join('')}</div>
    ${step(2,t('Geschichte','Story'))}<div class="dm-cards dm-gs dmf-gesch">${dmStories(w,welt)}</div>
    ${step(3,t('Die Runde','The round'))}
    <label>${esc(t('Titel','Title'))}</label><input class="dmf-titel" maxlength="60" placeholder="${esc(t('Die Glocke von Hallstein','The bell of Hallstein'))}">
    <label>${esc(t('Einstieg (frei)','Opening (optional)'))}</label><textarea class="dmf-einstieg" rows="2" maxlength="400" placeholder="${esc(t('Ein Dorf, dessen Glocke nachts von selbst läutet.','A village whose bell rings by itself at night.'))}"></textarea>
    <label>${esc(t('Ton','Tone'))}</label><div class="dm-cards dm-klein dmf-ton">${w.toene.map((x,i)=>dmCard(`data-dmseg="${x.id}"`,i===1||w.toene.length===1,x.zeichen,x.name,'')).join('')}</div>
    <div class="dm-two"><div><label>${esc(t('Zeit je Zug','Time per turn'))}</label><select class="dmf-zug">${w.zug_s.map(s=>`<option value="${s}"${s===w.zug_standard?' selected':''}>${esc(min(s))}</option>`).join('')}</select></div>
    <div><label>${esc(t('Die Runde gilt','The round lasts'))}</label><select class="dmf-stunden">${w.stunden.map(h=>`<option value="${h}">${esc(min(h*3600))}</option>`).join('')}</select></div></div>
    ${step(4,t('Dein Held','Your hero'))}${dmHeroForm(w,D.helden,'dmf-')}
    <label>${esc(t('Erzählweise','Way of telling'))}</label>${dmWeise('dmf-weise','normal')}
    <label class="dm-check"><input type="checkbox" class="dmf-vorlesen"> ${esc(t('Erzählung vorlesen (Erzähler und NPC mit eigener Stimme)','Read the story aloud (narrator and NPCs in their own voices)'))}</label>
    <details class="adv"><summary>${esc(t('Dungeon-Master-Prompt','Dungeon Master prompt'))}</summary><div class="fh">${esc(t('Dahinter stehen immer die festen Regeln des Panels: JSON, Namen, Ton, keine erfundenen Werte.','The panel\'s fixed rules always stand behind it: JSON, names, tone, no invented values.'))}</div><textarea class="dmf-prompt" rows="6" maxlength="4000">${esc(w.prompt)}</textarea></details>
    <div class="row"><button type="button" class="b p" data-dmmake="1">${esc(t('Runde starten','Start the round'))}</button></div></div>`}
// a hero's state by the panel (Punkt 1 of 2026-10-24): down with the turns left, unconscious, fallen
const dmZustText=h=>h.zustand==='boden'?t('am Boden · Rettung ✓'+h.erfolge+' · noch '+h.noch+(h.noch===1?' Fehlwurf':' Fehlwürfe'),'down · saves ✓'+h.erfolge+' · '+h.noch+(h.noch===1?' failure':' failures')+' left'):h.zustand==='ohnmacht'?t('ohnmächtig bis zum nächsten Kapitel','unconscious until the next chapter'):h.zustand==='tot'?t('gefallen','fallen'):'';
const dmZust=h=>(h&&h.zustand?`<span class="dm-zst" data-z="${esc(h.zustand)}">${{boden:'⚠',ohnmacht:'💤',tot:'✝'}[h.zustand]||''} ${esc(dmZustText(h))}</span>`:'')
  +(h&&(h.zust||[]).length?h.zust.map(z=>`<span class="dm-zst dm-zst2" title="${esc(z.info)}">☠ ${esc(z.name)}${z.noch?' · '+esc(t(z.noch===1?'noch 1 Zug':`noch ${z.noch} Züge`,z.noch===1?'1 turn left':`${z.noch} turns left`)):''}</span>`).join(''):'');   // from a foe's hit (Kampf Teil 2)
// what the own seat reads instead of the action field while its hero cannot act
const dmZustSatz=h=>h.zustand==='boden'?t('Dein Held liegt am Boden. Ein Freund kann ihm einen Heiltrank geben, ihn heilen oder ihm aufhelfen. Jeden erzählten Zug würfelt das Panel einen Rettungswurf: ab 10 gelingt er, drei gelungene oder eine 20 und er steht mit 1 Leben auf. Bisher '+h.erfolge+' gelungen, noch '+h.noch+(h.noch===1?' Fehlwurf':' Fehlwürfe')+', dann fällt er.','Your hero is down. A friend can give them a healing potion, heal them or help them up. Each told turn the panel rolls a death save: 10 or more succeeds, three successes or a 20 and they get up with 1 life. So far '+h.erfolge+' succeeded, '+h.noch+(h.noch===1?' failure':' failures')+' left, then they fall.')
  :h.zustand==='ohnmacht'?t('Dein Held ist ohnmächtig. Er wacht am nächsten Tisch wieder auf, behält seine Dinge, aber nicht sein Gold.','Your hero is unconscious. They wake at the next table, keep their things but not their gold.')
  :t('Dein Held ist gefallen. Seine Dinge und sein Gold liegen hier für die anderen. Für einen neuen Helden nimmt der Gastgeber deinen Platz zurück und lädt dich neu ein.','Your hero has fallen. Their things and gold lie here for the others. For a new hero the host takes your seat back and invites you again.');
// a friend down: the own healing potion for them, by the panel (data-dmhero „trinken“ with an)
function dmHelfen(v,p){const me=v.ich;if(p.zustand!=='boden'||p.ich||!me||me.zustand||v.status==='ende')return '';const it=(me.tasche||[]).find(x=>x.heilt);
  return it?`<button type="button" class="b dm-helfen" data-dmhero="trinken" data-i="${esc(it.i)}" data-an="${esc(p.pid)}">🧪 ${esc(t('Heiltrank geben','Give a healing potion'))}</button>`:`<small class="mut">${esc(t('Hilf ihm in deiner Aktion auf.','Help them up in your action.'))}</small>`}
// the kept heroes as cards like at the table: values, life, level and gold
function dmHeroes(D){const hs=D.helden;
  const list=hs.length?`<div class="dm-hcards">${hs.map((h,i)=>`<div class="dm-seat dm-hero dm-hcard"><div class="dm-hhead">${h.bild?`<span class="dm-av dm-avb" data-c="${i%5}"><img alt="" loading="lazy" src="/api/profile/dungeon/held/${esc(h.hid)}/bild?v=${h.stufe}"></span>`:`<span class="dm-av" data-c="${i%5}">${esc((h.name||'?').slice(0,1).toUpperCase())}</span>`}<div><b>${esc(h.name)}</b> <i>${esc(h.volk)} ${esc(h.klasse)}</i><small class="mut">${esc(t('Stufe','Level'))} ${h.stufe} · ${h.ep} EP${h.ep_tisch?' · +'+h.ep_tisch+' '+esc(t('EP noch am Tisch','EP still at the table')):''} · ${h.gold} ${esc(t('Gold','gold'))}</small>${dmZust(h)}</div></div>
    ${dmBar(h.leben,h.leben_max)}<small class="mut">${esc(t('Leben','Life'))} ${h.leben}/${h.leben_max}</small>
    <div class="dm-stats">${(h.werte||[]).map(x=>`<span title="${esc(x.name)}"><small>${esc(x.kurz)}</small><b>${x.wert}</b><i>${dmBo(x.mod)}</i></span>`).join('')}</div>
    ${h.satz?`<small class="dm-isatz">„${esc(h.satz)}“</small>`:''}${dmHeroThings(h)}<div class="dm-hostb"><button type="button" class="b danger" data-dmdelhero="${esc(h.hid)}">${esc(t('Löschen','Delete'))}</button></div></div>`).join('')}</div>`
    :`<div class="ic-empty">${esc(t('Noch keine Helden. Ein Held entsteht mit deiner ersten Runde und behält Stufe, Werte und Beute.','No heroes yet. A hero comes with your first round and keeps level, values and loot.'))}</div>`;
  return `<h3 class="sec">${esc(t('Deine Helden','Your heroes'))} · ${hs.length}/${D.helden_max}</h3>${list}
    <div class="ic-danger"><div class="ic-mid"><b>${esc(t('Alle Spieldaten löschen','Delete all game data'))}</b><span>${esc(t('Deine Helden, Kampagnen, Runden und deine Plätze in fremden Runden.','Your heroes, campaigns, rounds and your seats in other rounds.'))}</span></div><button type="button" class="b danger" data-dmwipe="1">${esc(t('Löschen …','Delete …'))}</button></div>`}
// pictures of the round (Stufe 3): the own page loads them by their path, a guest's seat by its code (POST, blob)
const DMI={};
function dmImg(mode,v,k,id,ver){const src=mode==='p'?(k==='b'?`/api/profile/dungeon/${v.rid}/bild/${id}`:`/api/profile/dungeon/${v.rid}/portraet/${id}?v=${ver||1}`):(DMI[k+id+':'+(ver||1)]||'');
  return `<img alt="" loading="lazy" data-dmimg="${k}:${esc(id)}:${ver||1}"${src?` src="${esc(src)}"`:''}>`}
async function dmImgFill(w){if(!DG.code)return;for(const im of w.querySelectorAll('img[data-dmimg]:not([src])')){const [k,id,ver]=im.dataset.dmimg.split(':'),key=k+id+':'+ver;
    if(key in DMI){if(DMI[key])im.src=DMI[key];continue}DMI[key]='';
    try{const r=await /*raw: a guest seat's picture as a blob, api() would open the login on a 401*/fetch(k==='b'?'/api/dungeon/bild':'/api/dungeon/portraet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(k==='b'?{code:DG.code,b:id}:{code:DG.code,pid:id})});
      if(!r.ok){delete DMI[key];continue}DMI[key]=URL.createObjectURL(await r.blob())}catch(e){delete DMI[key];continue}
    document.querySelectorAll(`#dgcard img[data-dmimg="${im.dataset.dmimg}"]`).forEach(x=>x.src=DMI[key])}}
function dmAv(mode,v,p,c){return p.bild?`<span class="dm-av dm-avb" data-c="${c}">${dmImg(mode,v,'p',p.pid,p.stufe)}</span>`:`<span class="dm-av" data-c="${c}">${esc((p.name||'?').slice(0,1).toUpperCase())}</span>`}
// the scene picture once (Punkt 7 of 2026-10-24): the newest large at its place in the log, so it scrolls with the
// story and never covers it; older ones small; only when its line left the shown log it opens the feed
const dmNewest=v=>((v.bilder||[]).slice(-1)[0]||{}).b||'';
const dmBildGross=(mode,v,b,ort)=>`<figure class="dm-bild">${dmImg(mode,v,'b',b)}${ort?`<figcaption>${esc(ort)}</figcaption>`:''}</figure>`;
function dmScene(v,mode){const b=(v.bilder||[]).slice(-1)[0];
  return b&&!v.log.some(e=>e.art==='bild'&&e.b===b.b)?dmBildGross(mode,v,b.b,b.ort):''}
const dmMalt=v=>v.bild_malt?`<div class="dm-malt" role="status">🖼 ${esc(v.bild_hint||t('Das Szenenbild wird gemalt …','The scene picture is being painted …'))}</div>`:'';
// better stories: the open threads the panel keeps (promises, quests, questions), the chapter's truth only for the host
// the right column (Dominik 2026-10-24 „sehr durcheinander und lang“): turn and own hero on top, below one tab at a
// time of map, threads and date; the last tab is remembered per device (the host's controls are the console window since
// 2026-10-25)
function dmSeite(v,mode){const hp=dmHandy()?DMA.handy:'';   // on the phone „Karte“ is its own pane, „Held“ shows the others
  const teile=[['karte','🗺',t('Karte','Map'),dmKarte(v,mode)],
    ['faeden','📜',t('Fäden','Threads'),dmThreads(v)],['schrift','✉',t('Schriftstücke','Writings'),dmSchriften(v)],['album','🐉',t('Album','Album'),dmAlbumAlle(v)],['termin','📅',t('Termin','Date'),dmDate(v,mode)]].filter(x=>x[3]&&(hp==='karte'?x[0]==='karte':hp!=='held'||x[0]!=='karte')).map(x=>[x[0],x[1]+'|'+x[2],x[3]]);if(!teile.length)return '';
  if(!DMA.seite){try{DMA.seite=localStorage.getItem('dm-seite')||''}catch(e){}}
  const on=(teile.find(x=>x[0]===DMA.seite)||teile[0])[0];
  return `${teile.length>1?`<div class="lseg dm-seite" role="tablist">${teile.map(x=>`<button type="button" role="tab" aria-selected="${x[0]===on}" class="${x[0]===on?'on':''}" data-dmseite="${x[0]}"><span aria-hidden="true">${x[1].split('|')[0]}</span>${esc(x[1].split('|')[1])}</button>`).join('')}</div>`:''}
    <div class="dm-seitein">${teile.find(x=>x[0]===on)[2]}</div>`}
// the draggable edge between the story and the right column (Dominik 2026-10-25, Vorschlag 3): the width is kept per
// device; arrows move it by DMBR[3], a double tap goes back to the start width; hidden where the table is one column
const DMBR=[260,560,320,16];   // narrowest, widest, start, step in px
function dmBreite(){if(DMA.breite==null){try{DMA.breite=+localStorage.getItem('dm-breite')||0}catch(e){DMA.breite=0}}
  return Math.max(DMBR[0],Math.min(DMBR[1],DMA.breite||DMBR[2]))}
const dmZiehe=()=>`<div class="dm-ziehe" role="separator" aria-orientation="vertical" tabindex="0" aria-valuemin="${DMBR[0]}" aria-valuemax="${DMBR[1]}" aria-valuenow="${dmBreite()}" aria-label="${esc(t('Breite der Spalte, mit den Pfeiltasten oder ziehen','Width of the column, with the arrow keys or by dragging'))}" title="${esc(t('Ziehen: Spalte breiter oder schmaler · Doppelklick: zurück','Drag: column wider or narrower · double click: back'))}"></div>`;
function dmBreiteSetzen(el,w,keep){w=Math.max(DMBR[0],Math.min(DMBR[1],Math.round(w)));DMA.breite=w;const g=el.closest('.dm-grid');if(g)g.style.setProperty('--dm-side',w+'px');el.setAttribute('aria-valuenow',w);
  if(keep){try{localStorage.setItem('dm-breite',String(w))}catch(e){}}}
document.body.addEventListener('pointerdown',e=>{const h=e.target.closest('.dm-ziehe');if(!h||e.button)return;e.preventDefault();
  const x0=e.clientX,w0=dmBreite();h.setPointerCapture(e.pointerId);h.classList.add('on');
  const mv=ev=>dmBreiteSetzen(h,w0+x0-ev.clientX,false),up=()=>{h.classList.remove('on');h.removeEventListener('pointermove',mv);h.removeEventListener('pointerup',up);h.removeEventListener('pointercancel',up);dmBreiteSetzen(h,DMA.breite||w0,true)};
  h.addEventListener('pointermove',mv);h.addEventListener('pointerup',up);h.addEventListener('pointercancel',up)});
document.body.addEventListener('keydown',e=>{const h=e.target.closest&&e.target.closest('.dm-ziehe');if(!h||!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();
  dmBreiteSetzen(h,dmBreite()+(e.key==='ArrowLeft'?DMBR[3]:-DMBR[3]),true)});
document.body.addEventListener('dblclick',e=>{const h=e.target.closest('.dm-ziehe');if(h)dmBreiteSetzen(h,DMBR[2],true)});
// the phone (Punkt 10 of the review of 2026-10-24): one pane at a time, the bar at the bottom picks it (Geschichte, Gruppe,
// Held, Karte); a new turn while another pane is open puts a dot on „Geschichte“. The panel's own bar stays away at the table.
const DMH=[['geschichte','📖','Geschichte','Story'],['gruppe','👥','Gruppe','Group'],['held','📜','Held','Hero'],['karte','🗺','Karte','Map']];
const dmHandy=()=>!!(window.matchMedia&&matchMedia('(max-width:760px)').matches);
function dmUnten(v,mode){const z=DMH.filter(x=>x[0]!=='karte'||v.karte);if(!z.some(x=>x[0]===DMA.handy))DMA.handy='geschichte';
  const neu=DMA.handy!=='geschichte'&&DMA.hzug[mode]>=0&&v.zug>DMA.hzug[mode];
  return `<nav class="dm-unten" aria-label="${esc(t('Spieltisch','Game table'))}">${z.map(x=>`<button type="button" data-dmh="${x[0]}" class="${x[0]===DMA.handy?'on':''}" aria-pressed="${x[0]===DMA.handy}"><span aria-hidden="true">${x[1]}</span>${esc(t(x[2],x[3]))}${neu&&x[0]==='geschichte'?`<em class="dm-hneu" title="${esc(t('Neuer Zug','New turn'))}"></em>`:''}</button>`).join('')}</nav>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmh],#dgcard [data-dmh]');if(!b)return;const g=!!b.closest('#dgcard'),S=g?DG:DM;
  if(DMA.handy==='geschichte'&&b.dataset.dmh!=='geschichte'&&S.v)DMA.hzug[g?'g':'p']=S.v.zug;DMA.handy=b.dataset.dmh;
  g?dgDraw():dmDraw();window.scrollTo(0,0)});
// an open row („Stimme des Erzählers“, „⋯ Mehr“) stays open across the table's repaints
// a tab of „Nur für dich“ in the console
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmgtab]');if(!b)return;DMA.gtab=b.dataset.dmgtab;dmDraw()});
document.addEventListener('toggle',e=>{const d=e.target;if(!(d instanceof Element)||!d.matches('[data-dmauf]'))return;if(d.open)DMA.auf=d.dataset.dmauf;else if(DMA.auf===d.dataset.dmauf)DMA.auf=''},true);
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmseite]');if(!b)return;DMA.seite=b.dataset.dmseite;
  try{localStorage.setItem('dm-seite',DMA.seite)}catch(x){}
  if(b.closest('#dgcard'))dgDraw();else dmDraw()});
function dmThreads(v){const f=v.faeden||[];if(!f.length)return '';return `<ul class="dm-faeden">${f.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`}
// the quest of the prologue, pinned under the turn until a goal is reached (then ticked)
// Aufträge von Personen (LlamaTale idea 2, dungeon_auftraege): the errands the panel gave, with their clues; done ones struck through
const dmAuftraege=v=>(v.auftraege||[]).filter(a=>a.status!=='zurueck').map(a=>`<details class="dm-auftrag dm-errand${a.status==='erfuellt'?' ok':''}"><summary><small>${esc(a.status==='erfuellt'?t('Auftrag erfüllt','Errand done'):t('Auftrag von '+a.von,'Errand from '+a.von))} · 🪙 ${esc(String(a.lohn))}</small><b>${a.status==='erfuellt'?'✓':'📜'} ${esc(a.text)}</b></summary>${a.spuren.map(s=>`<small class="mut">🔎 ${esc(s)}</small>`).join('')}</details>`).join('');
const dmAuftrag=v=>{const a=v.auftrag;return a?`<div class="dm-auftrag${a.ok?' ok':''}"><small>${esc(a.ok?t('Auftrag erfüllt','Quest done'):t('Auftrag','Quest'))}</small><b>${a.ok?'✓':'🎯'} ${esc(a.text)}</b></div>`:''};
function dmTruth(v){const w=v.wahrheit;if(!w)return '';
  return `<details class="adv dm-plan"><summary>${esc(t('Wahrheit dieses Kapitels','Truth of this chapter'))} · ${esc(t('nur du siehst das','only you see this'))}</summary>
    <ul>${w.personen.map(p=>`<li><b>${esc(p.name)}</b>${p.rolle?' · '+esc(p.rolle):''}${p.ziel?` <small class="mut">${esc(t('will: ','wants: ')+p.ziel)}</small>`:''}${p.sprache?` <small class="mut">${esc(t('spricht: ','talks: ')+p.sprache)}</small>`:''}</li>`).join('')}</ul>
    ${w.gruppen.length?`<small class="mut">${esc(t('Gruppen: ','Groups: ')+w.gruppen.map(g=>g.name+(g.will?' ('+g.will+')':'')).join(' · '))}</small>`:''}
    ${w.geheimnisse.length?`<small class="mut">${esc(t('Geheimnisse: ','Secrets: ')+w.geheimnisse.join(' · '))}</small>`:''}</details>`}
// the thing memory (Dominik 2026-10-24 „1 c“): what the story named with fixed features; the host fixes or forgets one
function dmThings(v){const xs=v.dinge;if(!xs||!xs.length)return '';const n=DM.ding,o=document.querySelector('#dmview .dm-dname'),om=document.querySelector('#dmview .dm-dmerk');
  return `<details class="adv dm-plan dm-dinge" data-dmauf="dinge"${DMA.auf==='dinge'||n!=null?' open':''}><summary>${esc(t('Gemerkte Dinge','Kept things'))} · ${esc(t('nur du siehst das','only you see this'))}</summary>
    <small class="mut">${esc(t('So beschreibt der Dungeon-Master diese Dinge immer; widerspricht eine Erzählung, schreibt er sie einmal neu.','The Dungeon Master always describes these things so; when a narration contradicts them, it writes it once again.'))}</small>
    <ul>${xs.map((x,i)=>i===n?`<li class="dm-dedit"><input class="dm-dname" maxlength="40" value="${esc(o?o.value:x.name)}" aria-label="${esc(t('Name','Name'))}"><input class="dm-dmerk" maxlength="80" value="${esc(om?om.value:x.merkmale)}" aria-label="${esc(t('Merkmale','Features'))}"><span><button type="button" class="b pri" data-dmdingsave="${i}">${esc(t('Sichern','Save'))}</button><button type="button" class="b" data-dmding="">${esc(t('Abbrechen','Cancel'))}</button></span></li>`
      :`<li><b>${esc(x.name)}</b>${x.merkmale?' · '+esc(x.merkmale):''}${x.ort?` <small class="mut">${esc(x.ort)}</small>`:''}<span class="dm-dknopf"><button type="button" class="ic-ib" data-dmding="${i}" title="${esc(t('Ändern','Change'))}" aria-label="${esc(t('Ändern','Change')+': '+x.name)}">✏️</button><button type="button" class="ic-ib" data-dmdingweg="${i}" title="${esc(t('Vergessen','Forget'))}" aria-label="${esc(t('Vergessen','Forget')+': '+x.name)}">🗑</button></span></li>`).join('')}</ul></details>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmding],#dmview [data-dmdingsave],#dmview [data-dmdingweg]');if(!b||!DM.rid)return;const B=b.dataset;
  if(B.dmding!==undefined){DM.ding=B.dmding===''?null:+B.dmding;dmDraw();return}
  const n=+(B.dmdingsave||B.dmdingweg),w=$('dmview'),body=B.dmdingweg!==undefined?{n,weg:true}:{n,name:(w.querySelector('.dm-dname')||{}).value||'',merkmale:(w.querySelector('.dm-dmerk')||{}).value||''};
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/dinge`,body,DM);if(d){DM.v=d;DM.at=Date.now();DM.ding=null}dmDraw()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmdaumen]');if(!b)return;const g=!!b.closest('#dgcard'),body={zug:+b.dataset.zug,gut:b.dataset.dmdaumen==='1'};
  try{let d;if(g)d=await dgPub('/api/dungeon/daumen',Object.assign({code:DG.code},body));else{const x=await apiTry(`/api/profile/dungeon/${DM.rid}/daumen`,xjson('POST',body));if(!x.r.ok)throw new Error();d=x.d}
    const v=g?DG.v:DM.v;if(v){v.daumen=d.daumen;v.fall=d.fall;g?dgDraw():dmDraw()}}catch(x){dmSay(g?DG:DM,t('Das hat nicht geklappt.','That did not work.'),true)}});
// „Erzähler-Fehler“ (dungeon_erzaehlstand.py): after a 👎 of one of the last turns a fixed reason, the turn becomes a case
function dmGrund(v,e){const z=String(e.n||1),f=(v.fall||{})[z];if(!v.ich||!v.gruende||e.prolog||(v.daumen||{})[z]!==-1)return '';
  if(f){const g=v.gruende.find(x=>x[0]===f);return `<div class="dm-grund"><span class="pill">${esc(t('Als Erzähler-Fehler gemeldet','Reported as a narrator error'))}: ${esc(g?g[1]:f)}</span></div>`}
  if(!(e.n>=v.zug-3))return '';
  return `<div class="dm-grund" role="group" aria-label="${esc(t('Was war falsch?','What was wrong?'))}"><span>${esc(t('Was war falsch?','What was wrong?'))}</span>${v.gruende.map(([k,l])=>`<button type="button" data-dmgrund="${esc(k)}" data-zug="${z}">${esc(l)}</button>`).join('')}</div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmgrund]');if(!b)return;const g=!!b.closest('#dgcard'),body={zug:+b.dataset.zug,gut:false,grund:b.dataset.dmgrund};
  b.closest('.dm-grund').querySelectorAll('button').forEach(x=>x.disabled=true);
  try{let d;if(g)d=await dgPub('/api/dungeon/daumen',Object.assign({code:DG.code},body));else{const x=await apiTry(`/api/profile/dungeon/${DM.rid}/daumen`,xjson('POST',body));if(!x.r.ok)throw new Error();d=x.d}
    const v=g?DG.v:DM.v;if(v){v.daumen=d.daumen;v.fall=d.fall;g?dgDraw():dmDraw()}}catch(x){dmSay(g?DG:DM,t('Das hat nicht geklappt.','That did not work.'),true)}});
// staying with it (Stufe 5a): the game date, „🔔 Mitteilungen“ of the own seat, the look back after a longer break
const DMRB={};
function dmDate(v,mode){const host=mode==='p'&&v.gastgeber&&v.status!=='ende',has=v.termin*1000>Date.now();if(!has&&!host&&v.melden==null)return '';
  const pad=n=>String(n).padStart(2,'0'),d=new Date(has?v.termin*1000:Date.now()+86400000),loc=`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `<div class="dm-termin">${has?`<b>📅 ${esc(dmWhen(v.termin))}</b><button type="button" class="b" data-dmics="1">${esc(t('In den Kalender','Add to calendar'))}</button>`:`<small class="mut">${esc(t('Noch kein Termin.','No date yet.'))}</small>`}
    ${host?`<div class="dm-tset"><input type="datetime-local" class="dm-tin" value="${loc}" aria-label="${esc(t('Nächster Spieltermin','Next game date'))}"><button type="button" class="b" data-dmtermin="1">${esc(has?t('Termin ändern','Change date'):t('Termin setzen','Set date'))}</button>${has?`<button type="button" class="b" data-dmtermin="0">${esc(t('Termin weg','Remove date'))}</button>`:''}</div>`:''}
    ${v.melden!=null&&mode==='p'?`<button type="button" class="b" data-dmmelden="${v.melden?0:1}">${esc(v.melden?t('🔔 Mitteilungen an','🔔 Notes on'):t('🔕 Mitteilungen aus','🔕 Notes off'))}</button><small class="mut">${esc(t('Eine Mitteilung, wenn du dran bist, eine Erinnerung, wenn der Zug auf dich wartet, und eine 15 Minuten vor dem Termin.','A note when it is your turn, a reminder when the turn waits for you and one 15 minutes before the date.'))}</small>`:''}</div>`}
function dmBack(v){const r=v.rueckblick;if(!r)return '';
  if(DMRB[v.rid]===undefined){let last=0;try{last=+localStorage.getItem('dm-zuletzt-'+v.rid)||0}catch(e){}DMRB[v.rid]=!!last&&Date.now()-last>12*3600000}
  try{localStorage.setItem('dm-zuletzt-'+v.rid,String(Date.now()))}catch(e){}
  if(!DMRB[v.rid])return '';
  return `<div class="dm-rueck"><h5>${esc(t('Was letztes Mal geschah','Last time'))} · ${esc(t('bis Zug','up to turn'))} ${r.zug}</h5>${r.erzaehlt.map(x=>`<p>${esc(x)}</p>`).join('')}
    ${r.beute.length?`<small class="mut">${esc(t('Beute: ','Loot: ')+r.beute.join(' · '))}</small>`:''}${r.stufen.length?`<small class="mut">${esc(t('Stufen: ','Levels: ')+r.stufen.join(' · '))}</small>`:''}
    <button type="button" class="b p" data-dmrueck="1">${esc(t('Weiter spielen','Play on'))}</button></div>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmrueck]');if(!b)return;const m=b.closest('#dgcard')?'g':'p',v=m==='g'?DG.v:DM.v;if(v)DMRB[v.rid]=false;m==='g'?dgDraw():dmDraw()});
// the date as a calendar file: the browser saves it, the calendar app opens it
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmics]');if(!b)return;const g=!!b.closest('#dgcard');
  try{const r=g?await /*raw: public route of a guest seat*/fetch('/api/dungeon/termin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code})}):await api(`/api/profile/dungeon/${DM.rid}/termin.ics`);
    if(!r.ok)throw new Error();const u=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=u;a.download='dungeon-master.ics';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),5000)}
  catch(x){dmSay(g?DG:DM,t('Den Termin gibt es nicht mehr.','The date is gone.'),true)}});
function dmBar(v,max,cls){const pc=Math.max(0,Math.min(100,Math.round(100*v/(max||1))));return `<i class="dm-bar ${cls||''}"><em style="width:${pc}%"></em></i>`}
// pictures of items and spells (dungeon_dingbild.py, 5i): the picture in its rarity's frame, the kind's sign until it is painted
// big: the merchant's and the detail's large picture; everywhere else the small copy (Dominik 2026-10-25, slow over the proxy)
function dmDing(it,big){return it.bild?`<span class="dm-ding"><img alt="" loading="lazy" decoding="async" data-dmdbild="${esc(it.bild)}"${big?'':' data-dmdk="1"'}></span>`:it.zeichen?`<span class="dm-ding dm-dz" aria-hidden="true">${esc(it.zeichen)}</span>`:''}
async function dmDingFill(w,mode){for(const im of w.querySelectorAll('img[data-dmdbild]:not([src])')){const n=im.dataset.dmdbild,k=!!im.dataset.dmdk,key=(k?'k':'d')+n;
    if(mode==='p'){im.src='/api/profile/dungeon/ding/'+encodeURIComponent(n)+(k?'?klein=1':'');continue}
    if(key in DMI){if(DMI[key])im.src=DMI[key];continue}DMI[key]='';
    try{const r=await /*raw: a guest seat's picture as a blob, api() would open the login on a 401*/fetch('/api/dungeon/ding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,name:n,klein:k})});
      if(!r.ok){delete DMI[key];continue}DMI[key]=URL.createObjectURL(await r.blob())}catch(e){delete DMI[key];continue}
    document.querySelectorAll(`#dgcard img[data-dmdbild="${n}"]${k?'[data-dmdk]':':not([data-dmdk])'}`).forEach(x=>x.src=DMI[key])}}
// ▲/▼ against what the hero wears and „passt“ for the class (Gegenstands-Punkt 10), from the panel's numbers of this view
let DMCMP={};
function dmCmp(it){const c=it&&DMCMP[it.i];if(!c)return '';
  return ` <span class="dm-cmp ${c.besser>0?'up':c.besser<0?'dn':'eq'}">${c.besser>0?'▲ '+esc(t('besser als deins','better than yours')):c.besser<0?'▼ '+esc(t('schwächer als deins','weaker than yours')):'= '+esc(t('wie deins','like yours'))}</span>${c.passt?'':` <span class="dm-cmp no">✗ ${esc(t('nicht für deine Klasse','not for your class'))}</span>`}`}
function dmItem(it,acts){return `<div class="dm-item ${DMSEL[it.selten]||''}"${it.i?` data-dmi="${esc(it.i)}"`:''}><div>${dmDing(it)}<b>${esc(it.name)}</b>${dmCmp(it)}${it.n>1?` <span class="pill">×${it.n}</span>`:''} <small>${esc(it.selten_name)}</small>${it.legende?` <small class="dm-leg">✦ ${t('Einzelstück','One of a kind')}</small>`:''}${it.kg?` <small>· ${String(it.kg).replace('.',L==='en'?'.':',')} kg</small>`:''}</div>${it.fund?`<small class="dm-ifund">${esc(t('Gefunden in: ','Found in: ')+it.fund)}</small>`:''}${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}${it.info?`<small class="dm-iinfo">${esc(it.info)}</small>`:''}<small>${it.zeilen.map(dmFx).join(' · ')}</small>${acts||''}</div>`}
// the prologue's hold (Dominik 2026-10-24 „keinerlei anhalts punkt was zu tun ist“): why each hero is here, and
// „Was ihr tun könnt“ as buttons that write the possibility into the own field (own ideas go on as before)
function dmProlog(v,e){const nm=pid=>((v.plaetze||[]).find(p=>p.pid===pid)||{}).name||'',hk=Object.entries(e.haken||{}).filter(([p])=>nm(p));
  return `${hk.length?`<ul class="dm-haken">${hk.map(([p,x])=>`<li${p===v.pid?' class="me"':''}><b>${esc(nm(p))}</b> ${esc(x)}</li>`).join('')}</ul>`:''}${(e.wege||[]).length?`<div class="dm-wege"><small>${esc(t('Was ihr tun könnt','What you can do'))}</small>${e.wege.map(x=>`<button type="button" class="dm-weg" data-dmweg="${esc(x)}">${esc(x)}</button>`).join('')}</div>`:''}`}
// Spieler anleiten (dungeon_anleiten.py): „Das kannst du hier“, buttons only from the scene's data and the narrator's
// checked ways; a tap puts the text into the field like the prologue's ways, „· Geschick“ is the value that likely counts
function dmKannst(k){return `<div class="dm-wege dm-kannst"><small>${esc(t('Das kannst du hier','What you can do here'))}</small>${k.map(x=>`<button type="button" class="dm-weg" data-dmweg="${esc(x.text)}">${esc(x.text)}${x.wert?` <small class="mut">· ${esc(x.wert)}</small>`:''}</button>`).join('')}</div>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmweg]');if(!b)return;const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
  ta.value=b.dataset.dmweg;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus()});
// Heldenmut (Idee 8): 👍 for another player's action of the last three turns; half of the others give its hero a second one
function dmLob(v,e){if(!v.mut||!v.ich||e.pid===v.pid||!(e.n<v.zug&&e.n>=v.zug-3))return '';const on=(v.mut.lob||[]).includes(e.n+':'+e.pid),l=t('Mutig! Ein 👍 für Heldenmut','Brave! A 👍 for heroic courage');
  return `<button type="button" class="ic-ib dm-lob${on?' on':''}" data-dmlob="${esc(e.pid)}" data-zug="${e.n}" title="${esc(l)}" aria-label="${esc(l)}" aria-pressed="${on}"${on?' disabled':''}>👍</button>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmlob]');if(!b)return;const g=!!b.closest('#dgcard'),body={zug:+b.dataset.zug,aktion:b.dataset.dmlob};b.disabled=true;
  try{let d;if(g)d=await dgPub('/api/dungeon/daumen',Object.assign({code:DG.code},body));else{const x=await apiTry(`/api/profile/dungeon/${DM.rid}/daumen`,xjson('POST',body));if(!x.r.ok)throw new Error();d=x.d}
    const v=g?DG.v:DM.v;if(v){v.mut=d.mut;g?dgDraw():dmDraw()}}catch(x){b.disabled=false;dmSay(g?DG:DM,t('Das hat nicht geklappt.','That did not work.'),true)}});
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmmut]');if(!b)return;const m=b.dataset.dmmut;DMA.mut[m]=DMA.mut[m]?0:1;b.classList.toggle('on',!!DMA.mut[m]);b.setAttribute('aria-pressed',String(!!DMA.mut[m]))});
// Sprachen der Völker (D&D idea 7, dungeon_sprachen): the sounds for everyone, the meaning only for who knows the tongue
function dmFremd(v,e){const f=e.fremd,s=(v.fremd||{})[String(e.k)];return `<div class="dm-npc dm-fremd">${dmGesicht(v,f.name)}<em>${esc(f.name)} · ${esc(f.sprache||'')}</em><p>„${esc(f.laut)}“</p><p class="dm-fremdt">${s?esc(t('du verstehst: ','you understand: '))+'„'+esc(s)+'“':'('+esc(t('unverständlich','not understood'))+', '+esc(f.sprache||'')+')'}</p></div>`}
function dmLog(v,e,col){const W=v.werte||{},sys=Array.isArray(e.text)?e.text[L==='en'?1:0]:e.text;
  if(e.art==='dm'){const my=(v.daumen||{})[String(e.n||1)]||0,th=v.ich?`<span class="dm-thumbs">${[[1,'👍',t('Gut erzählt','Well told')],[-1,'👎',t('Nicht so gut','Not so good')]].map(([g,i,l])=>`<button type="button" class="ic-ib${my===g?' on':''}" data-dmdaumen="${g}" data-zug="${e.n||1}" title="${esc(l)}" aria-label="${esc(l)}" aria-pressed="${my===g}">${i}</button>`).join('')}</span>`:'';
    return `<div class="dm-dm" data-dmzug="${e.prolog?0:(e.n||1)}"><div class="dm-n">${esc(e.prolog?t('Prolog','Prologue'):t('Zug','Turn')+' '+(e.n||1))}${e.neu?` <span class="pill ok">${esc(t('neu erzählt','told again'))}</span>`:''}${v.neu_laeuft&&v.neu_laeuft===e.n?` <span class="pill on">${esc(t('wird neu erzählt …','being told again …'))}</span>`:''}${th}</div><p>${dmSaetze(v,e)}</p>${dmGrund(v,e)}${(e.npc||[]).filter(n=>!n.im_text).map(n=>`<div class="dm-npc">${dmGesicht(v,n.name)}<em>${esc(n.name)}</em><p>„${esc(n.sagt)}“</p></div>`).join('')}${(e.helden||[]).map(n=>`<div class="dm-npc dm-heldsagt"><em>💬 ${esc(n.name)}</em><p>„${esc(n.sagt)}“</p></div>`).join('')}${e.fremd?dmFremd(v,e):''}${e.prolog?dmProlog(v,e):''}</div>`}
  if(e.art==='aktion')return `<div class="dm-act">${dmAv(v.mode,v,Object.assign({name:e.name},(v.plaetze||[]).find(p=>p.pid===e.pid)||{}),col?col(e.pid):0)}<div class="dm-bub"><b>${esc(e.name)}</b><p>${esc(e.text)}</p></div>${dmLob(v,e)}${dmHide(v,'aktion',e.n,e.pid)}</div>`;
  if(e.art==='wurf')return dmPK(v,e,`<span class="dm-d20">${e.w}</span>${dmBeleg(e)}`)+(e.knapp?`<div class="dm-knappz">⚖ ${esc(t('Knapp daneben, mit Preis: ','Near miss, at a price: ')+(e.preis_t||''))}</div>`:'')
    +(e.hilfe||e.gruppe?`<div class="dm-knappz">${e.hilfe?'🤝 '+esc(t('mit Hilfe von ','with help from ')+e.hilfe):''}${e.hilfe&&e.gruppe?' · ':''}${e.gruppe?'👥 '+esc(t('Gruppenprobe: die Hälfte reicht','group check: half is enough')):''}</div>`:'')+dmLeiste(e);
  if(e.art==='folge'&&e.was==='heilung'&&!e.zahl)return `<div class="dm-sys mut">${esc(t(e.name+': schon volles Leben ('+e.leben+')',e.name+': already at full life ('+e.leben+')'))}</div>`;
  if(e.art==='folge')return `<div class="dm-sys ${e.was==='heilung'?'ok':'bad'}">${esc(e.name)}: ${e.was==='heilung'?'+':'−'}${e.zahl} ${esc(t('Leben','life'))} (${esc(t('jetzt','now'))} ${e.leben})${e.weniger?' · '+esc(t(e.weniger+' weniger durch Eisenhaut',e.weniger+' less by iron skin')):''}${e.von?' · '+esc(t('von ','by ')+e.von):''}${e.grund==='verschnaufen'?' · '+esc(t('verschnauft nach dem Kampf','catches breath after the fight')):''}${e.probe?' · '+esc(t('Probe „'+e.probe+'“ misslungen','check "'+e.probe+'" failed')):''}${e.sart?dmArt(e):''}</div>`;
  if(e.art==='begegnung')return dmBegegnung(e);
  if(e.art==='angriff')return dmAngriff(e,W);
  if(e.art==='ehrung')return dmEhrung(v,e);
  if(e.art==='gefaehrte'){const s={sold:[`🤝 ${e.name} bekommt den Lohn für dieses Kapitel: ${e.gold} Gold.`,`🤝 ${e.name} gets the pay for this chapter: ${e.gold} gold.`],ohne_sold:[`🤝 ${e.name} bleibt auch ohne Lohn.`,`🤝 ${e.name} stays even without pay.`],gegangen:[`🤝 Ohne Lohn geht ${e.name} eigene Wege.`,`🤝 Without pay ${e.name} goes their own way.`],am_boden:[`🤝 ${e.name} geht zu Boden und kämpft in diesem Kampf nicht mehr.`,`🤝 ${e.name} goes down and fights no more in this fight.`],geflohen:[`🤝 ${e.name} verliert den Mut und flieht aus diesem Kampf.`,`🤝 ${e.name} loses heart and flees this fight.`]}[e.was];return s?`<div class="dm-sys${e.was==='sold'||e.was==='ohne_sold'?' ok':''}">${esc(t(...s))}</div>`:''}   // companions (round 2, idea 9)
  if(e.art==='wunsch')return `<div class="dm-sys ok">💖 ${esc(t('Der Herzenswunsch von '+e.name+' hat sich erfüllt.',e.name+'\'s heart\'s wish has come true.'))}</div>`;   // a heart's wish come true (round 2, idea 7), never the wish
  if(e.art==='verrat')return `<div class="dm-sys">🤫 ${esc(t(e.an+' erzählt weiter, was '+e.name+' geflüstert hat.',e.an+' passes on what '+e.name+' whispered.'))}</div>`;   // a whisper told on (round 2, idea 5)
  if(e.art==='ansage')return `<div class="dm-sys dm-ansage">⚠ ${(e.ansagen||[]).map(x=>esc(x.t)).join('<br>⚠ ')}</div>`;   // the foes' next blows (round 2, idea 2)
  if(e.art==='kapitel_ende')return `<div class="dm-sys">📖 ${esc(t('Kapitel '+e.kapitel+' ist zu Ende.','Chapter '+e.kapitel+' has ended.'))}</div>`;
  if(e.art==='rast')return `<div class="dm-narbez">${e.rast==='lang'?'🔥 '+esc(t('Lange Rast','Long rest')):'☕ '+esc(t('Kurze Rast','Short rest'))} · ${esc(e.landschaft||'')}${e.gestoert?' · '+esc(t('Nacht gestört','night disturbed')):''}</div>`;   // a rest (D&D idea 4)
  if(e.art==='reise'){const E={ruhig:t('ruhige Reise','a quiet journey'),ausgeruht:t('ausgeruht angekommen','arrived rested'),hungrig:t('hungrig angekommen','arrived hungry'),ueberrascht:t('überrascht','caught off guard'),verirrt:t('verirrt, ein Tag mehr','lost, a day more')};return `<div class="dm-narbez">🧭 ${esc(t('Reise','Journey'))} · ${esc(String(e.etappen||0))} ${esc(t('Etappen','stages'))} · ${esc(e.landschaft||e.land||'')} · ${esc(E[e.ergebnis]||'')}${(e.rollen||[]).map(x=>`<br>${x.ok?'✓':'✗'} ${esc(x.name||'')} (${esc(x.rolle||'')}): ${esc(String(x.w))}${x.bonus<0?'−':'+'}${esc(String(Math.abs(x.bonus||0)))} = ${esc(String(x.gesamt))} / ${esc(String(x.schwer))}`).join('')}${e.t?'<br>'+esc(e.t):''}</div>`;}   // a journey (D&D idea 9)
  if(e.art==='narbe')return `<div class="dm-narbez">${e.pflaster?'🩹':'🩸'} ${esc(t(`${e.name}: ${e.t[0]}`,`${e.name}: ${e.t[1]}`))}${e.folge?` <span class="pill warn">${esc(e.folge)}</span>`:''}</div>`;   // a wound (D&D idea 8)
  if(e.art==='schrift'){const s=(v.schrift||[]).find(x=>x.id===e.sid);return s?dmPergament(v,s):''}   // only a writing this seat may see
  if(e.art==='gegner'&&e.was==='phase2')return `<div class="dm-sys dm-phase2">👑 ${esc(t(e.gegner+' ist schwer getroffen und wird wütend: zweite Phase, trifft leichter.',e.gegner+' is badly hurt and turns furious: second phase, hits more easily.'))}</div>`;
  if(e.art==='rettung')return `<div class="dm-wurf ${e.ok?'ok':'bad'}"><span class="dm-d20">${e.w}</span>${esc(t('Rettungswurf ','Save '))}${esc(e.name)} · ${esc(W[e.wert]||e.wert)} = <b>${e.gesamt}</b> ${esc(t('gegen','vs'))} ${e.gegen} · ${e.ok?esc(t('widersteht: ','resists: ')+e.zustand):`<b>${esc(e.zustand)}</b>`}</div>`;
  // a state's damage carries zustand; a hero's state (boden, auf, ohnmacht, tot) carries was and is drawn below
  if(e.art==='zustand'&&e.zustand)return `<div class="dm-sys bad">🔥 ${esc(t(e.name+' leidet: '+e.zustand+', −'+e.schaden+' Leben.',e.name+' suffers: '+e.zustand+', −'+e.schaden+' life.'))}</div>`;
  if(e.art==='gegner')return `<div class="dm-sys ${e.was==='besiegt'?'ok':'mut'}">${e.was==='besiegt'?'✝':'🏃'} ${esc({besiegt:t(e.gegner+' ist besiegt.',e.gegner+' is defeated.'),geflohen:t(e.gegner+' flieht.',e.gegner+' flees.'),aufgegeben:t(e.gegner+' gibt auf und läuft davon.',e.gegner+' gives up and runs off.')}[e.was]||e.gegner)}</div>`;
  if(e.art==='kampf')return `<div class="dm-akt">⚔ ${esc({sieg:t('Der Kampf ist gewonnen.','The fight is won.'),frieden:t('Der Kampf endet ohne Sieger.','The fight ends without a winner.'),flucht:t('Die Gruppe entkommt.','The group gets away.'),gnade:t('Der Kampf ist verloren, aber niemand stirbt.','The fight is lost, but nobody dies.')}[e.was]||'')} <small class="mut">${esc(t(e.besiegt+' besiegt, '+e.geflohen+' geflohen',e.besiegt+' defeated, '+e.geflohen+' fled'))}${e.ep?' · +'+e.ep+' '+esc(t('EP für jeden','XP each')):''}</small></div>`;
  if(e.art==='zustand')return `<div class="dm-zstz" data-z="${esc(e.was)}">${{boden:'⚠',auf:'✚',ohnmacht:'💤',tot:'✝',gnade:'🕊',stabil:'🛌'}[e.was]||''} ${esc(e.was==='boden'?t(e.name+' liegt am Boden. Ab dem nächsten Zug würfelt das Panel Rettungswürfe.',e.name+' is down. From the next turn the panel rolls death saves.')
    :e.was==='gnade'?t('Ein Fremder findet '+e.name+' und bringt ihn in Sicherheit. Er erwacht mit 1 Leben'+(e.gold?', ohne '+e.gold+' Gold':'')+(e.ding?', ohne '+e.ding:'')+'.','A stranger finds '+e.name+' and brings them to safety. They wake with 1 life'+(e.gold?', without '+e.gold+' gold':'')+(e.ding?', without '+e.ding:'')+'.')
    :e.was==='stabil'?t(e.name+' ist stabil, aber bewusstlos. Heilung hilft auf, ohne Kampf kommt '+e.name+' mit 1 Leben zu sich.',e.name+' is stable but unconscious. Healing gets them up; with no fight they come to with 1 life.')
    :e.was==='auf'?t(e.name+' steht wieder auf.',e.name+' is back on their feet.'):e.was==='ohnmacht'?t(e.name+' ist ohnmächtig und wacht im nächsten Kapitel auf.',e.name+' is unconscious and wakes in the next chapter.')
    :t(e.name+' ist gefallen.'+(e.dinge||e.gold?' Was er trug, liegt hier.':''),e.name+' has fallen.'+(e.dinge||e.gold?' What they carried lies here.':'')))}</div>`;
  if(e.art==='todeswurf')return `<div class="dm-zstz" data-z="${e.ok?'auf':'boden'}">🎲 ${esc(t(e.name+' würfelt einen Rettungswurf: '+e.wurf+(e.wurf===20?', sofort wieder auf!':e.wurf===1?', zählt doppelt.':e.ok?', gelungen.':', misslungen.')+' ✓'+e.erfolge+' ✗'+e.fehl,e.name+' rolls a death save: '+e.wurf+(e.wurf===20?', up at once!':e.wurf===1?', counts twice.':e.ok?', success.':', failure.')+' ✓'+e.erfolge+' ✗'+e.fehl))}</div>`;
  if(e.art==='orakel'){const A={ja_und:t('Ja, und …','Yes, and …'),ja:t('Ja','Yes'),nein:t('Nein','No'),nein_und:t('Nein, und …','No, and …')},li=L==='en'?1:0;
    return `<div class="dm-orakel">🔮 ${e.frage?`<b>${esc(e.frage)}</b> → <b class="dm-oant" data-a="${esc(e.antwort)}">${esc(A[e.antwort]||'')}</b> <small class="mut">${e.w} ${esc(t('von 100, bis','of 100, up to'))} ${e.chance} · ${esc(t('Chaos','chaos'))} ${e.chaos}</small>`:esc(t('Orakel','Oracle'))}${e.ereignis?`<div>⚡ ${esc(t('Ereignis: ','Event: ')+e.ereignis[li])}</div>`:''}${(e.zuege||[]).map(z=>`<div><small class="mut">${esc(z.name[li])}:</small> ${esc(z.t[li])}</div>`).join('')}</div>`}
  if(e.art==='fraktion')return `<div class="dm-sys ${e.was==='voll'?'bad':'mut'}">⏳ ${esc(e.was==='voll'?t(e.name+' hat erreicht, was sie wollten. Die Welt ist nicht mehr dieselbe.',e.name+' have got what they wanted. The world is not the same any more.')
    :e.was==='hilft'?t('Die Helden bringen '+e.name+' ihrem Ziel näher: '+e.stand+' von '+e.felder+'.','The heroes bring '+e.name+' closer to their goal: '+e.stand+' of '+e.felder+'.')
    :t('Die Helden stören '+e.name+': die Uhr fällt auf '+e.stand+' von '+e.felder+'.','The heroes hinder '+e.name+': the clock falls to '+e.stand+' of '+e.felder+'.'))}</div>`;
  if(e.art==='geste')return `<div class="dm-sys mut">🤲 ${esc(e.text[L==='en'?1:0])}</div>`;   // a small gesture (LlamaTale idea 7, dungeon_nsc.geste)
  if(e.art==='nsc')return `<div class="dm-sys ${e.haltung>0?'ok':e.haltung<0?'bad':'mut'}">🤝 ${esc(e.text[L==='en'?1:0])}</div>`;
  if(e.art==='zufall')return `<div class="dm-sys ${e.treffer?'bad':'mut'}">🎲 ${esc(t('Zufallsregel','Random rule'))} „${esc(e.regel)}“${e.name?' ('+esc(e.name)+')':''}: ${e.w} ${esc(t('von 100, bis','of 100, up to'))} ${e.prozent} ${esc(e.treffer?t('→ trifft','→ hits'):t('→ nichts','→ nothing'))}</div>`;
  if(e.art==='kraft')return `<div class="dm-zauber">${e.wie==='heilen'?'✨ '+esc(t(e.name+' heilt '+e.fuer+' mit '+e.kraft+'.',e.name+' heals '+e.fuer+' with '+e.kraft+'.')):e.wie==='wiederbeleben'?'✨ '+esc(t(e.name+' holt '+e.fuer+' mit '+e.kraft+' zurück.',e.name+' brings '+e.fuer+' back with '+e.kraft+'.')):'🛡 '+esc(t(e.name+' fängt mit '+e.kraft+' den Treffer für '+e.fuer+' ab.',e.name+' takes the hit for '+e.fuer+' with '+e.kraft+'.'))}</div>`;
  if(e.art==='rune')return `<div class="dm-sys ok dm-runez">ᚱ ${esc(e.was==='fund'?t('Fund für '+e.name+': '+e.wort+' '+e.rune+'.','Find for '+e.name+': '+e.wort+' '+e.rune+'.'):t(e.name+' setzt '+e.wort+' '+e.rune+' in '+e.ding+' ein. Sie sitzt jetzt fest.',e.name+' sets '+e.wort+' '+e.rune+' into '+e.ding+'. It stays in for good.'))}</div>`;   // Runen und Sockel (dungeon_runen)
  if(e.art==='beute')return `<div class="dm-beute"><div class="dm-n">${esc(t('Beute für ','Loot for '))}${esc(e.name)}</div><div data-dmbeute="${esc('b:'+e.n+':'+(e.item&&e.item.i||''))}">${dmItem(e.item)}</div>${e.boden?`<small class="mut">${esc(t('Zu schwer oder kein Platz: liegt hier am Boden.','Too heavy or no room: lies here on the ground.'))}</small>`:''}${e.gold?`<small class="mut">${esc(t('Gold für jeden: ','Gold for everyone: '))}${e.gold}</small>`:''}</div>`;
  if(e.art==='markt')return `<div class="dm-akt">⚖ ${esc(e.name)} ${esc(e.auf?t('bietet hier Waren an.','offers goods here.'):t('zieht weiter.','moves on.'))}</div>`;
  if(e.art==='quest'){const w={genommen:t('nimmt','takes'),gefunden:t('findet','finds'),gegeben:t('gibt','gives'),abgelegt:t('legt ab:','puts down:'),verbraucht:t('braucht auf:','uses up:')}[e.was]||e.was;
    return `<div class="dm-sys dm-qline">✦ ${e.wer?esc(e.wer)+' ':''}${esc(e.wer?w:t('Hier liegt','Lying here:'))} <b>${esc(e.name)}</b>${e.an?' '+esc(t('an','to'))+' '+esc(e.an):''}</div>`}
  if(e.art==='handel'){const w={kauf:t('kauft','buys'),verkauf:t('verkauft','sells'),erkannt:t('erkennt','identifies'),geben:t('gibt','gives')}[e.was]||e.was;return `<div class="dm-sys mut">⚖ ${esc(e.name)} ${esc(w)} <b>${esc(e.ding)}</b>${e.gold?' · '+e.gold+' '+esc(t('Gold','gold')):''}</div>`}
  if(e.art==='zauber')return `<div class="dm-zauber">✦ ${esc(e.name)} ${esc(t('wirkt','casts'))} <b>${esc(e.zauber)}</b>${e.gruppe?' '+esc(t('auf die Gruppe','on the group')):''}: ${esc(e.satz)}${(e.heilt||[]).map(x=>' · '+esc(x.name)+' +'+(+x.zahl||0)+' '+esc(t('Leben','life'))).join('')}</div>`;
  if(e.art==='dienst')return `<div class="dm-sys ok dm-dienst">🏘 ${esc(sys)}</div>`;
  if(e.art==='ooc'){const f=e.fen==='haendler'&&v.markt?['haendler','⚖ '+t('Händler','Merchant')]:e.fen==='pult'&&v.gastgeber?['pult','🎲 '+t('Spielleiter-Pult','Game master console')]:null;   // typed buying or resting (Review 27.10. Paket 6): the window that does it
    return `<div class="dm-ooc">(OOC: ${esc(e.text)})${f?` <button type="button" class="b" data-dmfen="${f[0]}">${esc(f[1])} ›</button>`:''}</div>`}
  if(e.art==='bild')return !(v.bilder||[]).some(x=>x.b===e.b)?'':e.b===dmNewest(v)?dmBildGross(v.mode,v,e.b,e.ort):`<div class="dm-bildk">${dmImg(v.mode,v,'b',e.b)}${e.ort?`<small class="mut">🖼 ${esc(e.ort)}</small>`:''}</div>`;
  if(e.art==='akt')return `<div class="dm-akt">❖ ${esc(sys||'')}</div>`;
  if(e.art==='ep')return `<div class="dm-sys mut">${esc(e.name)} +${e.zahl} EP${(e.grund||[]).length?' ('+esc(e.grund.map(g=>t(...(DMEPGRUND[g]||[g,g]))).join(', '))+')':''}${e.ende?' · '+esc(t('am Ende der Runde gutgeschrieben','credited at the end of the round')):e.tisch?' · '+esc(t('noch am Tisch, zählt am Ende der Runde','still at the table, counts at the end of the round')):''}</div>`;
  if(e.art==='stufe')return `<div class="dm-stufe">★ ${esc(e.name)} ${esc(t('erreicht Stufe','reaches level'))} ${e.stufe}!</div>`;
  return `<div class="dm-sys mut">${esc(sys||'')}</div>`}
// what can be done with an item in the own bag (side column, hero sheet, item window)
function dmActs(v,it){const h=v.ich,others=v.plaetze.filter(p=>!p.frei&&!p.ich);
  const give=it=>others.length?`<select data-dmgive="${esc(it.i)}" aria-label="${esc(t('Geben an','Give to'))}"><option value="">${esc(t('Geben …','Give …'))}</option>${others.map(p=>`<option value="${esc(p.pid)}">${esc(p.name)}</option>`).join('')}</select>`:'';
  const m=v.markt,rolle=h.tasche.find(x=>x.erkennt),open=v.status!=='ende';
  const know=it=>it.u?(rolle&&rolle.i!==it.i?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}" data-mit="${esc(rolle.i)}">${esc(t('Mit Rolle erkennen','Identify with scroll'))}</button>`:'')+(m&&m.erkennen[it.i]?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}"${h.gold<m.erkennen[it.i]?' disabled':''}>${esc(t('Erkennen lassen','Have it named'))} · ${m.erkennen[it.i]} ${esc(t('Gold','gold'))}</button>`:''):'';
  return open?`<div class="dm-iacts">${it.platz.length&&it.n===1?`<button type="button" class="b" data-dmhero="anlegen" data-i="${esc(it.i)}">${esc(t('Anlegen','Equip'))}</button>`:''}${it.art==='trank'?`<button type="button" class="b" data-dmhero="${it.oel?'auftragen':'trinken'}" data-i="${esc(it.i)}">${esc(it.oel?t('Auf die Waffe','On the weapon'):t('Trinken','Drink'))}</button>`:''}${it.art==='zauber'?`<button type="button" class="b" data-dmhero="wirken" data-i="${esc(it.i)}">${esc(t('Wirken','Cast'))}</button>`:''}${know(it)}${m&&m.verkauf[it.i]?`<button type="button" class="b" data-dmhero="verkaufen" data-i="${esc(it.i)}">${esc(t('Verkaufen','Sell'))} · ${m.verkauf[it.i]} ${esc(t('Gold','gold'))}</button>`:''}${give(it)}<button type="button" class="b" data-dmhero="fallen" data-i="${esc(it.i)}" title="${esc(t('Hier ablegen, die Gruppe kann es aufheben','Put it down here, the group can pick it up'))}">${esc(t('Hinlegen','Put down'))}</button></div>`:''}
// the hero sheet (Dominik 2026-10-24 „alles“): the portrait large, the values as tiles, below one tab open at a time
// (Ausrüstung, Das kann ich, Tasche, Werte verteilen), the last one kept on this device
const DMBT={t:null},DMBTABS=['aus','kann','tasche','werte'];
function dmBTab(){if(DMBT.t===null){try{DMBT.t=localStorage.getItem('dm-bogen')||''}catch(e){DMBT.t=''}}return DMBTABS.includes(DMBT.t)?DMBT.t:'aus'}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmbt]');if(!b)return;DMBT.t=b.dataset.dmbt;try{localStorage.setItem('dm-bogen',DMBT.t)}catch(x){}
  if(!b.dataset.dmfen)(b.closest('#dgcard')?dgDraw():dmDraw())});
// the hero's places for what it wears (SLOTS of dungeon.py), one list for the sheet and the heroes tab
const dmSlots=()=>({kopf:t('Kopf','Head'),hals:t('Hals','Neck'),koerper:t('Körper','Body'),haupthand:t('Haupthand','Main hand'),nebenhand:t('Nebenhand','Off hand'),haende:t('Hände','Hands'),guertel:t('Gürtel','Belt'),fuesse:t('Füße','Feet'),ring1:t('Ring','Ring'),ring2:t('Ring','Ring')});
// Dominik 2026-10-25 „unter dem Reiter Helden … was hat er für Gegenstände, Gold und so weiter“: what a kept hero wears
// and carries, with where each thing was found, to look at between the rounds (changed only at the table)
function dmHeroThings(h){const slot=dmSlots(),an=Object.entries(h.an||{}).filter(([,it])=>it),bag=h.tasche||[];
  const n=an.length+bag.reduce((a,x)=>a+(x.n||1),0);
  return `<details class="dm-hdet"><summary>🎒 ${esc(t('Ausrüstung und Tasche','Equipment and bag'))} · ${n} ${esc(n===1?t('Ding','thing'):t('Dinge','things'))} · ${h.gold} ${esc(t('Gold','gold'))}</summary>
    ${an.length?`<div class="dm-n">${esc(t('Trägt','Wears'))}</div>${an.map(([k,it])=>`<small class="mut">${esc(slot[k]||k)}</small>${dmItem(it)}`).join('')}`:''}
    <div class="dm-n">${esc(t('In der Tasche','In the bag'))} · ${bag.length}/${h.tasche_max||bag.length}</div>${bag.length?bag.map(x=>dmItem(x)).join(''):`<small class="mut">${esc(t('Leer.','Empty.'))}</small>`}
    ${(h.kann&&h.kann.zauber||[]).length?`<div class="dm-n">${esc(t('Zauber','Spells'))}</div><small>${h.kann.zauber.map(z=>esc(z.name)).join(' · ')}</small>`:''}</details>`}
// Quest-Gegenstände (Punkt 15 of 2026-10-24): the own special things (give on, put down), what the others carry, and
// for the host every thing with its place (quest_geheim); they weigh nothing and are never for sale
function dmQuest(v,open){const Q=v.quest;if(!Q)return '';const z=esc(Q.zeichen||'✦');
  const row=(x,acts)=>`<div class="dm-line dm-quest"><span>${z} <b>${esc(x.name)}</b>${x.info?` <small class="mut">${esc(x.info)}</small>`:''}${x.wer?` <small class="mut">· ${esc(x.wer)}</small>`:''}</span>${acts||''}</div>`;
  const mine=Q.meine.map(x=>row(x,open?`<span class="dm-iacts">${Q.an.length?`<select data-dmqgive="${esc(x.q)}" aria-label="${esc(t('Geben an','Give to'))}"><option value="">${esc(t('Geben …','Give …'))}</option>${Q.an.map(p=>`<option value="${esc(p.pid)}">${esc(p.name)}</option>`).join('')}</select>`:''}<button type="button" class="b" data-dmhero="questablegen" data-q="${esc(x.q)}">${esc(t('Hinlegen','Put down'))}</button></span>`:'')).join('');
  const G=v.quest_geheim;
  const all=G?`<div class="dm-geheim"><small class="mut">${esc(t('Nur du siehst das: alle besonderen Dinge der Runde','Only you see this: every special thing of the round'))} · ${G.alle.length}/${G.max}</small>${G.alle.map(x=>row(x,`<small class="mut">${esc(x.wer?'':x.ort?t('liegt an Ort ','lies at place ')+x.ort:t('liegt in der Szene','lies in the scene'))}${x.gesehen?'':' · '+esc(t('noch nicht erzählt','not told yet'))}</small>`)).join('')}</div>`:'';
  if(!Q.meine.length&&!Q.gruppe.length&&!all)return '';
  return `<h5>${z} ${esc(t('Besondere Dinge','Special things'))}</h5>${mine||`<small class="mut">${esc(t('Du trägst keins.','You carry none.'))}</small>`}${Q.gruppe.map(x=>row(x)).join('')}${all}`}
function dmMe(v,mode){const h=v.ich;if(!h)return '';
  const open=v.status!=='ende',acts=it=>dmActs(v,it),tab=dmBTab(),kn=h.kann?h.kann.faehigkeiten.length+h.kann.zauber.length:0,offen=h.punkte||h.wahl.length;
  const slot=dmSlots();
  const zwei=h.an.haupthand&&h.an.haupthand.zweihand,kg=x=>String(x).replace('.',L==='en'?'.':',');
  const doll=['hals','kopf','ring1','haupthand','koerper','nebenhand','haende','guertel','ring2','fuesse'].map(k=>{const it=h.an[k];
    return `<div class="dm-pl${it?' voll '+(DMSEL[it.selten]||''):''}" data-dmslot="${k}"${it?` draggable="true" data-dmdrag="${esc(k)}" title="${esc([it.name,...it.zeilen].join(' · '))}"`:''}><small>${esc(slot[k])}</small>${it?`${dmDing(it)}<b>${esc(it.u?it.name.replace(/ \(.*\)$/,'')+' ?':it.name)}</b>${open?`<button type="button" class="ic-ib" data-dmhero="ablegen" data-platz="${k}" title="${esc(t('Ablegen','Unequip'))}" aria-label="${esc(t('Ablegen','Unequip')+': '+it.name)}">×</button>`:''}`:k==='nebenhand'&&zwei?`<i>${esc(t('beide Hände','both hands'))}</i>`:'<i>–</i>'}</div>`}).join('');
  const bag=`<h5>${esc(t('Tasche','Bag'))} · ${h.tasche.length}/${h.tasche_max} · ${kg(h.kg)} / ${kg(h.trag)} kg${h.belastet?` <span class="pill warn">${esc(t('belastet: Geschick mit Nachteil','burdened: Dexterity at disadvantage'))}</span>`:''}</h5>${dmBar(h.kg,h.trag,h.belastet?'low':'')}
    <div class="dm-bag" data-dmbag="1">${h.tasche.map(it=>`<div class="dm-drag"${open&&it.platz.length&&it.n===1?` draggable="true" data-dmdrag="${esc(it.i)}" data-dmpl="${esc(it.platz.join(' '))}"`:''}>${dmItem(it,acts(it))}</div>`).join('')||`<small class="mut">${esc(t('leer','empty'))}</small>`}</div>`;
  const qh=(v.quest&&v.quest.hier)||[];
  const ground=((v.boden||[]).length||v.boden_gold||qh.length)&&open?`<h5>${esc(t('Liegt hier','Lying here'))}</h5>${qh.map(x=>`<div class="dm-line dm-quest"><span>${esc(v.quest.zeichen)} <b>${esc(x.name)}</b></span><button type="button" class="b" data-dmhero="questaufheben" data-q="${esc(x.q)}">${esc(t('Aufheben','Pick up'))}</button></div>`).join('')}${v.boden_gold?`<div class="dm-line dm-bgold"><span>💰 ${v.boden_gold} ${esc(t('Gold','gold'))}</span><button type="button" class="b" data-dmhero="aufheben" data-i="gold">${esc(t('Aufheben','Pick up'))}</button></div>`:''}${(v.boden||[]).map(it=>dmItem(it,`<div class="dm-iacts"><button type="button" class="b" data-dmhero="aufheben" data-i="${esc(it.i)}">${esc(t('Aufheben','Pick up'))}</button></div>`)).join('')}`:'';
  const paint=v.portraet_malt?`<small class="mut">🖼 ${esc(v.portraet_hint||t('Dein Porträt wird gemalt …','Your portrait is being painted …'))}</small>`
    :v.bilder_an&&h.bild_neu&&open?`<button type="button" class="b" data-dmportraet="1" title="${esc(t('Einmal je Stufe, aus Volk, Klasse und deinem Satz.','Once per level, from people, class and your sentence.'))}">${esc(h.bild?t('🖼 Neu malen','🖼 Paint again'):t('🖼 Porträt malen lassen','🖼 Have a portrait painted'))}</button>`:'';
  const port=`<div class="dm-bport"><span class="dm-pbig">${h.bild?dmImg(mode,v,'p',v.pid,h.stufe):dmPic('',h.name,'gross')}</span>${paint}</div>`;
  const tiles=`<div class="dm-wk">${h.werte.map(x=>dmErkBtn(mode,'b:w:'+x.id,`<small>${esc(x.kurz)}</small><b>${x.wert}</b>${dmBo(x.gesamt)}`,x.name)).join('')}</div>`;
  const tb=[['aus','⚔ '+t('Ausrüstung','Equipment')],['kann','✨ '+t('Das kann ich','What I can do')+(kn?' · '+kn:'')],['tasche','🎒 '+t('Tasche','Bag')+' · '+h.tasche.length],['werte','⭐ '+t('Werte verteilen','Spend points')+(offen?' •':'')]];
  const werte=`${h.punkte?`<div class="dm-hint">${esc(t('Neue Stufe: verteile '+h.punkte+' Wertpunkt'+(h.punkte>1?'e':'')+'.','New level: spend '+h.punkte+' value point'+(h.punkte>1?'s':'')+'.'))}</div>
      <div class="dm-werte">${h.werte.map(x=>`<span>${esc(x.kurz)} <b>${x.wert}</b>${x.wert<h.wert_max?`<button type="button" class="b dm-plus" data-dmhero="punkt" data-wert="${esc(x.id)}" title="${esc(t('Wertpunkt hierhin','Value point here'))}">+1</button>`:''}</span>`).join('')}</div>`:''}
    ${h.wahl.length?`<div class="dm-hint">${esc(t('Neue Fähigkeit wählen:','Pick a new ability:'))}</div>${h.wahl.map(f=>`<button type="button" class="b dm-fa" data-dmhero="faehigkeit" data-id="${esc(f.id)}"><b>${esc(f.name)}</b><small>${dmFx(f.satz)}</small></button>`).join('')}`:''}
    ${offen?'':`<small class="mut">${esc(t('Gerade nichts zu verteilen. Jede neue Stufe bringt einen Wertpunkt, manche eine neue Fähigkeit.','Nothing to spend right now. Every new level brings a value point, some a new ability.'))}</small>`}
    <div class="dm-voice"><label>${esc(t('Geschlecht deines Helden','Your hero\'s gender'))}</label>${dmSex(h.geschlecht,true)}<small class="mut">${esc(t('So nennt die Erzählung deinen Helden: er, sie oder bei divers nur beim Namen. Ändern macht das Porträt neu malbar.','This is how the narration refers to your hero: he, she, or for non-binary they or the name. Changing it lets the portrait be painted anew.'))}</small></div>
    ${(v.stimmen||[]).length?`<div class="dm-voice"><label>${esc(t('Stimme deines Helden','Your hero\'s voice'))}</label><div class="dm-inp"><select data-dmvoice="1" aria-label="${esc(t('Stimme deines Helden','Your hero\'s voice'))}"><option value="">${esc(t('Keine, nur der Erzähler','None, only the narrator'))}</option>${dmVoiceGroups(h,v)}</select><button type="button" class="b" data-dmprobe="1"${h.stimme||h.klang?'':' disabled'}>${esc('▶ '+t('Probe','Sample'))}</button></div>${v.stimme_design?`<input class="dm-klang" data-dmvoice="1" maxlength="80" value="${esc(h.klang||'')}" placeholder="${esc(t('oder beschreiben: tiefe, raue Zwergenstimme','or describe it: deep, rough dwarf voice'))}" aria-label="${esc(t('Stimme beschreiben','Describe the voice'))}">`:''}<small class="mut">${esc(t('Ist Vorlesen an, spricht diese Stimme, was dein Held in Anführungszeichen sagt: „Halt, wer da?“','When reading aloud is on, this voice speaks what your hero says in quotes: "Halt, who goes there?"'))}</small></div>`:''}
    ${mode==='g'?`<div class="dm-figur"><button type="button" class="b" data-dmfigur="1">${esc(t('Figur-Code holen','Get a hero code'))}</button>${DG.figur?`<input readonly value="${esc(DG.figur)}" aria-label="${esc(t('Figur-Code','Hero code'))}"><small class="mut">${esc(t('Nur einmal zu sehen. Damit nimmst du deinen Helden in eine andere Runde mit (30 Tage, einmal).','Shown once. Take your hero into another round with it (30 days, once).'))}</small>`:''}</div>`:''}`;
  const body=tab==='kann'?dmKann(h):tab==='tasche'?bag+dmRunen(v,mode,open)+dmQuest(v,open)+dmTrade(v,mode):tab==='werte'?werte:`<div class="dm-doll">${doll}</div>${ground}`;
  return `<div class="dm-me dm-bogen">${port}<div class="dm-bkopf"><h4>${esc(h.name)} <small class="mut">${h.geschlecht_name?esc(h.geschlecht_name)+' · ':''}${esc(h.volk)} · ${esc(h.klasse)} · ${esc(t('Stufe','Level'))} ${h.stufe}</small></h4>${h.satz?`<small class="mut">${esc(h.satz)}</small>`:''}
    ${dmErkBtn(mode,'b:leben',`<span class="dm-line"><span>${esc(t('Leben','Life'))} ${dmZust(h)}</span>${(h.widerstand||[]).length?`<span class="dm-zst dm-wid" title="${esc(t('Treffer dieser Art kosten nur die Hälfte.','Hits of this kind cost only half.'))}">🛡 ${esc(h.widerstand.join(', '))}</span>`:''}<span>${h.leben} / ${h.leben_max}</span></span>${dmBar(h.leben,h.leben_max,h.leben*3<h.leben_max?'low':'')}`,t('Leben erklären','Explain life'))}
    ${dmErkBtn(mode,'b:stufe',`<span class="dm-line"><span>${esc(t('Erfahrung','Experience'))}</span><span>${h.ep}${h.ep_naechste?' / '+h.ep_naechste:''} EP</span></span>${h.ep_naechste?dmBar(h.ep,h.ep_naechste,'ep'):''}${h.ep_tisch?`<small class="dm-eptisch">+${h.ep_tisch} ${esc(t('EP noch am Tisch: zählen am Ende der Runde','EP still at the table: they count at the end of the round'))}</small>`:''}`,t('Stufe erklären','Explain level'))}
    ${tiles}<div class="dm-line dm-bsum"><span>${dmErkBtn(mode,'b:rk',`${esc(t('Rüstungsklasse','Armour class'))} <b>${h.rk}</b>`,t('Rüstungsklasse','Armour class'))} · ${dmErkBtn(mode,'b:gold',`${esc(t('Gold','Gold'))} <b>${h.gold}</b>`,t('Gold','Gold'))}</span><span class="mut">${esc(t('Tasche','Bag'))} ${h.tasche.length}/${h.tasche_max} · ${kg(h.kg)} kg</span></div>
    ${dmErkBox(mode,'b:',{...Object.fromEntries(Object.entries(dmErkFix()).map(([k,x])=>[k,esc(x)])),...Object.fromEntries(h.werte.map(x=>['w:'+x.id,dmErkWert(x,x.gesamt)]))})}
    ${(h.segen||[]).length?`<div class="dm-segen">${h.segen.map(x=>`<span class="pill ok">${esc(x.wert)} ${dmBo(x.bonus)} · ${esc(x.zuege===1?t('noch 1 Zug','1 turn left'):t('noch '+x.zuege+' Züge',x.zuege+' turns left'))}${x.name?' · '+esc(x.name):''}</span>`).join(' ')}</div>`:''}${dmNarben(h)}</div>
    <div class="dm-btabs lseg" role="tablist">${tb.map(([k,l])=>`<button type="button" role="tab" class="${k===tab?'on':''}" aria-selected="${k===tab}" data-dmbt="${k}">${esc(l)}</button>`).join('')}</div>
    <div class="dm-btab dm-btab-${tab}" role="tabpanel">${body}</div></div>`}
// Runen und Sockel (dungeon_runen.py): the rune bag beside the bag; pick a rune and an own thing with a free socket,
// the panel's preview says what it does there (or why not), only „Einsetzen“ sets it for good; never in a fight
const DMRU={p:{},g:{}};
function dmRunen(v,mode,open){const h=v.ich,R=h&&h.runen;if(!R)return '';const S=DMRU[mode];
  if(v.rune_vorschau)S.v=v.rune_vorschau;
  const all=[...Object.values(h.an||{}).filter(Boolean),...h.tasche],name=i=>(all.find(x=>x.i===i)||{}).name||'',n=R.runen.reduce((a,x)=>a+x.n,0);
  const rows=R.runen.map(x=>`<div class="dm-line dm-rune${S.rune===x.id?' on':''}"><span>ᚱ <b>${esc(x.name)}</b> <small class="mut">${esc(x.sinn)} · ${esc(t('Rang','rank'))} ${x.rang}${x.n>1?' · ×'+x.n:''}</small><br><small>${esc(t('Waffe','Weapon'))}: ${esc(x.wirkung.waffe||'–')} · ${esc(t('Rüstung','Armour'))}: ${esc(x.wirkung.ruestung||'–')} · ${esc(t('Schild','Shield'))}: ${esc(x.wirkung.schild||'–')}</small></span>${open&&R.an&&x.ziele.length?`<select data-dmrunziel="${esc(x.id)}" aria-label="${esc(t('Einsetzen in','Set into')+': '+x.name)}"><option value="">${esc(t('Einsetzen in …','Set into …'))}</option>${x.ziele.map(i=>`<option value="${esc(i)}"${S.rune===x.id&&S.i===i?' selected':''}>${esc(name(i))}</option>`).join('')}</select>`:''}</div>`).join('');
  const pv=S.v&&S.rune?`<div class="dm-hint${S.v.ok?'':' warn'}" role="status">${esc(S.v.text)}${S.v.ok&&open?` <button type="button" class="b p" data-dmrunsetz="1">${esc(t('Einsetzen','Set'))}</button>`:''}</div>`:'';
  return `<h5>ᚱ ${esc(R.woerter)} · ${n}/${R.max}</h5>${R.an?'':`<small class="mut">${esc(t('Ruhen: auf diesem Spark gerade aus.','Resting: switched off on this Spark right now.'))}</small>`}${rows||`<small class="mut">${esc(t('Noch keine. Funde und der Krämer bringen welche.','None yet. Finds and the trader bring some.'))}</small>`}${pv}`}
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmrunziel],#dgcard [data-dmrunziel]');if(!s)return;const mode=s.closest('#dgcard')?'g':'p',S=DMRU[mode];
  S.rune=s.dataset.dmrunziel;S.i=s.value;S.v=null;if(!S.i){mode==='g'?dgDraw():dmDraw();return}
  await dmHeroDo(mode,{was:'rune',tun:'pruefen',rune:S.rune,i:S.i})});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmrunsetz],#dgcard [data-dmrunsetz],#dmview [data-dmrunkauf],#dgcard [data-dmrunkauf],#dmview [data-dmrunverk],#dgcard [data-dmrunverk]');if(!b)return;
  const mode=b.closest('#dgcard')?'g':'p',S=DMRU[mode];
  if(b.dataset.dmrunsetz){const body={was:'rune',tun:'einsetzen',rune:S.rune,i:S.i};DMRU[mode]={};await dmHeroDo(mode,body);return}
  await dmHeroDo(mode,{was:'rune',tun:b.dataset.dmrunkauf?'kaufen':'verkaufen',rune:b.dataset.dmrunkauf||b.dataset.dmrunverk})});
// a trade: the offer form keeps its picks across repaints (one per page kind), the panel checks and swaps
const TX={p:null,g:null};
function dmTrade(v,mode){const h=v.ich,others=v.plaetze.filter(p=>!p.frei&&!p.ich),x=TX[mode];
  const its=a=>a.length?a.map(it=>`<span class="dm-tx-it dm-s${it.selten}">${esc(it.name)}</span>`).join(''):'';
  const side=(a,g)=>[its(a),g?`<span class="dm-tx-it">${g} ${esc(t('Gold','gold'))}</span>`:''].join('')||'–';
  const list=(v.angebote||[]).map(o=>`<div class="dm-tx"><div><small class="mut">${esc(o.mir?t(o.von_name+' bietet dir','Offer from '+o.von_name):t('Dein Angebot an '+o.an_name,'Your offer to '+o.an_name))}</small></div>
    <div class="dm-tx-row"><div>${side(o.gebe,o.gold)}</div><span aria-hidden="true">⇄</span><div>${side(o.will,o.will_gold)}</div></div>
    <div class="dm-iacts">${o.mir?`<button type="button" class="b p" data-dmtx="annehmen" data-t="${esc(o.t)}">${esc(t('Annehmen','Accept'))}</button><button type="button" class="b" data-dmtx="ablehnen" data-t="${esc(o.t)}">${esc(t('Ablehnen','Decline'))}</button>`
      :`<button type="button" class="b" data-dmtx="ablehnen" data-t="${esc(o.t)}">${esc(t('Zurückziehen','Withdraw'))}</button>`}</div></div>`).join('');
  if(!others.length&&!list)return '';
  let form='';
  if(x){const o=others.find(p=>p.pid===x.an)||others[0];if(o)x.an=o.pid;
    const pick=(a,set,k)=>a.map(it=>`<label class="dm-tx-pick"><input type="checkbox" data-dmtxpick="${k}" value="${esc(it.i)}"${set.includes(it.i)?' checked':''}>${dmItem(it)}</label>`).join('')||`<small class="mut">${esc(t('leer','empty'))}</small>`;
    form=o?`<div class="dm-txform"><label>${esc(t('Mit','With'))} <select data-dmtxan>${others.map(p=>`<option value="${esc(p.pid)}"${p.pid===o.pid?' selected':''}>${esc(p.name)}</option>`).join('')}</select></label>
      <h6>${esc(t('Du gibst','You give'))}</h6>${pick(h.tasche,x.gebe,'gebe')}<label>${esc(t('Gold','Gold'))} <input type="number" min="0" max="${h.gold}" value="${x.gold}" data-dmtxgold="gold"></label>
      <h6>${esc(t('Du bekommst von '+o.name,'You get from '+o.name))}</h6>${pick(o.tasche||[],x.will,'will')}<label>${esc(t('Gold','Gold'))} <input type="number" min="0" value="${x.will_gold}" data-dmtxgold="will_gold"></label>
      <small class="mut">${esc(t('Bis zu '+v.tausch_teile+' Dinge je Seite. Erst wenn '+o.name+' annimmt, tauscht das Panel.','Up to '+v.tausch_teile+' things per side. The panel swaps only when '+o.name+' accepts.'))}</small>
      <div class="dm-iacts"><button type="button" class="b p" data-dmtx="tauschen">${esc(t('Angebot senden','Send offer'))}</button><button type="button" class="b" data-dmtx="zu">${esc(t('Abbrechen','Cancel'))}</button></div></div>`:'';}
  return `<h5>${esc(t('Tauschen','Trade'))}</h5>${list}${form||(others.length&&v.status!=='ende'?`<button type="button" class="b" data-dmtx="auf">${esc(t('Tausch anbieten','Offer a trade'))}</button>`:'')}`}
async function dmTx(B,mode,post){const x=TX[mode];
  if(B.dmtx==='auf'){TX[mode]={an:'',gebe:[],will:[],gold:0,will_gold:0};return true}
  if(B.dmtx==='zu'){TX[mode]=null;return true}
  if(B.dmtx==='tauschen'){if(!x)return true;if(!(x.gebe.length||x.gold)||!(x.will.length||x.will_gold)){return t('Wähle auf beiden Seiten etwas.','Pick something on both sides.')}
    if(await post({was:'tauschen',an:x.an,gebe:x.gebe,will:x.will,gold:x.gold,will_gold:x.will_gold}))TX[mode]=null;return true}
  await post({was:B.dmtx,t:B.t});return true}
document.body.addEventListener('change',e=>{const el=e.target.closest('[data-dmtxan],[data-dmtxpick],[data-dmtxgold]');if(!el)return;
  const mode=el.closest('#dgcard')?'g':'p',x=TX[mode];if(!x)return;const D=el.dataset;
  if(D.dmtxan!==undefined){x.an=el.value;x.will=[];x.will_gold=0;mode==='g'?dgDraw():dmDraw();return}
  if(D.dmtxpick){const a=x[D.dmtxpick];const i=a.indexOf(el.value);if(el.checked&&i<0)a.push(el.value);if(!el.checked&&i>=0)a.splice(i,1);return}
  if(D.dmtxgold)x[D.dmtxgold]=Math.max(0,Math.floor(+el.value||0))});
// the fight (review point 2, 2026-10-24): the encounter as a card with every foe of the bestiary (a tap shows its
// values), every attack with its d20 against the armour class, and the bar of the foes while the fight lasts
const DMGEF=()=>({leicht:t('leicht','easy'),mittel:t('mittel','medium'),schwer:t('schwer','hard')});
// Tabletop-Punkt 11: the host sees a foe's life in numbers, every other seat its state as a word with four steps
function dmLage(g){return g.max!=null?`<span class="dm-line"><span></span><span>${g.leben} / ${g.max}</span></span>${dmBar(g.leben,g.max,g.leben*3<g.max?'low':'')}`:`<span class="dm-lage" data-lage="${esc(g.lage||'')}">${esc(g.lage_name||'')}</span>`}
function dmCr(s){return {0.125:'⅛',0.25:'¼',0.5:'½'}[s]||String(s)}
// one fight box, not two (Punkt 2 of the table review of 2026-10-24): the encounter in the story is one line of foes,
// a tap opens the foe's window with its values; life stands only in the fight box above
function dmBegegnung(e){return `<div class="dm-beg"><div class="dm-n">⚔ ${esc(t('Begegnung','Encounter'))} <span class="pill" data-gefahr="${esc(e.gefahr)}">${esc(DMGEF()[e.gefahr]||e.gefahr)}</span></div><div class="dm-begl">${(e.gegner||[]).map((g,j)=>`<span class="dm-begc" data-dmgeg="${esc('g:'+e.n+':'+j)}" role="button" tabindex="0" title="${esc(g.info||g.name)}">${dmDing(g)}<b>${esc(g.name)}</b>${g.anzahl>1?` <span class="pill">×${g.anzahl}</span>`:''}</span>`).join('')}</div></div>`}
// Kampf Teil 2: the damage kind, how the foe took it, the weapon's properties that worked
const DMART={hieb:['Hieb','slashing'],stich:['Stich','piercing'],wucht:['Wucht','bludgeoning'],feuer:['Feuer','fire'],kaelte:['Kälte','cold'],blitz:['Blitz','lightning'],saeure:['Säure','acid'],gift:['Gift','poison'],nekrotisch:['nekrotisch','necrotic'],strahlend:['strahlend','radiant'],psychisch:['psychisch','psychic'],donner:['Donner','thunder'],energie:['Energie','force']};
const DMWIRKT={resistenz:['halbiert','halved'],immun:['wirkungslos','no effect'],schwaeche:['doppelt!','double!']};
const DMEIG={leicht:['leicht','light'],finesse:['Finesse','finesse'],reichweite:['Reichweite','reach'],wurf:['Wurf','thrown'],schwer:['schwer','heavy'],vielseitig:['beidhändig','two hands']};
function dmArt(e){return (e.sart&&DMART[e.sart]?` <small class="pill">${esc(t(...DMART[e.sart]))}</small>`:'')+(e.wirkt&&DMWIRKT[e.wirkt]?` <small class="pill ${e.wirkt==='schwaeche'?'ok':'warn'}">${esc(t(...DMWIRKT[e.wirkt]))}</small>`:'')+(e.eig||[]).filter(x=>DMEIG[x]).map(x=>` <small class="pill">${esc(t(...DMEIG[x]))}</small>`).join('')}
// Würfel-Beleg (Tabletop-Punkt 2): every roll of the panel shows its receipt id; the narration may only tell its numbers
// the receipt id (W-2) only as the tooltip, never as a bare label on the card (Dominik 2026-10-27: „W-2“ unclear)
const dmBeleg=e=>e.beleg&&e.echt?`<small class="dm-beleg" title="${esc(t('Würfel-Beleg ','Dice receipt ')+e.beleg+t(': die Erzählung nennt nur Zahlen, die hier stehen.',': the narration tells only numbers that stand here.'))}">${esc(t('echt gewürfelt','real dice'))}</small>`:'';
function dmAngriff(e,W){if(e.kann_nicht)return `<div class="dm-wurf bad">⛓ ${esc(t(e.name+' kann nicht angreifen: '+e.kann_nicht+'.',e.name+' cannot attack: '+e.kann_nicht+'.'))}</div>`;
  if(e.gegner_rettung)return dmRettungG(e,W);
  const fx=(e.extra||[]).map(x=>` · ${esc(t('davon ','of it '))}${x.schaden} ${esc((DMART[x.art]||[x.art,x.art])[L==='en'?1:0])}`).join('')+(e.raub?' · '+esc(t(e.name+' heilt '+e.raub,e.name+' heals '+e.raub)):'')+(e.glueck?' · 🍀 '+esc(t('Glück','Luck')):'')
    +(e.krit_tabelle||e.patzer_tabelle?` · <i class="dm-tab" data-tab="${e.krit_tabelle?'krit':'patzer'}">${e.krit_tabelle?'💥 '+esc(t('Kritisch: ','Critical: ')):'🙃 '+esc(t('Patzer: ','Fumble: '))}${esc(e.krit_tabelle||e.patzer_tabelle)}</i>`:'');   // D&D idea 2: the table's line, panel data
  const res=e.treffer?`<b>${esc(e.krit?t('Kritischer Treffer!','Critical hit!'):t('Treffer','Hit'))}</b> −${e.schaden} ${esc(t('Leben','life'))}${dmArt(e)}${fx}`:`<b>${esc(t('daneben','miss'))}</b>${fx}`;
  return e.von_gegner?`<div class="dm-wurf dm-gzug ${e.treffer?'bad':'ok'}"><span class="dm-d20">${e.w}</span>${esc(e.gegner)} → ${esc(e.name)} · ${dmBo(e.bonus)} = <b>${e.gesamt}</b> ${esc(t('gegen RK','vs AC'))} ${e.rk} · ${res}${dmBeleg(e)}</div>`
    :`<div class="dm-wurf ${e.treffer?'ok':'bad'}"><span class="dm-d20">${e.w}</span>${dmVt(e)}${e.mut?`<span class="dm-vt dm-mutw">⭐ ${esc(t('Heldenmut','Heroic courage'))}</span> `:''}${esc(e.name)} → ${esc(e.gegner)}${e.mit?' · '+esc(e.mit):''} · ${esc(W[e.wert]||e.wert)} ${dmBo(e.bonus)} = <b>${e.gesamt}</b> ${esc(t('gegen RK','vs AC'))} ${e.rk} · ${res}${dmBeleg(e)}</div>`}
// Kampf-Audit H4: a spell with a saving throw: the foe's d20 against the spell's DC, the damage and the state, panel data
function dmRettungG(e,W){const r=e.gegner_rettung;
  const res=(r.ok?`<b>${esc(t('geschafft','passed'))}</b>`:`<b>${esc(t('nicht geschafft','failed'))}</b>`)+(e.schaden?` −${e.schaden} ${esc(t('Leben','life'))}${dmArt(e)}`:'')+(e.zustand?` <small class="pill warn">${esc(e.zustand)}</small>`:'');
  return `<div class="dm-wurf ${r.ok?'bad':'ok'}"><span class="dm-d20">${r.w}</span>${esc(e.name)} → ${esc(e.gegner)}${e.mit?' · '+esc(e.mit):''} · ${esc(t('Rettungswurf','saving throw'))} ${esc(W[r.wert]||r.wert)} = <b>${r.gesamt}</b> ${esc(t('gegen SG','vs DC'))} ${r.gegen} · ${res}${dmBeleg(e)}</div>`}
// Schriftstücke (D&D idea 3, dungeon_schrift): a found writing as a parchment; the host chooses who sees it (all, one
// seat, nobody) with chips, a seat sees only what the panel sends it
function dmPergament(v,s,klein){const sp=v.plaetze.filter(p=>!p.frei),wer=s.sicht==='alle'?t('alle sehen es','everyone sees it'):s.sicht==='niemand'?t('nur du siehst es','only you see it'):t('nur für ','only for ')+(s.fuer||'');
  return `<figure class="dm-perg${klein?' klein':''}" data-art="${esc(s.art)}"><figcaption><span aria-hidden="true">${esc(s.zeichen||'✉')}</span> <b>${esc(s.titel)}</b>${s.geheim?` <small class="pill">${esc(t('nur für dich','only for you'))}</small>`:''}</figcaption><blockquote>${esc(s.text)}</blockquote>${s.von?`<cite>— ${esc(s.von)}</cite>`:''}
    ${s.sicht?`<div class="dm-pergsicht" role="group" aria-label="${esc(t('Wer sieht es','Who sees it'))}"><small class="mut">${esc(wer)}</small>${[['alle',t('Alle','All')],['niemand',t('Niemand','Nobody')]].concat(sp.map(p=>[p.pid,p.name])).map(([k,l])=>`<button type="button" class="pill${s.sicht===k?' on':''}" aria-pressed="${s.sicht===k}" data-dmschrift="${esc(s.id)}" data-sicht="${esc(k)}">${esc(l)}</button>`).join('')}</div>`:''}</figure>`}
const dmSchriften=v=>(v.schrift||[]).length?v.schrift.slice().reverse().map(s=>dmPergament(v,s,true)).join(''):'';
// Narben (D&D idea 8, dungeon_narben): the hero's wounds in its sheet, a consequence red until a healer takes it
const dmNarben=h=>(h.narben||[]).length?`<div class="dm-narben"><small class="mut">${esc(t('Narben','Scars'))}:</small> ${h.narben.map(x=>`<span class="pill${x.folge?' warn':''}" title="${esc(x.folge?t('Bis ein Heiler in einer Siedlung sie nimmt.','Until a healer in a settlement takes it.'):t('Bleibt als Erinnerung.','Stays as a memory.'))}">${x.pflaster?'🩹':'〰'} ${esc(x.t)}${x.folge?' · '+esc(x.folge):''}</span>`).join(' ')}</div>`:'';
// Monster-Album (D&D idea 12, dungeon_album): the foes the own hero's group defeated; the album knows more after 1, 3
// and 5 wins (name, picture, text and saying; values; what hurts it more or less and the states it causes)
const dmAlbumW=e=>e.werte?`<div class="dm-albw">${[[t('Stufe','Level'),e.werte.stufe],[t('Leben','Life'),e.werte.leben],[t('Rüstung','Armour'),e.werte.rk],[t('Angriff','Attack'),'+'+e.werte.angriff],[t('Schaden','Damage'),e.werte.schaden]].map(([k,x])=>`<span><small>${esc(k)}</small><b>${esc(String(x))}</b></span>`).join('')}</div>`:'';
const dmAlbumK=e=>[['schwaeche',t('Schwach gegen','Weak to')],['resistenz',t('Hält aus','Resists')],['immun',t('Immun','Immune')],['zustaende',t('Bewirkt','Causes')]].filter(([k])=>(e[k]||[]).length).map(([k,l])=>`<div><small class="mut">${esc(l)}:</small> ${e[k].map(x=>`<span class="pill">${esc(x)}</span>`).join(' ')}</div>`).join('');
const dmAlbum=v=>(v.album||[]).length?`<div class="dm-album">${v.album.map(e=>`<details class="dm-albe"><summary>${dmDing(e)}<b>${esc(e.name)}</b> <span class="dm-albs" aria-label="${esc(t(`Stufe ${e.stufe} von 3`,`stage ${e.stufe} of 3`))}">${'★'.repeat(e.stufe)}${'☆'.repeat(3-e.stufe)}</span><small class="mut">${esc(t(`${e.siege}× besiegt`,`defeated ${e.siege}×`))}</small></summary>
  <p>${esc(e.info)}</p>${e.sage?`<blockquote class="dm-albsage">${esc(e.sage)}</blockquote>`:''}${dmAlbumW(e)}${dmAlbumK(e)}${e.naechste?`<small class="mut">${esc(t(`Mehr weißt du nach ${e.naechste} Siegen.`,`You learn more after ${e.naechste} wins.`))}</small>`:''}</details>`).join('')}</div>`:'';
// its page „Personen“ (people catalog): the people the hero's table met; the page knows more after 1, 2 and 4 meetings
// (name, face, looks and world; occupation and manner; traits and how the person stands towards the hero)
const dmAlbumP=v=>(v.album_personen||[]).length?`<div class="dm-album">${v.album_personen.map(e=>`<details class="dm-albe"><summary>${dmDing(e)}<b>${esc(e.name)}</b> <span class="dm-albs" aria-label="${esc(t(`Stufe ${e.stufe} von 3`,`stage ${e.stufe} of 3`))}">${'★'.repeat(e.stufe)}${'☆'.repeat(3-e.stufe)}</span><small class="mut">${esc(t(`${e.treffen}× getroffen`,`met ${e.treffen}×`))}</small></summary>
  ${e.aussehen?`<p>${esc(e.aussehen)}</p>`:''}${[[t('Welt','World'),e.welt],[t('Beruf','Occupation'),e.beruf],[t('Art','Manner'),e.art],[t('Wesen','Traits'),(e.wesen||[]).join(', ')],[t('Zu dir','Towards you'),e.haltung]].filter(x=>x[1]).map(([k,x])=>`<div><small class="mut">${esc(k)}:</small> ${esc(x)}</div>`).join('')}${e.naechste?`<small class="mut">${esc(t(`Mehr weißt du nach ${e.naechste} Treffen.`,`You learn more after ${e.naechste} meetings.`))}</small>`:''}</details>`).join('')}</div>`:'';
function dmAlbumAlle(v){const m=dmAlbum(v),p=dmAlbumP(v);if(!m||!p)return m||p;const on=DMA.albseite==='personen'?'personen':'monster';
  return `<div class="lseg dm-albseite" role="tablist">${[['monster',t('Monster','Monsters')],['personen',t('Personen','People')]].map(([k,l])=>`<button type="button" role="tab" aria-selected="${k===on}" class="${k===on?'on':''}" data-dmalbseite="${k}">${esc(l)}</button>`).join('')}</div>${on==='personen'?p:m}`}
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmalbseite]');if(!b)return;DMA.albseite=b.dataset.dmalbseite;
  if(b.closest('#dgcard'))dgDraw();else dmDraw()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmschrift]');if(!b||!DM.rid)return;
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/erzaehler`,{schrift:{id:b.dataset.dmschrift,sicht:b.dataset.sicht}},DM);if(d){DM.v=d;DM.at=Date.now();dmDraw()}});
// Ehrungen des Abends (D&D idea 1, dungeon_ehre): the titles, then one certificate per hero with the panel's numbers
const DMEHRZ=()=>[['treffer',t('Treffer','hits')],['krit',t('kritisch','critical')],['schaden',t('Schaden','damage')],['zwanzig',t('20er','20s')],['eins',t('Einsen','1s')],['proben',t('Proben geschafft','checks passed')],['rettet',t('Freunden geholfen','friends helped')],['heilung',t('Leben geschenkt','life given')]];
function dmEhrung(v,e){return `<div class="dm-ehrung" role="group" aria-label="${esc(t('Ehrungen des Abends','Honours of the evening'))}"><div class="dm-n">🏅 ${esc(t('Ehrungen des Abends','Honours of the evening'))}</div>
  ${(e.titel||[]).map(x=>`<div class="dm-ehrt"><b>${esc(x.titel)}</b> ${esc(x.name)}</div>`).join('')}
  <div class="dm-urks">${(e.urkunden||[]).map(u=>`<div class="dm-urk"><b>${esc(u.name)}</b>${u.titel.length?`<i>${esc(u.titel.join(' · '))}</i>`:''}<div class="dm-urkz">${DMEHRZ().filter(([k])=>u.zahlen[k]).map(([k,l])=>`<span><b>${u.zahlen[k]}</b><small>${esc(l)}</small></span>`).join('')}</div></div>`).join('')}</div></div>`}
function dmKampf(v){const k=v.kampf;if(!k)return '';
  return `<div class="dm-kampf" role="status"><div class="dm-n">⚔ ${esc(t('Kampf','Fight'))} <span class="pill" data-gefahr="${esc(k.gefahr)}">${esc(DMGEF()[k.gefahr]||k.gefahr)}</span> <small class="mut">${esc(t(k.stehen+' stehen noch',k.stehen+' still standing'))}</small></div>
    <div class="dm-kgs">${k.gegner.map(g=>`<div class="dm-kg${g.aus?' aus':''}" data-dmgeg="kg:${esc(g.k)}" role="button" tabindex="0">${dmDing(g)}<div><b>${g.boss?'👑 ':''}${esc(g.name)}</b>${g.aus?`<small class="mut">${esc(g.aus==='besiegt'?t('besiegt','defeated'):t('geflohen','fled'))}</small>`:dmLage(g)+(g.zust||[]).map(z=>`<small class="dm-gzust">${esc(z)}</small>`).join('')}</div></div>`).join('')}</div></div>`}
// the group as a list (Punkt 5 of the table review of 2026-10-24): one row per hero with picture, name, life and state;
// a tap on the row shows the values and what it wears, the host's „⋯“ stays in the row
function dmGruppeZeile(v,mode,p,c){const k=mode+':'+p.pid,auf=!!DMA.gauf[k],low=p.leben*3<p.leben_max?'low':'';
  const st=p.gehandelt?['ok',t('hat gehandelt','acted')]:p.online?['',t('denkt nach','thinking')]:['away',t('nicht da','away')];
  return `<div class="dm-seat dm-hero${p.ich?' me':''}${auf?' auf':''}"><div class="dm-hhead dm-gz" data-dmgauf="${esc(k)}" role="button" tabindex="0" aria-expanded="${auf}" title="${esc(auf?t('Weniger zeigen','Show less'):t('Werte und Ausrüstung zeigen','Show values and equipment'))}">${dmAv(mode,v,p,c)}<div class="dm-gzt"><span><b>${esc(p.name)}</b> <i>${esc(p.volk)} ${esc(p.klasse)}</i></span><small class="mut">${esc(t('Stufe','Level'))} ${p.stufe}${p.gastgeber?' · '+esc(t('leitet','hosts')):p.gast?' · '+esc(t('Gast','guest')):''}</small>${dmZust(p)}<span class="dm-gmini">${dmBar(p.leben,p.leben_max,low)}<small>${p.leben}/${p.leben_max}</small></span></div><small class="dm-state ${st[0]}">${esc(st[1])}</small>${mode==='p'&&v.gastgeber&&!p.gastgeber?dmSeatMenu(p):''}</div>${dmHelfen(v,p)}
    ${auf?`<div class="dm-gdet">${dmErkBtn(mode,`s:${p.pid}:leben`,`<span class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${p.leben} / ${p.leben_max}</span></span>${dmBar(p.leben,p.leben_max,low)}`,t('Leben erklären','Explain life'))}${dmErkBtn(mode,`s:${p.pid}:stufe`,esc(t('Stufe','Level'))+' '+p.stufe,t('Stufe erklären','Explain level'))}
      ${p.karte?`<div class="dm-stats">${p.karte.werte.map(x=>dmErkBtn(mode,`s:${p.pid}:w:${x.kurz}`,`<small>${esc(x.kurz)}</small><b>${x.wert}</b><i>${dmBo(x.mod)}</i>`,x.name)).join('')}${dmErkBtn(mode,`s:${p.pid}:rk`,`<small>${esc(t('RK','AC'))}</small><b>${p.karte.rk}</b>`,t('Rüstungsklasse','Armour class'))}</div>
      ${p.karte.dinge.length?`<div class="dm-pills">${p.karte.dinge.map(d=>`<button type="button" class="dm-erkb dm-sding" data-dmsding="${esc(p.pid)}|${esc(d.platz)}" aria-label="${esc(d.name)}">${esc(d.name)}</button>`).join('')}</div>`:''}`:''}${dmErkBox(mode,`s:${p.pid}:`,dmErkSeat(p))}</div>`:''}</div>`}
document.body.addEventListener('click',e=>{const r=e.target.closest('.dm [data-dmgauf]');if(!r||e.target.closest('button,select,input,summary,details'))return;
  DMA.gauf[r.dataset.dmgauf]=!DMA.gauf[r.dataset.dmgauf];r.closest('#dgcard')?dgDraw():dmDraw()});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('.dm [data-dmgauf]')){e.preventDefault();e.target.click()}});
function dmTable(w,v,mode){DMCMP=v.vergleich||{};const dmkH=typeof DMK!=='undefined'?DMK.html:'',fe=w.querySelector('.dm-feed'),fEnd=!fe||fe.scrollHeight-fe.scrollTop-fe.clientHeight<48,fen=dmFenKeep(w),mk=typeof dmkKeep==='function'?dmkKeep(w):null,cols=dmColKeep(w),tk=dmTalkKeep(w),keep=w.querySelector('.dm-in'),kv=keep?keep.value:'',kf=!!keep&&document.activeElement===keep;
  const st=v.status==='ende'?t('beendet','ended'):v.dm?t('der Dungeon-Master erzählt …','the Dungeon Master is narrating …'):v.pause?t('Pause','paused'):'';
  const done=v.plaetze.filter(p=>!p.frei&&p.gehandelt).length,all=v.plaetze.filter(p=>!p.frei).length;
  const seats=v.plaetze.filter(p=>!p.frei),col=pid=>Math.max(0,seats.findIndex(p=>p.pid===pid))%5;
  const group=v.plaetze.map(p=>p.frei?`<div class="dm-seat free"><span class="dm-av">+</span><div><b>${esc(t('Platz frei','Free seat'))}</b><small class="mut">${esc(t('Link verschickt ','Link sent '))}${esc(dmWhen(p.made))}</small></div><button type="button" class="b" data-dmseatdel="${esc(p.pid)}">${esc(t('Zurücknehmen','Take back'))}</button></div>`
    :p.ich&&v.ich?`<div class="dm-seat dm-hero me dm-ichz">${dmAv(mode,v,p,col(p.pid))}<div><b>${esc(p.name)}</b> <small class="mut">${esc(t('du','you'))} · ${p.leben}/${p.leben_max}</small>${dmZust(p)}</div><small class="dm-state ${p.gehandelt?'ok':''}">${esc(p.gehandelt?t('hat gehandelt','acted'):t('denkt nach','thinking'))}</small></div>`
    :dmGruppeZeile(v,mode,p,col(p.pid))).join('')
    // a hero who joined during a fight waits at the edge until it is over (Dominik 2026-10-25, Punkt 1)
    +(v.am_rand||[]).map(p=>`<div class="dm-seat dm-hero dm-rand"><span class="dm-av">⏳</span><div><b>${esc(p.name)}</b><small class="mut">${esc(t('wartet am Rand, bis der Kampf vorbei ist','waits at the edge until the fight is over'))}</small></div>${mode==='p'&&v.gastgeber?`<button type="button" class="b" data-dmseatdel="${esc(p.pid)}">${esc(t('Zurücknehmen','Take back'))}</button>`:''}</div>`).join('')
    +dmGefaehrten(v);
  const sc=v.szene&&(v.szene.ort||v.szene.stimmung)?`<div class="dm-scene"><i>${esc(t('Ort:','Place:'))}</i> ${esc([v.szene.ort,v.szene.stimmung].filter(Boolean).join(' · '))}</div>`:'';
  const wait=seats.filter(p=>!p.gehandelt&&!p.ruht&&!p.zustand&&!(p.ich&&v.meine_aktion)).map(p=>p.name);   // the own seat never waits once it acted
  const S=mode==='p'?DM:DG,sid=mode==='p'?'dmsend':'dgsend';
  // after „Handeln“ (Dominik 2026-10-24 „beim click auf handeln passiert nichts weiter“): the own action stands as a card with
  // ✓, who is still missing and „Ändern“; the field comes back on „Ändern“ or with the next turn
  const mine=!!v.meine_aktion&&!v.dm&&DMA.aendern[mode]!==v.zug,u=dmUhr(v,S);
  const plus=v.mehr_ich&&v.status==='laeuft'&&v.ich?`<button type="button" class="b dm-plus1" data-dmmehr="1">${esc(t('+1 Minute','+1 minute'))}</button>`:'';
  const dran=v.ich&&!v.dm&&!v.pause&&!v.ich.zustand?`<b class="dm-dran">● ${esc(t('Du bist dran','Your turn'))}</b>`:'';
  const uhr=v.dm||v.status==='ende'?'':`<div class="dm-zeitz">${dran}<small class="mut dm-left${u.warn?' dm-warn':''}">${esc(u.text)}</small>${plus}</div>`;
  const input=v.status==='ende'?'':!v.ich?(v.wartet?`<div class="dm-hint dm-rand">⏳ ${esc(t(v.wartet.name+' wartet am Rand, bis der Kampf vorbei ist. Danach kommt '+v.wartet.name+' an den Tisch.',v.wartet.name+' waits at the edge until the fight is over. Then '+v.wartet.name+' comes to the table.'))}</div>`:''):v.ich.zustand?`<div class="dm-hint dm-zsatz" data-z="${esc(v.ich.zustand)}">${esc(dmZustSatz(v.ich))}</div>`:mine?dmMine(v,wait,S,plus):`${uhr}${wait.length&&!v.dm?`<small class="dm-wait">${esc(t('Warten auf: ','Waiting for: '))}<b>${esc(wait.join(', '))}</b></small>`:''}${dmTyping(v)}<div class="dm-inp"><textarea class="dm-in" rows="1" data-zeilen="4" data-senden="${sid}" maxlength="${v.text_max}" placeholder="${esc(t('Was macht ','What does ')+v.ich.name+t('? ',' do? '))}" aria-label="${esc(t('Deine Aktion','Your action'))}"${v.dm?' disabled':''}></textarea><button type="button" class="b dm-mic${DMA.rec&&DMA.mode===mode?' on':''}" data-dmmic="1" title="${esc(t('Sprechen statt tippen','Speak instead of typing'))}" aria-label="${esc(t('Sprechen statt tippen','Speak instead of typing'))}"${v.dm?' disabled':''}>${DMA.rec&&DMA.mode===mode?'● '+esc(t('Fertig','Done')):'🎤'}</button>${v.mut&&v.mut.frei>0?`<button type="button" class="b dm-mut${DMA.mut[mode]?' on':''}" data-dmmut="${mode}" aria-pressed="${!!DMA.mut[mode]}" title="${esc(t('Misslingt die Probe, wird sie einmal neu gewürfelt; ein Treffer wird kritisch. Noch '+v.mut.frei+' heute.','If the check fails it is rolled once more; a hit becomes critical. '+v.mut.frei+' left today.'))}"${v.dm?' disabled':''}>⭐ ${esc(t('Heldenmut','Heroic courage'))}</button>`:''}<button type="button" class="b p" id="${sid}" data-dmsend="1"${v.dm?' disabled':''}>${esc(t('Handeln','Act'))}</button></div>${v.anleiten&&(v.anleiten.knoepfe||[]).length&&!v.dm?dmKannst(v.anleiten.knoepfe):''}${v.haltung&&!v.dm?dmHaltung():''}${(v.umgebung||[]).length&&!v.dm?dmUmgebung(v):''}${dmFluestern(v)}${dmGedanken(v)}${dmWunsch(v)}${dmMsg(S)}`;
  // the host's console (Dominik 2026-10-25 „Spielleiter-Pult als Fenster“ with the draggable edge, Vorschlag 2+3 of the
  // right column; „Tafeln“ since „empfehlung umsetzten für das spielleiter pult“): the column keeps „Jetzt weiter“ and the
  // button to the console; the console is a big window with „Jetzt weiter“ and who acted on top, four equal cards „Zug“,
  // „Am Tisch“, „Erzähler“, „Schwierigkeit“ and one strip „Nur für dich“ with the story's plan, the truth, the things,
  // the random rules and the oracle; a choice is a band of buttons, never a cut list
  const tile=(attr,ic,name,sub,on,off)=>`<button type="button" class="dm-tile${on?' on':''}" ${attr}${off?` disabled title="${esc(off)}"`:''}><span aria-hidden="true">${ic}</span><span><b>${esc(name)}</b><small>${esc(sub)}</small></span></button>`;
  const frei=v.max-all-v.plaetze.filter(p=>p.frei).length-(v.am_rand||[]).length,erz=(v.erzaehler_liste||[]).find(x=>x.k===v.erzaehler_k),erzw=dmErzWahl(v);
  const leitet=mode==='p'&&v.gastgeber&&v.status!=='ende';
  const weiter=leitet?`<button type="button" class="dm-go" data-dmweiter="1"${done&&!v.dm?'':' disabled'}>▶ ${esc(t('Jetzt weiter','Go on now'))}${wait.length&&!v.dm?` <small>· ${esc(t('wartet auf '+wait.length,'waiting for '+wait.length))}</small>`:''}</button>`:'';
  const host=leitet?`${weiter}<button type="button" class="dm-zeile dm-pultk" data-dmfen="pult"><span>🎲 ${esc(t('Spielleiter-Pult öffnen','Open the game master console'))}</span><small>${esc(v.pause?t('Pause','paused'):v.markt?t('Markt offen','market open'):'')} ›</small></button>`:'';
  const schalt=(attr,ic,name,sub,on)=>`<button type="button" class="dm-schalt" role="switch" aria-checked="${!!on}" ${attr}><span>${ic} ${esc(name)} <small>${esc(sub)}</small></span><i class="dm-sw${on?' on':''}" aria-hidden="true"></i></button>`;
  const pseg=(k,name,list,cur)=>`<div class="dm-pseg" role="radiogroup" aria-label="${esc(name)}">${list.map(([x,n])=>`<label${x===cur?' class="on"':''}><input type="radio" name="${k}" data-${k}="1" value="${esc(x)}"${x===cur?' checked':''}><span>${esc(n)}</span></label>`).join('')}</div>`;
  const zug=`${schalt(`data-dmpause="${v.pause?0:1}"`,'⏸',t('Pause','Pause'),v.pause?t('Zeit steht','clock stopped'):t('Zeit anhalten','stop the clock'),v.pause)}${schalt(`data-dmmarkt="${v.markt?0:1}"`,'⚖',t('Markt','Market'),v.markt?t('offen','open'):t('geschlossen','closed'),!!v.markt)}
    <details class="dm-mehr" data-dmauf="mehr"${DMA.auf==='mehr'||DM.kap||DM.ende?' open':''}><summary>⋯ ${esc(t('Kapitel oder Runde beenden','End chapter or round'))}</summary><div class="dm-hostb"><button type="button" class="b" data-dmkap="1">${esc(DM.kap?t('Kapitel wirklich beenden?','Really end the chapter?'):t('Kapitel beenden','End chapter'))}</button><button type="button" class="b danger" data-dmend="1">${esc(DM.ende?t('Wirklich beenden?','Really end?'):t('Runde beenden','End round'))}</button></div></details>`;
  const tisch=`<div class="dm-tiles dm-tiles-r">${tile(`data-dmvorlesen="${v.vorlesen?0:1}"`,'🔊',t('Vorlesen','Read aloud'),v.vorlesen?t('an','on'):t('aus','off'),v.vorlesen)}${v.bilder_an?tile('data-dmbild="1"','🖼',t('Szenenbild','Scene picture'),t('jetzt malen','paint now'),false,v.bild_grund):''}${tile('data-dminvite="1"','＋',t('Einladen','Invite'),frei>0?(frei===1?t('1 Platz frei','1 seat free'):t(frei+' Plätze frei',frei+' seats free')):t('kein Platz frei','no seat free'),false,frei>0?'':t('Alle Plätze sind besetzt.','All seats are taken.'))}${dmRastTiles(v,tile)}</div>
    ${v.mail_vorschau!=null?`<label class="dm-schalt" title="${esc(t('Gäste mit Gast-Konto bekommen „Du bist dran“ per Mail. Darin steht dann auch der letzte Satz des Erzählers, ohne Links, höchstens 160 Zeichen.','Guests with a guest account get "Your turn" by mail. It then also holds the narrator\'s last sentence, without links, at most 160 characters.'))}"><span>✉ ${esc(t('Letzter Satz in der Mail','Last sentence in the mail'))}</span><input type="checkbox" class="dm-swc" role="switch" data-dmvorschau="1"${v.mail_vorschau?' checked':''}></label>`:''}
    ${v.echt_plaetze&&v.echt_plaetze.length?`<div class="dm-plabel" title="${esc(t('Wer hier an ist, wirft seinen eigenen W20 und tippt oder sagt die Zahl; nach 30 Sekunden würfelt der Spark selbst. Im Auto fragt der Spark nie.','Whoever is on here throws their own d20 and taps or says the number; after 30 seconds the Spark rolls itself. In the car the Spark never asks.'))}">🎲 ${esc(t('Eigene Würfel','Own dice'))}</div><div class="dm-echtwahl" role="group" aria-label="${esc(t('Eigene Würfel','Own dice'))}">${v.echt_plaetze.map(p=>`<button type="button" class="${p.an?'on':''}" aria-pressed="${p.an}" data-dmechtsitz="${esc(p.pid)}">${p.an?'✓ ':''}${esc(p.name)}${p.auto?` <small title="${esc(t('spielt gerade im Auto, wird nicht gefragt','plays in the car right now, not asked'))}">🚗</small>`:''}</button>`).join('')}</div>`:''}
    ${v.bilder_an&&v.bild_grund&&!v.bild_malt?`<small class="mut dm-bgrund">🖼 ${esc(v.bild_grund)}</small>`:''}
    ${DM.made?`<div class="mitmade"><div class="jqr">${DM.made.qr||''}</div><div class="sp"><input readonly value="${esc(DM.made.link)}" aria-label="${esc(t('Der Link','The link'))}"><small class="mut">${esc(t('Nur jetzt zu sehen. Wer ihn öffnet, sitzt auf diesem Platz: als Gast ohne Profil oder mit seinem Profil.','Shown only now. Whoever opens it takes this seat: as a guest without a profile or with their profile.'))}</small></div></div>`:''}`;
  const erzaehler=`<div class="dm-plabel">${esc(t('Erzählweise','Way of telling'))}</div>${pseg('dmweise',t('Erzählweise','Way of telling'),[['knapp',t('knapp','brief')],['normal',t('normal','normal')],['ausfuehrlich',t('ausführlich','rich')]],v.erzaehlweise||'normal')}
    ${v.anleiten&&v.anleiten.wahl?`<div class="dm-plabel" title="${esc(t('Einsteiger: vier Vorschläge mit dem Wert, der vermutlich zählt, im Auto nach jeder Erzählung vorgelesen. Normal: drei Vorschläge. Erfahren: keine Vorschläge, nur die Erzählform.','Beginner: four suggestions with the value that likely counts, read aloud in the car after every narration. Normal: three suggestions. Experienced: no suggestions, only the form of the narration.'))}">${esc(t('Spieler anleiten','Guide the players'))}</div>${pseg('dmanleit',t('Spieler anleiten','Guide the players'),v.anleiten.wahl,v.anleiten.stufe)}`:''}
    ${v.vorlesen&&v.stimme_design===false?dmDesignAus():''}
    ${erzw?`<details class="dm-zeile-d" data-dmauf="erz"${DMA.auf==='erz'?' open':''}><summary class="dm-zeile"><span>🎙 ${esc(erz?erz.name:t('Stimme des Erzählers','Narrator\'s voice'))}</span><small>${esc(t('Probe · Ändern','Sample · Change'))} ›</small></summary>${erzw}</details>`:''}`;
  const schwer=`${v.kampfstufe?`<div class="dm-plabel" title="${esc(t('Wie schwer die nächsten Begegnungen sind. Mittel ist auf 70 bis 90 von 100 Siegen eingestellt; Leicht, Schwer und Tödlich folgen der Tabelle des SRD 5.2.1.','How hard the next encounters are. Medium is set to 70 to 90 wins in 100; easy, hard and deadly follow the table of the SRD 5.2.1.'))}">${esc(t('Kampfstufe','Combat stage'))}</div>${pseg('dmkstufe',t('Kampfstufe','Combat stage'),v.kampfstufe.wahl,v.kampfstufe.wert)}`:''}
    ${v.regler?`<label class="dm-schalt" title="${esc(t('Nach jedem Kampf stellt der Spark die nächsten Begegnungen nach festen Zahlen um höchstens ein Viertel leichter oder schwerer. Die Spieler sehen nur die Gefahr. Festhalten hält den Wert.','After every fight the Spark sets the next encounters at most a quarter easier or harder by fixed numbers. The players see only the danger. Hold keeps the value.'))}"><span>🎚 ${esc(t('Regler festhalten','Hold the dial'))} <small>${esc(t('Gefahr','danger'))} ${v.regler.wert>0?'+':''}${v.regler.wert} %</small></span><input type="checkbox" class="dm-swc" role="switch" data-dmregler="1"${v.regler.fest?' checked':''}></label><div class="dm-gauge" role="img" aria-label="${esc(t('Gefahr','danger')+' '+(v.regler.wert>0?'+':'')+v.regler.wert+' %')}"><i style="left:${Math.max(0,Math.min(100,50+v.regler.wert*2))}%"></i></div>`:''}`;
  const karte=(k,ic,ti,inner)=>inner.trim()?`<div class="dm-pult-sp" role="group" aria-label="${esc(ti)}" data-pult="${k}"><h5>${ic} ${esc(ti)}</h5>${inner}</div>`:'';
  const wer=seats.map(p=>`<span class="dm-pwer${p.gehandelt?' ok':''}">${p.gehandelt?'✓':p.ruht||p.zustand?'–':'…'} ${esc(p.name)}</span>`).join('');
  const geh=[['plan','📖',t('Geschichte','Story'),dmPlanHost(v)],['wahr','🔒',t('Wahrheit','Truth'),dmTruth(v)],['dinge','🧰',t('Dinge','Things'),dmThings(v)],
    ['zufall','🎲',t('Zufallsregeln','Random rules'),dmZufallHost(v)],['orakel','🔮',t('Orakel','Oracle'),dmOrakelHost(v)]].filter(x=>x[3]);
  const gt=(geh.find(x=>x[0]===(DM.ding!=null?'dinge':DMA.gtab))||geh[0]||[])[0];
  const geheim=geh.length?`<div class="dm-pgeheim"><h5>🔒 ${esc(t('Nur für dich','Only for you'))}</h5><div class="dm-gtabs" role="tablist">${geh.map(([k,ic,n])=>`<button type="button" role="tab" class="dm-gtab${k===gt?' on':''}" aria-selected="${k===gt}" data-dmgtab="${k}">${ic} ${esc(n)}</button>`).join('')}</div><div class="dm-gpane" role="tabpanel">${geh.find(x=>x[0]===gt)[3].replace(/^\s*<details\b/,'<details open')}</div></div>`:'';
  const pult=leitet?`<div class="dm-pkopf">${weiter}${wer?`<div class="dm-pwerl">${wer}</div>`:''}</div><div class="dm-pult">${karte('zug','🎲',t('Zug','Turn'),zug)}${karte('tisch','👥',t('Am Tisch','At the table'),tisch)}${karte('erz','📜',t('Erzähler','Narrator'),erzaehler)}${karte('schwer','⚔',t('Schwierigkeit','Difficulty'),schwer)}</div>${geheim}`:'';
  v.mode=mode;const log=window.dmWFeed?dmWFeed(v,col):v.log.map(e=>dmLog(v,e,col)).join('');   // an own die waits for its tap (dungeonwarten.js, 1a)
  dmLook(w,v.farben);w.classList.toggle('dm-voll',DMA.voll);w.classList.add('dm-amtisch');w.dataset.welt=v.welt_id||'';
  // the head (Punkt 1 of the table review of 2026-10-24): on the phone one row with title, turn, 🔊 and „⋯“; the rest
  // (back, sounds, guide, light or dark, full screen, the host's console) opens under „⋯“; no full screen in the app
  dmMorph(w,`<div class="dm-head${DMA.kopf?' auf':''}">${mode==='p'?`<button type="button" class="b dm-kopfm" data-dmback="1">${esc(t('← Runden','← Rounds'))}</button>`:''}<div class="dm-htitle"><h3>${esc(v.titel)}</h3>${sc}<small class="mut"><span class="dm-hmehr">${esc(v.welt)} · ${esc(v.ton)}${v.kapitel?' · '+esc(t('Kapitel','Chapter'))+' '+v.kapitel:''}${v.akte?' · '+esc(v.erzaehlt?t('Geschichte erzählt','story told'):t('Akt','Act')+' '+v.akt+'/'+v.akte):''} · </span>${esc(t('Zug','Turn'))} ${v.zug}${st?' · '+esc(st):''}</small></div>${dmLesKnopf(v,mode)}${v.ich?`<button type="button" class="b dm-help dm-kopfm" data-dmhilfe="${DMA.hilfe===false||DMA.hilfe==='kurz'?0:'zu'}">${esc('❔ '+t('So spielst du','How to play'))}</button>`:''}${dmModus()}${DMA.app?'':dmVollKnopf()}${leitet?`<button type="button" class="b dm-kopfm dm-kopfpult" data-dmfen="pult">🎲 ${esc(t('Spielleiter-Pult','Game master console'))}</button>`:''}<button type="button" class="b dm-kopfk" data-dmkopf="1" aria-expanded="${!!DMA.kopf}" title="${esc(t('Mehr','More'))}" aria-label="${esc(t('Mehr','More'))}">⋯</button></div>
    ${v.ich?dmHilfe():''}<div class="dm-grid" data-dmpane="${DMA.handy}" style="--dm-side:${dmBreite()}px"><div class="dm-col dm-group"><h5>${esc(t('Gruppe','Group'))} · ${all}/${v.max}</h5>${group}</div>
    <div class="dm-col dm-story">${dmBack(v)}${dmPauseBar(v,leitet)}${dmKalender(v)}${dmTageszeit(v)}${dmKnapp(v)}${dmRast(v)}${dmKampf(v)}<div class="dm-feed" aria-live="polite">${dmScene(v,mode)}${log}${dmMalt(v)}${dmWait(v)}</div>${input?`<div class="dm-handeln">${input}</div>`:''}${dmTalk(v,mode)}</div>
    <div class="dm-col dm-side">${dmZiehe()}${dmAuftrag(v)}${dmAuftraege(v)}${dmMeKurz(v,mode)}${host?`<div class="dm-pultz">${host}</div>`:''}${dmSeite(v,mode)}</div></div>${input?'':dmMsg(S)}${dmUnten(v,mode)}${dmFenster(v,mode,pult)}`,(x,n)=>!!dmkH&&dmkH===DMK.html&&x.classList.contains('dmk')&&n.classList.contains('dmk'));
  if(mk)mk();                        // the map's node stays while its drawing is the same (dungeonkarte.js)
  fen();cols();tk();dmUntenPlatz(w);
  if(mode==='g')dmImgFill(w);
  dmDingFill(w,mode);
  if(window.dmTon)dmTon(w,v,mode);   // music, sounds and the rolling d20 (dungeon-ton.js)
  dmWOthers(w,v);                    // another seat threw its die (dungeonwarten.js)
  DMLES[mode].w=w;dmMit(mode);       // the sentence being read stays marked (Tabletop 16)
  const f=w.querySelector('.dm-feed'),lk=(v.log||[]).length+':'+JSON.stringify((v.log||[]).slice(-1)[0]||'').length;
  if(f&&(fEnd||DMA.feedk[mode]!==lk))f.scrollTop=f.scrollHeight;DMA.feedk[mode]=lk;
  const inp=w.querySelector('.dm-in');if(inp){if(DMA.rf&&DMA.rf.m===mode){inp.value=DMA.rf.t;DMA.rf=null;inp.focus({preventScroll:true})}else if(kv)inp.value=kv;else if(DMA.aendern[mode]===v.zug&&v.meine_aktion)inp.value=v.meine_aktion;if(kf||!keep&&DMA.aendern[mode]===v.zug)inp.focus({preventScroll:true})}
  dmLeft(S);
  dmLesung(mode,v)}
// the table is never built anew (Dominik 2026-10-27 „die seite im spiel läd zum teil immer neu, bilder flackern, texte
// formatieren sich um und springen“): the new HTML goes into the nodes there, a node stays when it is the same thing
// (same tag, id, key or start of its text, looked for a few places ahead), only what changed is set; a picture keeps the
// address its filler gave it (src, href), so nothing loads again, and scroll, focus and open details stay; a node stay(old, new)
// names stays as it is (the map while its drawing is the same, dungeonkarte.js)
const DMMORPH_VOR=6;
function dmMorph(w,html,stay){if(!w.firstChild){w.innerHTML=html;return}const n=document.createElement(w.tagName);n.innerHTML=html;dmMorphKids(w,n,stay||(()=>false))}
function dmMorphKey(x){return x.nodeType!==1?'#'+x.nodeType:x.nodeName+'|'+(x.id||x.getAttribute('data-key')||'')+'|'+(x.getAttribute('class')||'')+'|'+(x.textContent||'').slice(0,40)}
function dmMorphKids(a,b,stay){let o=a.firstChild;
  for(const nb of [...b.childNodes]){const k=dmMorphKey(nb);let m=o,i=0;
    while(m&&i<DMMORPH_VOR&&dmMorphKey(m)!==k){m=m.nextSibling;i++}
    if(m&&i<DMMORPH_VOR&&dmMorphKey(m)===k){while(o!==m){const x=o;o=o.nextSibling;x.remove()}}
    else m=o&&o.nodeName===nb.nodeName&&o.nodeType===nb.nodeType?o:null;
    if(m){if(m.nodeType!==1||!stay(m,nb))dmMorphNode(m,nb,stay);o=m.nextSibling}else a.insertBefore(nb,o)}
  while(o){const x=o;o=o.nextSibling;x.remove()}}
function dmMorphNode(a,b,stay){if(a.nodeType!==1){if(a.nodeValue!==b.nodeValue)a.nodeValue=b.nodeValue;return}
  const pic=a.nodeName==='IMG'||a.nodeName.toLowerCase()==='image';
  for(const at of [...a.attributes])if(!b.hasAttribute(at.name)&&!(pic&&(at.name==='src'||at.name==='href')))a.removeAttribute(at.name);
  for(const at of [...b.attributes])if(a.getAttribute(at.name)!==at.value)a.setAttribute(at.name,at.value);
  if(a.nodeName==='TEXTAREA'||a.nodeName==='INPUT'&&document.activeElement===a)return;   // what is typed stays (dmTable puts it back)
  dmMorphKids(a,b,stay)}
// on the phone the field stands above the bar in every pane (Punkt 3 of the table review): the table keeps room for
// both under the story, measured again while the field grows
function dmUntenPlatz(w){const h=w.querySelector('.dm-handeln'),u=w.querySelector('.dm-unten');
  const set=()=>{w.style.setProperty('--dm-hh',(h&&h.offsetHeight||0)+'px');w.style.setProperty('--dm-uh',(u&&u.offsetHeight||0)+'px')};set();
  if(DMA.ro)DMA.ro.disconnect();DMA.ro=window.ResizeObserver&&h?new ResizeObserver(set):null;if(DMA.ro)DMA.ro.observe(h)}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmkopf]');if(b){DMA.kopf=!DMA.kopf;const hd=b.closest('.dm-head');hd.classList.toggle('auf',DMA.kopf);b.setAttribute('aria-expanded',String(DMA.kopf));return}
  if(DMA.kopf&&e.target.closest('.dm-head.auf .dm-kopfm,.dm-head.auf [data-dmfen]')){DMA.kopf=false;const hd=document.querySelector('.dm-head.auf');if(hd)hd.classList.remove('auf')}});
// the group and the side column keep their scroll across the table's repaints (Dominik 2026-10-25 „die rechte Seite springt
// immer wieder hoch“); the story's feed goes to its end on its own
function dmColKeep(w){const s=['.dm-group','.dm-side'].map(c=>{const x=w.querySelector(c);return [c,x?x.scrollTop:0]}),y=window.scrollY;
  return ()=>{s.forEach(([c,t])=>{const x=w.querySelector(c);if(x&&t)x.scrollTop=t});if(Math.abs(window.scrollY-y)>1)window.scrollTo(0,y)}}
// Orakel (Tabletop-Punkt 8): the host asks yes or no with a likelihood, or rolls up to three tables; the chaos grade
// moves the chance; the answer is a line in the feed and goes to the narration only as data
function dmOrakelHost(v){const O=v.orakel;if(!O)return '';const D=DMA.ork||{frage:'',odds:'offen',tab:[]};
  const chips=O.tabellen.map(([id,n,g])=>`<label class="dm-otab"><input type="checkbox" data-dmotab="${esc(id)}"${D.tab.includes(id)?' checked':''}${!D.tab.includes(id)&&D.tab.length>=O.max?' disabled':''}> ${esc(n)}${g==='eigen'?' ✎':''}</label>`).join('');
  return `<details class="dm-zeile-d" data-dmauf="orakel"${DMA.auf==='orakel'?' open':''}><summary class="dm-zeile"><span>🔮 ${esc(t('Orakel','Oracle'))}</span><small>${esc(t('Chaos ','Chaos '))}${O.chaos} · ${esc(t('noch '+O.frei+' in diesem Zug','left this turn: '+O.frei))} ›</small></summary>
    <small class="mut">${esc(t('Eine Ja-oder-Nein-Frage oder bis zu '+O.max+' Tabellen. Das Panel würfelt einen W100; je höher das Chaos, desto eher ja und desto öfter ein Ereignis. Die Antwort steht im Verlauf, die Erzählung hält sich daran.','A yes-or-no question or up to '+O.max+' tables. The panel rolls a d100; the higher the chaos, the likelier a yes and the more often an event. The answer stands in the feed, the narration holds to it.'))}</small>
    <input data-dmofrage maxlength="${O.frage_max}" value="${esc(D.frage)}" placeholder="${esc(t('z. B. Ist die Brücke bewacht?','e.g. Is the bridge guarded?'))}" aria-label="${esc(t('Frage','Question'))}">
    <div class="dm-hostb"><select data-dmoodds aria-label="${esc(t('Wie wahrscheinlich','How likely'))}">${O.odds.map(([k,n])=>`<option value="${esc(k)}"${k===D.odds?' selected':''}>${esc(n)}</option>`).join('')}</select>
    <label class="dm-ochaos">${esc(t('Chaos','Chaos'))} <input type="range" data-dmochaos min="${O.chaos_min}" max="${O.chaos_max}" value="${O.chaos}"> <b>${O.chaos}</b></label></div>
    <div class="dm-otabs">${chips}</div><div class="dm-hostb"><button type="button" class="b p" data-dmofrag="1"${O.frei?'':' disabled'}>🔮 ${esc(t('Orakel fragen','Ask the oracle'))}</button></div></details>`}
function dmOrakelDraft(box){return {frage:box.querySelector('[data-dmofrage]').value,odds:box.querySelector('[data-dmoodds]').value,tab:[...box.querySelectorAll('[data-dmotab]:checked')].map(x=>x.dataset.dmotab)}}
document.body.addEventListener('input',e=>{const b=e.target.closest('#dmview details[data-dmauf="orakel"]');if(b&&e.target.matches('[data-dmofrage]'))DMA.ork=dmOrakelDraft(b)});
document.body.addEventListener('change',async e=>{const b=e.target.closest('#dmview details[data-dmauf="orakel"]');if(!b)return;DMA.ork=dmOrakelDraft(b);DMA.auf='orakel';
  if(e.target.matches('[data-dmochaos]')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/orakel`,{chaos:+e.target.value},DM);if(d){DM.v=d;DM.at=Date.now()}}dmDraw()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmofrag]');if(!b)return;const box=b.closest('details'),D=dmOrakelDraft(box);DMA.auf='orakel';
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/orakel`,Object.assign({tabellen:D.tab},D.frage.trim()?{frage:D.frage.trim(),wahrscheinlichkeit:D.odds}:{}),DM);
  if(d){DM.v=d;DM.at=Date.now();DMA.ork=null;dmSay(DM,t('Das Orakel hat geantwortet.','The oracle has answered.'),false)}else DMA.ork=D;dmDraw()});
// the admin's story of the round: only the host sees the plan, the players only the act's number
// Zufallsregeln (Tabletop-Punkt 9): the host's own rules, only the host sees them; the panel rolls and applies them
function dmZufallHost(v){const Z=v.zufall;if(!Z)return '';const rows=DMA.zufDraft||Z.regeln,opt=(l,cur)=>l.map(([k,n])=>`<option value="${esc(k)}"${k===cur?' selected':''}>${esc(n)}</option>`).join('');
  const row=(x,i)=>`<div class="dm-zregel" data-dmzrow="${i}"><input data-z="name" maxlength="${Z.name_max}" value="${esc(x.name||'')}" placeholder="${esc(t('Name, z. B. Steinschlag','Name, e.g. Rockfall'))}" aria-label="${esc(t('Name','Name'))}">
    <label>${esc(t('Chance','Chance'))} <input data-z="prozent" type="number" min="1" max="100" value="${x.prozent||10}"> %</label><select data-z="ausloeser" aria-label="${esc(t('Auslöser','Trigger'))}">${opt(Z.ausloeser,x.ausloeser||'zug')}</select>
    <select data-z="wirkung" aria-label="${esc(t('Wirkung','Effect'))}">${opt(Z.wirkungen,x.wirkung||'schaden')}</select><input data-z="zahl" type="number" min="0" max="50" value="${x.zahl||0}" aria-label="${esc(t('Zahl','Number'))}">
    <select data-z="wer" aria-label="${esc(t('Wer würfelt','Who rolls'))}">${opt(Z.wer,x.wer||'alle')}</select><input data-z="text" maxlength="${Z.text_max}" value="${esc(x.text||'')}" placeholder="${esc(t('Nur bei Hinweis: was die Erzählung aufgreift','Only for a hint: what the narration takes up'))}" aria-label="${esc(t('Hinweis','Hint'))}">
    <button type="button" class="ic-ib" data-dmzweg="${i}" title="${esc(t('Regel entfernen','Remove rule'))}" aria-label="${esc(t('Regel entfernen','Remove rule'))}">✕</button></div>`;
  return `<details class="dm-zeile-d" data-dmauf="zufall"${DMA.auf==='zufall'?' open':''}><summary class="dm-zeile"><span>🎲 ${esc(t('Zufallsregeln','Random rules'))}</span><small>${rows.length}/${Z.max} · ${esc(t('nur du siehst sie','only you see them'))} ›</small></summary>
    <small class="mut">${esc(t('Das Panel würfelt bei jedem Auslöser einen W100; bis zur Chance trifft die Regel. Jeder Wurf steht im Verlauf, ein Hinweis geht nur als Daten an die Erzählung.','The panel rolls a d100 at every trigger; up to the chance the rule hits. Every roll stands in the feed, a hint goes to the narration only as data.'))}</small>
    ${rows.map(row).join('')}<div class="dm-hostb">${rows.length<Z.max?`<button type="button" class="b" data-dmzneu="1">＋ ${esc(t('Regel','Rule'))}</button>`:''}<button type="button" class="b p" data-dmzsave="1">${esc(t('Speichern','Save'))}</button></div></details>`}
function dmZufallRows(box){return [...box.querySelectorAll('[data-dmzrow]')].map(r=>{const g=k=>r.querySelector(`[data-z="${k}"]`).value;return {name:g('name').trim(),prozent:+g('prozent')||0,ausloeser:g('ausloeser'),wirkung:g('wirkung'),zahl:+g('zahl')||0,wer:g('wer'),text:g('text').trim()}})}
document.body.addEventListener('input',e=>{const r=e.target.closest('#dmview [data-dmzrow]');if(r)DMA.zufDraft=dmZufallRows(r.closest('details'))});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmzneu],#dmview [data-dmzweg],#dmview [data-dmzsave]');if(!b)return;const box=b.closest('details');
  const rows=dmZufallRows(box);DMA.auf='zufall';
  if(b.dataset.dmzneu){DMA.zufDraft=rows.concat([{name:'',prozent:10,ausloeser:'zug',wirkung:'schaden',zahl:1,wer:'alle',text:''}]);dmDraw();return}
  if(b.dataset.dmzweg!==undefined){rows.splice(+b.dataset.dmzweg,1);DMA.zufDraft=rows;dmDraw();return}
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/zufall`,{regeln:rows.filter(x=>x.name).map(x=>x.wirkung==='hinweis'?Object.assign(x,{zahl:0}):x)},DM);
  if(d){DM.v=d;DM.at=Date.now();DMA.zufDraft=null;dmSay(DM,t('Zufallsregeln gespeichert.','Random rules saved.'),false)}dmDraw()});
function dmPlanHost(v){const p=v.plan;if(!p)return '';const cur=v.erzaehlt?-1:v.akt-1;
  return `<details class="adv dm-plan"><summary>${esc(t('Geschichte: ','Story: ')+p.titel)} · ${esc(t('nur du siehst das','only you see this'))}</summary><small class="mut">${esc(t('Ziel: ','Goal: ')+p.ziel)}${p.gegner?' · '+esc(t('Gegenspieler: ','Foe: ')+p.gegner):''}</small>
    <ol>${p.akte.map((a,i)=>`<li class="${i===cur?'on':i<cur||cur<0?'mut':''}"><b>${esc(a.titel)}</b> <small>${esc(a.inhalt)}</small><small class="mut">${esc(t('Wendepunkt: ','Turning point: ')+a.wende)} · ${a.zuege} ${esc(t('Züge','turns'))}</small>${(a.spuren||[]).length?`<ul class="dm-spuren">${a.spuren.map((s,j)=>`<li>${i===cur&&(v.spuren_gezeigt||[]).includes(j)||i<cur||cur<0?'✓':'🔎'} ${esc(s)}</li>`).join('')}</ul>`:''}</li>`).join('')}</ol>
    <small class="mut">${esc(t('Der Dungeon-Master entscheidet, wann der nächste Akt beginnt (frühestens nach '+v.akt_min+' Zügen); läuft ein Akt anderthalbmal so lange wie geplant, geht das Panel selbst weiter.','The Dungeon Master decides when the next act begins (after '+v.akt_min+' turns at the earliest); when an act runs one and a half times as long as planned, the panel moves on by itself.'))}</small></details>`}
// read aloud piece by piece (Punkt 16 of 2026-10-24): every device that has it on plays the round's pieces in order
// as the Spark makes them, guests and the iPhone app too; browsers allow sound only after a tap, so one tap on
// „🔊 Ton an“ unlocks this page's player, then it runs by itself. Entering mid-turn reads nothing old.
const DMLES={p:{n:null,k:0,frei:false,laeuft:false,el:null,url:''},g:{n:null,k:0,frei:false,laeuft:false,el:null,url:''}};
// 0.1 s of real silence (an empty file does not play in Safari) as a blob: the panel's CSP allows media only from 'self'
// and blob:, a data: URL is blocked (Dominik 2026-10-24, Chrome: „violates … media-src 'self' blob:“)
let DMSTILLURL='';
function dmStill(){if(!DMSTILLURL){const b=atob('UklGRmQGAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YUAGAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);
  DMSTILLURL=URL.createObjectURL(new Blob([u],{type:'audio/wav'}))}return DMSTILLURL}
function dmLesHier(){try{return localStorage.getItem('dm-ton')!=='0'}catch(e){return true}}
function dmLesKnopf(v,mode){if(!v.vorlesen)return '';const A=DMLES[mode],hier=dmLesHier();
  // on the phone only the sign shows (Punkt 1 of the table review), the words stay for the screen reader
  const main=!hier?'':!A.frei?`<button type="button" class="b dm-hear dm-tonan" data-dmhear="frei">${esc(t('🔊 Ton an','🔊 Sound on'))}</button>`
    :A.laeuft||v.liest?`<button type="button" class="b dm-hear" data-dmhear="stopp" aria-label="${esc(t('Vorlesen stoppen','Stop reading'))}">⏹<span class="dm-lt"> ${esc(t('Vorlesen stoppen','Stop reading'))}</span></button>`
    :`<button type="button" class="b dm-hear" data-dmhear="nochmal" aria-label="${esc(t('Nochmal hören','Listen again'))}"${v.lesung?'':' disabled'}>🔊<span class="dm-lt"> ${esc(t('Nochmal hören','Listen again'))}</span></button>`;
  return `${main}<button type="button" class="ic-ib dm-tonhier dm-kopfm" data-dmhear="${hier?'aus':'an'}" aria-pressed="${hier}" title="${esc(hier?t('Auf diesem Gerät nicht vorlesen','Do not read aloud on this device'):t('Auf diesem Gerät vorlesen','Read aloud on this device'))}" aria-label="${esc(hier?t('Auf diesem Gerät nicht vorlesen','Do not read aloud on this device'):t('Auf diesem Gerät vorlesen','Read aloud on this device'))}">${hier?'🔈':'🔇'}</button>`}
function dmLesung(mode,v){const A=DMLES[mode],T=v.lesung;if(!T)return;
  if(T.x&&T.n===A.n&&A.laeuft){dmLesStopp(mode);return}     // an X-Karte stopped this turn's reading (Tabletop 18)
  if(A.n===null){A.n=T.n;A.k=T.k;return}
  if(T.n!==A.n){A.n=T.n;A.k=0}
  dmLesWeiter(mode)}
// the tap unlocks the player: only a refusal of the browser (NotAllowedError) keeps it locked, any other error of the
// silent file does not (Dominik 2026-10-24 „passiert aber nichts“ after „Tippe noch einmal auf 🔊 Ton an“)
async function dmLesFrei(mode){const A=DMLES[mode];if(!A.el){A.el=new Audio();A.el.setAttribute('playsinline','')}A.el.src=dmStill();
  try{const AC=window.AudioContext||window.webkitAudioContext;if(AC){DMLES.ac=DMLES.ac||new AC();DMLES.ac.resume()}}catch(e){}
  try{await A.el.play();A.frei=true}catch(e){A.frei=!(e&&e.name==='NotAllowedError')}}
// a piece as MP3, asked once; the next one loads while this one plays (Dominik 2026-10-25: over the proxy each piece
// loaded only after the last one ended, a pause after every sentence)
function dmLesHol(mode,n,k){const A=DMLES[mode],key=n+':'+k;A.pre=A.pre||{};
  for(const x in A.pre)if(!x.startsWith(n+':'))delete A.pre[x];
  if(!A.pre[key])A.pre[key]=(mode==='p'?api(`/api/profile/dungeon/${DM.rid}/ton/${n}/${k}?mp3=1`)
    :/*raw: public route of a guest seat*/fetch('/api/dungeon/ton',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,zug:n,k,mp3:true})}))
    .then(async r=>r.ok?URL.createObjectURL(await r.blob()):'').catch(()=>'');
  return A.pre[key]}
async function dmLesWeiter(mode){const A=DMLES[mode],S=mode==='p'?DM:DG,T=S.v&&S.v.lesung;
  if(A.laeuft&&T&&T.n===A.n&&T.k>A.k+1)dmLesHol(mode,A.n,A.k+1);
  if(!T||A.laeuft||!A.frei||!dmLesHier()||!S.v.vorlesen||T.n!==A.n||A.k>=T.k)return;
  const n=A.n,k=A.k;A.laeuft=true;let gone=true;
  try{const url=await dmLesHol(mode,n,k);delete A.pre[n+':'+k];
    if(T.k>k+1)dmLesHol(mode,n,k+1);
    if(url){if(A.url)URL.revokeObjectURL(A.url);A.url=url;A.el.src=url;dmMit(mode);
      await new Promise((ok,no)=>{A.el.onended=ok;A.el.onerror=ok;A.el.play().catch(no)})}}
  catch(e){if(e&&e.name==='NotAllowedError'){A.frei=false;gone=false}}      // the browser locked the sound again: a tap
  A.laeuft=false;if(gone&&A.n===n&&A.k===k)A.k=k+1;
  const now=S.v&&S.v.lesung;if(now&&A.k<now.k&&now.n===A.n)dmLesWeiter(mode);else{if(now&&!now.fertig)S.at=0;mode==='p'?dmDraw():dgDraw()}}
function dmLesStopp(mode){const A=DMLES[mode],S=mode==='p'?DM:DG;if(A.el)A.el.pause();const T=S.v&&S.v.lesung;if(T){A.n=T.n;A.k=99999}A.laeuft=false;dmMit(mode)}
// read along (Tabletop 16): the piece being read is marked in its turn's narration, found by its words (the spoken
// piece has no markup and no quote marks), one <mark> per text node; every repaint marks it again, nothing plays, nothing marked
const DMWORT=/[\p{L}\p{N}]+/gu;
function dmMit(mode){const A=DMLES[mode],S=mode==='p'?DM:DG,w=A.w,T=S.v&&S.v.lesung;if(!w)return;
  w.querySelectorAll('mark.dm-mit').forEach(m=>{const p=m.parentNode;m.replaceWith(...m.childNodes);p.normalize()});
  const txt=A.laeuft&&T&&T.n===A.n&&(T.texte||[])[A.k],want=String(txt||'').toLowerCase().match(DMWORT)||[];if(!want.length)return;
  const box=w.querySelector(`.dm-dm[data-dmzug="${A.n}"]`)||[...w.querySelectorAll('.dm-dm')].pop();if(!box)return;
  const all=[],words=[],tw=document.createTreeWalker(box,NodeFilter.SHOW_TEXT);
  for(let x;(x=tw.nextNode());){all.push(x);for(const m of x.data.matchAll(DMWORT))words.push({x,a:m.index,b:m.index+m[0].length,t:m[0].toLowerCase()})}
  let at=-1;for(let i=0;at<0&&i+want.length<=words.length;i++)if(want.every((t,j)=>words[i+j].t===t))at=i;if(at<0)return;
  const f=words[at],l=words[at+want.length-1],seg=all.slice(all.indexOf(f.x),all.indexOf(l.x)+1);
  for(const x of seg){const a=x===f.x?f.a:0,b=x===l.x?l.b:x.data.length;if(b<=a||!x.data.slice(a,b).trim())continue;
    const r=document.createRange();r.setStart(x,a);r.setEnd(x,b);const m=document.createElement('mark');m.className='dm-mit';r.surroundContents(m)}}
async function dmHear(mode,was){const A=DMLES[mode],S=mode==='p'?DM:DG,T=S.v&&S.v.lesung;
  if(was==='aus'){try{localStorage.setItem('dm-ton','0')}catch(e){}dmLesStopp(mode)}
  else if(was==='stopp')dmLesStopp(mode);
  else{if(was==='an'){try{localStorage.setItem('dm-ton','1')}catch(e){}}
    await dmLesFrei(mode);if(was==='nochmal'&&T){A.n=T.n;A.k=0}
    if(!A.frei)dmSay(S,t('Der Browser lässt den Ton gerade nicht zu. Tippe noch einmal auf „🔊 Ton an“.','The browser does not allow sound right now. Tap "🔊 Sound on" once more.'),false);
    dmLesWeiter(mode)}
  mode==='p'?dmDraw():dgDraw()}
// speak instead of type: up to 30 s, the panel's speech recognition writes it into the own field, sending stays a tap
// fertig(text) (the real dice of dungeon_echt, Punkt 5 of the D&D ideas) takes the heard text instead of the action field
async function dmMic(mode,fertig){const S=mode==='p'?DM:DG;
  if(DMA.rec){DMA.rec.stop();return}
  if(!window.isSecureContext||!navigator.mediaDevices){dmSay(S,t('Das Mikrofon braucht https.','The microphone needs https.'),true);return}
  let st;try{st=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch{dmSay(S,t('Kein Zugriff aufs Mikrofon.','No access to the microphone.'),true);return}
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  const rec=new MediaRecorder(st,mime?{mimeType:mime}:{}),parts=[];DMA.rec=rec;DMA.mode=mode;
  rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
  const stop=setTimeout(()=>rec.state!=='inactive'&&rec.stop(),30000);
  rec.onstop=async()=>{clearTimeout(stop);st.getTracks().forEach(x=>x.stop());DMA.rec=null;mode==='p'?dmDraw():dgDraw();
    dmSay(S,t('Erkenne Sprache …','Transcribing …'),false);
    try{const wav=await toWav(new Blob(parts,{type:rec.mimeType||'audio/webm'}));
      const b64=await new Promise((ok,no)=>{const fr=new FileReader();fr.onload=()=>ok(String(fr.result).split(',')[1]||'');fr.onerror=no;fr.readAsDataURL(wav)});
      let d;if(mode==='p'){const x=await apiTry(`/api/profile/dungeon/${DM.rid}/hoeren`,xjson('POST',{wav:b64}));if(!x.r.ok){dmSay(S,dmErr(x.r.status,x.d.detail),true);return}d=x.d}
      else d=await dgPub('/api/dungeon/hoeren',{code:DG.code,wav:b64});
      const ta=document.querySelector(mode==='p'?'#dmview .dm-in':'#dgcard .dm-in');
      if(fertig){if(d.text)fertig(d.text)}else if(ta&&d.text){ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+d.text;ta.focus()}dmSay(S,d.text?'':t('Nichts verstanden.','Nothing understood.'),false)}
    catch(e){dmSay(S,mode==='p'?t('Das hat nicht geklappt.','That did not work.'):dgErr(e),true)}};
  rec.start();mode==='p'?dmDraw():dgDraw()}
// the open page asks every poll seconds while it is to be seen; a redraw only when something changed (typing stays)
// the host paused the round (Dominik 2026-10-26 „sollte auch angezeigt werden, dass das Spiel sich gerade in Pause
// befindet“): a bar over the story for every seat and guest, the host gets „Weiter“ right there
// Knapp daneben (dungeon_knapp, D&D round 2 idea 1): the own near miss asks give up or pay; the others see who chooses
// Lagerfeuer und Rast (D&D idea 4, dungeon_rast): the host's two tiles in the console; the camp above the story while the
// rest waits for its narration, with the night watches and the own question card of the campfire
const DMWACHE={ruhig:'🌙',geraeusch:'👂',besuch:'🚶',ueberfall:'⚔'};
function dmRastTiles(v,tile){const r=v.rast;if(!r||!('kurz_frei' in r))return '';const zu=!r.geht?t('Nicht im Kampf und nur eine Rast auf einmal.','Not in a fight and only one rest at a time.'):'';
  return tile('data-dmrast="kurz"','☕',t('Kurze Rast','Short rest'),t(`noch ${r.kurz_frei}×`,`${r.kurz_frei}× left`),false,zu||(r.kurz_frei?'':t('Erst wieder nach einer langen Rast.','Only again after a long rest.')))
    +tile('data-dmrast="lang"','🔥',t('Lange Rast','Long rest'),r.lang_in?t(`in ${r.lang_in} Zügen`,`in ${r.lang_in} turns`):t('mit Nachtwachen','with night watches'),false,zu||(r.lang_in?t(`Die nächste lange Rast geht in ${r.lang_in} Zügen.`,`The next long rest is possible in ${r.lang_in} turns.`):''))}
// Tageszeit vom Panel (LlamaTale idea 1, dungeon_tageszeit): the section by the panel's rules and the turns until the next
function dmTageszeit(v){const z=v.tageszeit;if(!z)return '';return `<div class="dm-kalender dm-tageszeit" data-zeit="${esc(z.zeit)}">${esc(z.zeichen)} ${esc(z.name)} · ${esc(z.zuege===1?t('noch 1 Zug','1 turn left'):t(`noch ${z.zuege} Züge`,`${z.zuege} turns left`))}${z.dunkel?' · '+esc(t('ohne Licht: Nachteil','no light: disadvantage')):''}</div>`}
// Kalender der Welt (D&D idea 6, dungeon_kalender): the date, the moons, a festival today or soon, the market day
// Gegner-Ansagen und Haltung (round 2, idea 2, dungeon_haltung): two chips put the stance's word into the action
function dmHaltung(){return `<div class="dm-haltung">${[['Abwehr','Defend','🛡','+2 Rüstung, eigener Angriff mit Nachteil','+2 armour, own attack at a disadvantage'],['Ausweichen','Dodge','💨','Rettungswürfe mit Vorteil','saves with advantage']].map(([de,en,z,sd,se])=>`<button type="button" class="b" data-dmhaltung="${esc(t(de,en))}" title="${esc(t(sd,se))}">${z} ${esc(t(de,en))}</button>`).join('')}</div>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmhaltung]');if(!b)return;const a=b.closest('.dm-handeln'),x=a&&a.querySelector('textarea.dm-in');if(!x)return;
  x.value=(x.value.trim()?x.value.trim()+' ':'')+b.dataset.dmhaltung+'.';x.focus()});
// Herzenswunsch (round 2, idea 7, dungeon_wunsch): the own hero's secret wish, from the world's list or in own words; the host sees every seat's
// Gefährten (round 2, idea 9, dungeon_gefaehrte): the hired companions as rows of the group, without a seat; the panel rolls their blows
const DMGFAUS={am_boden:['am Boden','down'],geflohen:['geflohen','fled']};
// why a hero's experience grew (Kampfzug-Prüfung 4, dungeon.apply mark): fixed words of the panel
const DMEPGRUND={probe:['Probe','check'],ort:['neuer Ort','new place'],kampf:['Kampf','fight'],ziel:['Ziel','goal'],wunsch:['Herzenswunsch','heart\'s wish'],akt:['Akt','act'],auftrag:['Auftrag','errand']};
// the companion's face instead of 🤝 once painted (dungeon_gesicht, round 2, idea 9)
function dmGefaehrten(v){return (v.gefaehrten||[]).map(c=>`<div class="dm-seat dm-hero dm-gefaehrte${c.aus||!c.dabei?' aus':''}">${c.bild?`<span class="dm-av dm-avb"><img alt="${esc(t('Gesicht von ','Face of ')+c.name)}" loading="lazy" decoding="async" data-dmdbild="${esc(c.bild)}" data-dmdk="1"></span>`:'<span class="dm-av" aria-hidden="true">🤝</span>'}<div><b>${esc(c.name)}</b> <small class="mut">${esc(t('Gefährte','Companion'))}${c.von?' · '+esc(t('von ','of ')+c.von):''} · ${c.leben}/${c.max}</small><small class="dm-isatz">${esc(c.satz)}</small></div>${c.aus?`<small class="dm-state">${esc(t(...DMGFAUS[c.aus]||[c.aus,c.aus]))}</small>`:!c.dabei?`<small class="dm-state">${esc(t('wartet auf den Lohn','waits for the pay'))}</small>`:''}</div>`).join('')}
function dmWunsch(v){const w=v.wunsch;if(!w)return '';
  const andere=(w.andere||[]).map(x=>`<li>${esc(x.name)}: ${esc(x.text)}${x.erfuellt?' ✓':''}</li>`).join('');
  const kopf=w.text?(w.erfuellt?' ✓ '+esc(t('erfüllt','fulfilled')):w.dran?' · '+esc(t('in diesem Akt','this act')):''):' · '+esc(t('noch keiner','none yet'));
  return `<details class="dm-wunsch"><summary>💖 ${esc(t('Herzenswunsch','Heart\'s wish'))}${kopf}</summary>${w.text?`<p>${esc(w.text)}</p>`:''}`
    +`<select class="dm-wuid" aria-label="${esc(t('Wunsch aus der Liste','Wish from the list'))}"><option value="">${esc(t('Eigene Worte …','Own words …'))}</option>${(w.wahl||[]).map(x=>`<option value="${esc(x.id)}"${x.id===w.id?' selected':''}>${esc(x.t)}</option>`).join('')}</select>`
    +`<textarea class="dm-wutext" maxlength="${esc(String(w.max))}" rows="2" placeholder="${esc(t('Nur du und der Spielleiter sehen ihn.','Only you and the game master see it.'))}">${w.id?'':esc(w.text)}</textarea>`
    +`<button type="button" class="b" data-dmwunsch="1">${esc(t('Speichern','Save'))}</button>${w.text?` <button type="button" class="b" data-dmwunsch="0">${esc(t('Entfernen','Remove'))}</button>`:''}`
    +`${andere?`<small class="mut">${esc(t('Wünsche der anderen (nur für dich als Spielleiter):','The others\' wishes (only for you as game master):'))}</small><ul>${andere}</ul>`:''}</details>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmwunsch]');if(!b)return;const box=b.closest('.dm-wunsch'),g=!!b.closest('#dgcard'),S=g?DG:DM;
  const body=b.dataset.dmwunsch==='1'?{id:box.querySelector('.dm-wuid').value,text:box.querySelector('.dm-wutext').value.trim()}:{id:'',text:''};b.disabled=true;
  try{if(g){DG.v=await dgPub('/api/dungeon/wunsch',Object.assign({code:DG.code},body));DG.at=Date.now();dgDraw()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/wunsch`,xjson('POST',body));if(!r.ok){b.disabled=false;dmSay(DM,dmErr(r.status,d.detail),true);return}DM.v=d;DM.at=Date.now();dmDraw()}}
  catch(x){b.disabled=false;dmSay(S,g?dgErr(x):t('Das hat nicht geklappt.','That did not work.'),true)}});
// Flüstern mit einer Figur (round 2, idea 5, dungeon_fluestern): once a turn a word only this seat hears; the answer is read aloud only by this device
function dmFluestern(v){const f=v.fluestern;if(!f)return '';
  const meine=(f.meine||[]).slice(-3).reverse().map(x=>`<div class="dm-fl"><small class="mut">🤫 ${esc(t('Du zu '+x.an+': ','You to '+x.an+': ')+x.text)}</small><div><b>${esc(x.an)}:</b> „${esc(x.antwort)}“ <button type="button" class="b" data-dmflsag="${esc(x.antwort)}" title="${esc(t('Nur auf diesem Gerät vorlesen','Read aloud on this device only'))}" aria-label="${esc(t('Vorlesen','Read aloud'))}">🔊</button></div>${x.gold?`<small>🪙 +${esc(String(x.gold))} ${esc(t('Gold geschenkt','gold given'))}</small>`:''}${x.verraten?`<small class="dm-warn">${esc(t(x.an+' hat es weitererzählt.',x.an+' told on it.'))}</small>`:''}</div>`).join('');
  const andere=(f.andere||[]).filter(x=>x.zug===v.zug).map(x=>`<small class="mut">🤫 ${esc(t(x.wer+' flüstert mit '+x.an+'.',x.wer+' whispers with '+x.an+'.'))}</small>`).join('<br>');
  const form=f.frei&&f.figuren.length?`<details class="dm-flform"><summary>🤫 ${esc(t('Flüstern','Whisper'))}</summary><select class="dm-flan" aria-label="${esc(t('Mit wem','With whom'))}">${f.figuren.map(n=>`<option>${esc(n)}</option>`).join('')}</select><textarea class="dm-flin" maxlength="200" rows="2" placeholder="${esc(t('Nur diese Figur hört es.','Only this person hears it.'))}"></textarea><button type="button" class="b" data-dmfl="1">${esc(t('Flüstern','Whisper'))}</button></details>`:'';
  return form||meine||andere?`<div class="dm-fluestern">${form}${meine}${andere?`<div>${andere}</div>`:''}</div>`:''}
document.body.addEventListener('click',async e=>{const s=e.target.closest('[data-dmflsag]');
  if(s){try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(s.dataset.dmflsag);u.lang=L==='en'?'en-GB':'de-DE';speechSynthesis.speak(u)}catch{}return}
  const b=e.target.closest('[data-dmfl]');if(!b)return;const box=b.closest('.dm-flform'),g=!!b.closest('#dgcard'),S=g?DG:DM;
  const body={an:box.querySelector('.dm-flan').value,text:box.querySelector('.dm-flin').value.trim()};if(!body.text)return;b.disabled=true;
  try{if(g){DG.v=await dgPub('/api/dungeon/fluestern',Object.assign({code:DG.code},body));DG.at=Date.now();dgDraw()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/fluestern`,xjson('POST',body));if(!r.ok){b.disabled=false;dmSay(DM,dmErr(r.status,d.detail),true);return}DM.v=d;DM.at=Date.now();dmDraw()}}
  catch(x){b.disabled=false;dmSay(S,g?dgErr(x):t('Das hat nicht geklappt.','That did not work.'),true)}});
// Gedanken lesen (LlamaTale idea 5, dungeon_gedanken): the fixed lines only this seat heard; the host also whose thoughts were read
function dmGedanken(v){const g=v.gedanken;if(!g)return '';
  const meine=(g.meine||[]).slice().reverse().map(x=>`<div class="dm-fl dm-gedanken${x.ok?'':' mut'}"><small>🧠 ${esc(x.zeile)}</small></div>`).join('');
  const andere=(g.andere||[]).filter(x=>x.zug===v.zug-1||x.zug===v.zug).map(x=>`<small class="mut">🧠 ${esc(t(x.wer+' liest die Gedanken von '+x.nsc+'.',x.wer+' reads the thoughts of '+x.nsc+'.'))}</small>`).join('<br>');
  return meine||andere?`<div class="dm-fluestern">${meine}${andere?`<div>${andere}</div>`:''}</div>`:''}
// Umgebung nutzen (round 2, idea 3, dungeon_umgebung): the fight's props as chips, a chip puts its use into the action
function dmUmgebung(v){return `<div class="dm-haltung dm-umgebung">${v.umgebung.map(x=>`<button type="button" class="b" data-dmumgebung="${esc(t('Ich nutze '+x.name,'I use the '+x.name))}" title="${esc(x.wirkt)}">${esc(x.zeichen)} ${esc(x.name)}</button>`).join('')}</div>`}
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmumgebung]');if(!b)return;const a=b.closest('.dm-handeln'),x=a&&a.querySelector('textarea.dm-in');if(!x)return;
  x.value=(x.value.trim()?x.value.trim()+' ':'')+b.dataset.dmumgebung+'.';x.focus()});
function dmKalender(v){const k=v.kalender;if(!k)return '';return `<div class="dm-kalender">📅 ${esc(k.text)}${k.fest?` · 🎉 <b>${esc(k.fest)}</b>${k.aufschlag?` (${esc(t('Dienste','services'))} +${esc(String(k.aufschlag))} %)`:''}`:k.bald?` · ${esc(k.bald)} ${esc(t('in','in'))} ${esc(String(k.in))} ${esc(k.in===1?t('Tag','day'):t('Tagen','days'))}`:''}${k.markt?' · 🧺 '+esc(t('Markttag','market day')):''}${k.fest&&k.satz?`<div class="dm-kalsatz">${esc(k.satz)}</div>`:''}</div>`}
function dmRast(v){const e=v.rast&&v.rast.jetzt;if(!e)return '';
  return `<div class="dm-rast" role="status"><b>${e.art==='lang'?'🔥 '+esc(t('Lange Rast','Long rest')):'☕ '+esc(t('Kurze Rast','Short rest'))}</b> <small class="mut">· ${esc(e.landschaft)}</small>${e.gestoert?` <span class="pill warn">${esc(t('Nacht gestört','night disturbed'))}</span>`:''}
    ${e.wachen.length?`<ol class="dm-wachen">${e.wachen.map(x=>`<li>${DMWACHE[x.art]||'·'} ${esc(x.t)}</li>`).join('')}</ol>`:''}${e.frage?`<div class="dm-frage">🔥 ${esc(t('Frage am Lagerfeuer','Question at the campfire'))}: <b>${esc(e.frage)}</b></div>`:''}</div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmrast]');if(!b||!DM.rid||b.disabled)return;
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/rast`,{art:b.dataset.dmrast},DM);if(d){DM.v=d;DM.at=Date.now();dmDraw()}});
function dmKnapp(v){const k=v.knapp;if(!k)return '';const W=v.werte||{},f=k.frage;
  if(!f)return k.andere.length?`<div class="dm-knapp mut" role="status">⚖ ${esc(t(k.andere.join(', ')+' überlegt, ob es einen Preis zahlt …',k.andere.join(', ')+' is deciding whether to pay a price …'))}</div>`:'';
  const was=(W[f.wert]||f.wert)+': '+f.gesamt+(L==='en'?' vs ':' gegen ')+f.schwer+(f.wofuer?' · '+f.wofuer:'');
  return `<div class="dm-knapp" role="alertdialog" aria-label="${esc(t('Knapp daneben','Near miss'))}"><b>⚖ ${esc(t('Knapp daneben!','Near miss!'))}</b><small>${esc(was+'. '+t('Aufgeben oder es mit einem gewürfelten Preis doch schaffen? Noch '+k.rest+' s.','Give up, or make it after all at a rolled price? '+k.rest+' s left.'))}</small><div class="dm-knappb"><button type="button" class="b" data-dmknapp="aufgeben">${esc(t('Aufgeben','Give up'))}</button><button type="button" class="b p" data-dmknapp="zahlen">${esc(t('Zahlen','Pay'))}</button></div></div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('[data-dmknapp]');if(!b)return;const g=!!b.closest('#dgcard'),S=g?DG:DM,v=S.v;if(!v||!v.knapp)return;
  const body={zug:v.knapp.zug,wahl:b.dataset.dmknapp};b.disabled=true;
  try{if(g){DG.v=await dgPub('/api/dungeon/knapp',Object.assign({code:DG.code},body));DG.at=Date.now();dgDraw()}
    else{const {r,d}=await apiTry(`/api/profile/dungeon/${DM.rid}/knapp`,xjson('POST',body));if(!r.ok){dmSay(DM,dmErr(r.status,d.detail),true);b.disabled=false;return}DM.v=d;DM.at=Date.now();dmDraw()}}
  catch(x){b.disabled=false;dmSay(S,g?dgErr(x):t('Das hat nicht geklappt.','That did not work.'),true)}});
function dmPauseBar(v,leitet){if(!v.pause||v.status==='ende')return '';
  return `<div class="dm-pausebar" role="status"><span aria-hidden="true">⏸</span><div><b>${esc(t('Pause','Paused'))}</b><small>${esc(leitet?t('Du hast die Runde angehalten, die Zeit steht. Aktionen können schon geschrieben werden.','You paused the round, the clock stands still. Actions can be written already.'):t('Der Spielleiter hat die Runde angehalten, die Zeit steht. Du kannst deine Aktion schon schreiben.','The game master paused the round, the clock stands still. You may write your action already.'))}</small></div>${leitet?`<button type="button" class="b p" data-dmpause="0">▶ ${esc(t('Weiter','Go on'))}</button>`:''}</div>`}
function dmSig(v){return v?[v.zug,v.log.length,v.dm,v.pause,v.status,v.vorlesen,v.liest,v.spricht,v.lesung?[v.lesung.n,v.lesung.k,v.lesung.fertig].join():'',v.akt,v.erzaehlt,v.plaetze.map(p=>[p.pid,p.gehandelt,p.online,p.leben,p.stufe,p.zustand,p.noch].join()).join('|'),v.meine_aktion,JSON.stringify(v.fluestern||null),JSON.stringify(v.gedanken||null),JSON.stringify(v.auftraege||null),JSON.stringify(v.wunsch||null),JSON.stringify(v.gefaehrten||null),JSON.stringify(v.ich),JSON.stringify(v.angebote||[]),JSON.stringify(v.markt||null),(v.boden||[]).map(x=>x.i).join(),v.plaetze.map(p=>(p.tasche||[]).map(x=>x.i).join()).join('|'),(v.bilder||[]).map(x=>x.b).join(),v.bild_malt,v.bild_hint,v.bild_grund,v.portraet_malt,v.portraet_hint,JSON.stringify(v.karte||null),v.plaetze.map(p=>p.bild).join(),v.termin,v.melden,JSON.stringify(v.musik||null),(v.faeden||[]).join('|'),JSON.stringify(v.auftrag||null),JSON.stringify(v.daumen||{}),JSON.stringify(v.fall||{}),v.neu_laeuft||0,JSON.stringify(v.mut||null),JSON.stringify(v.siedlung||null),JSON.stringify(v.grenzen||null),JSON.stringify(v.zufall||null),JSON.stringify(v.orakel||null),JSON.stringify(v.kampfstufe||null),JSON.stringify(v.nsc||null),JSON.stringify(v.nsc_geheim||null),JSON.stringify(v.fraktionen||null),JSON.stringify(v.fraktionen_geheim||null),JSON.stringify(v.quest||null),JSON.stringify(v.quest_geheim||null),JSON.stringify(v.wahrheit||null),JSON.stringify(v.dinge||null),(v.tisch||[]).length,(v.tippt||[]).join(),JSON.stringify(v.warten||null),JSON.stringify(v.echt||null),JSON.stringify(v.knapp||null),JSON.stringify(v.schrift||null),JSON.stringify(v.echt_plaetze||null),JSON.stringify(v.rueckfrage||null),JSON.stringify(v.anleiten||null)].join('#'):''}
setInterval(async()=>{if(document.visibilityState!=='visible')return;
  if(DM.v&&$('dmview')&&$('dungeon').classList.contains('on')&&!DM.busy&&Date.now()-DM.at>=DM.v.poll*1000){const old=dmSig(DM.v),at0=DM.at;DM.at=Date.now();
    // „nichts neu“ (Punkt 14 of 2026-10-24): the panel answers {neu:false} while the seat's stand is the same; the clock keeps its start (t0)
    const {r,d}=await apiTry('/api/profile/dungeon/'+DM.rid+'?stand='+encodeURIComponent(DM.v.stand||''));
    if(r.ok&&DM.v&&d.neu===false){if(!DM.v.t0)DM.v.t0=at0;DM.at=Date.now();dmLeft(DM)}
    else if(r.ok&&DM.v){DM.v=d;DM.at=Date.now();if(dmSig(d)!==old)dmDraw();else dmLeft(DM)}}
  else if(DM.v)dmLeft(DM);
  else if(!DM.v&&DM.data&&(DM.data.kampagnen||[]).some(k=>k.schreibt)&&$('dmview')&&Date.now()-DM.at>=3000){DM.at=Date.now();dmLoad()}
  const m=$('dgmodal');if(DG.v&&m&&m.style.display==='grid'&&!DG.busy&&Date.now()-DG.at>=DG.v.poll*1000){const old=dmSig(DG.v),at0=DG.at;DG.at=Date.now();
    try{const d=await dgPub('/api/dungeon/lage',{code:DG.code,stand:DG.v.stand||''});
      if(d.neu===false){if(!DG.v.t0)DG.v.t0=at0;DG.at=Date.now();dmLeft(DG)}else{DG.v=d;DG.at=Date.now();if(dmSig(d)!==old)dgDraw()}}
    catch(e){dmSay(DG,dgErr(e),true)}}},1000);
// „✓ Gesendet“: the card pops in for a moment, a phone vibrates once
function dmSent(){DMA.gesendet=Date.now();try{if(navigator.vibrate)navigator.vibrate(30)}catch(e){}}
// the host on a fellow player's seat (Dominik 2026-10-24 „andere spieler bearbeiten, bzw. löschen … den code nochmal dem
// spieler geben“): a guest's new link (shown once with its QR), not waited for / again, off the table (asks once more)
function dmSeatMenu(p){const k='s:'+p.pid,nl=DM.neulink&&DM.neulink.pid===p.pid?DM.neulink:null,weg=DM.sitzweg===p.pid;
  return `<details class="dm-smenu" data-dmauf="${esc(k)}"${DMA.auf===k||nl||weg?' open':''}><summary class="ic-ib" title="${esc(t('Mitspieler verwalten','Manage player'))}" aria-label="${esc(t('Mitspieler verwalten','Manage player')+': '+p.name)}">⋯</summary><div class="dm-smenu-l">
    ${p.gast?`<button type="button" class="dm-zeile" data-dmsitz="link" data-pid="${esc(p.pid)}"><span>🔗 ${esc(t('Neuer Link','New link'))}</span><small>${esc(t('der alte gilt dann nicht mehr','the old one stops working'))}</small></button>`:''}
    ${nl?`<div class="mitmade"><div class="jqr">${nl.qr||''}</div><div class="sp"><input readonly value="${esc(nl.link)}" aria-label="${esc(t('Der neue Link','The new link'))}"><small class="mut">${esc(t('Nur jetzt zu sehen. Schick ihn '+p.name+'; der Held bleibt, wie er ist.','Shown only now. Send it to '+p.name+'; the hero stays as it is.'))}</small></div></div>`:''}
    <div class="dm-zeile dm-sname-z"><span>✎ ${esc(t('Umbenennen','Rename'))}</span><div class="row"><input class="dm-sname" maxlength="24" value="${esc(p.name)}" aria-label="${esc(t('Neuer Name des Helden','The hero\'s new name'))}"><button type="button" class="b" data-dmsitz="name" data-pid="${esc(p.pid)}">${esc(t('Sichern','Save'))}</button></div><small>${esc(t('nur der Name, die Werte bleiben','only the name, the values stay'))}</small></div>
    <button type="button" class="dm-zeile" data-dmsitz="${p.stumm?'laut':'stumm'}" data-pid="${esc(p.pid)}"><span>${esc(p.stumm?'💬 '+t('Wieder mitreden lassen','Let talk again'):'🔇 '+t('Im Tischgespräch stumm','Mute in table talk'))}</span><small>${esc(p.stumm?t(p.name+' kann wieder ins Tischgespräch schreiben',p.name+' can write in the table talk again'):t('Aktionen gehen weiter, nur das Tischgespräch nicht','actions go on, only the table talk stops'))}</small></button>
    <button type="button" class="dm-zeile" data-dmsitz="${p.ruht?'wecken':'ruhen'}" data-pid="${esc(p.pid)}"><span>${esc(p.ruht?'▶ '+t('Wieder warten','Wait again'):'⏸ '+t('Nicht mehr warten','Stop waiting'))}</span><small>${esc(p.ruht?t('der Zug wartet wieder auf '+p.name,'the turn waits for '+p.name+' again'):t('bis '+p.name+' wieder handelt','until '+p.name+' acts again'))}</small></button>
    <button type="button" class="dm-zeile dm-weg" data-dmseatdel="${esc(p.pid)}"><span>${esc(weg?t('Wirklich vom Tisch nehmen?','Really take off the table?'):t('Vom Tisch nehmen','Take off the table'))}</span><small>${esc(p.gast?t('ohne Gast-Konto oder Figur-Code ist der Held dann weg','without a guest account or hero code the hero is gone'):t('der Held bleibt im Profil','the hero stays in the profile'))}</small></button></div></details>`}
function dmMine(v,wait,S,plus){return `<div class="dm-mein${Date.now()-DMA.gesendet<2500?' neu':''}" role="status"><span class="dm-mein-ok" aria-hidden="true">✓</span><div class="dm-mein-t"><small>${esc(t('Deine Aktion für Zug '+v.zug,'Your action for turn '+v.zug))}</small><p>${dmFx(v.meine_aktion)}</p>
    <small class="dm-mein-w">${esc(wait.length?t('Wartet auf ','Waiting for ')+wait.join(', '):t('Alle haben gehandelt, der Dungeon-Master erzählt gleich.','Everyone has acted, the Dungeon Master tells on shortly.'))}<span class="dm-mein-z"></span></small></div>
    <div class="dm-mein-k"><button type="button" class="b" data-dmaendern="1">${esc(t('Ändern','Change'))}</button>${plus||''}</div></div>${v.rueckfrage?dmRf(v.rueckfrage):''}${dmMsg(S)}`}
// Rückfrage bei unklaren Aktionen (dungeon_rueckfrage.py): the question, up to three suggestions from the scene's data
// (tap: into the field, still to change) and „So lassen“; the action counts as written when the turn's time runs out
function dmRf(f){return `<div class="dm-hint dm-rf" role="group" aria-label="${esc(f.frage)}"><b>❓ ${esc(f.frage)}</b>${f.warum?` <small class="mut">${esc(f.warum)}</small>`:''}
    <div class="dm-kfilter">${(f.vorschlaege||[]).map(x=>`<button type="button" class="dm-kf" data-dmrf="${esc(x)}">${esc(x)}</button>`).join('')}<button type="button" class="b" data-dmrfok="1">${esc(t('So lassen','Keep it'))}</button></div>
    <small class="mut">${esc(t('Ohne Antwort gilt die Aktion wie geschrieben, sobald die Zugzeit um ist.','Without an answer the action counts as written once the turn\'s time is up.'))}</small></div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmrf],#dgcard [data-dmrf],#dmview [data-dmrfok],#dgcard [data-dmrfok]');if(!b)return;
  const g=!!b.closest('#dgcard'),v=g?DG.v:DM.v;if(!v)return;
  if(b.dataset.dmrf!==undefined){DMA.rf={m:g?'g':'p',t:b.dataset.dmrf};DMA.aendern[g?'g':'p']=v.zug;g?dgDraw():dmDraw();return}
  const body={text:v.meine_aktion,zug:v.zug,so_lassen:true};
  if(g){await dgAct('/api/dungeon/aktion',body);dgDraw();return}
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/aktion`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()});
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmaendern],#dgcard [data-dmaendern]');if(!b)return;const g=!!b.closest('#dgcard'),v=g?DG.v:DM.v;if(!v)return;
  DMA.aendern[g?'g':'p']=v.zug;g?dgDraw():dmDraw()});
// the turn's clock (Dominik 2026-10-24 „die interaktion geht zu schnell weg“, „1-5“): first the reading time, then the
// turn's time; after the last action GNADE_S to change it; red from warn_s on, a phone vibrates once per turn
const dmMS=s=>Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
function dmUhr(v,S){const el=(Date.now()-(v.t0||S.at))/1000,lese=Math.max(0,Math.round(v.lesen-el)),gn=Math.max(0,Math.round(v.gnade-el));
  const sek=Math.max(0,Math.round(v.rest-Math.max(0,el-v.lesen))),done=v.plaetze.filter(p=>!p.frei&&p.gehandelt).length,all=v.plaetze.filter(p=>!p.frei).length;
  const warn=!!done&&!v.pause&&!v.spricht&&!gn&&!lese&&sek<=v.warn_s;
  const mehr=(v.mehr||[]).length?t(' · mehr Zeit für ',' · more time for ')+v.mehr.join(', '):'';
  const text=`${done} ${t('von','of')} ${all} ${t('haben gehandelt','have acted')}`+(v.pause?'':v.spricht?t(' · wird vorgelesen, die Uhr startet danach',' · being read aloud, the clock starts afterwards'):gn?t(' · geht in '+gn+' s weiter',' · goes on in '+gn+' s'):
    lese?t(' · Lesezeit, die Uhr startet in '+lese+' s',' · reading time, the clock starts in '+lese+' s'):done?t(' · weiter spätestens in ',' · goes on at the latest in ')+dmMS(sek):'')+mehr;
  const mine=v.pause?t(' · Pause',' · paused'):v.spricht?t(' · wird vorgelesen, die Uhr startet danach',' · being read aloud, the clock starts afterwards'):gn?t(' · geht in '+gn+' s weiter, „Ändern“ geht noch',' · goes on in '+gn+' s, "Change" still works'):t(' · spätestens in ',' · at the latest in ')+dmMS(sek)+dmMehrIch(v);
  return {text,mine,warn}}
// the own card's line names the own extra minute as „für dich“, never the own name (it waits for nobody else)
function dmMehrIch(v){const me=v.ich&&v.ich.name,m=v.mehr||[],o=m.filter(x=>x!==me);
  return (o.length?t(' · mehr Zeit für ',' · more time for ')+o.join(', '):'')+(me&&m.includes(me)?t(' · +1 Minute für dich',' · +1 minute for you'):'')}
function dmLeft(S){const v=S.v,els=document.querySelectorAll(S===DM?'#dmview .dm-left':'#dgcard .dm-left');if(!v||v.dm||v.status==='ende')return;   // the clock above the field or, once acted, in the own card
  const u=dmUhr(v,S);els.forEach(el=>{el.textContent=u.text;el.classList.toggle('dm-warn',u.warn)});
  if(u.warn&&DMA.warnt!==S.v.rid+':'+v.zug){DMA.warnt=S.v.rid+':'+v.zug;try{if(navigator.vibrate)navigator.vibrate([60,80,60])}catch(e){}}
  const z=document.querySelector(S===DM?'#dmview .dm-mein-z':'#dgcard .dm-mein-z');if(z){z.textContent=u.mine;z.classList.toggle('dm-warn',u.warn)}}
const dmHeroBody2=B=>({was:B.dmhero,i:B.i,wert:B.wert,id:B.id,platz:B.platz,mit:B.mit,an:B.an,q:B.q});
async function dmHeroDo(mode,b){if(mode==='g'){await dgAct('/api/dungeon/held',b);return}
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,b,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
document.body.addEventListener('dragstart',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmdrag],#dgcard [data-dmdrag]');if(!el)return;
  e.dataTransfer.setData('text/plain','dm:'+el.dataset.dmdrag);e.dataTransfer.effectAllowed='move';
  const pl=(el.dataset.dmpl||'').split(' ').filter(Boolean);if(pl.length)el.closest('#dmview,#dgcard').querySelectorAll('[data-dmslot]').forEach(s=>s.classList.add(pl.includes(s.dataset.dmslot)?'dm-passt':'dm-nein'))});   // where it fits lights up
document.body.addEventListener('dragend',()=>document.querySelectorAll('.dm-passt,.dm-nein').forEach(s=>s.classList.remove('dm-passt','dm-nein')));
document.body.addEventListener('dragover',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmslot],#dmview [data-dmbag],#dgcard [data-dmslot],#dgcard [data-dmbag]');if(el)e.preventDefault()});
document.body.addEventListener('drop',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmslot],#dmview [data-dmbag],#dgcard [data-dmslot],#dgcard [data-dmbag]');if(!el)return;
  const x=(e.dataTransfer.getData('text/plain')||'');if(!x.startsWith('dm:'))return;e.preventDefault();const id=x.slice(3),mode=el.closest('#dgcard')?'g':'p';
  if(el.dataset.dmslot&&id.startsWith('i'))dmHeroDo(mode,{was:'anlegen',i:id,platz:el.dataset.dmslot});
  else if(el.dataset.dmbag&&!id.startsWith('i'))dmHeroDo(mode,{was:'ablegen',platz:id})});
async function dmSend(path,b,S,x){if(S.busy)return null;S.busy=true;
  const o=x?xjson(x.method,Object.assign({lang:dmLang()},x.body||{})):b===null?{method:'DELETE'}:xjson('POST',Object.assign({lang:dmLang()},b||{}));const {r,d}=await apiTry(path,o);S.busy=false;
  if(!r.ok){dmSay(S,dmErr(r.status,d.detail),true);return null}S.msg='';S.err=false;return d}
// ---------------------------------------------------------------- clicks of the own page
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmopen],#dmview [data-dmback],#dmview [data-dmmake],#dmview [data-dmseg],#dmview [data-dmgs],#dmview [data-dmsend],#dmview [data-dmhero],#dmview [data-dmweiter],#dmview [data-dmpause],#dmview [data-dmmarkt],#dmview [data-dminvite],#dmview [data-dmsitz],#dmview [data-dmseatdel],#dmview [data-dmend],#dmview [data-dmdelhero],#dmview [data-dmwipe],#dmview [data-dmtx],#dmview [data-dmvorlesen],#dmview [data-dmkap],#dmview [data-dmhear],#dmview [data-dmvoll],#dmview [data-dmhilfe],#dmview [data-dmprobe],#dmview [data-dmerzprobe],#dmview [data-dmerzneu],#dmview [data-dmmic],#dmview [data-dmkweiter],#dmview [data-dmkedit],#dmview [data-dmksave],#dmview [data-dmkneu],#dmview [data-dmkdel],#dmview [data-dmkbuch],#dmview [data-dmkblatt],#dmview [data-dmkseite],#dmview [data-dmbild],#dmview [data-dmportraet],#dmview [data-dmtermin],#dmview [data-dmmelden],#dmview [data-dmmehr],#dmview [data-dmhide]');
  if(!b)return;const B=b.dataset,w=$('dmview'),rid=DM.rid;
  if(B.dmseg!==undefined){b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));if(b.closest('.dmf-welt'))dmWorld(w,B.dmseg);return}
  if(B.dmgs!==undefined){dmStory(w,b);return}
  if(B.dmopen){DM.rid=B.dmopen;DM.made=null;DM.ende=false;DMLES.p.n=null;await dmRound();return}
  if(B.dmback){DM.rid='';DM.v=null;DM.made=null;await dmLoad();return}
  if(B.dmmake){const q=c=>w.querySelector(c),D=DM.data,body={titel:q('.dmf-titel').value.trim(),welt:q('.dmf-welt .on').dataset.dmseg,einstieg:q('.dmf-einstieg').value.trim(),
      ton:+q('.dmf-ton .on').dataset.dmseg,zug_s:+q('.dmf-zug').value,stunden:+q('.dmf-stunden').value,held:dmHeroBody(w,'dmf-'),vorlesen:q('.dmf-vorlesen').checked,erzaehlweise:q('.dmf-weise').value};
    const gs=q('.dmf-gesch .on');if(gs&&gs.dataset.dmgs)body.geschichte=gs.dataset.dmgs;
    const p=q('.dmf-prompt').value.trim();if(p&&p!==D.wahl.prompt)body.prompt=p;
    if(body.titel.length<2){dmSay(DM,t('Bitte gib der Runde einen Titel.','Please give the round a title.'),true);return}
    const pt=q('.dmf-portraet'),want=pt&&pt.checked&&typeof body.held==='object';
    let d=await dmSend('/api/profile/dungeon/runde',body,DM);if(d&&want)d=await dmSend(`/api/profile/dungeon/${d.rid}/portraet`,{},DM)||d;
    if(d){DM.rid=d.rid;DM.v=d;DM.at=Date.now();DMLES.p.n=-1;dmDraw()}return}
  if(B.dmtx){const m=await dmTx(B,'p',async b2=>{const d=await dmSend(`/api/profile/dungeon/${rid}/held`,b2,DM);if(d){DM.v=d;DM.at=Date.now()}return !!d});
    if(typeof m==='string')dmSay(DM,m,true);dmDraw();return}
  if(B.dmhear){dmHear('p',B.dmhear);return}
  if(B.dmvoll){dmVoll(B.dmvoll==='1');return}
  if(B.dmhilfe){dmHilfeAuf(B.dmhilfe);dmDraw();return}
  if(B.dmprobe){dmProbe('p',DM.v&&DM.v.ich||{});return}
  if(B.dmerzprobe){const sel=document.querySelector('#dmview [data-dmerz]');dmProbe('p',{erzaehler:sel?sel.value:''});return}
  if(B.dmmic){dmMic('p');return}
  if(B.dmkedit!==undefined){DM.edit=B.dmkedit;dmDraw();return}
  if(B.dmkbuch!==undefined){if(!B.dmkbuch){DM.buch=null;dmDraw();return}const {r,d}=await apiTry(`/api/profile/dungeon/kampagne/${B.dmkbuch}/chronik`);
    if(!r.ok){dmSay(DM,dmErr(r.status,d.detail),true);dmDraw();return}DM.buch={kid:B.dmkbuch,d,i:Math.max(0,(d.seiten||[]).length-1)};dmDraw();return}
  if(B.dmkblatt&&DM.buch){DM.buch.i+=Number(B.dmkblatt);dmDraw();return}
  if(B.dmkseite&&DM.buch){const d=await dmSend(`/api/profile/dungeon/kampagne/${DM.buch.kid}/chronik/loeschen`,{kapitel:Number(B.dmkseite)},DM);if(d){DM.buch.d=d;DM.buch.i=Math.min(DM.buch.i,d.seiten.length-1);dmLoad()}dmDraw();return}
  if(B.dmksave||B.dmkneu||B.dmkdel){const kid=B.dmksave||B.dmkneu||B.dmkdel;
    const x=B.dmksave?await dmSend('/api/profile/dungeon/kampagne/'+kid,null,DM,{method:'PUT',body:{bisher:(w.querySelector('.dm-kedit')||{}).value||''}})
      :B.dmkneu?await dmSend(`/api/profile/dungeon/kampagne/${kid}/neu`,{},DM):await dmSend('/api/profile/dungeon/kampagne/'+kid,null,DM);
    if(x){DM.data=x;DM.edit=''}dmDraw();return}
  if(B.dmkweiter){const d=await dmSend(`/api/profile/dungeon/kampagne/${B.dmkweiter}/weiter`,{},DM);if(d){DM.rid=d.rid;DM.v=d;DM.at=Date.now();DMLES.p.n=-1}dmDraw();return}
  if(B.dmkap){if(!DM.kap){DM.kap=true;dmDraw();return}DM.kap=false;
    const x=await dmSend(`/api/profile/dungeon/${rid}/kapitel`,{},DM);if(x){DM.data=x;DM.rid='';DM.v=null;DM.made=null;DM.at=Date.now();icTabSet('dungeon','runden')}dmDraw();return}
  if(B.dmdelhero){const d=await dmSend('/api/profile/dungeon/held/'+B.dmdelhero,null,DM);if(d){DM.data=d;dmDraw()}return}
  if(B.dmwipe){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich alles löschen?','Really delete everything?');return}
    const d=await dmSend('/api/profile/dungeon/daten',null,DM);if(d){DM.rid='';DM.v=null;await dmLoad()}return}
  let d=null;
  if(B.dmsend){const ta=w.querySelector('.dm-in');const text=(ta&&ta.value||'').trim();if(!text)return;
    d=await dmSend(`/api/profile/dungeon/${rid}/aktion`,{text,zug:DM.v.zug,mut:!!DMA.mut.p},DM);if(d){if(ta)ta.value='';DMA.aendern.p=0;DMA.mut.p=0;dmSent()}}
  else if(B.dmhero)d=await dmSend(`/api/profile/dungeon/${rid}/held`,dmHeroBody2(B),DM);
  else if(B.dmmarkt)d=await dmSend(`/api/profile/dungeon/${rid}/markt`,{auf:B.dmmarkt==='1'},DM);
  else if(B.dmweiter)d=await dmSend(`/api/profile/dungeon/${rid}/weiter`,{},DM);
  else if(B.dmpause)d=await dmSend(`/api/profile/dungeon/${rid}/pause`,{an:B.dmpause==='1'},DM);
  else if(B.dmvorlesen)d=await dmSend(`/api/profile/dungeon/${rid}/vorlesen`,{an:B.dmvorlesen==='1'},DM);
  else if(B.dmerzneu)d=await dmSend(`/api/profile/dungeon/${rid}/erzaehler`,{k:''},DM);
  else if(B.dmbild)d=await dmSend(`/api/profile/dungeon/${rid}/bild`,{},DM);
  else if(B.dmportraet)d=await dmSend(`/api/profile/dungeon/${rid}/portraet`,{},DM);
  else if(B.dmmehr)d=await dmSend(`/api/profile/dungeon/${rid}/mehrzeit`,{},DM);
  else if(B.dmmelden)d=await dmSend(`/api/profile/dungeon/${rid}/melden`,{an:B.dmmelden==='1'},DM);
  else if(B.dmtermin){const x=w.querySelector('.dm-tin'),tt=B.dmtermin==='1'&&x&&x.value?Math.floor(new Date(x.value).getTime()/1000):0;
    if(B.dmtermin==='1'&&!(tt*1000>Date.now())){dmSay(DM,t('Bitte einen Zeitpunkt in der Zukunft wählen (höchstens 60 Tage).','Please pick a time in the future (60 days at most).'),true);return}
    d=await dmSend(`/api/profile/dungeon/${rid}/termin`,{t:tt},DM)}
  else if(B.dminvite){d=await dmSend(`/api/profile/dungeon/${rid}/platz`,{base:location.origin},DM);if(d)DM.made={link:d.link,qr:d.qr}}
  else if(B.dmseatdel){const fp=!b.closest('.dm-smenu');if(!fp&&DM.sitzweg!==B.dmseatdel){DM.sitzweg=B.dmseatdel;dmDraw();return}
    DM.sitzweg='';d=await dmSend(`/api/profile/dungeon/${rid}/platz/${B.dmseatdel}`,null,DM)}
  else if(B.dmhide){d=await dmSend(`/api/profile/dungeon/${rid}/verbergen`,{art:B.dmhide,n:+B.n,pid:B.pid||''},DM);if(d)sayToast(t('Ausgeblendet','Hidden'))}
  else if(B.dmsitz){d=await dmSend(`/api/profile/dungeon/${rid}/platz/${B.pid}`,null,DM,{method:'PUT',body:{was:B.dmsitz,base:location.origin,name:B.dmsitz==='name'?((b.closest('.dm-smenu')||document).querySelector('.dm-sname')||{}).value||'':undefined}});
    if(d&&B.dmsitz==='name')sayToast(t('Umbenannt','Renamed'));
    DM.neulink=d&&d.link?{pid:B.pid,link:d.link,qr:d.qr}:null}
  else if(B.dmend){if(!DM.ende){DM.ende=true;dmDraw();return}DM.ende=false;
    const x=await dmSend(`/api/profile/dungeon/${rid}`,null,DM);if(x){DM.data=x;DM.rid='';DM.v=null;DM.made=null;dmDraw()}return}
  if(d){DM.v=d;DM.at=Date.now()}dmDraw()});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmvoice],#dgcard [data-dmvoice]');if(!s)return;
  const box=s.closest('.dm-voice'),body={was:'stimme',stimme:(box.querySelector('select[data-dmvoice]')||{}).value||'',klang:((box.querySelector('.dm-klang')||{}).value||'').trim()};
  if(s.closest('#dmview')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
  else await dgAct('/api/dungeon/held',body)});
// a fixed sentence in the hero's voice, fetched when asked (the same playback as the turn read aloud)
// the host's narrator voice (dungeon_stimmen.py): only with VoiceDesign; pick one of the world's, roll a new one, listen
// the round's way of telling (Dominik 2026-10-24 „erzählungen etwas ausweiten“): knapp, normal or ausführlich; the
// panel makes the moments (a new place, a fight, a 20 or a 1) longer by itself
function dmWeise(cls,cur,attr){const W={knapp:t('knapp','brief'),normal:t('normal','normal'),ausfuehrlich:t('ausführlich','rich')};
  return `<select${cls?` class="${cls}"`:''} ${attr||''} aria-label="${esc(t('Erzählweise','Way of telling'))}">${Object.keys(W).map(k=>`<option value="${k}"${k===cur?' selected':''}>${esc(W[k])}</option>`).join('')}</select>`}
function dmErzWahl(v){if(!v.stimme_design||!(v.erzaehler_liste||[]).length)return '';
  return `<div class="dm-voice dm-erzwahl"><label>${esc(t('🎙 Stimme des Erzählers','🎙 Narrator\'s voice'))}</label><div class="dm-inp"><select data-dmerz="1" aria-label="${esc(t('Stimme des Erzählers','Narrator\'s voice'))}">${v.erzaehler_liste.map(x=>`<option value="${esc(x.k)}"${x.k===v.erzaehler_k?' selected':''}>${esc(x.name)}</option>`).join('')}</select><button type="button" class="b" data-dmerzprobe="1">${esc('▶ '+t('Probe','Sample'))}</button><button type="button" class="b" data-dmerzneu="1">${esc('🎲 '+t('Neu','New'))}</button></div><small class="mut">${esc(t('Jede Geschichte bekommt ihre eigene Erzählerstimme, jede Figur ihre eigene; die Stimmung der Szene färbt den Erzähler.','Every story gets its own narrator voice, every character its own; the mood of the scene colours the narrator.'))}</small></div>`}
async function dmProbe(mode,h){const A=DMA[mode],voice=h.stimme||'',klang=h.klang||'',erz=h.erzaehler||'';if(!voice&&!klang&&!erz)return;
  try{let r;if(mode==='p')r=await api(`/api/profile/dungeon/${DM.rid}/probe?stimme=${encodeURIComponent(voice)}&klang=${encodeURIComponent(klang)}&erzaehler=${encodeURIComponent(erz)}&lang=${L==='en'?'en':'de'}`);
    else r=await /*raw: public route of a guest seat*/fetch('/api/dungeon/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,stimme:voice,klang})});
    if(!r.ok){dmSay(mode==='p'?DM:DG,t('Die Sprachausgabe ist gerade belegt.','The speech output is busy right now.'),1);return}
    if(r.headers.get('X-Stimme')==='fest')dmSay(mode==='p'?DM:DG,t('Stimmen aus Beschreibung laufen gerade nicht, die Probe kommt in der festen Stimme.','Voices from a description are not running right now, the sample uses the fixed voice.'));
    if(A.el)A.el.pause();if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(await r.blob());A.el=new Audio(A.url);await A.el.play()}catch(e){}}
// the host's choice of the seats with own dice (dungeon_echt.choose): a tap switches one seat
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview .dm-echtwahl [data-dmechtsitz]');if(!b||!DM.rid||!DM.v||!DM.v.echt_plaetze)return;
  const pid=b.dataset.dmechtsitz,an=DM.v.echt_plaetze.filter(p=>p.an&&p.pid!==pid).map(p=>p.pid).concat(b.classList.contains('on')?[]:[pid]);
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/erzaehler`,{echt:an},DM);if(d){DM.v=d;DM.at=Date.now();dmDraw()}});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmerz],#dmview [data-dmweise],#dmview [data-dmanleit],#dmview [data-dmregler],#dmview [data-dmvorschau],#dmview [data-dmkstufe]');if(!s||!DM.rid)return;
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/erzaehler`,s.dataset.dmkstufe?{kampfstufe:s.value}:s.dataset.dmanleit?{anleitung:s.value}:s.dataset.dmregler?{regler_fest:s.checked}:s.dataset.dmvorschau?{mail_vorschau:s.checked}:s.dataset.dmweise?{weise:s.value}:{k:s.value},DM);if(d){DM.v=d;DM.at=Date.now();dmDraw()}});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmgive],#dgcard [data-dmgive],#dmview [data-dmqgive],#dgcard [data-dmqgive]');if(!s||!s.value)return;
  const body=s.dataset.dmqgive?{was:'questgeben',q:s.dataset.dmqgive,an:s.value}:{was:'schenken',i:s.dataset.dmgive,an:s.value};
  if(s.closest('#dmview')){const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
  else await dgAct('/api/dungeon/held',body)});
document.body.addEventListener('change',e=>{const s=e.target.closest('#dmview .dmf-held,#dgcard .dgf-held');if(!s)return;
  const n=s.parentNode.querySelector('.dm-neu');if(n)n.hidden=!!s.value});
// ---------------------------------------------------------------- a seat link (#spiel=<code>): guest or own profile
async function dgPub(p,b){const r=await /*raw: public route of a guest seat, api() would open the login on a 401*/fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:'');e.status=r.status;throw e}return d}
const dgErr=e=>DMGRUND[e.message]?t(...DMGRUND[e.message]):e.status===404?t('Der Dungeon-Master ist auf diesem Spark gerade aus.','The Dungeon Master is switched off on this Spark right now.')
  :e.status===429?t('Zu viele Versuche. Bitte später noch einmal.','Too many attempts. Please try again later.')
  :e.status===400?t('Der Link passt nicht mehr: abgelaufen, zurückgenommen oder die Runde ist vorbei.','The link does not fit any more: expired, taken back or the round is over.')
  :t('Das hat nicht geklappt.','That did not work.');
window.dmHash=()=>{const w=/^#weiter=([A-Za-z0-9_-]{43})$/.exec(location.hash);if(w){history.replaceState(null,'',location.pathname+location.search);dgWeiter(w[1]);return true}
  // „&app=1“: the iPhone app opened the seat in its own window (DungeonView.swift): no full screen, no brand row there
  const m=/^#spiel=([A-Za-z0-9_-]{32})(&app=1)?$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);DG.code=m[1];DMA.app=!!m[2];dgStart();return true};
// „Weiterspielen“ of a guest's mail (#weiter=<once>): the panel gives this device a fresh key for its seat, the mail never holds one
async function dgWeiter(tok){const box=dgBox();box.innerHTML=dgHead()+`<div class="mut">${esc(t('Öffne deinen Platz …','Opening your seat …'))}</div>`;
  try{DG.code=(await dgPub('/api/dungeon/weiter',{t:tok})).code}catch(e){box.innerHTML=dgHead()+`<div class="err">${esc(e.status===400?t(...DMGRUND.weiter):dgErr(e))}</div>`;return}
  dgStart()}
function dgBox(){let m=$('dgmodal');if(!m){m=document.createElement('div');m.id='dgmodal';m.className='modal dgmodal';
  m.innerHTML='<div class="card modalcard dgcard" id="dgcard"></div>';document.body.appendChild(m)}m.style.display='grid';document.body.classList.add('dg-offen');document.body.classList.toggle('dg-gast',dgGast());return $('dgcard')}
// a guest without a profile sees only the game (Dominik 2026-10-24 „das muss richtig abgesichert sein das man da nicht
// irgenwie raus kommt“): no „Schließen“, everything else of the page hidden (body.dg-gast); the server lets a seat code
// reach only /api/dungeon/* of its own seat anyway
const dgGast=()=>!DM.on;
const dgHead=()=>`<div class="row joinbrand"><span class="logo"></span><b>Spark</b>${dgGast()?'':`<button type="button" class="b dg-leave" data-dgleave="1">${esc(t('Schließen','Close'))}</button>`}</div>`;
async function dgStart(){const box=dgBox();box.innerHTML=dgHead()+`<div class="mut">${esc(t('Lade die Einladung …','Loading the invitation …'))}</div>`;
  try{DG.info=await dgPub('/api/dungeon/platz',{code:DG.code})}catch(e){box.innerHTML=dgHead()+`<div class="err">${esc(dgErr(e))}</div>`;return}
  if(!DG.info.frei){try{DG.v=await dgPub('/api/dungeon/lage',{code:DG.code});DG.at=Date.now();dgDraw()}catch(e){box.innerHTML=dgHead()+`<div class="err">${esc(dgErr(e))}</div>`}return}
  dgForm()}
function dgForm(){const I=DG.info,box=dgBox(),w=I.wahl;let name='';try{name=localStorage.getItem('dgname')||''}catch{}
  const mine=DM.on&&DM.data?DM.data.helden:[];
  box.innerHTML=dgHead()+`<div class="dm dm-invite"><div class="dm-gtop">${dmModus()}</div><small class="mut">${esc(I.von?t('Einladung von ','Invitation from ')+I.von:t('Einladung','Invitation'))}</small><h2>${esc(I.titel)}</h2>
    <div class="mut">${I.spieler} ${esc(t('von','of'))} ${I.max} ${esc(t('Plätzen','seats'))} · ${esc(t('gilt bis ','until '))}${esc(dmWhen(I.until))}</div>
    ${DM.on?`<div class="lseg dm-seg dgf-wie"><button type="button" class="on" data-dgwie="p">${esc(t('Mit meinem Profil','With my profile'))}</button><button type="button" data-dgwie="g">${esc(t('Als Gast','As a guest'))}</button></div>`:''}
    ${(I.kampagne_helden||[]).length?`<label>${esc(t('Deine Figur aus dem letzten Kapitel','Your character from the last chapter'))}</label><select class="dgf-kamp"><option value="">${esc(t('Keine, eine neue Figur','None, a new character'))}</option>${I.kampagne_helden.map(h=>`<option value="${esc(h.hid)}">${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}</option>`).join('')}</select>`:''}
    ${I.gastkonto?`<div class="dg-konto" data-wo="form">${dgKontoHtml('form')}</div>`:''}
    <div class="dgf-body">${dmHeroForm(w,DM.on?mine:[],'dgf-')}</div>
    ${`<details class="adv"><summary>${esc(t('Ich habe einen Figur-Code','I have a hero code'))}</summary><input class="dgf-figur" maxlength="32" autocomplete="off" aria-label="${esc(t('Figur-Code','Hero code'))}"></details>`}
    <div class="row joinfoot"><button class="b p" type="button" data-dgjoin="1">${esc(t('Mitspielen','Join'))}</button></div>
    <small class="mut">${esc(DM.on?t('Mit deinem Profil behält dein Held Stufe und Beute. Als Gast speichert der Spark nur Name und Figur in dieser Runde.','With your profile your hero keeps level and loot. As a guest the Spark keeps only name and character in this round.'):t('Kein Konto, keine PIN. Der Spark speichert nur Spielname und Figur in dieser Runde, bis sie endet.','No account, no PIN. The Spark keeps only the name and character in this round until it ends.'))}</small>
    ${dmMsg(DG)}</div>`;
  dmLook(box.querySelector('.dm-invite'),dmWelt(w,I.welt).farben);
  dmDingFill(box,'g');const n=box.querySelector('.dgf-name');if(n&&!n.value)n.value=name;if(n)n.focus();if(I.gastkonto)dgKontoLoad()}
// at the table a guest's brand row goes away (Punkt 1 of the table review): nothing in it to tap, the table's head says enough
function dgDraw(){const box=dgBox();if(!DG.v)return;let w=box.querySelector('.dm');if(!w){box.innerHTML=(dgGast()?'':dgHead())+'<div class="dm"></div><div class="dg-konto" data-wo="tisch"></div>';w=box.querySelector('.dm')}dmTable(w,DG.v,'g');
  const k=box.querySelector('.dg-konto[data-wo="tisch"]');if(k){if(DG.v.gastkonto){if(!k.dataset.on){k.dataset.on='1';dgKontoLoad()}else k.innerHTML=dgKontoHtml('tisch')}else k.innerHTML=''}}
// the guest account (dungeon_gast.py): an address gets a 6-digit code, the code a token for this device (localStorage);
// with it the guest keeps up to 8 heroes, takes them into new rounds and may get „Du bist dran“ by mail
function dgTok(v){try{if(v===undefined)return localStorage.getItem('dgkonto')||'';if(v)localStorage.setItem('dgkonto',v);else localStorage.removeItem('dgkonto')}catch{}return v||''}
async function dgKontoLoad(){const K=DG.konto;K.tok=dgTok();if(K.tok){try{const d=await dgPub('/api/dungeon/gast',{code:DG.code,was:'konto',token:K.tok});K.v=d.konto;K.gebunden=d.gebunden}catch(e){if(e.message==='konto'){dgTok('');K.tok='';K.v=null}}}if(!DG.v)dgKontoForm();dgKontoPaint()}
function dgKontoPaint(){document.querySelectorAll('#dgcard .dg-konto').forEach(x=>{if(x.dataset.wo==='form'||DG.v&&DG.v.gastkonto)x.innerHTML=dgKontoHtml(x.dataset.wo)});
  const f=document.querySelector('#dgcard .dgf-kontoheld');if(f)f.closest('.dgf-kontowahl').hidden=!f.options.length}
function dgKontoHtml(wo){const K=DG.konto,v=K.v,msg=K.msg?`<div class="dmmsg${K.err?' err':''}">${esc(K.msg)}</div>`:'';
  if(!K.tok||!v){const pin=K.step==='pin';
    return `<details class="adv dg-kbox"${pin||K.msg?' open':''}><summary>${esc(t('Gast-Konto mit E-Mail: Helden aufbewahren','Guest account with e-mail: keep your heroes'))}</summary>
      <small class="mut">${esc(t('Du bekommst einen Code per Mail. Damit bewahrt der Spark bis zu 8 Helden für dich auf, auch auf einem anderen Gerät. Gespeichert wird nur ein Hash deiner Adresse.','You get a code by mail. With it the Spark keeps up to 8 heroes for you, also on another device. Only a hash of your address is stored.'))}</small>
      <div class="dm-inp"><input type="email" class="dgk-adr" maxlength="254" autocomplete="email" value="${esc(K.adr)}" aria-label="${esc(t('E-Mail-Adresse','E-mail address'))}" placeholder="${esc(t('deine@adresse.de','you@example.com'))}"><button type="button" class="b" data-dgk="code">${esc(pin?t('Neuer Code','New code'):t('Code senden','Send code'))}</button></div>
      ${pin?`<div class="dm-inp"><input class="dgk-pin" inputmode="numeric" maxlength="6" autocomplete="one-time-code" aria-label="${esc(t('Code aus der Mail','Code from the mail'))}" placeholder="123456"><button type="button" class="b p" data-dgk="anmelden">${esc(t('Anmelden','Sign in'))}</button></div>`:''}${msg}</details>`}
  const hs=v.helden.map(h=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(h.name)}</span><small class="ic-meta">${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}</small></div><button type="button" class="b danger" data-dgk="held_weg" data-hid="${esc(h.hid)}">${esc(K.weg===h.hid?t('Wirklich?','Really?'):t('Löschen','Delete'))}</button></div>`).join('');
  const seat=wo==='tisch'&&DG.v&&DG.v.ich;
  return `<details class="adv dg-kbox"${K.msg?' open':''}><summary>${esc(t('Gast-Konto','Guest account'))} · ${v.helden.length}/${v.helden_max} ${esc(t('Helden','heroes'))}</summary>
    ${seat?(K.gebunden?`<small class="mut">✓ ${esc(t('Dein Held wird in deinem Gast-Konto aufbewahrt.','Your hero is kept in your guest account.'))}</small>`:`<button type="button" class="b p" data-dgk="merken">${esc(t('Diesen Helden aufbewahren','Keep this hero'))}</button>`):''}
    ${hs?`<div class="ic-list">${hs}</div>`:''}
    ${v.zugmail?`<div class="row"><small class="mut">${esc(t('„Du bist dran“ kommt per Mail.','"Your turn" comes by mail.'))}</small><button type="button" class="b" data-dgk="zugaus">${esc(t('Ausschalten','Switch off'))}</button></div>`
      :`<div class="dm-inp"><input type="email" class="dgk-adr" maxlength="254" autocomplete="email" aria-label="${esc(t('E-Mail-Adresse','E-mail address'))}" placeholder="${esc(t('Adresse für „Du bist dran“','Address for "Your turn"'))}"><button type="button" class="b" data-dgk="zugan">${esc(t('Du bist dran per Mail','Your turn by mail'))}</button></div><small class="mut">${esc(t('Dafür bewahrt der Spark deine Adresse versiegelt auf, bis du es ausschaltest.','For this the Spark keeps your address sealed until you switch it off.'))}</small>`}
    <div class="row"><button type="button" class="b" data-dgk="ab">${esc(t('Auf diesem Gerät abmelden','Sign out on this device'))}</button><button type="button" class="b danger" data-dgk="loeschen">${esc(K.weg==='*'?t('Wirklich alles löschen?','Really delete everything?'):t('Gast-Konto löschen','Delete guest account'))}</button></div>${msg}</details>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dgcard [data-dgk]');if(!b)return;const K=DG.konto,k=b.dataset.dgk,box=b.closest('.dg-konto');
  const adr=((box&&box.querySelector('.dgk-adr'))||{}).value||'';K.msg='';K.err=false;
  const call=async body=>{b.disabled=true;try{return await dgPub('/api/dungeon/gast',Object.assign({code:DG.code,token:K.tok},body))}catch(x){K.msg=dgErr(x);K.err=true;return null}finally{b.disabled=false}};
  if(k==='ab'){dgTok('');K.tok='';K.v=null;K.step='';dgKontoPaint();return}
  if(k==='held_weg'&&K.weg!==b.dataset.hid){K.weg=b.dataset.hid;dgKontoPaint();return}
  if(k==='loeschen'&&K.weg!=='*'){K.weg='*';dgKontoPaint();return}
  K.weg='';let d=null;
  if(k==='code'){K.adr=adr.trim();d=await call({was:'code',adresse:K.adr});if(d){K.step='pin';K.msg=t('Der Code ist unterwegs. Schau in dein Postfach.','The code is on its way. Check your mailbox.')}}
  else if(k==='anmelden'){const pin=((box&&box.querySelector('.dgk-pin'))||{}).value||'';d=await call({was:'anmelden',adresse:K.adr,pin:pin.trim()});if(d){K.tok=dgTok(d.token);K.v=d.konto;K.gebunden=d.gebunden;K.step=''}}
  else if(k==='loeschen'){d=await call({was:'loeschen'});if(d){dgTok('');K.tok='';K.v=null;K.msg=t('Dein Gast-Konto ist gelöscht.','Your guest account is deleted.')}}
  else{d=await call(k==='zugan'?{was:'zugmail',an:true,adresse:adr.trim()}:k==='zugaus'?{was:'zugmail',an:false}:k==='merken'?{was:'merken'}:{was:'held_weg',hid:b.dataset.hid});if(d){K.v=d.konto;K.gebunden=d.gebunden}}
  if(!DG.v&&DG.info)dgKontoForm();dgKontoPaint()});
// the join form: the account's heroes to pick instead of a new one
function dgKontoForm(){const box=$('dgcard'),body=box&&box.querySelector('.dgf-body'),K=DG.konto;if(!body)return;let s=box.querySelector('.dgf-kontowahl');
  const hs=K.v?K.v.helden:[];if(!s){s=document.createElement('div');s.className='dgf-kontowahl';body.parentNode.insertBefore(s,body)}
  s.hidden=!hs.length;s.innerHTML=hs.length?`<label>${esc(t('Held aus deinem Gast-Konto','Hero from your guest account'))}</label><select class="dgf-kontoheld"><option value="">${esc(t('Keiner, eine neue Figur','None, a new character'))}</option>${hs.map(h=>`<option value="${esc(h.hid)}">${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}</option>`).join('')}</select>`:''}
async function dgAct(path,b){if(DG.busy)return;DG.busy=true;
  try{DG.v=await dgPub(path,Object.assign({code:DG.code},b));DG.at=Date.now();DG.msg='';DG.err=false;dgDraw()}catch(e){dmSay(DG,dgErr(e),true)}DG.busy=false}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dgcard [data-dgleave],#dgcard [data-dgjoin],#dgcard [data-dgwie],#dgcard [data-dmsend],#dgcard [data-dmhero],#dgcard [data-dmfigur],#dgcard [data-dmtx],#dgcard [data-dmhear],#dgcard [data-dmvoll],#dgcard [data-dmhilfe],#dgcard [data-dmprobe],#dgcard [data-dmmic],#dgcard [data-dmportraet],#dgcard [data-dmmehr]');if(!b)return;
  const B=b.dataset,box=$('dgcard');
  if(B.dgleave){if(dgGast())return;DG.v=null;$('dgmodal').style.display='none';document.body.classList.remove('dg-offen');return}
  if(B.dmhear){dmHear('g',B.dmhear);return}
  if(B.dmvoll){dmVoll(B.dmvoll==='1');return}
  if(B.dmhilfe){dmHilfeAuf(B.dmhilfe);dgDraw();return}
  if(B.dmprobe){dmProbe('g',DG.v&&DG.v.ich||{});return}
  if(B.dmmic){dmMic('g');return}
  if(B.dmmehr){await dgAct('/api/dungeon/mehrzeit',{});return}
  if(B.dgwie){b.parentNode.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    box.querySelector('.dgf-body').innerHTML=dmHeroForm(DG.info.wahl,B.dgwie==='p'&&DM.data?DM.data.helden:[],'dgf-');dmDingFill(box,'g');return}
  if(B.dgjoin){const wie=(box.querySelector('.dgf-wie .on')||{dataset:{dgwie:'g'}}).dataset.dgwie,held=dmHeroBody(box,'dgf-');
    const fig=((box.querySelector('.dgf-figur')||{}).value||'').trim(),kamp=wie==='g'&&((box.querySelector('.dgf-kamp')||{}).value||'');
    const kh=wie==='g'&&((box.querySelector('.dgf-kontoheld')||{}).value||'');
    if(kh){b.disabled=true;try{DG.v=await dgPub('/api/dungeon/beitreten',{code:DG.code,konto:DG.konto.tok,konto_held:kh});DG.at=Date.now();dgDraw()}catch(e){dmSay(DG,dgErr(e),true);b.disabled=false}return}
    if(kamp){b.disabled=true;try{DG.v=await dgPub('/api/dungeon/beitreten',{code:DG.code,kampagne:kamp});DG.at=Date.now();dgDraw()}catch(e){dmSay(DG,dgErr(e),true);b.disabled=false}return}
    if(!fig&&typeof held==='object'){if(held.name.length<2){dmSay(DG,t('Bitte gib deiner Figur einen Namen.','Please name your character.'),true);return}try{localStorage.setItem('dgname',held.name)}catch{}}
    b.disabled=true;
    if(wie==='p'){const {r,d}=await apiTry('/api/profile/dungeon/beitreten',xjson('POST',fig?{code:DG.code,figur:fig}:{code:DG.code,held}));b.disabled=false;
      if(!r.ok){dmSay(DG,dmErr(r.status,d.detail),true);return}
      const pt=box.querySelector('.dgf-portraet');let v2=d;if(pt&&pt.checked&&!fig&&typeof held==='object')v2=await dmSend(`/api/profile/dungeon/${d.rid}/portraet`,{},DM)||d;
      $('dgmodal').style.display='none';document.body.classList.remove('dg-offen');DM.rid=v2.rid;DM.v=v2;DM.at=Date.now();icTabSet('dungeon','runden');goSec('dungeon');return}
    const pt=box.querySelector('.dgf-portraet'),want=pt&&pt.checked&&!fig;
    try{DG.v=await dgPub('/api/dungeon/beitreten',fig?{code:DG.code,figur:fig}:{code:DG.code,held});DG.at=Date.now();dgDraw();if(want)await dgAct('/api/dungeon/portraet/malen',{})}
    catch(e){dmSay(DG,dgErr(e),true);b.disabled=false}return}
  if(B.dmsend){const ta=box.querySelector('.dm-in');const text=(ta&&ta.value||'').trim();if(!text)return;
    await dgAct('/api/dungeon/aktion',{text,zug:DG.v.zug,mut:!!DMA.mut.g});const t2=box.querySelector('.dm-in');if(!DG.err){if(t2)t2.value='';DMA.aendern.g=0;DMA.mut.g=0;dmSent();dgDraw()}return}
  if(B.dmhero){await dgAct('/api/dungeon/held',dmHeroBody2(B));return}
  if(B.dmportraet){await dgAct('/api/dungeon/portraet/malen',{});return}
  if(B.dmtx){const m=await dmTx(B,'g',async b2=>{await dgAct('/api/dungeon/held',b2);return !DG.err});if(typeof m==='string')dmSay(DG,m,true);dgDraw();return}
  if(B.dmfigur){if(DG.busy)return;DG.busy=true;try{const d=await dgPub('/api/dungeon/figur',{code:DG.code});DG.figur=d.figur;dgDraw()}catch(e){dmSay(DG,dgErr(e),true)}DG.busy=false}});
// ---------------------------------------------------------------- the admin's rules: the tab „Regeln“ (dungeon_regelseite.py)
// Dominik 2026-10-24 „die regel seite sollte für den admin hier sein“, „unübersichtlich“: the sections on the left,
// the chosen one on the right; a part of the catalog as a list with picture, values and the balance mark, the
// detail below it. Without a profile (admin only) the same page opens as a card from Funktionen.
const DMR={teil:'geschichten',k:{},sel:'',q:'',f:'alle',m:'alle',gw:'alle',edit:null,err:'',neu:{},busy:'',v:1,welt:{},st:null};
const DMRKAT=['gegenstaende','gegner','klassen','voelker','hintergruende','welten','toene','zustaende','tabellen'];
// the parts with a list and a detail: the rules, and the people of the catalog while it is on (Personen-Katalog 1)
const dmRKats=()=>DMRKAT.concat(DMP.d&&DMP.d.personen_an?['personen']:[]);
const dmRNamen=()=>({geschichten:t('Geschichten','Stories'),personen:t('Personen (NSC)','People (NPC)'),gegenstaende:t('Gegenstände','Items'),gegner:t('Gegner (Bestiarium)','Foes (bestiary)'),klassen:t('Klassen','Classes'),
  voelker:t('Völker','Peoples'),hintergruende:t('Hintergründe','Backgrounds'),welten:t('Welten','Worlds'),toene:t('Töne','Tones'),zustaende:t('Zustände','Conditions'),tabellen:t('Tabellen','Tables'),
  stimmen:t('Stimmen','Voices'),bilder:t('Bilder','Pictures'),musik:t('Musik','Music'),gaeste:t('Gäste mit E-Mail','Guests with e-mail'),ankommt:t('Wie es ankommt','How it lands'),pruefstand:t('Balance-Prüfstand','Balance bench'),erzaehlstand:t('Erzähler-Prüfstand','Narrator bench'),erzaehlfehler:t('Erzähler-Fehler','Narrator errors'),json:t('Für Fortgeschrittene (JSON)','Advanced (JSON)')});
const dmRTab=()=>!!(PROFILE&&DM.on&&ADMIN);
async function dmRules(){if(dmRTab()&&$('dmroot')){icTabSet('dungeon','regeln');goSec('dungeon');return}
  let m=$('dmadm');if(!m){m=document.createElement('div');m.id='dmadm';m.className='modal';
    m.innerHTML='<div class="card modalcard dmadmcard" id="dmadmcard"></div>';document.body.appendChild(m)}
  m.style.display='grid';dmRulesLoad()}
function dmRulesBox(){const w=document.createElement('div');w.className='dm-regeln';w.innerHTML='<div class="dm-rcard" id="dmadmcard"></div>';setTimeout(dmRulesLoad,0);return w}
async function dmRulesLoad(){const c=$('dmadmcard');if(!c)return;c.innerHTML=`<div class="mut">${esc(t('Lade die Regeln …','Loading the rules …'))}</div>`;
  DMP.g=null;const {r,d}=await apiTry('/api/admin/dungeon?lang='+dmLang());if(!$('dmadmcard'))return;if(!r.ok){$('dmadmcard').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  try{DMA.voices=((await (await api('/api/tts/voices')).json()).voices||[]).filter(x=>typeof x==='string')}catch{DMA.voices=[]}dmRulesDraw(d,'')}
// „Gäste mit E-Mail“ (dungeon_gast.py): the mailbox the codes and „Du bist dran“ go from, and the numbers
function dmGastAdm(g){if(!g||!g.an)return `<div class="fh">${esc(t('Aus. Gäste mit E-Mail sind nicht freigegeben.','Off. Guests with e-mail are not released.'))}</div>`;
  return `<div class="pintro">${esc(t('Gäste bekommen einen Code und auf Wunsch „Du bist dran“ von diesem Postfach. Der Spark speichert nur einen Hash der Adresse, die Adresse selbst nur versiegelt, wenn ein Gast Zug-Mails will.','Guests get a code and, if they want, "Your turn" from this mailbox. The Spark keeps only a hash of the address, the address itself only sealed when a guest wants turn mails.'))}</div>
    <div class="row"><select id="dmgastpf" aria-label="${esc(t('Postfach','Mailbox'))}"><option value="">${esc(t('Kein Postfach','No mailbox'))}</option>${g.postfaecher.map(x=>`<option value="${esc(x.k)}"${x.k===g.absender?' selected':''}>${esc(x.name)}</option>`).join('')}</select><button type="button" class="b" data-dmadm="mailpf">${esc(t('Sichern','Save'))}</button></div>
    <div class="dm-sum"><span class="pill${g.bereit?' ok':' warn'}">${esc(g.bereit?t('bereit','ready'):t('kein Postfach mit Ausgangsserver','no mailbox with outgoing server'))}</span> <span class="pill">${esc(t('Gast-Konten','Guest accounts'))} ${g.konten}</span> <span class="pill">${esc(t('mit Zug-Mail','with turn mail'))} ${g.zugmail}</span> <span class="pill">${esc(t('Helden','heroes'))} ${g.helden}</span> <span class="pill">${esc(t('Mails heute','mails today'))} ${g.mails_heute}</span></div>`}
function dmRulesDraw(d,err){const c=$('dmadmcard');if(!c)return;DMP.d=d;const S=d.summe,N=dmRNamen(),tab=!!c.closest('.dm-regeln');
  const n={geschichten:(d.geschichten||[]).length,gegenstaende:S.gegenstaende,klassen:S.klassen,voelker:S.voelker,welten:S.welten,toene:S.toene};
  for(const k of dmRKats())if(DMR.k[k])n[k]=DMR.k[k].zeilen.length;
  const nb=k=>`<button type="button" class="${DMR.teil===k?'on':''}" data-dmrteil="${k}"${DMR.teil===k?' aria-current="true"':''}><span>${esc(N[k])}</span>${n[k]!=null?`<small>${n[k]}</small>`:''}</button>`;
  const nav=`<nav class="dm-rnav" aria-label="${esc(t('Teile der Regeln','Parts of the rules'))}">${nb('geschichten')}${dmRKats().map(nb).join('')}<hr>${['stimmen','bilder','musik','gaeste','ankommt','pruefstand','erzaehlstand','erzaehlfehler'].map(nb).join('')}<hr>${nb('json')}</nav>`;
  c.innerHTML=`<div class="dm-rhead"><h2>${esc(t('Dungeon-Master: Regeln','Dungeon Master: rules'))}</h2>${tab?'':`<button type="button" class="b" data-dmadm="close">${esc(t('Schließen','Close'))}</button>`}</div>
    <div class="dm-rlay">${nav}<div class="dm-rin">${dmRTeil(d,err)}</div></div>`;
  if(DMR.teil==='musik'&&window.dmMusikAdm)dmMusikAdm();
  if(DMR.teil==='pruefstand')dmPruefLook();
  if(DMR.teil==='erzaehlstand')dmErzLook();
  if(DMR.teil==='erzaehlfehler')dmFallLook();
  if(dmRKats().includes(DMR.teil)&&!DMR.k[DMR.teil])dmKatLoad(DMR.teil)}
function dmRTeil(d,err){const k=DMR.teil,N=dmRNamen(),h=`<h3 class="sec">${esc(N[k])}</h3>`,E=err?`<div class="err dm-adm-err">${err}</div>`:'';
  if(k==='geschichten')return DMP.g?dmPlanForm(d):dmPlans(d)+E;
  if(dmRKats().includes(k))return dmKat(k);
  if(k==='stimmen')return h+`<div class="fh">${esc(t('Drei feste Stimmen, alle verschieden: der Erzähler, NPCs (Männer) und NPCs (Frauen). Sie sprechen, wenn keine beschriebene Stimme (VoiceDesign) da ist; wörtliche Rede in der Erzählung spricht immer die Figur, nie der Erzähler.','Three fixed voices, all different: the narrator, NPCs (men) and NPCs (women). They speak when no described voice (VoiceDesign) is there; quoted speech in the narration is always spoken by the character, never by the narrator.'))}</div>
    <div class="dm-two">${[['erzaehler',t('Stimme des Erzählers','Narrator voice')],['npc',t('NPCs (Männer)','NPCs (men)')],['npc_w',t('NPCs (Frauen)','NPCs (women)')]].map(([v,nm])=>{const cur=((d.eigene||{}).stimmen||{})[v]||'',grund=((d.standard||{}).stimmen||{})[v]||'';
      return `<div><label>${esc(nm)}</label><select class="dmadm-voice" data-k="${v}"><option value="">${esc(grund?t('Voreinstellung','Preset')+' ('+grund+')':t('Standardstimme','Default voice'))}</option>${[...new Set([cur,...(DMA.voices||[])].filter(Boolean))].map(x=>`<option${x===cur?' selected':''}>${esc(x)}</option>`).join('')}</select></div>`}).join('')}</div>
    ${E}<div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Speichern','Save'))}</button></div>`;
  if(k==='bilder')return dmThumbsPics(d);
  if(k==='musik')return '<div id="dmmusikadm"></div>';
  if(k==='pruefstand')return h+`<div id="dmpruef"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='erzaehlstand')return h+`<div id="dmerzst"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='erzaehlfehler')return h+`<div id="dmfall"><div class="mut">${esc(t('Lade …','Loading …'))}</div></div>`;
  if(k==='gaeste')return h+dmGastAdm(d.gastmail)+E;
  if(k==='ankommt')return h+(dmThumbsAdmin(d.daumen)||`<div class="fh">${esc(t('Noch keine 👍 oder 👎 in einer Runde.','No 👍 or 👎 in a round yet.'))}</div>`);
  const names={welten:t('Welten','Worlds'),toene:t('Töne','Tones'),voelker:t('Völker','Peoples'),klassen:t('Klassen','Classes'),faehigkeiten:t('Fähigkeiten','Abilities'),gegenstaende:t('Gegenstände','Items'),seltenheit:t('Seltenheiten','Rarities'),effekte:t('Effekte','Effects'),werte:t('Werte','Values')};
  return h+`<div class="pintro">${esc(t('Ergänze oder ändere Welten, Töne, Völker, Klassen mit Fähigkeiten, Gegenstände, Effekte, Kurven und den Standard-Prompt. Ein Eintrag mit derselben id ersetzt den mitgelieferten, "aus": true nimmt ihn heraus. Das Panel prüft alles, bevor es gilt.','Add or change worlds, tones, peoples, classes with abilities, items, effects, curves and the default prompt. An entry with the same id replaces the shipped one, "aus": true takes it out. The panel checks everything before it counts.'))}</div>
    <div class="dm-sum">${Object.entries(names).map(([x,nm])=>`<span class="pill">${esc(nm)} ${d.summe[x]}</span>`).join(' ')}</div>
    <label for="dmadmtxt">${esc(t('Deine Ergänzungen (JSON)','Your additions (JSON)'))}</label><textarea id="dmadmtxt" rows="14" data-fest spellcheck="false" class="mono">${esc(JSON.stringify(d.eigene||{},null,2))}</textarea>${E}
    <details class="adv"><summary>${esc(t('Mitgelieferte Regeln ansehen (zum Kopieren)','See the shipped rules (to copy)'))}</summary><pre class="dm-pre">${esc(JSON.stringify(d.standard,null,2))}</pre></details>
    <div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmadm="reset">${esc(t('Zurück auf Standard','Back to default'))}</button></div>`}
const dmThumbsPics=d=>`<div id="dmbilder">${dmDingAdmin(d.dingbilder)||`<div class="fh">${esc(t('Bilder für Ausrüstung und Zauber sind aus.','Pictures for gear and spells are off.'))}</div>`}</div>`;
// ---- one part of the catalog: search, filters, the list with picture and mark, the detail with „Ändern“ and „Nochmal malen“
// peoples, classes and backgrounds are shown and painted in the world chosen above the list (DMR.welt per part)
const dmRWelt=teil=>DMR.welt[teil]?'&welt='+encodeURIComponent(DMR.welt[teil]):'';
async function dmKatLoad(teil){const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'?lang='+dmLang()+dmRWelt(teil));
  if(!r.ok){DMR.k[teil]={zeilen:[],eintraege:{},fehler:dmErr(r.status,d.detail)}}else DMR.k[teil]=d;if(DMR.teil===teil&&DMP.d)dmRulesDraw(DMP.d,'')}
const DMRMARKE={schwach:'',ok:'ok',stark:'warn',zu_stark:'bad'};
const DMRSTAND=()=>({runde:t('aus einer Runde','from a round'),grund:t('Grundregel','Base'),srd:'SRD',eigen:t('eigen','own'),geaendert:t('geändert','changed'),aus:t('ausgeblendet','hidden')});
function dmRFilter(teil){if(teil==='gegenstaende')return [['alle',t('Alle','All')],['waffe',t('Waffen','Weapons')],['ruestung',t('Rüstung','Armour')],['zauber',t('Zauber','Spells')],['trank',t('Tränke','Potions')],['werkzeug',t('Werkzeug','Tools')],['schatz',t('Schätze','Treasure')]];
  if(teil==='gegner')return [['alle',t('Alle','All')],['s0',t('Stufe 0-4','Level 0-4')],['s5',t('Stufe 5-10','Level 5-10')],['s11',t('Stufe 11+','Level 11+')],['boss',t('Bosse','Bosses')],['frisch',t('Neu','New')]];return null}
function dmRPass(x){const f=DMR.f,q=DMR.q.trim().toLowerCase();
  if(q&&!(x.name.toLowerCase().includes(q)||String(x.id).toLowerCase().includes(q)))return false;
  if(DMR.m!=='alle'&&!(x.marke&&(DMR.m==='stark'?['stark','zu_stark'].includes(x.marke.marke):x.marke.marke===DMR.m)))return false;
  if(x.welten&&DMR.gw!=='alle'&&!x.welten.includes(DMR.gw))return false;
  if(f==='alle')return true;if(f==='boss')return !!x.boss;if(f==='frisch')return !!x.frisch;
  if(f==='zauber')return ['zauber','rolle'].includes(x.art);if(f==='schatz')return ['schatz','schmuck'].includes(x.art);
  if(f[0]==='s'&&x.stufe!=null){const s=+x.stufe;return f==='s0'?s<5:f==='s5'?s>=5&&s<=10:s>10}
  return x.art===f}
// a foe's damage kind and what hurts it more (▲ double), less (▼ half) or not at all (✕), as symbols (Bestiarium-Punkt 9)
function dmRArt(K,x){const A=K.arten||{},a=x.arten,z=i=>A[i]?`<span title="${esc(A[i].name)}">${A[i].zeichen}</span>`:'';if(!a)return '';
  const g=(k,s,l)=>a[k]&&a[k].length?`<span class="dm-rak" title="${esc(l)}">${s}${a[k].map(z).join('')}</span>`:'';
  return `<span class="dm-rart">${z(a.art)}${g('schwaeche','▲',t('Schwäche: doppelter Schaden','Weak: double damage'))}${g('resistenz','▼',t('Widerstand: halber Schaden','Resists: half damage'))}${g('immun','✕',t('Immun: kein Schaden','Immune: no damage'))}</span>`}
// v: the picture's own version (row bv/nv, its file time) so the browser keeps it; k: the small copy for the list
const dmRImg=(n,v,k)=>`<img alt="" loading="lazy" decoding="async" src="/api/admin/dungeon/bild/${encodeURIComponent(n)}?v=${v||DMR.v}${k?'&klein=1':''}">`;
// an item's picture in its rarity's frame, as in the bag (DMSEL; Dominik 2026-10-24 „farblich anders umrandet“)
function dmRThumb(x,K){const s=x.selten?' '+(DMSEL[x.selten]||''):'selten' in x?' dm-sx':'';
  if(!K.bilder_an&&!x.bild||!('bild' in x))return `<span class="dm-rth dm-dz${s}" aria-hidden="true">${esc(x.zeichen||'·')}</span>`;
  return x.bild?`<span class="dm-rth${s}">${dmRImg(x.bild,x.bv,1)}</span>`:`<span class="dm-rth dm-rno${s}" aria-hidden="true">${esc(x.zeichen||'')}</span>`}
function dmKat(teil){const K=DMR.k[teil],N=dmRNamen(),St=DMRSTAND();
  if(!K)return `<h3 class="sec">${esc(N[teil])}</h3><div class="mut">${esc(t('Lade …','Loading …'))}</div>`;
  if(K.fehler)return `<h3 class="sec">${esc(N[teil])}</h3><div class="err">${esc(K.fehler)}</div>`;
  const F=dmRFilter(teil),hasM=K.zeilen.some(x=>x.marke),rows=K.zeilen.filter(dmRPass),MAX=200;
  const nm={alle:t('Alle','All'),stark:t('stark und zu stark','strong and too strong'),zu_stark:t('zu stark','too strong'),schwach:t('schwach','weak')};
  const list=rows.slice(0,MAX).map(x=>{const m=x.marke&&x.marke.marke!=='ok'?`<span class="pill ${DMRMARKE[x.marke.marke]}" title="${esc(x.marke.grund)}">${esc(x.marke.name)}</span>`:'';
    return `<div class="dm-rrow${String(x.id)===DMR.sel?' on':''}${x.stand==='aus'?' dm-raus':''}${x.selten?' dm-rsel '+(DMSEL[x.selten]||''):'selten' in x?' dm-rsel dm-sx':''}"><button type="button" class="dm-rmain" data-dmrsel="${esc(x.id)}">${dmRThumb(x,K)}<span class="dm-rtxt"><b>${esc(x.name)}</b><small>${esc(x.zeile)}</small>${dmRArt(K,x)}</span></button>
      <span class="dm-rpills">${x.boss?`<span class="pill warn">👑 ${esc(t('Boss','Boss'))}</span>`:''}${x.frisch?`<span class="pill ok">${esc(t('neu','new'))}</span>`:''}${m}${x.stand!=='grund'&&x.stand!=='srd'?`<span class="pill">${esc(St[x.stand])}</span>`:''}${x.neu?`<span class="pill warn">${esc(t('neues Bild','new picture'))}</span>`:''}</span>
      ${'bild' in x&&!x.bild&&K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(t('Malen','Paint'))}</button>`:''}</div>`}).join('');
  const wsel=K.welten?`<select class="dmr-w" aria-label="${esc(t('Bilder in der Welt','Pictures in the world'))}">${K.welten.map(w=>`<option value="${esc(w.id)}"${w.id===K.welt?' selected':''}>${esc(t('Bilder in: ','Pictures in: ')+w.name)}</option>`).join('')}</select>`:'';
  const gsel=K.weltfilter?`<select class="dmr-gw" aria-label="${esc(t('Welt','World'))}"><option value="alle">${esc(t('Alle Welten','All worlds'))}</option>${K.weltfilter.map(w=>`<option value="${esc(w.id)}"${w.id===DMR.gw?' selected':''}>${esc(w.name)}</option>`).join('')}</select>`:'';
  return `<h3 class="sec">${esc(N[teil])} · ${K.zeilen.length}${K.neu?` <button type="button" class="b" data-dmrneu="1">＋ ${esc(t('Neue Person','New person'))}</button>`:''}</h3>
    <div class="dm-rsrch">${wsel}${gsel}<input type="search" class="dmr-q" value="${esc(DMR.q)}" placeholder="${esc(t('Suchen …','Search …'))}" aria-label="${esc(t('Suchen','Search'))}">
      ${F?`<div class="lseg dm-rseg">${F.map(([v,l])=>`<button type="button" class="${DMR.f===v?'on':''}" data-dmrf="${v}">${esc(l)}</button>`).join('')}</div>`:''}
      ${hasM?`<select class="dmr-m" aria-label="${esc(t('Gleichgewicht','Balance'))}">${['alle','stark','zu_stark','schwach'].map(v=>`<option value="${v}"${DMR.m===v?' selected':''}>${esc(v==='alle'?t('Gleichgewicht: alle','Balance: all'):nm[v])}</option>`).join('')}</select>`:''}</div>
    ${K.seltenheiten?dmRSelLeg(K):''}<div class="dm-rkat"><div class="dm-rlist" role="list">${list||`<div class="ic-empty">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`}${rows.length>MAX?`<div class="mut dm-rmehr">${esc(t(`${rows.length-MAX} weitere, bitte genauer suchen`,`${rows.length-MAX} more, please search more closely`))}</div>`:''}</div>
    <div class="dm-rdet" id="dmrdet">${dmRDet(teil)}</div></div>`}
// a table of the catalog in full (Dominik 2026-10-25 „ich sehe gar nicht die tabellen“): the die, every row, the worlds of a row
function dmRTafel(x){const w=x.tafel.some(z=>z.w);
  return `<div class="dm-rtafel" role="region" tabindex="0" aria-label="${esc(t('Tabelle','Table'))}"><table><thead><tr><th>${esc(t('W','d')+x.tafel.length)}</th><th>${esc(t('Ergebnis','Result'))}</th>${w?`<th>${esc(t('Nur in','Only in'))}</th>`:''}</tr></thead>
    <tbody>${x.tafel.map(z=>`<tr><td>${z.n}</td><td>${esc(z.t)}</td>${w?`<td>${esc(z.w)}</td>`:''}</tr>`).join('')}</tbody></table></div>`}
// the rarities as frames: a fixed one shows its colour, a rolled item (most of them) gets it when it is found
function dmRSelLeg(K){return `<div class="dm-rsleg" aria-label="${esc(t('Seltenheit','Rarity'))}">${K.seltenheiten.map(s=>`<span class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(s.name)}</span>`).join('')}<span class="dm-rsl"><i class="dm-rth dm-sx"></i>${esc(t('gewürfelt beim Fund','rolled when found'))}</span></div>`}
function dmRSelLadder(K,x){if(!K.seltenheiten)return '';
  if(x.selten){const s=K.seltenheiten.find(z=>z.id===x.selten);return s?`<div class="fh dm-rsfest"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(x.preis==null?t(`Immer ${s.name}: +${s.bonus}, Preis ×${s.preis}`,`Always ${s.name}: +${s.bonus}, price ×${s.preis}`):x.preis?t(`Immer ${s.name}: +${s.bonus}, Preis ${x.preis} Gold`,`Always ${s.name}: +${s.bonus}, price ${x.preis} gold`):t(`Immer ${s.name}: +${s.bonus}, unverkäuflich`,`Always ${s.name}: +${s.bonus}, not for sale`))}</div>`:''}
  return `<div class="dm-rsleiter"><div class="fh">${esc(t('Die Seltenheit wird beim Fund gewürfelt (W100 nach einer festen Tabelle je Stufe, Truhen und Bosse würfeln höher) und gibt den Rahmen:','The rarity is rolled when it is found (d100 by a fixed table per level, chests and bosses roll higher) and gives the frame:'))}</div>
    ${K.seltenheiten.map(s=>`<div class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i><b>${esc(s.name)}</b><small>${esc(t(`+${s.bonus} · Preis ×${s.preis}${s.stufe>1?` · ab Stufe ${s.stufe}`:s.stufe?'':' · nie'}`,`+${s.bonus} · price ×${s.preis}${s.stufe>1?` · from level ${s.stufe}`:s.stufe?'':' · never'}`))}</small></div>`).join('')}</div>`}
// a person's voice (Dominik 2026-10-27 „stimmen verändern, die genutzt werden wenn diese etwas sagen“): five fixed
// lists, „▶ Probe“ before saving, „Nach dem Namen“ gives the voice back to the name; only the panel's fixed words
// VoiceDesign not running (Dominik 2026-10-27 „stimme klang bei alles gleich“): every person speaks in the fixed voice, said with the way to switch it on
function dmDesignAus(){return `<div class="fh dm-designaus">${esc(t('Stimmen aus Beschreibung laufen gerade nicht: jede Person spricht in der festen Stimme. Einschalten (Admin): ','Voices from a description are not running right now: every person speaks in the fixed voice. Switch on (admin): '))}<a href="#" class="wayl" data-way="Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“">${esc(t('Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“','Settings → Speech output → "Also serve VoiceDesign"'))}</a>.</div>`}
function dmRStimme(K,x,e){const cur=(DMR.st&&DMR.st.id===String(x.id))?DMR.st.t:(e.stimme_jetzt||{});
  return `<div class="dm-voice dm-rstimme"><label>${esc(t('🎙 Stimme, wenn die Person spricht','🎙 Voice when the person speaks'))}</label>${K.stimme_design===false?dmDesignAus():''}
    <div class="dm-rstw">${(K.stimmwahl||[]).map(m=>`<select data-dmrst="${esc(m.k)}" aria-label="${esc(m.name)}">${m.werte.map(([v,w])=>`<option value="${esc(v)}"${v===cur[m.k]?' selected':''}>${esc(m.name+': '+w)}</option>`).join('')}</select>`).join('')}</div>
    <div class="row"><button type="button" class="b" data-dmrstimme="probe">${esc('▶ '+t('Probe','Sample'))}</button><button type="button" class="b p" data-dmrstimme="setzen">${esc(t('Stimme speichern','Save voice'))}</button>${Object.keys(e.stimme||{}).length?`<button type="button" class="b" data-dmrstimme="name">${esc(t('Nach dem Namen','By the name'))}</button>`:''}</div></div>`}
function dmRDet(teil){const K=DMR.k[teil],St=DMRSTAND(),x=K.zeilen.find(z=>String(z.id)===DMR.sel)||(DMR.edit&&DMR.edit.neu?{id:DMR.edit.e.id,name:t('Neue Person','New person')}:null);
  if(!x)return `<div class="ic-empty">${esc(t('Tippe links einen Eintrag an.','Tap an entry on the left.'))}</div>`;
  const e=K.eintraege[String(x.id)]||{},li=L==='en'?1:0,tx=v=>Array.isArray(v)?v[li]||v[0]:v||'';
  if(DMR.edit)return `<b class="dm-rname">${esc(DMR.edit.kopie?t('Eigene Kopie','Own copy'):t('Ändern','Edit'))}: ${esc(x.name)}</b>
    <div class="fh">${esc(t('Der ganze Eintrag; das Panel prüft ihn wie alle Regeln. „Zu stark“ ist nur ein Hinweis.','The whole entry; the panel checks it like every rule. "Too strong" is only a hint.'))}</div>
    <textarea class="mono dmr-txt" rows="16" data-fest spellcheck="false">${esc(JSON.stringify(DMR.edit.e,null,2))}</textarea>${DMR.err?`<div class="err dm-adm-err">${DMR.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmrdo="setzen">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmrdo="abbrechen">${esc(t('Abbrechen','Cancel'))}</button></div>`;
  const m=x.marke,neu=DMR.neu[String(x.id)]||x.neu,b='bild' in x;
  const pic=b?`<div class="dm-rbild${x.selten?' '+(DMSEL[x.selten]||''):''}">${neu?`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild,x.bv):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(t('jetzt','now'))}</figcaption></figure><figure>${dmRImg(neu,DMR.neu[String(x.id)]?DMR.v:x.nv)}<figcaption>${esc(t('neu gemalt','painted again'))}</figcaption></figure></div>
      <div class="row"><button type="button" class="b p" data-dmrbild="neu" data-id="${esc(x.id)}">${esc(t('Neues behalten','Keep the new one'))}</button><button type="button" class="b" data-dmrbild="alt" data-id="${esc(x.id)}">${esc(t('Altes behalten','Keep the old one'))}</button></div>`
      :`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild,x.bv):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(x.bild?t('jetzt','now'):t('noch kein Bild','no picture yet'))}</figcaption></figure></div>`}
      <div class="row">${K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(DMR.busy===String(x.id)?t('Malt gerade …','Painting …'):x.bild?t('Nochmal malen','Paint again'):t('Malen','Paint'))}</button>`:`<small class="mut">${esc(t('Die Bilder sind aus; einschalten im Abschnitt „Bilder“.','Pictures are off; switch them on in the part "Pictures".'))}</small>`}</div></div>`:'';
  return `<div class="dm-rdkopf"><div><b class="dm-rname">${esc(x.zeichen||'')} ${esc(x.name)}</b> <span class="pill">${esc(St[x.stand])}</span>${m?` <span class="pill ${DMRMARKE[m.marke]}">${esc(m.name)}</span>`:''}</div></div>
    <div class="dm-rdgrid"><div><div class="dm-rzeile">${esc(x.zeile)}</div>${(x.werte||[]).length?`<dl class="dm-rwerte">${x.werte.map(([a,v])=>`<dt>${esc(a)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:''}${dmRSelLadder(K,x)}${x.tafel?dmRTafel(x):''}${m&&m.grund?`<div class="fh dm-rgrund">${esc(m.grund)}</div>`:''}${tx(e.info||e.satz)?`<p class="dm-rinfo">${esc(tx(e.info||e.satz))}</p>`:''}${teil==='personen'&&K.stimmwahl?dmRStimme(K,x,e):''}
      <div class="row"><button type="button" class="b" data-dmrdo="aendern">${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmrdo="kopie">${esc(t('Eigene Kopie','Own copy'))}</button>
      ${x.stand==='aus'||x.stand==='geaendert'?`<button type="button" class="b" data-dmrdo="zurueck">${esc(t('Zurück auf mitgeliefert','Back to shipped'))}</button>`:''}
      ${x.stand==='eigen'||teil==='personen'?`<button type="button" class="b danger" data-dmrdo="zurueck">${esc(teil==='personen'?t('Person löschen','Delete person'):t('Eigenen Eintrag löschen','Delete own entry'))}</button>`:x.stand!=='aus'?`<button type="button" class="b" data-dmrdo="aus">${esc(t('Ausblenden','Hide'))}</button>`:''}</div></div>${pic}</div>`}
// the list keeps its place when it is drawn again (Dominik 2026-10-24 „beim Klicken hüpft die Liste“)
function dmRDraw(){const c=$('dmadmcard');if(!c||!DMP.d)return;const l=c.querySelector('.dm-rlist'),top=l?l.scrollTop:0;
  dmRulesDraw(DMP.d,'');const n=c.querySelector('.dm-rlist');if(n)n.scrollTop=top}
// a tap on an entry: only the mark and the detail change, the list stays as it is
function dmRPick(){const c=$('dmadmcard'),det=$('dmrdet');if(!c||!det||!DMR.k[DMR.teil])return dmRDraw();
  c.querySelectorAll('.dm-rrow').forEach(r=>{const b=r.querySelector('[data-dmrsel]');r.classList.toggle('on',!!b&&b.dataset.dmrsel===DMR.sel)});
  det.innerHTML=dmRDet(DMR.teil)}
async function dmRDo(teil,was,id,eintrag){const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'?lang='+dmLang()+dmRWelt(teil),xjson('POST',{was,id,eintrag}));
  if(!r.ok){DMR.err=Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>'):esc(dmErr(r.status,d.detail));dmRDraw();return false}
  DMR.k[teil]=d;DMR.edit=null;DMR.err='';if(eintrag)DMR.sel=String(eintrag.id);dmRDraw();
  if(d.hinweis)sayToast(t('Gespeichert. Hinweis: ','Saved. Hint: ')+d.hinweis.name+' · '+d.hinweis.grund);else sayToast(t('Gespeichert','Saved'));return true}
const DMRWARUM=()=>({aus:t('Die Bilder sind aus.','Pictures are off.'),tag:t('Das Tageslimit für Bilder ist erreicht.','The day limit for pictures is reached.'),pruefung:t('Die Bildbeschreibung hat die Prüfung nicht bestanden.','The picture prompt did not pass the check.'),
  missing:t('Das Bildmodell fehlt.','The picture model is missing.'),ohne_pruefung:t('Die Bildprüfung fehlt.','The image check is missing.'),belegt:t('Das Bildmodell ist gerade belegt.','The picture model is busy right now.')});
document.body.addEventListener('input',e=>{const q=e.target.closest('#dmadmcard .dmr-q');if(!q)return;DMR.q=q.value;const p=q.selectionStart;dmRDraw();const n=document.querySelector('#dmadmcard .dmr-q');if(n){n.focus();n.setSelectionRange(p,p)}});
document.body.addEventListener('change',e=>{const w=e.target.closest('#dmadmcard .dmr-w');if(w){DMR.welt[DMR.teil]=w.value;DMR.neu={};dmKatLoad(DMR.teil);return}
  const g=e.target.closest('#dmadmcard .dmr-gw');if(g){DMR.gw=g.value;dmRDraw();return}
  const s=e.target.closest('#dmadmcard .dmr-m');if(!s)return;DMR.m=s.value;dmRDraw()});
document.body.addEventListener('click',async e=>{const c=e.target.closest('#dmadmcard');if(!c)return;const teil=DMR.teil;
  const nb=e.target.closest('[data-dmrteil]');if(nb){DMR.teil=nb.dataset.dmrteil;DMR.sel='';DMR.q='';DMR.f='alle';DMR.m='alle';DMR.gw='alle';DMR.edit=null;DMR.err='';DMP.g=null;dmRDraw();return}
  const fb=e.target.closest('[data-dmrf]');if(fb){DMR.f=fb.dataset.dmrf;dmRDraw();return}
  const sb=e.target.closest('[data-dmrsel]');if(sb){DMR.sel=sb.dataset.dmrsel;DMR.edit=null;DMR.err='';dmRPick();const d=$('dmrdet');if(d&&window.innerWidth<900)d.scrollIntoView({block:'start',behavior:'smooth'});return}
  const nn=e.target.closest('[data-dmrneu]');if(nn){const K=DMR.k[teil],w=((K&&K.weltfilter)||[])[0];   // a new person of the catalog: an empty card to fill
    DMR.edit={neu:true,e:{id:'p'+Math.random().toString(16).slice(2,10).padEnd(8,'0'),name:'',welt:w?w.id:'',rolle:'',ziel:'',karte:{aussehen:['',''],art:['',''],beruf:['',''],wunsch:['',''],geheimnis:['','']},wesen:{}}};DMR.sel='';DMR.err='';dmRDraw();return}
  const db=e.target.closest('[data-dmrdo]');if(db){const K=DMR.k[teil],x=K&&K.zeilen.find(z=>String(z.id)===DMR.sel);if(!x&&!(DMR.edit&&DMR.edit.neu))return;const was=db.dataset.dmrdo;
    if(was==='abbrechen'){DMR.edit=null;DMR.err='';dmRDraw();return}
    if(was==='aendern'||was==='kopie'){const e0=JSON.parse(JSON.stringify(K.eintraege[String(x.id)]||{}));
      if(was==='kopie'){const ids=new Set(K.zeilen.map(z=>String(z.id)));let n=2;while(ids.has(`${x.id}_${n}`))n++;e0.id=typeof x.id==='number'?Math.max(...K.zeilen.map(z=>+z.id||0))+1:`${x.id}_${n}`;}
      DMR.edit={e:e0,kopie:was==='kopie'};DMR.err='';dmRDraw();return}
    if(was==='setzen'){let ent;try{ent=JSON.parse(c.querySelector('.dmr-txt').value)}catch{DMR.edit.e=c.querySelector('.dmr-txt').value;DMR.err=esc(t('Das ist kein gültiges JSON.','This is not valid JSON.'));dmRDraw();return}
      DMR.edit.e=ent;await dmRDo(teil,'setzen',String(ent.id),ent);return}
    if(db.classList.contains('danger')&&db.dataset.sure!=='1'){db.dataset.sure='1';db.textContent=t('Wirklich löschen?','Really delete?');return}
    await dmRDo(teil,was,String(x.id));return}
  const vb=e.target.closest('[data-dmrstimme]');if(vb){const id=DMR.sel,was=vb.dataset.dmrstimme,st={};
    c.querySelectorAll('[data-dmrst]').forEach(s=>{st[s.dataset.dmrst]=s.value});
    if(was==='probe'){DMR.st={id,t:st};try{const r=await api('/api/admin/dungeon/personen/probe',xjson('POST',{stimme:st,lang:dmLang()}));
        if(!r.ok){sayToast(t('Die Sprachausgabe ist gerade belegt.','The speech output is busy right now.'));return}
        if(r.headers.get('X-Stimme')==='fest')sayToast(t('Stimmen aus Beschreibung laufen gerade nicht, die Probe kommt in der festen Stimme.','Voices from a description are not running right now, the sample uses the fixed voice.'));
        const A=DMA.p;if(A.el)A.el.pause();if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(await r.blob());A.el=new Audio(A.url);await A.el.play()}catch(err){}return}
    DMR.st=null;await dmRDo(teil,'stimme',id,{id,stimme:was==='name'?{}:st});return}
  const pb=e.target.closest('[data-dmrbild]');if(pb){const id=pb.dataset.id,was=pb.dataset.dmrbild;if(DMR.busy)return;
    if(was==='malen'){DMR.busy=id;dmRDraw()}
    const {r,d}=await apiTry('/api/admin/dungeon/katalog/'+teil+'/bild',xjson('POST',{id,was,welt:DMR.welt[teil]||(DMR.k[teil]||{}).welt||''}));DMR.busy='';
    if(!r.ok){sayToast(DMRWARUM()[d.detail]||dmErr(r.status,d.detail));dmRDraw();return}
    if(was==='malen'&&d.neu)DMR.neu[id]=d.neu;else delete DMR.neu[id];DMR.v=Date.now();DMR.sel=id;
    await dmKatLoad(teil);return}});
document.body.addEventListener('click',async e=>{if(e.target.closest('#dmrules')){dmRules();return}
  const b=e.target.closest('#dmadmcard [data-dmadm]');if(!b)return;const k=b.dataset.dmadm;
  if(k==='close'){$('dmadm').style.display='none';return}
  if(k==='mailpf'){const {r,d}=await apiTry('/api/admin/dungeon/gastmail',xjson('PUT',{absender:$('dmgastpf').value}));
    if(r.ok)dmRulesDraw(d,'');else dmRulesDraw(DMP.d,esc(dmErr(r.status,d.detail)));return}
  if(k[0]==='g'){await dmPlanClick(b,k);return}
  if(k==='reset'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich auf Standard?','Really back to default?');return}
    const {r,d}=await apiTry('/api/admin/dungeon',{method:'DELETE'});if(r.ok){DMR.k={};dmRulesDraw(d,'')}return}
  // „Speichern“ in Stimmen keeps the own rules as they are, the JSON part reads them from its field
  const ta=$('dmadmtxt');let own;
  if(ta){try{own=JSON.parse(ta.value||'{}')}catch{dmRulesDraw(DMP.d,esc(t('Das ist kein gültiges JSON.','This is not valid JSON.')));$('dmadmtxt').value=ta.value;return}}else own=JSON.parse(JSON.stringify(DMP.d.eigene||{}));
  const sv={},vs=document.querySelectorAll('#dmadmcard .dmadm-voice');vs.forEach(x=>{sv[x.dataset.k]=x.value});
  if(vs.length){Object.keys(sv).forEach(x=>{if(!sv[x])delete sv[x]});if(Object.keys(sv).length)own.stimmen=sv;else delete own.stimmen}   // empty: the preset
  const keep=ta&&ta.value;const {r,d}=await apiTry('/api/admin/dungeon',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({eigene:own})});
  if(r.ok){DMR.k={};dmRulesDraw(d,'');sayToast(t('Regeln gespeichert','Rules saved'));return}
  dmRulesDraw(DMP.d,Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>'):esc(dmErr(r.status,d.detail)));if(keep&&$('dmadmtxt'))$('dmadmtxt').value=keep});
// 👍/👎 per narration over all rounds, per world and tone (numbers only; the model learns nothing from them)
function dmThumbsAdmin(x){if(!x||!x.length)return '';const n=a=>a[L==='en'?1:0];
  return `<h3 class="sec">${esc(t('Wie die Erzählungen ankommen','How the narrations land'))}</h3><div class="dm-sum">${x.map(r=>`<span class="pill">${esc(n(r.welt))} · ${esc(n(r.ton))}: 👍 ${r.hoch} · 👎 ${r.runter}</span>`).join(' ')}</div>`}
// Bilder für Ausrüstung und Zauber (dungeon_dingbild.py): how many there are, the last run, „Bilder jetzt erstellen“ and „Anhalten“
function dmDingAdmin(x){if(!x)return '';const L0=x.letzter||{},warum={fertig:t('alle fertig','all done'),morgen:t('Nacht vorbei','night over'),tag:t('Tageslimit erreicht','day limit reached'),angehalten:t('angehalten','stopped'),aus:t('ausgeschaltet','switched off'),notaus:'Notaus',voll:t('Warteschlange voll','queue full'),missing:t('Bildmodell fehlt','picture model missing'),ohne_pruefung:t('Bildprüfung fehlt','image check missing')};
  return `<div id="dmding"><h3 class="sec">${esc(t('Bilder für Ausrüstung und Zauber','Pictures for gear and spells'))} · ${x.fertig}/${x.von}</h3>
    <div class="fh">${esc(x.an?(x.bilder?t(`Ein Bild je Gegenstand und Zauber im Stil jeder Welt (${x.stile} Stile). Der Spark malt fehlende Bilder nachts von ${x.nacht[0]} bis ${x.nacht[1]} Uhr, höchstens ${x.tag_max} am Tag; bis dahin zeigt der Tisch das Zeichen der Art.`,`One picture per item and spell in the style of each world (${x.stile} styles). The Spark paints missing pictures at night from ${x.nacht[0]} to ${x.nacht[1]}, at most ${x.tag_max} a day; until then the table shows the kind's sign.`):t('Dafür muss auch „Bilder malen“ freigegeben sein.','“Painting pictures” must be released for this too.')):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Bilder für Ausrüstung und Zauber.','Off. Switch it on under Features → AI Dungeon Master → Pictures for gear and spells.'))}</div>
    <div class="dm-sum"><span class="pill">${esc(t('heute','today'))} ${x.heute}</span> <span class="pill">${esc(t('Fundstücke','Finds'))} ${x.funde}</span>${x.abgelehnt?` <span class="pill warn">${esc(t('abgelehnt','refused'))} ${x.abgelehnt}</span>`:''}${x.laeuft?` <span class="pill on">${esc(x.grund==='alle'?t('malt alle, ohne Tageslimit','painting all, no day limit'):t('malt gerade','painting now'))} · ${x.gemalt} · ${esc(t('noch','left'))} ${x.offen}</span>`:L0.ende?` <span class="pill">${esc(t('zuletzt','last'))} ${esc(new Date(L0.ende*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))} · ${L0.gemalt} · ${esc(warum[L0.warum]||L0.warum||'')}</span>`:''}</div>
    <div class="row">${x.laeuft?`<button type="button" class="b" data-dmding="stop">${esc(x.grund==='alle'?t('Abbrechen','Cancel'):t('Anhalten','Stop'))}</button>`:`<button type="button" class="b p" data-dmding="start"${!x.an||!x.bilder||!x.offen?' disabled':''}>${esc(t('Bilder jetzt erstellen','Create pictures now'))}</button>
      <button type="button" class="b" data-dmding="alle" title="${esc(t('Malt alle fehlenden Bilder (Gegenstände, Zauber, Gegner, Orts- und Raumarten, Völker, Klassen) ohne Tageslimit, eins nach dem anderen über die Warteschlange.','Paints every missing picture (items, spells, foes, kinds of places and rooms, peoples, classes) without the day limit, one after the other through the queue.'))}"${!x.an||!x.bilder||!x.offen?' disabled':''}>${esc(t('Alle Bilder malen','Paint all pictures'))} · ${x.offen}</button>`}</div></div>`}
// Balance-Prüfstand (dungeon_pruefstand.py): how often a group wins a fight of „mittel“, per level, for the group size
// chosen; the aim as a green band, a bar outside it red. Numbers from the panel's own fights, never the model.
const DMPS={g:4,t:0};
function dmPruefBox(x){const z=x.zellen||{},G=DMPS.g,lv=Object.keys(z).map(k=>k.split('/')).filter(([,g])=>+g===G).map(([s])=>+s).sort((a,b)=>a-b);
  const [lo,hi]=x.ziel,W=520,H=230,B=196,sc=1.7,bw=Math.min(40,(W-60)/Math.max(1,lv.length)-8);
  const bars=lv.map((s,i)=>{const c=z[s+'/'+G],hgt=c.siege*sc,xx=48+i*(bw+8),off=c.siege<lo||c.siege>hi;
    return `<rect x="${xx}" y="${B-hgt}" width="${bw}" height="${hgt}" rx="4" class="${off?'dm-ps-aus':'dm-ps-in'}"><title>${esc(t('Stufe','Level'))} ${s}: ${c.siege} %</title></rect><text x="${xx+bw/2}" y="${B-hgt-5}" text-anchor="middle" class="dm-ps-z">${c.siege}</text><text x="${xx+bw/2}" y="${B+15}" text-anchor="middle">${s}</text>`}).join('');
  const chart=lv.length?`<svg viewBox="0 0 ${W} ${H}" class="dm-ps-svg" role="img" aria-label="${esc(t(`Siege je Stufe, Gruppe aus ${G}`,`Wins per level, group of ${G}`))}"><rect x="40" y="${B-hi*sc}" width="${W-44}" height="${(hi-lo)*sc}" class="dm-ps-ziel"/><line x1="40" y1="${B}" x2="${W-4}" y2="${B}" class="dm-ps-ax"/><text x="2" y="${B-hi*sc+4}">${hi} %</text><text x="2" y="${B-lo*sc+4}">${lo} %</text><text x="2" y="${B+4}">0 %</text>${bars}<text x="${W/2}" y="${H-2}" text-anchor="middle">${esc(t('Stufe der Gruppe','Level of the group'))}</text></svg>`
    :`<div class="fh">${esc(t('Noch kein Durchlauf.','No run yet.'))}</div>`;
  const rows=lv.map(s=>{const c=z[s+'/'+G];return `<tr><td>${s}</td><td>${c.siege} %</td><td>${c.leben} %</td><td>${c.runden}</td></tr>`}).join('');
  return `<div class="fh">${esc(x.an?t(`Der Spark spielt nachts je Stufe und Gruppengröße ${x.kaempfe||200} Kämpfe der Gefahr „mittel“ mit den echten Regeln und Würfeln durch, ohne Modell. Ziel: ${lo} bis ${hi} % Siege.`,`At night the Spark plays ${x.kaempfe||200} fights of danger "medium" per level and group size with the real rules and dice, without the model. Aim: ${lo} to ${hi} % wins.`):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Balance-Prüfstand.','Off. Switch it on under Features → AI Dungeon Master → Balance bench.'))}</div>
    <div class="row dm-ps-g" role="group" aria-label="${esc(t('Gruppengröße','Group size'))}">${Array.from({length:x.gruppe_max},(_,i)=>i+1).map(g=>`<button type="button" class="b${g===G?' on':''}" data-dmps="${g}"${g===G?' aria-pressed="true"':' aria-pressed="false"'}>${g} ${esc(g===1?t('Held','hero'):t('Helden','heroes'))}</button>`).join('')}</div>
    ${chart}${rows?`<table class="dm-ps-t"><thead><tr><th>${esc(t('Stufe','Level'))}</th><th>${esc(t('Siege','Wins'))}</th><th>${esc(t('Leben verloren','Life lost'))}</th><th>${esc(t('Runden','Turns'))}</th></tr></thead><tbody>${rows}</tbody></table>`:''}
    ${dmPruefGeld(x)}
    <div class="dm-sum">${x.zeit?`<span class="pill">${esc(t('zuletzt','last'))} ${esc(new Date(x.zeit*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))}</span>`:''}${x.laeuft?` <span class="pill on">${esc(t('spielt gerade','playing now'))}</span>`:''}</div>
    <div class="row"><button type="button" class="b p" data-dmps="los"${!x.an||x.laeuft?' disabled':''}>${esc(t('Jetzt durchspielen','Play it through now'))}</button></div>`}
// the economy (Wirtschaft Punkt 6): income ÷ expenses of a hero per level as bars, the aim as a green band
function dmPruefGeld(x){const w=x.wirtschaft||{},lv=Object.keys(w).map(Number).sort((a,b)=>a-b);if(!lv.length)return '';
  const [lo,hi]=x.wirtschaft_ziel,W=520,H=200,B=166,sc=60,bw=Math.min(40,(W-60)/lv.length-8);
  const bars=lv.map((s,i)=>{const c=w[s],v=Math.min(2.6,c.verhaeltnis),xx=48+i*(bw+8),off=c.verhaeltnis<lo||c.verhaeltnis>hi;
    return `<rect x="${xx}" y="${B-v*sc}" width="${bw}" height="${v*sc}" rx="4" class="${off?'dm-ps-aus':'dm-ps-in'}"><title>${esc(t('Stufe','Level'))} ${s}: ${c.verhaeltnis}</title></rect><text x="${xx+bw/2}" y="${B-v*sc-5}" text-anchor="middle" class="dm-ps-z">${String(c.verhaeltnis).replace('.',L==='en'?'.':',')}</text><text x="${xx+bw/2}" y="${B+15}" text-anchor="middle">${s}</text>`}).join('');
  const rows=lv.map(s=>{const c=w[s];return `<tr><td>${s}</td><td>${c.kaempfe}</td><td>${c.einnahmen}</td><td>${c.zehntel}</td><td>${c.ausgaben}</td><td>${String(c.verhaeltnis).replace('.',L==='en'?'.':',')}</td><td>${c.fund_max}</td></tr>`}).join('');
  return `<h3 class="sec">${esc(t('Wirtschaft je Stufe','Economy per level'))}</h3><div class="fh">${esc(t(`Gold eines Helden je Stufe: Münzen und Verkäufe beim Händler gegen Gasthaus, Heiltränke, Gerüchte und Schmied. Ziel: ${lo} bis ${hi} mal so viel Einnahmen wie Ausgaben, der Rest ist für Lehrstunden und „Ausrüstung verbessern“.`,`A hero's gold per level: coins and sales to merchants against inn, healing potions, rumours and smith. Aim: ${lo} to ${hi} times as much income as expenses; the rest is for lessons and "Improve gear".`))}</div>
    <svg viewBox="0 0 ${W} ${H}" class="dm-ps-svg" role="img" aria-label="${esc(t('Einnahmen geteilt durch Ausgaben je Stufe','Income divided by expenses per level'))}"><rect x="40" y="${B-hi*sc}" width="${W-44}" height="${(hi-lo)*sc}" class="dm-ps-ziel"/><line x1="40" y1="${B}" x2="${W-4}" y2="${B}" class="dm-ps-ax"/><text x="2" y="${B-hi*sc+4}">${hi}×</text><text x="2" y="${B-lo*sc+4}">${lo}×</text>${bars}<text x="${W/2}" y="${H-2}" text-anchor="middle">${esc(t('Stufe der Gruppe','Level of the group'))}</text></svg>
    <div class="dm-ps-w"><table class="dm-ps-t"><thead><tr><th>${esc(t('Stufe','Level'))}</th><th>${esc(t('Kämpfe','Fights'))}</th><th>${esc(t('Einnahmen','Income'))}</th><th>${esc(t('schlechtestes Zehntel','worst tenth'))}</th><th>${esc(t('Ausgaben','Expenses'))}</th><th>${esc(t('Verhältnis','Ratio'))}</th><th>${esc(t('größter Fund','biggest find'))}</th></tr></thead><tbody>${rows}</tbody></table></div>`}
async function dmPruefLook(){clearTimeout(DMPS.t);if(!$('dmpruef'))return;const {r,d}=await apiTry('/api/admin/dungeon/pruefstand');
  if(!$('dmpruef'))return;if(!r.ok){$('dmpruef').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  DMPS.d=d;$('dmpruef').innerHTML=dmPruefBox(d);if(d.laeuft)DMPS.t=setTimeout(dmPruefLook,3000)}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmpruef [data-dmps]');if(!b)return;const k=b.dataset.dmps;
  if(k!=='los'){DMPS.g=+k;if(DMPS.d)$('dmpruef').innerHTML=dmPruefBox(DMPS.d);return}
  b.disabled=true;const {r,d}=await apiTry('/api/admin/dungeon/pruefstand',xjson('POST',{}));
  if(!r.ok){sayToast(dmErr(r.status,d.detail));b.disabled=false;return}DMPS.d=d;$('dmpruef').innerHTML=dmPruefBox(d);DMPS.t=setTimeout(dmPruefLook,3000)});
// Erzähler-Prüfstand (dungeon_erzaehlstand.py, Tabletop-Punkt 4): fixed scenes through the running model, points by fixed
// rules per scene and model side by side; the model's own Einordnung only as a hint beside it
const DMES={t:0};
function dmErzBox(x){const ms=Object.entries(x.modelle||{}).sort((a,b)=>b[1].zeit-a[1].zeit),mx=2*x.szenen.length;
  const dot=s=>s?`<span class="dm-es-p" data-p="${s.punkte}" title="${esc(s.grund)}${s.versuche?' · '+s.versuche+' '+esc(t('Versuche','tries')):''} · ${s.sekunden} s">${s.punkte}</span>${s.einordnung?`<small class="mut" title="${esc(t('eigene Einschätzung des Modells','the model\'s own view'))}"> ${Math.round(s.einordnung.lebendig*100)}/${Math.round(s.einordnung.folgt*100)}</small>`:''}`:'–';
  const tab=ms.length?`<div class="dm-ps-w"><table class="dm-ps-t dm-es-t"><thead><tr><th>${esc(t('Szene','Scene'))}</th>${ms.map(([n])=>`<th>${esc(n)}</th>`).join('')}</tr></thead><tbody>
    ${x.szenen.map(([id,nm])=>`<tr><td>${esc(nm[L==='en'?1:0])}</td>${ms.map(([,m])=>`<td>${dot((m.szenen||{})[id])}</td>`).join('')}</tr>`).join('')}
    <tr class="dm-es-sum"><td>${esc(t('Punkte','Points'))}</td>${ms.map(([,m])=>`<td><b>${m.punkte}</b> / ${m.max||mx}</td>`).join('')}</tr>
    <tr><td>${esc(t('Dauer','Time'))}</td>${ms.map(([,m])=>`<td>${Math.round(m.sekunden)} s</td>`).join('')}</tr>
    <tr><td>${esc(t('zuletzt','last'))}</td>${ms.map(([,m])=>`<td>${esc(new Date(m.zeit*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))}</td>`).join('')}</tr></tbody></table></div>`
    :`<div class="fh">${esc(t('Noch kein Lauf.','No run yet.'))}</div>`;
  return `<div class="fh">${esc(x.an?t(`Der Spark spielt ${x.szenen.length} feste Szenen durch das laufende Sprachmodell, mit denselben Regeln wie am Tisch. Je Szene 2 Punkte, wenn der erste Versuch passt, 1 nach dem Nachbessern, 0 sonst.`,`The Spark plays ${x.szenen.length} fixed scenes through the running language model, with the same rules as at the table. Per scene 2 points when the first try passes, 1 after a rewrite, 0 otherwise.`):t('Aus. Einschalten unter Funktionen → KI-Dungeon-Master → Erzähler-Prüfstand.','Off. Switch it on under Features → AI Dungeon Master → Narrator bench.'))}${x.einordnung?' '+esc(t('Die kleinen Zahlen sind die eigene Einschätzung des Modells (lebendig / folgt den Aktionen, in Prozent), sie geben keine Punkte.','The small numbers are the model\'s own view (vivid / follows the actions, in per cent), they give no points.')):''}</div>
    ${tab}<div class="dm-sum">${x.laeuft?`<span class="pill on">${esc(t('prüft gerade','checking now'))}</span>`:''}</div>
    <div class="row"><button type="button" class="b p" data-dmes="los"${!x.an||x.laeuft?' disabled':''}>${esc(t('Jetzt prüfen','Check now'))}</button></div>`}
async function dmErzLook(){clearTimeout(DMES.t);if(!$('dmerzst'))return;const {r,d}=await apiTry('/api/admin/dungeon/erzaehlstand');
  if(!$('dmerzst'))return;if(!r.ok){$('dmerzst').innerHTML=`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`;return}
  $('dmerzst').innerHTML=dmErzBox(d);if(d.laeuft)DMES.t=setTimeout(dmErzLook,5000)}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmerzst [data-dmes]');if(!b)return;b.disabled=true;
  const {r,d}=await apiTry('/api/admin/dungeon/erzaehlstand',xjson('POST',{}));
  if(!r.ok){sayToast(dmErr(r.status,d.detail));b.disabled=false;return}$('dmerzst').innerHTML=dmErzBox(d);DMES.t=setTimeout(dmErzLook,5000)});
// „Erzähler-Fehler“ (dungeon_erzaehlstand.py): the turns a seat gave a 👎 with a fixed reason, heroes with the bench's
// names; „Als Prüfstand-Szene übernehmen“ makes one a scene of the narrator bench
function dmFallBox(x){const G=x.gruende||{},gl=k=>(G[k]||G.sonst||['',''])[L==='en'?1:0],when=z=>new Date(z*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'});
  const taken=new Set((x.szenen||[]).map(s=>s.id.slice(1)));
  const fall=f=>`<details class="dm-fall"><summary><b>${esc(gl(f.grund))}</b> <span class="mut">${esc(when(f.zeit))} · ${esc(f.lang==='en'?'English':'Deutsch')}</span>${taken.has(f.id)?` <span class="pill ok">${esc(t('im Prüfstand','in the bench'))}</span>`:''}</summary>
    ${f.taten.map(a=>`<div class="dm-fall-tat"><b>${esc((x.namen||[])[a.held]||'')}</b>: ${esc(a.text)}</div>`).join('')}
    ${f.wuerfe.length?`<div class="dm-sum">${f.wuerfe.map(w=>`<span class="pill${w.ok?' ok':' warn'}">${esc(w.wofuer||w.wert)}: ${w.w} ${esc(w.ok?t('geschafft','passed'):t('misslungen','failed'))}</span>`).join(' ')}</div>`:''}
    <p class="dm-fall-text">${esc(f.text)}</p>
    <div class="row">${taken.has(f.id)?'':`<button type="button" class="b p" data-dmfall="szene" data-id="${esc(f.id)}"${x.an?'':' disabled'}>${esc(t('Als Prüfstand-Szene übernehmen','Take over as a bench scene'))}</button>`}<button type="button" class="b" data-dmfall="loeschen" data-id="${esc(f.id)}">${esc(t('Löschen','Delete'))}</button></div></details>`;
  const own=(x.szenen||[]).length?`<h4>${esc(t('Eigene Szenen im Erzähler-Prüfstand','Own scenes in the narrator bench'))} <small class="mut">${x.szenen.length} / ${x.eigene_max}</small></h4>${x.szenen.map(s=>`<div class="dm-fall-sz"><span>${esc(s.name[L==='en'?1:0])}</span><button type="button" class="b" data-dmfall="szeneweg" data-id="${esc(s.id)}">${esc(t('Entfernen','Remove'))}</button></div>`).join('')}`:'';
  return `<div class="fh">${esc(x.an||x.beheben?t(`Hier landet jeder Zug, den ein Platz mit 👎 und einem Grund markiert hat (höchstens ${x.max}, die neuesten zuerst). Die Helden heißen hier wie im Prüfstand, Namen von Spielern stehen nie darin. „Als Prüfstand-Szene übernehmen“ spielt den Zug bei jedem Lauf des Erzähler-Prüfstands nach, mit demselben Ausgang jeder Probe.`,`Every turn a seat marked with 👎 and a reason lands here (at most ${x.max}, the newest first). The heroes carry the bench's names, players' names never stand here. "Take over as a bench scene" replays the turn on every run of the narrator bench, with the same outcome of every check.`):t('Fälle entstehen, solange der Erzähler-Prüfstand oder „Erzähler-Fehler beheben“ an ist (Funktionen → KI-Dungeon-Master). Als Prüfstand-Szene übernehmen geht nur mit dem Prüfstand, Löschen immer.','Cases come while the narrator bench or "Fix narrator errors" is on (Features → AI Dungeon Master). Taking over as a bench scene needs the bench, deleting always works.'))}</div>
    ${dmFallWochen(x)}${(x.faelle||[]).length?x.faelle.map(fall).join(''):`<div class="fh">${esc(t('Noch kein Fall.','No case yet.'))}</div>`}${own}`}
// the reports per week and reason, and the reasons that became standing hints of a world (numbers only)
function dmFallWochen(x){const G=x.gruende||{},gl=k=>(G[k]||['',''])[L==='en'?1:0],W=x.wochen||[];if(!W.length)return '';
  const ks=Object.keys(G).filter(k=>W.some(w=>w.gruende[k]));
  const welt=Object.entries(x.welten||{}).filter(([,g])=>g.length);
  return `<h4>${esc(t('Meldungen je Woche','Reports per week'))}</h4><div class="dm-ps-w"><table class="dm-ps-t"><thead><tr><th>${esc(t('Grund','Reason'))}</th>${W.map(w=>`<th>${esc(w.woche)}</th>`).join('')}</tr></thead><tbody>
    ${ks.map(k=>`<tr><td>${esc(gl(k))}</td>${W.map(w=>`<td>${w.gruende[k]||'–'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${welt.length?`<div class="fh">${esc(x.beheben?t('Feste Hinweise für den Erzähler, weil sie in dieser Welt oft gemeldet wurden:','Fixed hints for the narrator, because they were reported often in this world:'):t('Oft gemeldet (feste Hinweise gibt es erst mit „Erzähler-Fehler beheben“):','Reported often (fixed hints only come with "Fix narrator errors"):'))}</div><div class="dm-sum">${welt.map(([w,g])=>`<span class="pill">${esc(w)}: ${esc(g.map(gl).join(', '))}</span>`).join(' ')}</div>`:''}`}
async function dmFallLook(){if(!$('dmfall'))return;const {r,d}=await apiTry('/api/admin/dungeon/erzaehlfehler');if(!$('dmfall'))return;
  $('dmfall').innerHTML=r.ok?dmFallBox(d):`<div class="err">${esc(dmErr(r.status,d.detail))}</div>`}
document.addEventListener('click',async e=>{const b=e.target.closest('#dmfall [data-dmfall]');if(!b)return;const a=b.dataset.dmfall;b.disabled=true;
  const body=a==='szeneweg'?{szene:b.dataset.id,aktion:'loeschen'}:{fall:b.dataset.id,aktion:a};
  const {r,d}=await apiTry('/api/admin/dungeon/erzaehlfehler',xjson('POST',body));
  if(!r.ok){sayToast(r.status===409&&d.detail==='voll'?t('Schon so viele eigene Szenen, wie der Prüfstand nimmt. Entferne erst eine.','Already as many own scenes as the bench takes. Remove one first.'):dmErr(r.status,d.detail));b.disabled=false;return}
  $('dmfall').innerHTML=dmFallBox(d)});
let DMDT=0;
async function dmDingLook(){clearTimeout(DMDT);const box=$('dmding');if(!box)return;const {r,d}=await apiTry('/api/admin/dungeon/dingbilder');
  if(!r.ok||!$('dmding'))return;$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmding [data-dmding]');if(!b)return;b.disabled=true;
  const k=b.dataset.dmding,{r,d}=await apiTry('/api/admin/dungeon/dingbilder',k==='stop'?{method:'DELETE'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alle:k==='alle'})});
  if(!r.ok){b.disabled=false;sayToast(dmErr(r.status,d.detail));return}$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)});
// ---------------------------------------------------------------- the admin's stories (Geschichten-Planer)
// a story: idea, goal, foe, places, taboos and 3 to 5 acts with a turning point; „Vorschlag erzeugen“ lets the model
// write all of it from keywords, „↻“ one act again; the panel checks both like typed text before anything is kept
const DMP={d:null,g:null,gid:'',err:'',stich:'',hint:'',busy:false,host:false};
// the same form for a host's own story (Eigene Geschichten, dungeon_geschichten): DMP.host, its own sheet and endpoints
const dmPBox=()=>$(DMP.host?'dmgscard':'dmadmcard');
const dmPBase=()=>DMP.host?'/api/profile/dungeon/geschichten/':'/api/admin/dungeon/geschichte/';
function dmPDraw(d){if(DMP.host)dmGSheet();else dmRulesDraw(d,'')}
function dmPlans(d){const gs=d.geschichten||[],P=d.planer,own=gs.filter(g=>!g.von).length;   // a host's own (von) counts with the host
  return `<h3 class="sec">${esc(t('Geschichten','Stories'))} · ${own}/${P.max}</h3>
    <div class="fh">${esc(t('Lege fest, wie eine Geschichte verläuft. Wer eine Runde anlegt, wählt sie aus; den Plan sehen nur du und der Gastgeber.','Set how a story runs. Whoever starts a round picks it; only you and the host see the plan.'))}</div>
    ${gs.length?`<div class="ic-list">${gs.map(g=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(g.titel)}</span><small class="ic-meta">${esc(g.welt_name)} · ${esc(g.ton_name)} · ${g.akte.length} ${esc(t('Akte','acts'))}${g.von?' · '+esc(t('von '+g.von_name,'by '+g.von_name)):''}</small></div><button type="button" class="b" data-dmadm="gedit" data-gid="${esc(g.gid)}">${esc(t('Bearbeiten','Edit'))}</button></div>`).join('')}</div>`:''}
    <div class="row"><button type="button" class="b"${own>=P.max?' disabled':''} data-dmadm="gneu">${esc(t('Neue Geschichte','New story'))}</button></div>`}
function dmPlanForm(d){const g=DMP.g,P=d.planer,w=d.wahl;
  const opt=(a,cur)=>a.map(x=>`<option value="${esc(x.id)}"${String(x.id)===String(cur)?' selected':''}>${esc(x.name)}</option>`).join('');
  const nums=[];for(let n=P.akte[0];n<=P.akte[1];n++)nums.push(n);
  const akt=(a,i)=>`<div class="dmp-akt" data-i="${i}"><div class="dm-khead"><b>${esc(t('Akt','Act'))} ${i+1}</b><span><button type="button" class="b" data-dmadm="gakt" data-n="${i+1}"${DMP.busy?' disabled':''} title="${esc(t('Diesen Akt vom Modell neu schreiben lassen','Let the model write this act again'))}">↻ ${esc(t('Neu schreiben','Write again'))}</button>${g.akte.length>P.akte[0]?`<button type="button" class="b" data-dmadm="gminus" data-n="${i}">${esc(t('Entfernen','Remove'))}</button>`:''}</span></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-at" maxlength="60" value="${esc(a.titel||'')}">
    <label>${esc(t('Was geschieht','What happens'))}</label><textarea class="dmp-ai" rows="3" maxlength="${P.inhalt}">${esc(a.inhalt||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Wendepunkt am Ende','Turning point at the end'))}</label><input class="dmp-aw" maxlength="${P.wende}" value="${esc(a.wende||'')}"></div>
    <div><label>${esc(t('Geplante Züge','Planned turns'))}</label><input class="dmp-az" type="number" min="${P.zuege[0]}" max="${P.zuege[1]}" value="${a.zuege||6}"></div></div>
    ${P.quest?`<label>✦ ${esc(t('Besonderes Ding des Akts (frei lassen: keins)','The act\'s special thing (leave empty: none)'))}</label><input class="dmp-ad" maxlength="${P.quest}" value="${esc(a.ding||'')}" placeholder="${esc(t('zum Beispiel der Messingschlüssel','for example the brass key'))}">`:''}
    ${P.spuren?`<label>🔎 ${esc(t('Spuren zum Wendepunkt (eine je Zeile, bis zu '+P.spuren[0]+')','Clues to the turning point (one per line, up to '+P.spuren[0]+')'))}</label><textarea class="dmp-asp" rows="3" maxlength="${P.spuren[0]*(P.spuren[1]+1)}" placeholder="${esc(t('frische Wachsspuren am Turm','fresh wax on the tower'))}">${esc((a.spuren||[]).join('\n'))}</textarea>`:''}</div>`;
  const I=P.import||{};
  return `<h2>${esc(DMP.gid?t('Geschichte bearbeiten','Edit the story'):t('Neue Geschichte','New story'))}</h2><div class="dm-form dmp-form">
    ${I.an?`<div class="dm-k"><div class="lbl">📄 ${esc(t('Abenteuer aus einer Datei','Adventure from a file'))}</div>
      <div class="row"><input type="file" class="dmp-datei" accept="${esc(I.typen.join(','))}" aria-label="${esc(t('Datei mit dem Abenteuer','File with the adventure'))}"><button type="button" class="b p" data-dmadm="gimp"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell liest …','The model is reading …'):t('Übernehmen','Import'))}</button></div>
      <small class="mut">${esc(t(`PDF, Word, OpenDocument, Markdown, Text oder HTML bis ${I.mb} MB. Welt, Ton, Tabus und die Zahl der Akte unten gelten; das Modell fasst die Kapitel zu Akten zusammen, das Panel prüft den Entwurf. Erst „Speichern“ behält ihn, die Datei behält der Spark nicht.`,`PDF, Word, OpenDocument, Markdown, text or HTML up to ${I.mb} MB. World, tone, taboos and the number of acts below count; the model joins the chapters into acts, the panel checks the draft. Only "Save" keeps it, the Spark does not keep the file.`))}</small></div>`:''}
    ${DMP.host?'':`<div class="dm-k"><div class="lbl">✨ ${esc(t('Vom Sprachmodell entwerfen lassen','Let the language model draft it'))}</div>
      <textarea class="dmp-stich" rows="2" maxlength="${P.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht, eher düster','a cursed mountain village, a dragon that only guards, rather dark'))}">${esc(DMP.stich)}</textarea>
      <div class="row"><select class="dmp-n" aria-label="${esc(t('Akte','Acts'))}">${nums.map(n=>`<option value="${n}"${n===g.akte.length?' selected':''}>${n} ${esc(t('Akte','acts'))}</option>`).join('')}</select><button type="button" class="b p" data-dmadm="gvor"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell schreibt …','The model is writing …'):t('Vorschlag erzeugen','Create a proposal'))}</button></div>
      <small class="mut">${esc(t('Das Modell füllt alle Felder; das Panel prüft Länge, Ton und Tabus. Erst „Speichern“ behält die Geschichte.','The model fills every field; the panel checks length, tone and taboos. Only "Save" keeps the story.'))}</small></div>`}
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-titel" maxlength="60" value="${esc(g.titel||'')}">
    <div class="dm-two"><div><label>${esc(t('Welt','World'))}</label><select class="dmp-welt">${opt(w.welten,g.welt)}</select></div><div><label>${esc(t('Ton','Tone'))}</label><select class="dmp-ton">${opt(w.toene,g.ton)}</select></div></div>
    <label>${esc(t('Grundidee','Idea'))}</label><textarea class="dmp-idee" rows="3" maxlength="${P.idee}">${esc(g.idee||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Ziel der Helden','The heroes\' goal'))}</label><input class="dmp-ziel" maxlength="${P.ziel}" value="${esc(g.ziel||'')}"></div><div><label>${esc(t('Gegenspieler','Foe'))}</label><input class="dmp-gegner" maxlength="${P.ziel}" value="${esc(g.gegner||'')}"></div></div>
    <label>${esc(t('Schauplätze (mit Komma, bis zu '+P.orte+')','Places (comma separated, up to '+P.orte+')'))}</label><input class="dmp-orte" value="${esc((g.orte||[]).join(', '))}">
    <label>${esc(t('Tabus: kommt nie vor (mit Komma, bis zu '+P.tabus+')','Taboos: never happens (comma separated, up to '+P.tabus+')'))}</label><input class="dmp-tabus" value="${esc((g.tabus||[]).join(', '))}" placeholder="${esc(t('Spinnen, Folter','spiders, torture'))}">
    ${(P.personen||[]).length?dmPLeute(P,g):''}
    ${g.akte.map(akt).join('')}
    ${g.akte.length<P.akte[1]?`<div class="row"><button type="button" class="b" data-dmadm="gplus">${esc(t('Akt dazu','Add an act'))}</button></div>`:''}
    <label>${esc(t('Hinweis fürs Neuschreiben eines Akts (frei)','Hint for writing an act again (optional)'))}</label><input class="dmp-hint" maxlength="${P.stichworte}" value="${esc(DMP.hint)}" placeholder="${esc(t('mehr Rätsel, weniger Kampf','more riddles, less fighting'))}">
    ${DMP.err?`<div class="err dm-adm-err">${DMP.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmadm="gsave"${DMP.busy?' disabled':''}>${esc(t('Prüfen und speichern','Check and save'))}</button>${DMP.gid?`<button type="button" class="b danger" data-dmadm="gdel">${esc(DMP.host&&DMP.von!=='eigen'?t('Ausblenden','Hide'):t('Löschen','Delete'))}</button>`:''}<button type="button" class="b" data-dmadm="gback">${esc(t('Zurück','Back'))}</button></div></div>`}
// Personen-Katalog 2: known people of the story's world to tick (name and occupation only), up to P.personen_max
function dmPLeute(P,g){const xs=P.personen.filter(p=>p.welt===g.welt),on=g.personen||[],li=dmLang()==='en'?1:0;
  return `<label>${esc(t('Bekannte Personen aus dem Katalog (bis zu '+P.personen_max+')','Known people from the catalog (up to '+P.personen_max+')'))}</label><div class="dmp-leute" data-max="${P.personen_max}">${xs.map(p=>`<label class="dm-check"><input type="checkbox" class="dmp-p" value="${esc(p.id)}"${on.includes(p.id)?' checked':''}> ${esc(p.name)}${p.beruf[li]?` <small class="mut">${esc(p.beruf[li])}</small>`:''}</label>`).join('')||`<small class="mut">${esc(t('In dieser Welt kennt der Katalog noch niemanden.','The catalog knows nobody in this world yet.'))}</small>`}</div>`}
document.body.addEventListener('change',e=>{const x=e.target;if(!x.closest('#dmadmcard .dmp-form,#dmgscard .dmp-form'))return;
  if(x.matches('.dmp-welt')){DMP.g=dmPlanRead();dmPDraw(DMP.d);return}
  if(x.matches('.dmp-p')&&x.checked){const box=x.closest('.dmp-leute');if(box.querySelectorAll('.dmp-p:checked').length>+box.dataset.max)x.checked=false}});
function dmPlanRead(){const c=dmPBox(),q=x=>(c.querySelector(x)||{}).value||'',list=x=>q(x).split(',').map(s=>s.trim()).filter(Boolean);
  DMP.stich=q('.dmp-stich');DMP.hint=q('.dmp-hint');
  const ton=q('.dmp-ton');
  return {titel:q('.dmp-titel').trim(),welt:q('.dmp-welt'),ton:/^\d+$/.test(ton)?+ton:ton,lang:dmLang(),idee:q('.dmp-idee').trim(),ziel:q('.dmp-ziel').trim(),
    gegner:q('.dmp-gegner').trim(),orte:list('.dmp-orte'),tabus:list('.dmp-tabus'),personen:[...c.querySelectorAll('.dmp-p:checked')].map(x=>x.value),
    akte:[...c.querySelectorAll('.dmp-akt')].map(a=>({titel:a.querySelector('.dmp-at').value.trim(),inhalt:a.querySelector('.dmp-ai').value.trim(),
      wende:a.querySelector('.dmp-aw').value.trim(),zuege:Math.floor(+a.querySelector('.dmp-az').value||0),...(a.querySelector('.dmp-ad')&&a.querySelector('.dmp-ad').value.trim()?{ding:a.querySelector('.dmp-ad').value.trim()}:{}),
      ...(a.querySelector('.dmp-asp')?{spuren:a.querySelector('.dmp-asp').value.split('\n').map(s=>s.trim()).filter(Boolean)}:{})}))}}
const dmPlanErr=(r,d)=>Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>')
  :d.detail==='kein vorschlag'?esc(t('Das Modell hat keinen brauchbaren Vorschlag geliefert. Bitte noch einmal oder mit anderen Stichworten.','The model gave no usable proposal. Please try again or with other keywords.'))
  :d.detail==='sprachmodell pausiert'?esc(t('Das Sprachmodell ist gerade pausiert.','The language model is paused right now.'))
  :d.detail==='unlesbar'?esc(t('Die Datei ist nicht lesbar (ein PDF ohne Textschicht oder eine kaputte Datei).','The file cannot be read (a PDF without a text layer or a broken file).'))
  :d.detail==='leer'?esc(t('In der Datei steht zu wenig Text für ein Abenteuer.','The file holds too little text for an adventure.'))
  :d.detail==='zu gross'?esc(t('Die Datei ist zu groß.','The file is too big.'))
  :d.detail==='dateiart'?esc(t('Diese Dateiart geht nicht: PDF, Word, OpenDocument, Markdown, Text oder HTML.','This file type does not work: PDF, Word, OpenDocument, Markdown, text or HTML.')):esc(dmErr(r.status,d.detail));
async function dmPlanClick(b,k){const d=DMP.d,w=d.wahl;if(DMP.busy)return;
  if(k==='gneu'){DMP.gid='';DMP.err='';DMP.stich='';DMP.hint='';DMP.g={titel:'',welt:w.welten[0].id,ton:(w.toene[1]||w.toene[0]).id,idee:'',ziel:'',gegner:'',orte:[],tabus:[],
    akte:Array.from({length:d.planer.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))};dmPDraw(d);return}
  if(k==='gedit'){const g=(d.geschichten||[]).find(x=>x.gid===b.dataset.gid);if(!g)return;DMP.gid=g.gid;DMP.err='';DMP.stich='';DMP.hint='';DMP.g=JSON.parse(JSON.stringify(g));dmPDraw(d);return}
  if(k==='gback'){DMP.g=null;dmPDraw(d);return}
  const g=dmPlanRead();DMP.g=g;
  if(k==='gplus'){g.akte.push({titel:'',inhalt:'',wende:'',zuege:6});dmPDraw(d);return}
  if(k==='gminus'){g.akte.splice(+b.dataset.n,1);dmPDraw(d);return}
  if(k==='gdel'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich löschen?','Really delete?');return}
    if(DMP.host){await dmGWas('loeschen',DMP.gid);return}
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+DMP.gid+'?lang='+dmLang(),{method:'DELETE'});if(r.ok){DMP.g=null;dmPDraw(x)}return}
  if(k==='gsave'){const {r,d:x}=await apiTry(dmPBase()+(DMP.gid||'neu')+'?lang='+dmLang(),xjson('PUT',g));
    if(r.ok){DMP.g=null;if(DMP.host)dmGDone(x);else dmPDraw(x);sayToast(t('Geschichte gespeichert','Story saved'));return}DMP.err=dmPlanErr(r,x);dmPDraw(d);return}
  const n=Math.floor(+(((dmPBox().querySelector('.dmp-n'))||{}).value||g.akte.length));
  if(k==='gimp'){const f=((dmPBox().querySelector('.dmp-datei')||{}).files||[])[0];
    if(!f){DMP.err=esc(t('Bitte zuerst eine Datei wählen.','Please pick a file first.'));dmPDraw(d);return}
    const fd=new FormData();fd.append('file',f,f.name);fd.append('welt',g.welt);fd.append('ton',String(g.ton));fd.append('akte',String(n));fd.append('tabus',g.tabus.join(','));fd.append('lang',g.lang);
    DMP.busy=true;DMP.err='';dmPDraw(d);
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/import',{method:'POST',body:fd});DMP.busy=false;
    if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang});sayToast(t(`Entwurf aus ${x.kapitel} Kapiteln, bitte prüfen und speichern`,`Draft from ${x.kapitel} chapters, please check and save`))}else DMP.err=dmPlanErr(r,x);
    if(DMP.g&&dmPBox())dmPDraw(DMP.d);return}
  const body=k==='gvor'?{welt:g.welt,ton:g.ton,akte:n,stichworte:DMP.stich,tabus:g.tabus,lang:g.lang}:{plan:g,n:+b.dataset.n,hinweis:DMP.hint};
  if(k==='gvor'&&DMP.stich.trim().length<3){DMP.err=esc(t('Bitte ein paar Stichworte eingeben.','Please enter a few keywords.'));dmPDraw(d);return}
  DMP.busy=true;DMP.err='';dmPDraw(d);
  const {r,d:x}=await apiTry(DMP.host?'/api/profile/dungeon/geschichten/akt':'/api/admin/dungeon/geschichte/'+(k==='gvor'?'vorschlag':'akt'),xjson('POST',body));DMP.busy=false;
  if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang})}else DMP.err=dmPlanErr(r,x);
  if(DMP.g&&dmPBox())dmPDraw(DMP.d)}
// ---------------------------------------------------------------- Eigene Geschichten (dungeon_geschichten): Bearbeiten in
// the planner's form on its own sheet, Kopieren, Löschen / Ausblenden, „＋ Neue Geschichte“ (tone, keywords, „Erstellen“)
const DMG={neu:null,busy:false,err:''};
const dmGBase='/api/profile/dungeon/geschichten/';
function dmGModal(){let m=$('dmgs');if(!m){m=document.createElement('div');m.id='dmgs';m.className='modal';
  m.innerHTML='<div class="card modalcard dmadmcard" id="dmgscard"></div>';document.body.appendChild(m)}m.style.display='grid';return m}
function dmGClose(){const m=$('dmgs');if(m)m.style.display='none';DMP.host=false;DMP.g=null;DMG.neu=null;DMG.busy=false}
function dmGSheet(){const c=$('dmgscard');if(!c)return;if(DMG.neu)c.innerHTML=dmGNeu();else if(DMP.g)c.innerHTML=dmPlanForm(DMP.d)}
function dmGNeu(){const w=DM.data.wahl,N=DMG.neu;
  return `<h2>＋ ${esc(t('Neue Geschichte','New story'))}</h2><div class="dm-form">
    <div class="lbl">${esc(t('Ton','Tone'))}</div><div class="dm-cards dm-klein">${w.toene.map(x=>`<button type="button" class="dm-card${String(x.id)===String(N.ton)?' on':''}" data-dmgton="${esc(String(x.id))}" aria-pressed="${String(x.id)===String(N.ton)}"><b>${esc((x.zeichen||'')+' '+x.name)}</b></button>`).join('')}</div>
    <label>${esc(t('Stichworte (frei)','Keywords (optional)'))}</label><textarea class="dmg-stich" rows="2" maxlength="${w.eigene.planer.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht','a cursed mountain village, a dragon that only guards'))}">${esc(N.stich||'')}</textarea>
    <small class="mut">${esc(t('Das Sprachmodell schreibt Titel, Grundidee und Akte in der gewählten Welt, das Panel prüft den Entwurf mit festen Regeln. Danach kannst du sie über ⋯ bearbeiten.','The language model writes title, idea and acts in the chosen world, the panel checks the draft by fixed rules. Afterwards you can edit it with ⋯.'))}</small>
    ${DMG.err?`<div class="err dm-adm-err">${DMG.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmgnw="erstellen"${DMG.busy?' disabled':''}>${esc(DMG.busy?t('Das Modell schreibt …','The model is writing …'):t('Erstellen','Create'))}</button><button type="button" class="b" data-dmgnw="selbst"${DMG.busy?' disabled':''}>${esc(t('Selbst schreiben','Write it yourself'))}</button><button type="button" class="b" data-dmgnw="zu">${esc(t('Abbrechen','Cancel'))}</button></div></div>`}
const dmGWelt=()=>{const w=$('dmview'),b=w&&w.querySelector('.dmf-welt .on');return b?b.dataset.dmseg:DM.welt};
function dmGDone(x){const D=DM.data;D.wahl.geschichten=x.geschichten||D.wahl.geschichten;if(D.wahl.eigene)D.wahl.eigene.aus=x.aus||0;dmGClose();
  const w=$('dmview'),f=w&&w.querySelector('.dm-form');if(!f||!f.querySelector('.dmf-gesch'))return;
  f.querySelector('.dmf-gesch').innerHTML=dmStories(D.wahl,dmGWelt());
  dmStory(w,(x.gid&&f.querySelector(`.dmf-gesch [data-dmgs="${x.gid}"]`))||f.querySelector('.dmf-gesch [data-dmgs=""]'))}
function dmGForm(g,gid,von){const D=DM.data;DMP.host=true;DMG.neu=null;DMP.gid=gid;DMP.von=von;DMP.err='';DMP.stich='';DMP.hint='';
  DMP.d={planer:D.wahl.eigene.planer,wahl:D.wahl};DMP.g=g;dmGModal();dmGSheet()}
async function dmGWas(was,gid){const L='?lang='+dmLang();
  if(was==='bearbeiten'){const {r,d}=await apiTry(dmGBase+gid+L);if(!r.ok){sayToast(dmErr(r.status,d.detail));return}dmGForm(d,gid,d.von);return}
  const {r,d}=was==='kopieren'?await apiTry(dmGBase+gid+'/kopie',xjson('POST',{lang:dmLang()}))
    :was==='zeigen'?await apiTry(dmGBase+'zeigen',xjson('POST',{lang:dmLang()})):await apiTry(dmGBase+gid+L,{method:'DELETE'});
  if(!r.ok){sayToast(dmErr(r.status,d.detail));return}dmGDone(d);
  sayToast(was==='kopieren'?t('Kopie angelegt','Copy made'):was==='zeigen'?t('Wieder da','Back again'):t('Erledigt','Done'))}
document.body.addEventListener('click',async e=>{const m=e.target.closest('#dmview [data-dmgmehr]');
  if(m){const p=m.parentNode.querySelector('.ic-pop'),open=!p.hidden;document.querySelectorAll('.ic-pop').forEach(x=>x.hidden=true);p.hidden=open;return}
  const a=e.target.closest('#dmview [data-dmgwas]');
  if(a){if(a.dataset.dmgwas==='loeschen'&&a.dataset.sure!=='1'){a.dataset.sure='1';a.textContent=t('Wirklich?','Really?');return}
    a.closest('.ic-pop').hidden=true;await dmGWas(a.dataset.dmgwas,a.dataset.gid);return}
  if(e.target.closest('#dmview [data-dmgzeigen]')){await dmGWas('zeigen','');return}
  if(e.target.closest('#dmview [data-dmgneu]')){const w=$('dmview'),on=w&&w.querySelector('.dmf-ton .on');
    DMG.neu={ton:on?on.dataset.dmseg:String((DM.data.wahl.toene[1]||DM.data.wahl.toene[0]).id),stich:''};DMG.err='';DMG.busy=false;DMP.host=true;dmGModal();dmGSheet();return}
  const c=e.target.closest('#dmgscard [data-dmgton],#dmgscard [data-dmgnw],#dmgscard [data-dmadm]');if(!c)return;const N=DMG.neu,box=$('dmgscard');
  if(N)N.stich=(box.querySelector('.dmg-stich')||{}).value||N.stich;
  if(c.dataset.dmgton){N.ton=c.dataset.dmgton;dmGSheet();return}
  const k=c.dataset.dmgnw;
  if(k==='zu'||c.dataset.dmadm==='gback'){dmGClose();return}
  if(c.dataset.dmadm){if(c.dataset.dmadm[0]==='g')await dmPlanClick(c,c.dataset.dmadm);return}
  const ton=/^\d+$/.test(N.ton)?+N.ton:N.ton,P=DM.data.wahl.eigene.planer;
  if(k==='selbst'){dmGForm({titel:'',welt:dmGWelt(),ton,idee:'',ziel:'',gegner:'',orte:[],tabus:[],akte:Array.from({length:P.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))},'','eigen');return}
  if(k==='erstellen'){if(DMG.busy)return;DMG.busy=true;DMG.err='';dmGSheet();
    const {r,d}=await apiTry(dmGBase+'erstellen',xjson('POST',{welt:dmGWelt(),ton,stichworte:N.stich,lang:dmLang()}));DMG.busy=false;
    if(r.ok){dmGDone(d);sayToast(t('Geschichte erstellt','Story created'));return}DMG.err=dmPlanErr(r,d);dmGSheet()}});
// the pictures of a hero's things load once its list opens (dmHeroThings)
document.addEventListener('toggle',e=>{if(e.target.matches&&e.target.matches('details.dm-hdet')&&e.target.open)dmDingFill(e.target,'p')},true);
