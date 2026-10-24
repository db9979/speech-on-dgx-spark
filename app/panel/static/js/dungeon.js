// KI-Dungeon-Master (dungeon.py, plan dungeon-master/plan.md): a page of its own in the menu. „Runden“ lists the own
// rounds and starts a new one; an open round is the table: the group on the left, the story in the middle, the round
// and the own hero on the right (a phone shows them one below the other). „Helden“ holds the kept heroes. A seat link
// (#spiel=<code>) opens the same table in a window, for a guest without a profile through /api/dungeon/*, for a
// signed-in profile with „Mit meinem Profil“. Every value comes from the panel; names, actions and the narration are
// only ever text (esc), never markup. Funktionen → KI-Dungeon-Master, button „Regeln anpassen“, is the admin's rules editor.
const DM={on:false,data:null,rid:'',v:null,seq:0,busy:false,msg:'',err:false,made:null,at:0,ende:false,form:{},edit:'',kap:false};
const DG={code:'',v:null,info:null,busy:false,msg:'',err:false,at:0,figur:'',konto:{tok:'',v:null,step:'',adr:'',msg:'',err:false,gebunden:false}};
// read aloud (the last turn's WAV, the host's device plays it by itself) and the microphone of a seat
const DMA={handy:'geschichte',hzug:{p:-1,g:-1},p:{el:null,url:''},g:{el:null,url:''},rec:null,parts:[],mode:'',t0:0,voll:false,hilfe:null,modus:'',aendern:{p:0,g:0},gesendet:0};
// the short guide for players at the table: opens by itself once on this device, then by its button
const DMHILFE=[['Karte und Gewölbe','Map and vaults','Die Karte zeigt, wo ihr seid, und wächst mit, je mehr ihr entdeckt. Tippe unter „Von hier aus“ einen Weg an, dann steht er in deinem Feld. In Gewölben würfelt das Panel Fallen; die Antwort auf ein Rätsel schreibst du einfach in deine Aktion.','The map shows where you are and grows as you explore. Tap a way under "From here" to put it in your field. In vaults the panel rolls the traps; just write the answer to a riddle into your action.'],
  ['Was du schreibst','What you write','Was deine Figur tut oder sagt, in ein, zwei Sätzen: „Ich schleiche zur Tür und lausche.“ Der Dungeon-Master erzählt, was daraus wird.','What your character does or says, in a sentence or two: "I sneak to the door and listen." The Dungeon Master tells what comes of it.'],
  ['Wann es weitergeht','When it goes on','Alle schreiben gleichzeitig. Haben alle gehandelt oder ist die Zugzeit um, erzählt der Dungeon-Master. „Warten auf“ zeigt, wer noch fehlt; bis dahin kannst du deine Aktion ändern.','Everyone writes at the same time. Once all have acted or the turn time is up, the Dungeon Master narrates. "Waiting for" shows who is still missing; until then you can change your action.'],
  ['Das kann ich','What I can do','Dein Bogen zeigt unter „Das kann ich“ deine Fähigkeiten und die Zauber deiner Klasse. Zaubertricks gehen beliebig oft, höhere Zauber brauchen eine Ladung, die Ladungen füllen sich mit jeder Runde und jedem Kapitel. Antippen schreibt es in deine Aktion. Was dein Held noch nicht kann, gelingt nicht: dann steht eine kleine Zeile nur für dich da.','Your sheet shows your abilities and your class\'s spells under "What I can do". Cantrips work any time, higher spells need a charge, the charges fill up with every round and chapter. A tap writes it into your action. What your hero cannot do yet does not work: then a small line just for you says so.'],
  ['Würfeln und Kampf','Dice and fights','Würfeln musst du nicht, das macht das Panel: ein W20 plus der Bonus deines Werts (16 gibt +3) gegen eine Schwierigkeit. Bei Vorteil würfelt es zweimal und nimmt den besseren Wurf, bei Nachteil den schlechteren. Kommt deine Probe, tippst du auf den großen Würfel oder schüttelst das Handy: er rollt auf die Zahl des Panels, die Leiste zeigt, wie knapp es war. Trefft ihr auf Gegner, wählt das Panel sie passend zu eurer Gruppe aus dem Bestiarium, die Karte „Begegnung“ zeigt sie; ein Tipp auf einen Gegner zeigt seine Werte. Greifst du an, würfelt das Panel: W20 + Wert-Bonus + Übungsbonus gegen die Rüstungsklasse (RK) des Gegners, eine 20 trifft immer doppelt, eine 1 nie. Schaden kommt von deiner Waffe oder deinem Zauber. Danach greift jeder Gegner, der noch steht, an; die Leiste über der Geschichte zeigt ihr Leben. Am Ende gibt es die Erfahrung aus dem Bestiarium, geteilt durch die Helden.','You never roll yourself, the panel does: a d20 plus your value\'s bonus (16 gives +3) against a difficulty. With advantage it rolls twice and keeps the better roll, with disadvantage the worse. When your check comes, tap the big die or shake your phone: it rolls onto the panel\'s number, the bar shows how close it was. When you meet foes, the panel picks them from the bestiary to fit your group, the card „Encounter“ shows them; a tap on a foe shows its values. When you attack, the panel rolls: d20 + value bonus + proficiency bonus against the foe\'s armour class (AC), a 20 always hits double, a 1 never hits. Damage comes from your weapon or spell. Then every foe still standing attacks; the bar above the story shows their life. At the end you get the experience of the bestiary, divided among the heroes.'],
  ['Am Boden und gefallen','Down and fallen','Bei 0 Leben liegt dein Held am Boden und kann nichts tun. Ein Freund gibt ihm mit „🧪 Heiltrank geben“ einen Trank, heilt ihn oder hilft ihm in seiner Aktion auf. Nach 3 erzählten Zügen ohne Heilung ist er gefallen: für immer, seine Dinge und sein Gold liegen unter „Liegt hier“ für die anderen. Am Kindertisch ist er nur ohnmächtig und wacht im nächsten Kapitel ohne Gold wieder auf. Vor jedem neuen Tisch rasten die Lebenden: volles Leben, volle Ladungen.','At 0 life your hero is down and cannot do anything. A friend gives them a potion with "🧪 Give a healing potion", heals them or helps them up in their action. After 3 told turns without healing they have fallen: for good, their things and gold lie under "Lying here" for the others. At the children\'s table they are only unconscious and wake in the next chapter without gold. Before every new table the living rest: full life, full charges.'],
  ['Kräfte und Erfahrung','Powers and experience','Manche Fähigkeiten setzt das Panel selbst um: Eisenhaut nimmt jedem Treffer 1 ab und „wirkt immer“, Schildwall fängt 1× je Szene den Treffer eines Freundes ab, Kampfschrei gibt der Gruppe +1 auf die Proben des Zugs. Nenne sie in deiner Aktion („Ich setze Schildwall ein“). Erfahrung sammelt sich am Tisch („+X EP noch am Tisch“) und zählt am Ende der Runde oder des Kapitels.','Some abilities the panel carries out itself: Iron skin takes 1 off every hit and "always works", Shield wall takes a friend\'s hit once a scene, Battle cry gives the group +1 on the turn\'s checks. Name them in your action ("I use Shield wall"). Experience gathers at the table ("+X XP still at the table") and counts at the end of the round or chapter.'],
  ['Leben, Beute, Tauschen','Life, loot, trading','Der Balken zeigt dein Leben. Beute landet in deiner Tasche (bis 12 Plätze, gleiche Tränke stapeln sich); Tränke und Zauber nutzt du dort. Tauschen geht per Angebot: erst wenn der andere annimmt, tauscht das Panel.','The bar shows your life. Loot lands in your bag (up to 12 places, the same potions stack); you use potions and spells from there. Trading works by offer: only when the other one accepts does the panel swap.'],
  ['Ausrüstung und Gewicht','Equipment and weight','„📜 Heldenbogen“ in der Seitenspalte öffnet deinen Bogen groß, ein Tipp auf ein Ding zeigt Bild, Beschreibung und Werte. Neun Plätze wie bei D&D: Ziehe ein Ding aus der Tasche auf seinen Platz oder tippe „Anlegen“. Du trägst Stärke mal 3,75 kg; ab drei Vierteln bist du belastet und würfelst Geschick mit Nachteil. Was nicht mehr passt, bleibt unter „Liegt hier“ am Boden.','"📜 Hero sheet" in the side column opens your sheet large, a tap on a thing shows its picture, description and values. Nine places as in D&D: drag a thing from the bag onto its place or tap "Equip". You carry strength times 3.75 kg; from three quarters you are burdened and roll dexterity with disadvantage. What no longer fits stays on the ground under "Lying here".'],
  ['Händler','Merchants','In Siedlungen bietet ein Händler Waren an, „⚖ Händler“ zeigt sie groß. Die Preise macht das Panel, Charisma gibt bis 20 % Rabatt; Verkaufen bringt die Hälfte. Sehr seltene Magie ist erst unerkannt: Eine Rolle des Erkennens oder der Händler nennt, was sie kann.','In settlements a merchant offers goods, "⚖ Merchant" shows them large. The panel sets the prices, Charisma gives up to 20 % off; selling fetches half. Very rare magic is unknown at first: a scroll of knowing or the merchant names what it does.'],
  ['Werte, Dinge und Werkzeuge','Values, things and tools','Tippe auf einen Wert, auf Leben, Stufe oder Rüstungsklasse: darunter steht, was es ist und wofür es zählt. Ein getragenes Ding öffnet sein Fenster mit Bild. Nennst du in deiner Aktion ein Werkzeug wie Seil oder Dietrich und passt die Probe, gibt es +2; bei einer 1 kann es zerbrechen.','Tap a value, life, level or armour class: below it says what it is and what it counts for. A worn thing opens its window with the picture. If your action names a tool like a rope or lockpick and the check fits, you get +2; on a 1 it can break.'],
  ['Warten und Tischgespräch','Waiting and table talk','Während der Dungeon-Master erzählt, zeigt der Tisch die Würfe schon vorab, dazu Wissenskarten der Welt. Im „💬 Tischgespräch“ unter dem Feld redet ihr miteinander; der Dungeon-Master liest das nie.','While the Dungeon Master narrates, the table already shows the rolls, plus lore cards of the world. In the "💬 Table talk" below the field you talk to each other; the Dungeon Master never reads it.'],
  ['Hören und Sprechen','Listen and speak','Ist Vorlesen an, tippst du einmal auf „🔊 Ton an“, danach liest jedes Gerät die Erzählung Satz für Satz von selbst vor. Was jemand wörtlich sagt, spricht die Figur, nie der Erzähler; dein Held bekommt eine eigene Stimme vorgeschlagen. Die Uhr startet erst nach dem Vorlesen. 🔈/🔇 schaltet es nur auf diesem Gerät an oder aus, „🔊 Nochmal hören“ liest den letzten Zug noch einmal. Mit 🎤 sprichst du deine Aktion; der Text landet im Feld, abgeschickt wird mit „Handeln“.','With reading aloud on, tap "🔊 Sound on" once; after that every device reads the narration sentence by sentence by itself. What someone says word for word is spoken by the character, never the narrator; your hero gets a voice of its own proposed. The clock starts only after the reading. 🔈/🔇 switches it on or off on this device only, "🔊 Listen again" reads the last turn once more. With 🎤 you speak your action; the text lands in the field, "Act" sends it.'],
  ['Als Gast','As a guest','Am Ende bekommst du einen Figur-Code. Damit spielt dein Held beim nächsten Mal weiter, auch in einem eigenen Profil. Schreib ihn dir auf.','At the end you get a hero code. With it your hero plays on next time, also in a profile of your own. Write it down.']];
// the guide is a window with one page per part (Punkt 9 of the review of 2026-10-24): ‹ › or the dots page, ✕, Esc or a tap beside it closes
function dmHilfe(){if(DMA.hilfe===null){let seen=false;try{seen=localStorage.getItem('dm-hilfe')==='1';localStorage.setItem('dm-hilfe','1')}catch(e){}DMA.hilfe=seen?false:0}
  if(DMA.hilfe===false)return '';const n=DMHILFE.length,i=Math.max(0,Math.min(n-1,+DMA.hilfe||0)),x=DMHILFE[i],titel='❔ '+t('So spielst du','How to play');
  return `<div class="dm-fen dm-fen-hilfe" data-dmfenbg="hilfe"><div class="dm-fen-box" role="dialog" aria-modal="true" aria-label="${esc(titel)}">
    <div class="dm-fen-kopf"><h3>${esc(titel)}</h3><button type="button" class="ic-ib" data-dmhilfe="zu" title="${esc(t('Schließen','Close'))}" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>
    <div class="dm-fen-body dm-hseite"><small class="mut">${esc(t('Seite '+(i+1)+' von '+n,'Page '+(i+1)+' of '+n))}</small><h4>${esc(t(x[0],x[1]))}</h4><p>${esc(t(x[2],x[3]))}</p></div>
    <div class="dm-hnav"><button type="button" class="b" data-dmhilfe="${i-1}"${i?'':' disabled'}>‹ ${esc(t('Zurück','Back'))}</button><span class="dm-hpunkte">${DMHILFE.map((y,k)=>`<button type="button" class="${k===i?'on':''}" data-dmhilfe="${k}" title="${esc(t(y[0],y[1]))}" aria-label="${esc(t(y[0],y[1]))}"></button>`).join('')}</span><button type="button" class="b p" data-dmhilfe="${i<n-1?i+1:'zu'}">${esc(i<n-1?t('Weiter','Next')+' ›':t('Fertig','Done'))}</button></div></div></div>`}
const dmHilfeAuf=w=>DMA.hilfe=w==='zu'?false:Math.max(0,Math.min(DMHILFE.length-1,+w||0));
// the table alone, filling the screen (the button again, Esc or leaving the browser's full screen ends it; without the browser's full screen, as on the iPhone, it fills the window)
function dmVoll(on){DMA.voll=on;const f=document.querySelector('[data-dmvoll]'),w=f&&f.closest('.dm');if(w)w.classList.toggle('dm-voll',on);
  try{if(on&&w&&w.requestFullscreen&&!document.fullscreenElement)w.requestFullscreen().catch(()=>{});if(!on&&document.fullscreenElement)document.exitFullscreen()}catch(e){}
  document.querySelectorAll('.dm-tisch [data-dmvoll]').forEach(b=>{b.dataset.dmvoll=on?0:1;b.textContent=on?'✕ '+t('Vollbild aus','Exit full screen'):'⛶ '+t('Vollbild','Full screen')})}
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
const dmTop=sub=>`<div class="dm-head dm-top"><div class="dm-htitle"><h3>⚔ ${esc(t('Dungeon-Master','Dungeon Master'))}</h3><small class="mut">${esc(sub)}</small></div>${dmModus()}</div>`;
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
function dmPaint(w){const D=DM.data;w.classList.remove('dm-voll');delete w.dataset.welt;dmLook(w,D&&dmWelt(D.wahl,DM.welt).farben);
  if(!D){w.innerHTML=`<div class="ld-empty mut">${esc(DM.err?DM.msg:t('Lade den Dungeon-Master …','Loading the Dungeon Master …'))}</div>`;return}
  if(w.dataset.tab==='helden'){w.innerHTML=dmTop(t('Deine Helden','Your heroes'))+dmHeroes(D)+dmMsg(DM);return}
  if(DM.v){dmTable(w,DM.v,'p');return}
  w.innerHTML=dmTop(t('Runden, Kampagnen und eine neue Runde','Rounds, campaigns and a new round'))+dmRounds(D)+dmCampaigns(D)+dmNew(D)+dmMsg(DM);dmDingFill(w,'p')}
const dmMsg=S=>`<div class="dmmsg ${S.err?'err':'mut'}" role="status">${esc(S.msg)}</div>`;
// a refusal of the panel as a sentence with what to do: the reason word of the rule (dungeon._http, one per raise in
// dungeon*.py, test_dungeon checks every one has its sentence) or the coarse word
// the host hides a line of table talk or an action (Punkt 13 of 2026-10-24); only on the own page, a guest never hosts
const dmHide=(v,art,n,pid)=>v.gastgeber?`<button type="button" class="ic-ib dm-hide" data-dmhide="${art}" data-n="${n}"${pid?` data-pid="${esc(pid)}"`:''} title="${esc(t('Für alle ausblenden','Hide for everyone'))}" aria-label="${esc(t('Für alle ausblenden','Hide for everyone'))}">⊘</button>`:'';
const DMGRUND={
  'wortliste':['Das geht an diesem Tisch nicht: Ein Wort steht auf der Wortliste der Runde (Ton, „nie“ oder Tabus der Geschichte). Formuliere es anders.','That does not work at this table: a word is on the round\'s word list (tone, "never" or the story\'s taboos). Put it another way.'],
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
  'erkennen':['Das kann der Händler gerade nicht erkennen, oder dein Gold reicht nicht.','The merchant cannot identify this right now, or your gold is not enough.'],
  'haendler':['Gerade ist kein Händler da.','There is no merchant here right now.'],
  'kein trank':['Das ist kein Trank.','That is no potion.'],
  'kein zauber':['Das ist kein Zauber.','That is no spell.'],
  'punkt':['Dafür hast du keinen Wertpunkt frei, oder der Wert ist schon ganz oben.','You have no value point for that, or the value is at the top already.'],
  'faehigkeit':['Diese Fähigkeit steht gerade nicht zur Wahl.','This ability is not on offer right now.'],
  'fallen':['Das kannst du hier nicht ablegen.','You cannot put that down here.'],
  'aufheben':['Das liegt nicht mehr hier, oder deine Tasche ist voll.','That is no longer here, or your bag is full.'],
  'ablegen':['An diesem Platz trägst du nichts.','You wear nothing in this place.'],
  'tausch':['Dieser Tausch geht so nicht.','This trade does not work like that.'],
  'angebot':['Dieses Tauschangebot passt nicht mehr: einer hat die Dinge oder das Gold nicht mehr.','This trade offer no longer fits: someone no longer has the things or the gold.'],
  'stimme':['Diese Stimme gibt es nicht, oder die Sprachausgabe kann sie nicht machen.','This voice does not exist, or the speech output cannot make it.'],
  'ton':['Diese Aufnahme gibt es nicht mehr.','This recording is gone.'],
  'bild':['Dieses Bild gibt es nicht mehr.','This picture is gone.'],
  'stueck':['Dieses Musikstück gibt es nicht mehr.','This piece of music is gone.'],
  'erzaehlung':['Diese Erzählung gibt es nicht mehr.','This narration is gone.'],
  'termin':['Dieser Termin passt nicht: er muss in der Zukunft liegen.','This date does not fit: it must lie in the future.'],
  'daumen':['Das ging nicht.','That did not work.'],
  'was':['Das ging nicht.','That did not work.'],
  'eingabe':['Die Eingabe passt nicht. Prüfe die Felder.','The input does not fit. Check the fields.'],
  'nicht da':['Das gibt es nicht mehr.','That is gone.']};
const dmErr=(status,d)=>typeof d==='string'&&DMGRUND[d]?t(...DMGRUND[d]):errSay(status,d,'');
function dmSay(S,x,err){S.msg=String(x||'').slice(0,300);S.err=!!err;document.querySelectorAll(S===DM?'#dmview .dmmsg':'#dgcard .dmmsg').forEach(m=>{m.className='dmmsg '+(err?'err':'mut');m.textContent=S.msg})}
function dmRounds(D){const st={laeuft:t('läuft','running'),ende:t('beendet','ended')};
  if(!D.runden.length)return `<div class="ic-empty">${esc(t('Noch keine Runde. Leg unten eine an und lade bis zu vier Mitspieler ein, auch Leute ohne Profil.','No round yet. Start one below and invite up to four players, also people without a profile.'))}</div>`;
  return `<h3 class="sec">${esc(t('Deine Runden','Your rounds'))}</h3><div class="ic-list">${D.runden.map(x=>`<div class="ic-row"><span class="dm-ic" aria-hidden="true">${esc(dmWelt(D.wahl,x.welt).zeichen||'')}</span><div class="ic-rmid"><span class="ic-t">${esc(x.titel)}</span><small class="ic-meta">${esc(st[x.status]||x.status)} · ${esc(t('Zug','Turn'))} ${x.zug} · ${x.spieler} ${esc(t('Spieler','players'))}${x.held?' · '+esc(x.held):''}${x.gastgeber?' · '+esc(t('du leitest','you host')):''}</small></div><button type="button" class="b p" data-dmopen="${esc(x.rid)}">${esc(t('Öffnen','Open'))}</button>${x.status==='ende'?`<button type="button" class="b danger" data-dmdel="${esc(x.rid)}">${esc(DM.del===x.rid?t('Wirklich?','Really?'):x.gastgeber?t('Löschen','Delete'):t('Ausblenden','Hide'))}</button>`:''}</div>`).join('')}</div>`}
// an ended round: the host deletes it, a player takes it off the own list (second tap confirms)
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmkann]');if(!b)return;const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
  ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+b.dataset.dmkann;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus()});
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmdel]');if(!b)return;const rid=b.dataset.dmdel;
  if(DM.del!==rid){DM.del=rid;dmDraw();return}DM.del='';const x=await dmSend(`/api/profile/dungeon/${rid}`,null,DM);if(x)DM.data=x;dmDraw()});
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
      :`<button type="button" class="b p" data-dmkweiter="${esc(k.kid)}"${k.schreibt?' disabled':''}>▶ ${esc(t('Kapitel '+(k.kapitel+1)+' beginnen','Start chapter '+(k.kapitel+1)))}</button><button type="button" class="b" data-dmkedit="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmkneu="${esc(k.kid)}"${k.schreibt?' disabled':''}>${esc(t('Neu schreiben lassen','Write it again'))}</button><button type="button" class="b danger" data-dmkdel="${esc(k.kid)}">${esc(t('Löschen','Delete'))}</button>`}</div></div>`}).join('')}</div>`}
// people and class of a new hero as cards (the hidden field keeps the choice): the people's bonus, the class's best values and life
const dmKurz=(w,id)=>(w.werte.find(x=>x.id===id)||{}).kurz||id;
function dmVolkSub(w,x){const e=Object.entries(x.werte||{});
  return e.length===w.werte.length&&e.every(([k,v])=>v===e[0][1])?t('alle Werte +','all values +')+e[0][1]:e.map(([k,v])=>dmKurz(w,k)+' +'+v).join(' · ')}
// the card names the class's best values and life, a badge on its picture counts what it can do from level 1
function dmKlasseSub(w,x){return x.reihe.slice(0,2).map(k=>dmKurz(w,k)).join(' · ')+' · '+t('Leben','life')+' '+x.leben}
function dmKlasseZahl(x){const st=x.start||{f:[],z:[]},f=st.f.length,z=st.z.length;
  return [f?f+' '+t(f===1?'Kraft':'Kräfte',f===1?'power':'powers'):'',z?z+' '+t('Zauber',z===1?'spell':'spells'):''].filter(Boolean).join(' · ')}
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
const dmPCard=(attr,on,x,sub,badge)=>`<button type="button" class="dm-card dm-pcard${on?' on':''}" ${attr}>${dmPic(dmHB(x),x.name)}${badge?`<em class="dm-pbadge">${esc(badge)}</em>`:''}<b>${esc(x.name)}</b>${sub?`<small>${dmFx(sub)}</small>`:''}</button>`;
// a power as a picture tile (class detail, „Das kann ich“): the colour on top is its kind, a tap explains it
// the colour of a kind (app.css), named here in full so every class is found
const DMKK={angriff:'k-angriff',heilen:'k-heilen',schutz:'k-schutz',sonst:'k-sonst'};
const DMKART=()=>({angriff:t('Angriff','Attack'),heilen:t('Heilen','Healing'),schutz:t('Schutz','Protection'),sonst:t('Sonstiges','Other')});
const dmKtSub=x=>x.grad===undefined?(x.wert?x.wert+' +'+x.bonus:''):x.grad&&x.rest!==undefined&&x.rest!==null?t('noch '+x.rest+' von '+x.voll,x.rest+' of '+x.voll+' left'):x.satz||'';
function dmKt(x,key,on,off){return `<button type="button" class="dm-kt ${DMKK[x.art]||DMKK.sonst}${on?' on':''}${off?' aus':''}${x.immer?' immer':''}" data-dmkt="${esc(key)}" aria-expanded="${!!on}">${dmPic(dmHB(x),x.name,'',DMZ[x.art]||DMZ.sonst)}${x.grad?`<em>${esc(t('Grad '+x.grad,'Grade '+x.grad))}</em>`:''}<b>${esc(x.name)}</b><small>${dmFx(dmKtSub(x))}</small></button>`}
// what the panel does for an ability (faehigkeiten[].wirkung, Punkt 3 of 2026-10-24); one that always works has no „Einsetzen“
const DMWIRK=()=>({weniger_schaden:t('das Panel zieht je Treffer 1 ab','the panel takes 1 off every hit'),abfangen:t('das Panel gibt dir 1× je Szene den Treffer eines Freundes','the panel gives you a friend\'s hit once a scene'),gruppe_probe:t('das Panel gibt der Gruppe +1 auf die Proben dieses Zugs','the panel gives the group +1 on this turn\'s checks')});
// what a power is: picture, kind, sentence, explanation and its values; „✨ Wirken“ writes it into the own action field
function dmKtDet(x,say){const zt=x.grad===undefined?t('Fähigkeit','Ability'):x.grad?t('Zauber Grad '+x.grad,'Spell grade '+x.grad):t('Zaubertrick','Cantrip');
  const chips=[DMKART()[x.art]||'',x.wert?`🎲 ${esc(x.wert)} ${dmBo(x.bonus)}`:'',x.grad?esc(x.rest===undefined||x.rest===null?t('Ladungen je Stufe','charges per level'):t('noch '+x.rest+' von '+x.voll+' Ladungen',x.rest+' of '+x.voll+' charges left')):x.grad===0?esc(t('beliebig oft','any time')):'',
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
function dmHeroForm(w,heroes,pre){const vk=(k,a,sub,badge)=>`<input type="hidden" class="${pre}${k}" value="${esc(a[0].id)}"><div class="dm-cards dm-klein dm-vk" data-dmvkk="${k}">${a.map((x,i)=>dmPCard(`data-dmvk="${esc(x.id)}"`,i===0,x,sub(w,x),badge&&badge(x))).join('')}</div>`;
  return `${heroes&&heroes.length?`<label>${esc(t('Held','Hero'))}</label><select class="${pre}held"><option value="">${esc(t('Neuer Held …','New hero …'))}</option>${heroes.map(h=>`<option value="${esc(h.hid)}"${h.zustand==='tot'?' disabled':''}>${esc(h.name)} · ${esc(h.klasse)} · ${esc(t('Stufe','level'))} ${h.stufe}${h.zustand==='tot'?' · '+esc(t('gefallen','fallen')):''}</option>`).join('')}</select>`:''}
    <div class="${pre}neu dm-neu"><label>${esc(t('Name deiner Figur','Name of your character'))}</label><input class="${pre}name" maxlength="24" autocomplete="off">
    <label>${esc(t('Volk','People'))}</label>${vk('volk',w.voelker,dmVolkSub)}<label>${esc(t('Klasse','Class'))}</label>${vk('klasse',w.klassen,dmKlasseSub,dmKlasseZahl)}<div class="${pre}kdet">${dmKlasseDet(w,w.klassen[0].id)}</div>
    <label>${esc(t('Werte','Values'))}</label><small class="mut">${esc(t('Die Zahlen 15, 14, 13, 12, 10 und 8 verteilen: ziehen oder zwei antippen tauscht sie. Dahinter das Volk, der Wert und der Bonus für Würfe.','Lay out 15, 14, 13, 12, 10 and 8: drag, or tap two to swap them. After it the people\'s bonus, the value and the bonus for rolls.'))}</small>
    <div class="${pre}vert dm-vert">${w.verteilung?dmVert(w,w.klassen[0].id,w.voelker[0].id):''}</div>
    <label>${esc(t('Ein Satz zu deiner Figur (frei)','One sentence about your character (optional)'))}</label><input class="${pre}satz" maxlength="120" autocomplete="off">
    ${w.bilder_an?`<label class="dm-check"><input type="checkbox" class="${pre}portraet"> ${esc(t('Porträt malen lassen (aus Volk, Klasse und deinem Satz)','Have a portrait painted (from people, class and your sentence)'))}</label>`:''}</div>`}
function dmHeroBody(box,pre){const sel=box.querySelector('.'+pre+'held');if(sel&&sel.value)return sel.value;
  const v=c=>(box.querySelector('.'+pre+c)||{}).value||'';const vt=box.querySelector('.'+pre+'vert');return {name:v('name').trim(),volk:v('volk'),klasse:v('klasse'),satz:v('satz').trim(),verteilung:vt?dmVertOf(vt):undefined}}
// the six values of a new hero: the fixed row (15 14 13 12 10 8) laid out by the class, the player drags or taps two numbers to swap them
const dmSign=m=>(m<0?'−':'+')+Math.abs(m);
// dice and bonuses stand out everywhere in the game (Dominik 2026-10-24 „Würfel und Bonis … gehen im fließtext unter“):
// dmBo a bonus as a coloured chip, dmFx a text escaped with every die („1W6+2“, „W20“, „2d8“) and signed number marked
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
function dmStories(w,welt){const ton=id=>w.toene.find(x=>x.id===id)||{};
  return dmCard('data-dmgs=""',true,'✒',t('Frei erzählen','Tell freely'),t('Der Dungeon-Master erfindet die Geschichte aus dem Einstieg.','The Dungeon Master makes up the story from the opening.'))
    +(w.geschichten||[]).filter(g=>g.welt===welt).map(g=>`<button type="button" class="dm-card dm-gcard" data-dmgs="${esc(g.gid)}"><b>${esc(g.titel)}</b><small class="dm-gidee">${esc(g.idee)}</small><small class="dm-gmeta">${esc((ton(g.ton).zeichen||'')+' '+(ton(g.ton).name||''))} · ${g.akte} ${esc(t('Akte','acts'))}${g.von==='admin'?' · '+esc(t('vom Admin','by the admin')):''}</small></button>`).join('')}
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
const dmZustText=h=>h.zustand==='boden'?t('am Boden · noch '+h.noch+(h.noch===1?' Zug':' Züge'),'down · '+h.noch+(h.noch===1?' turn':' turns')+' left'):h.zustand==='ohnmacht'?t('ohnmächtig bis zum nächsten Kapitel','unconscious until the next chapter'):h.zustand==='tot'?t('gefallen','fallen'):'';
const dmZust=h=>h&&h.zustand?`<span class="dm-zst" data-z="${esc(h.zustand)}">${{boden:'⚠',ohnmacht:'💤',tot:'✝'}[h.zustand]||''} ${esc(dmZustText(h))}</span>`:'';
// what the own seat reads instead of the action field while its hero cannot act
const dmZustSatz=h=>h.zustand==='boden'?t('Dein Held liegt am Boden. Ein Freund kann ihm einen Heiltrank geben, ihn heilen oder ihm aufhelfen. Noch '+h.noch+(h.noch===1?' erzählter Zug':' erzählte Züge')+' ohne Heilung, dann fällt er.','Your hero is down. A friend can give them a healing potion, heal them or help them up. '+h.noch+(h.noch===1?' told turn':' told turns')+' without healing, then they fall.')
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
    ${h.satz?`<small class="dm-isatz">„${esc(h.satz)}“</small>`:''}<div class="dm-hostb"><button type="button" class="b danger" data-dmdelhero="${esc(h.hid)}">${esc(t('Löschen','Delete'))}</button></div></div>`).join('')}</div>`
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
// time of map, host, threads and date; the last tab is remembered per device
function dmSeite(v,mode,host){const hp=dmHandy()?DMA.handy:'';   // on the phone „Karte“ is its own pane, „Held“ shows the others
  const teile=[['karte','🗺',t('Karte','Map'),dmKarte(v,mode)],['host','🎲',t('Leiten','Host'),host],
    ['faeden','📜',t('Fäden','Threads'),dmThreads(v)],['termin','📅',t('Termin','Date'),dmDate(v,mode)]].filter(x=>x[3]&&(hp==='karte'?x[0]==='karte':hp!=='held'||x[0]!=='karte')).map(x=>[x[0],x[1]+'|'+x[2],x[3]]);if(!teile.length)return '';
  if(!DMA.seite){try{DMA.seite=localStorage.getItem('dm-seite')||''}catch(e){}}
  const on=(teile.find(x=>x[0]===DMA.seite)||teile[0])[0];
  return `${teile.length>1?`<div class="lseg dm-seite" role="tablist">${teile.map(x=>`<button type="button" role="tab" aria-selected="${x[0]===on}" class="${x[0]===on?'on':''}" data-dmseite="${x[0]}"><span aria-hidden="true">${x[1].split('|')[0]}</span>${esc(x[1].split('|')[1])}</button>`).join('')}</div>`:''}
    <div class="dm-seitein">${teile.find(x=>x[0]===on)[2]}</div>`}
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
document.addEventListener('toggle',e=>{const d=e.target;if(!(d instanceof Element)||!d.matches('[data-dmauf]'))return;if(d.open)DMA.auf=d.dataset.dmauf;else if(DMA.auf===d.dataset.dmauf)DMA.auf=''},true);
document.body.addEventListener('click',e=>{const b=e.target.closest('[data-dmseite]');if(!b)return;DMA.seite=b.dataset.dmseite;
  try{localStorage.setItem('dm-seite',DMA.seite)}catch(x){}
  if(b.closest('#dgcard'))dgDraw();else dmDraw()});
function dmThreads(v){const f=v.faeden||[];if(!f.length)return '';return `<ul class="dm-faeden">${f.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`}
// the quest of the prologue, pinned under the turn until a goal is reached (then ticked)
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
    const v=g?DG.v:DM.v;if(v){v.daumen=d.daumen;g?dgDraw():dmDraw()}}catch(x){dmSay(g?DG:DM,t('Das hat nicht geklappt.','That did not work.'),true)}});
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
function dmDing(it){return it.bild?`<span class="dm-ding"><img alt="" loading="lazy" data-dmdbild="${esc(it.bild)}"></span>`:it.zeichen?`<span class="dm-ding dm-dz" aria-hidden="true">${esc(it.zeichen)}</span>`:''}
async function dmDingFill(w,mode){for(const im of w.querySelectorAll('img[data-dmdbild]:not([src])')){const n=im.dataset.dmdbild,key='d'+n;
    if(mode==='p'){im.src='/api/profile/dungeon/ding/'+encodeURIComponent(n);continue}
    if(key in DMI){if(DMI[key])im.src=DMI[key];continue}DMI[key]='';
    try{const r=await /*raw: a guest seat's picture as a blob, api() would open the login on a 401*/fetch('/api/dungeon/ding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,name:n})});
      if(!r.ok){delete DMI[key];continue}DMI[key]=URL.createObjectURL(await r.blob())}catch(e){delete DMI[key];continue}
    document.querySelectorAll(`#dgcard img[data-dmdbild="${n}"]`).forEach(x=>x.src=DMI[key])}}
function dmItem(it,acts){return `<div class="dm-item ${DMSEL[it.selten]||''}"${it.i?` data-dmi="${esc(it.i)}"`:''}><div>${dmDing(it)}<b>${esc(it.name)}</b>${it.n>1?` <span class="pill">×${it.n}</span>`:''} <small>${esc(it.selten_name)}</small>${it.kg?` <small>· ${String(it.kg).replace('.',L==='en'?'.':',')} kg</small>`:''}</div>${it.fund?`<small class="dm-ifund">${esc(t('Gefunden in: ','Found in: ')+it.fund)}</small>`:''}${it.satz?`<small class="dm-isatz">„${esc(it.satz)}“</small>`:''}${it.info?`<small class="dm-iinfo">${esc(it.info)}</small>`:''}<small>${it.zeilen.map(dmFx).join(' · ')}</small>${acts||''}</div>`}
// the prologue's hold (Dominik 2026-10-24 „keinerlei anhalts punkt was zu tun ist“): why each hero is here, and
// „Was ihr tun könnt“ as buttons that write the possibility into the own field (own ideas go on as before)
function dmProlog(v,e){const nm=pid=>((v.plaetze||[]).find(p=>p.pid===pid)||{}).name||'',hk=Object.entries(e.haken||{}).filter(([p])=>nm(p));
  return `${hk.length?`<ul class="dm-haken">${hk.map(([p,x])=>`<li${p===v.pid?' class="me"':''}><b>${esc(nm(p))}</b> ${esc(x)}</li>`).join('')}</ul>`:''}${(e.wege||[]).length?`<div class="dm-wege"><small>${esc(t('Was ihr tun könnt','What you can do'))}</small>${e.wege.map(x=>`<button type="button" class="dm-weg" data-dmweg="${esc(x)}">${esc(x)}</button>`).join('')}</div>`:''}`}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmweg]');if(!b)return;const w=b.closest('.dm'),ta=w&&w.querySelector('.dm-in');if(!ta||ta.disabled)return;
  ta.value=b.dataset.dmweg;ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus()});
function dmLog(v,e,col){const W=v.werte||{},sys=Array.isArray(e.text)?e.text[L==='en'?1:0]:e.text;
  if(e.art==='dm'){const my=(v.daumen||{})[String(e.n||1)]||0,th=v.ich?`<span class="dm-thumbs">${[[1,'👍',t('Gut erzählt','Well told')],[-1,'👎',t('Nicht so gut','Not so good')]].map(([g,i,l])=>`<button type="button" class="ic-ib${my===g?' on':''}" data-dmdaumen="${g}" data-zug="${e.n||1}" title="${esc(l)}" aria-label="${esc(l)}" aria-pressed="${my===g}">${i}</button>`).join('')}</span>`:'';
    return `<div class="dm-dm"><div class="dm-n">${esc(e.prolog?t('Prolog','Prologue'):t('Zug','Turn')+' '+(e.n||1))}${th}</div><p>${dmSaetze(v,e)}</p>${(e.npc||[]).filter(n=>!n.im_text).map(n=>`<div class="dm-npc"><em>${esc(n.name)}</em><p>„${esc(n.sagt)}“</p></div>`).join('')}${e.prolog?dmProlog(v,e):''}</div>`}
  if(e.art==='aktion')return `<div class="dm-act">${dmAv(v.mode,v,Object.assign({name:e.name},(v.plaetze||[]).find(p=>p.pid===e.pid)||{}),col?col(e.pid):0)}<div class="dm-bub"><b>${esc(e.name)}</b><p>${esc(e.text)}</p></div>${dmHide(v,'aktion',e.n,e.pid)}</div>`;
  if(e.art==='wurf')return `<div class="dm-wurf ${e.ok?'ok':'bad'}"><span class="dm-d20">${e.w}</span>${dmVt(e)}${dmTool(e)}${e.schrei?`<span class="dm-vt">${esc(t('Kampfschrei +1','Battle cry +1'))}</span>`:''}${esc(e.name)} · ${esc(W[e.wert]||e.wert)} ${dmBo(e.bonus)} = <b>${e.gesamt}</b> ${esc(t('gegen','vs'))} ${e.schwer} · <b>${esc(e.ok?t('geschafft','success'):t('nicht geschafft','failed'))}</b></div>${dmLeiste(e,v.werkzeug_bonus)}`;
  if(e.art==='folge')return `<div class="dm-sys ${e.was==='heilung'?'ok':'bad'}">${esc(e.name)}: ${e.was==='heilung'?'+':'−'}${e.zahl} ${esc(t('Leben','life'))} (${esc(t('jetzt','now'))} ${e.leben})${e.weniger?' · '+esc(t(e.weniger+' weniger durch Eisenhaut',e.weniger+' less by iron skin')):''}${e.von?' · '+esc(t('von ','by ')+e.von):''}</div>`;
  if(e.art==='begegnung')return dmBegegnung(e);
  if(e.art==='angriff')return dmAngriff(e,W);
  if(e.art==='gegner')return `<div class="dm-sys ${e.was==='besiegt'?'ok':'mut'}">${e.was==='besiegt'?'✝':'🏃'} ${esc({besiegt:t(e.gegner+' ist besiegt.',e.gegner+' is defeated.'),geflohen:t(e.gegner+' flieht.',e.gegner+' flees.'),aufgegeben:t(e.gegner+' gibt auf und läuft davon.',e.gegner+' gives up and runs off.')}[e.was]||e.gegner)}</div>`;
  if(e.art==='kampf')return `<div class="dm-akt">⚔ ${esc({sieg:t('Der Kampf ist gewonnen.','The fight is won.'),frieden:t('Der Kampf endet ohne Sieger.','The fight ends without a winner.'),flucht:t('Die Gruppe entkommt.','The group gets away.')}[e.was]||'')} <small class="mut">${esc(t(e.besiegt+' besiegt, '+e.geflohen+' geflohen',e.besiegt+' defeated, '+e.geflohen+' fled'))}${e.ep?' · +'+e.ep+' '+esc(t('EP für jeden','XP each')):''}</small></div>`;
  if(e.art==='zustand')return `<div class="dm-zstz" data-z="${esc(e.was)}">${{boden:'⚠',auf:'✚',ohnmacht:'💤',tot:'✝'}[e.was]||''} ${esc(e.was==='boden'?t(e.name+' liegt am Boden. Noch '+e.noch+(e.noch===1?' Zug':' Züge')+' ohne Heilung.',e.name+' is down. '+e.noch+(e.noch===1?' turn':' turns')+' left without healing.')
    :e.was==='auf'?t(e.name+' steht wieder auf.',e.name+' is back on their feet.'):e.was==='ohnmacht'?t(e.name+' ist ohnmächtig und wacht im nächsten Kapitel auf.',e.name+' is unconscious and wakes in the next chapter.')
    :t(e.name+' ist gefallen.'+(e.dinge||e.gold?' Was er trug, liegt hier.':''),e.name+' has fallen.'+(e.dinge||e.gold?' What they carried lies here.':'')))}</div>`;
  if(e.art==='kraft')return `<div class="dm-zauber">🛡 ${esc(t(e.name+' fängt mit '+e.kraft+' den Treffer für '+e.fuer+' ab.',e.name+' takes the hit for '+e.fuer+' with '+e.kraft+'.'))}</div>`;
  if(e.art==='beute')return `<div class="dm-beute"><div class="dm-n">${esc(t('Beute für ','Loot for '))}${esc(e.name)}</div>${dmItem(e.item)}${e.boden?`<small class="mut">${esc(t('Zu schwer oder kein Platz: liegt hier am Boden.','Too heavy or no room: lies here on the ground.'))}</small>`:''}${e.gold?`<small class="mut">${esc(t('Gold für jeden: ','Gold for everyone: '))}${e.gold}</small>`:''}</div>`;
  if(e.art==='markt')return `<div class="dm-akt">⚖ ${esc(e.name)} ${esc(e.auf?t('bietet hier Waren an.','offers goods here.'):t('zieht weiter.','moves on.'))}</div>`;
  if(e.art==='handel'){const w={kauf:t('kauft','buys'),verkauf:t('verkauft','sells'),erkannt:t('erkennt','identifies')}[e.was]||e.was;return `<div class="dm-sys mut">⚖ ${esc(e.name)} ${esc(w)} <b>${esc(e.ding)}</b>${e.gold?' · '+e.gold+' '+esc(t('Gold','gold')):''}</div>`}
  if(e.art==='zauber')return `<div class="dm-zauber">✦ ${esc(e.name)} ${esc(t('wirkt','casts'))} <b>${esc(e.zauber)}</b>${e.gruppe?' '+esc(t('auf die Gruppe','on the group')):''}: ${esc(e.satz)}</div>`;
  if(e.art==='ooc')return `<div class="dm-ooc">(OOC: ${esc(e.text)})</div>`;
  if(e.art==='bild')return !(v.bilder||[]).some(x=>x.b===e.b)?'':e.b===dmNewest(v)?dmBildGross(v.mode,v,e.b,e.ort):`<div class="dm-bildk">${dmImg(v.mode,v,'b',e.b)}${e.ort?`<small class="mut">🖼 ${esc(e.ort)}</small>`:''}</div>`;
  if(e.art==='akt')return `<div class="dm-akt">❖ ${esc(sys||'')}</div>`;
  if(e.art==='ep')return `<div class="dm-sys mut">${esc(e.name)} +${e.zahl} EP${e.ende?' · '+esc(t('am Ende der Runde gutgeschrieben','credited at the end of the round')):e.tisch?' · '+esc(t('noch am Tisch, zählt am Ende der Runde','still at the table, counts at the end of the round')):''}</div>`;
  if(e.art==='stufe')return `<div class="dm-stufe">★ ${esc(e.name)} ${esc(t('erreicht Stufe','reaches level'))} ${e.stufe}!</div>`;
  return `<div class="dm-sys mut">${esc(sys||'')}</div>`}
// what can be done with an item in the own bag (side column, hero sheet, item window)
function dmActs(v,it){const h=v.ich,others=v.plaetze.filter(p=>!p.frei&&!p.ich);
  const give=it=>others.length?`<select data-dmgive="${esc(it.i)}" aria-label="${esc(t('Geben an','Give to'))}"><option value="">${esc(t('Geben …','Give …'))}</option>${others.map(p=>`<option value="${esc(p.pid)}">${esc(p.name)}</option>`).join('')}</select>`:'';
  const m=v.markt,rolle=h.tasche.find(x=>x.erkennt),open=v.status!=='ende';
  const know=it=>it.u?(rolle&&rolle.i!==it.i?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}" data-mit="${esc(rolle.i)}">${esc(t('Mit Rolle erkennen','Identify with scroll'))}</button>`:'')+(m&&m.erkennen[it.i]?`<button type="button" class="b" data-dmhero="erkennen" data-i="${esc(it.i)}"${h.gold<m.erkennen[it.i]?' disabled':''}>${esc(t('Erkennen lassen','Have it named'))} · ${m.erkennen[it.i]} ${esc(t('Gold','gold'))}</button>`:''):'';
  return open?`<div class="dm-iacts">${it.platz.length&&it.n===1?`<button type="button" class="b" data-dmhero="anlegen" data-i="${esc(it.i)}">${esc(t('Anlegen','Equip'))}</button>`:''}${it.art==='trank'?`<button type="button" class="b" data-dmhero="trinken" data-i="${esc(it.i)}">${esc(t('Trinken','Drink'))}</button>`:''}${it.art==='zauber'?`<button type="button" class="b" data-dmhero="wirken" data-i="${esc(it.i)}">${esc(t('Wirken','Cast'))}</button>`:''}${know(it)}${m&&m.verkauf[it.i]?`<button type="button" class="b" data-dmhero="verkaufen" data-i="${esc(it.i)}">${esc(t('Verkaufen','Sell'))} · ${m.verkauf[it.i]} ${esc(t('Gold','gold'))}</button>`:''}${give(it)}<button type="button" class="b" data-dmhero="fallen" data-i="${esc(it.i)}" title="${esc(t('Hier ablegen, die Gruppe kann es aufheben','Put it down here, the group can pick it up'))}">${esc(t('Hinlegen','Put down'))}</button></div>`:''}
// the hero sheet (Dominik 2026-10-24 „alles“): the portrait large, the values as tiles, below one tab open at a time
// (Ausrüstung, Das kann ich, Tasche, Werte verteilen), the last one kept on this device
const DMBT={t:null},DMBTABS=['aus','kann','tasche','werte'];
function dmBTab(){if(DMBT.t===null){try{DMBT.t=localStorage.getItem('dm-bogen')||''}catch(e){DMBT.t=''}}return DMBTABS.includes(DMBT.t)?DMBT.t:'aus'}
document.body.addEventListener('click',e=>{const b=e.target.closest('.dm [data-dmbt]');if(!b)return;DMBT.t=b.dataset.dmbt;try{localStorage.setItem('dm-bogen',DMBT.t)}catch(x){}
  if(!b.dataset.dmfen)(b.closest('#dgcard')?dgDraw():dmDraw())});
function dmMe(v,mode){const h=v.ich;if(!h)return '';
  const open=v.status!=='ende',acts=it=>dmActs(v,it),tab=dmBTab(),kn=h.kann?h.kann.faehigkeiten.length+h.kann.zauber.length:0,offen=h.punkte||h.wahl.length;
  const slot={kopf:t('Kopf','Head'),hals:t('Hals','Neck'),koerper:t('Körper','Body'),haupthand:t('Haupthand','Main hand'),nebenhand:t('Nebenhand','Off hand'),haende:t('Hände','Hands'),fuesse:t('Füße','Feet'),ring1:t('Ring','Ring'),ring2:t('Ring','Ring')};
  const zwei=h.an.haupthand&&h.an.haupthand.zweihand,kg=x=>String(x).replace('.',L==='en'?'.':',');
  const doll=['hals','kopf','ring1','haupthand','koerper','nebenhand','haende','fuesse','ring2'].map(k=>{const it=h.an[k];
    return `<div class="dm-pl${it?' voll '+(DMSEL[it.selten]||''):''}" data-dmslot="${k}"${it?` draggable="true" data-dmdrag="${esc(k)}" title="${esc([it.name,...it.zeilen].join(' · '))}"`:''}><small>${esc(slot[k])}</small>${it?`${dmDing(it)}<b>${esc(it.u?it.name.replace(/ \(.*\)$/,'')+' ?':it.name)}</b>${open?`<button type="button" class="ic-ib" data-dmhero="ablegen" data-platz="${k}" title="${esc(t('Ablegen','Unequip'))}" aria-label="${esc(t('Ablegen','Unequip')+': '+it.name)}">×</button>`:''}`:k==='nebenhand'&&zwei?`<i>${esc(t('beide Hände','both hands'))}</i>`:'<i>–</i>'}</div>`}).join('');
  const bag=`<h5>${esc(t('Tasche','Bag'))} · ${h.tasche.length}/${h.tasche_max} · ${kg(h.kg)} / ${kg(h.trag)} kg${h.belastet?` <span class="pill warn">${esc(t('belastet: Geschick mit Nachteil','burdened: Dexterity at disadvantage'))}</span>`:''}</h5>${dmBar(h.kg,h.trag,h.belastet?'low':'')}
    <div class="dm-bag" data-dmbag="1">${h.tasche.map(it=>`<div class="dm-drag"${open&&it.platz.length&&it.n===1?` draggable="true" data-dmdrag="${esc(it.i)}"`:''}>${dmItem(it,acts(it))}</div>`).join('')||`<small class="mut">${esc(t('leer','empty'))}</small>`}</div>`;
  const ground=((v.boden||[]).length||v.boden_gold)&&open?`<h5>${esc(t('Liegt hier','Lying here'))}</h5>${v.boden_gold?`<div class="dm-line dm-bgold"><span>💰 ${v.boden_gold} ${esc(t('Gold','gold'))}</span><button type="button" class="b" data-dmhero="aufheben" data-i="gold">${esc(t('Aufheben','Pick up'))}</button></div>`:''}${(v.boden||[]).map(it=>dmItem(it,`<div class="dm-iacts"><button type="button" class="b" data-dmhero="aufheben" data-i="${esc(it.i)}">${esc(t('Aufheben','Pick up'))}</button></div>`)).join('')}`:'';
  const paint=v.portraet_malt?`<small class="mut">🖼 ${esc(v.portraet_hint||t('Dein Porträt wird gemalt …','Your portrait is being painted …'))}</small>`
    :v.bilder_an&&h.bild_neu&&open?`<button type="button" class="b" data-dmportraet="1" title="${esc(t('Einmal je Stufe, aus Volk, Klasse und deinem Satz.','Once per level, from people, class and your sentence.'))}">${esc(h.bild?t('🖼 Neu malen','🖼 Paint again'):t('🖼 Porträt malen lassen','🖼 Have a portrait painted'))}</button>`:'';
  const port=`<div class="dm-bport"><span class="dm-pbig">${h.bild?dmImg(mode,v,'p',v.pid,h.stufe):dmPic('',h.name,'gross')}</span>${paint}</div>`;
  const tiles=`<div class="dm-wk">${h.werte.map(x=>dmErkBtn(mode,'b:w:'+x.id,`<small>${esc(x.kurz)}</small><b>${x.wert}</b>${dmBo(x.gesamt)}`,x.name)).join('')}</div>`;
  const tb=[['aus','⚔ '+t('Ausrüstung','Equipment')],['kann','✨ '+t('Das kann ich','What I can do')+(kn?' · '+kn:'')],['tasche','🎒 '+t('Tasche','Bag')+' · '+h.tasche.length],['werte','⭐ '+t('Werte verteilen','Spend points')+(offen?' •':'')]];
  const werte=`${h.punkte?`<div class="dm-hint">${esc(t('Neue Stufe: verteile '+h.punkte+' Wertpunkt'+(h.punkte>1?'e':'')+'.','New level: spend '+h.punkte+' value point'+(h.punkte>1?'s':'')+'.'))}</div>
      <div class="dm-werte">${h.werte.map(x=>`<span>${esc(x.kurz)} <b>${x.wert}</b>${x.wert<h.wert_max?`<button type="button" class="b dm-plus" data-dmhero="punkt" data-wert="${esc(x.id)}" title="${esc(t('Wertpunkt hierhin','Value point here'))}">+1</button>`:''}</span>`).join('')}</div>`:''}
    ${h.wahl.length?`<div class="dm-hint">${esc(t('Neue Fähigkeit wählen:','Pick a new ability:'))}</div>${h.wahl.map(f=>`<button type="button" class="b dm-fa" data-dmhero="faehigkeit" data-id="${esc(f.id)}"><b>${esc(f.name)}</b><small>${dmFx(f.satz)}</small></button>`).join('')}`:''}
    ${offen?'':`<small class="mut">${esc(t('Gerade nichts zu verteilen. Jede neue Stufe bringt einen Wertpunkt, manche eine neue Fähigkeit.','Nothing to spend right now. Every new level brings a value point, some a new ability.'))}</small>`}
    ${(v.stimmen||[]).length?`<div class="dm-voice"><label>${esc(t('Stimme deines Helden','Your hero\'s voice'))}</label><div class="dm-inp"><select data-dmvoice="1" aria-label="${esc(t('Stimme deines Helden','Your hero\'s voice'))}"><option value="">${esc(t('Keine, nur der Erzähler','None, only the narrator'))}</option>${[...new Set([h.stimme,...v.stimmen].filter(Boolean))].map(x=>`<option${x===h.stimme?' selected':''}>${esc(x)}</option>`).join('')}</select><button type="button" class="b" data-dmprobe="1"${h.stimme||h.klang?'':' disabled'}>${esc('▶ '+t('Probe','Sample'))}</button></div>${v.stimme_design?`<input class="dm-klang" data-dmvoice="1" maxlength="80" value="${esc(h.klang||'')}" placeholder="${esc(t('oder beschreiben: tiefe, raue Zwergenstimme','or describe it: deep, rough dwarf voice'))}" aria-label="${esc(t('Stimme beschreiben','Describe the voice'))}">`:''}<small class="mut">${esc(t('Ist Vorlesen an, spricht diese Stimme, was dein Held in Anführungszeichen sagt: „Halt, wer da?“','When reading aloud is on, this voice speaks what your hero says in quotes: "Halt, who goes there?"'))}</small></div>`:''}
    ${mode==='g'?`<div class="dm-figur"><button type="button" class="b" data-dmfigur="1">${esc(t('Figur-Code holen','Get a hero code'))}</button>${DG.figur?`<input readonly value="${esc(DG.figur)}" aria-label="${esc(t('Figur-Code','Hero code'))}"><small class="mut">${esc(t('Nur einmal zu sehen. Damit nimmst du deinen Helden in eine andere Runde mit (30 Tage, einmal).','Shown once. Take your hero into another round with it (30 days, once).'))}</small>`:''}</div>`:''}`;
  const body=tab==='kann'?dmKann(h):tab==='tasche'?bag+dmTrade(v,mode):tab==='werte'?werte:`<div class="dm-doll">${doll}</div>${ground}`;
  return `<div class="dm-me dm-bogen">${port}<div class="dm-bkopf"><h4>${esc(h.name)} <small class="mut">${esc(h.volk)} · ${esc(h.klasse)} · ${esc(t('Stufe','Level'))} ${h.stufe}</small></h4>${h.satz?`<small class="mut">${esc(h.satz)}</small>`:''}
    ${dmErkBtn(mode,'b:leben',`<span class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${h.leben} / ${h.leben_max}</span></span>${dmBar(h.leben,h.leben_max,h.leben*3<h.leben_max?'low':'')}`,t('Leben erklären','Explain life'))}
    ${dmErkBtn(mode,'b:stufe',`<span class="dm-line"><span>${esc(t('Erfahrung','Experience'))}</span><span>${h.ep}${h.ep_naechste?' / '+h.ep_naechste:''} EP</span></span>${h.ep_naechste?dmBar(h.ep,h.ep_naechste,'ep'):''}${h.ep_tisch?`<small class="dm-eptisch">+${h.ep_tisch} ${esc(t('EP noch am Tisch: zählen am Ende der Runde','EP still at the table: they count at the end of the round'))}</small>`:''}`,t('Stufe erklären','Explain level'))}
    ${tiles}<div class="dm-line dm-bsum"><span>${dmErkBtn(mode,'b:rk',`${esc(t('Rüstungsklasse','Armour class'))} <b>${h.rk}</b>`,t('Rüstungsklasse','Armour class'))} · ${dmErkBtn(mode,'b:gold',`${esc(t('Gold','Gold'))} <b>${h.gold}</b>`,t('Gold','Gold'))}</span><span class="mut">${esc(t('Tasche','Bag'))} ${h.tasche.length}/${h.tasche_max} · ${kg(h.kg)} kg</span></div>
    ${dmErkBox(mode,'b:',{...Object.fromEntries(Object.entries(dmErkFix()).map(([k,x])=>[k,esc(x)])),...Object.fromEntries(h.werte.map(x=>['w:'+x.id,dmErkWert(x,x.gesamt)]))})}
    ${(h.segen||[]).length?`<div class="dm-segen">${h.segen.map(x=>`<span class="pill ok">${esc(x.wert)} ${dmBo(x.bonus)} · ${esc(x.zuege===1?t('noch 1 Zug','1 turn left'):t('noch '+x.zuege+' Züge',x.zuege+' turns left'))}${x.name?' · '+esc(x.name):''}</span>`).join(' ')}</div>`:''}</div>
    <div class="dm-btabs lseg" role="tablist">${tb.map(([k,l])=>`<button type="button" role="tab" class="${k===tab?'on':''}" aria-selected="${k===tab}" data-dmbt="${k}">${esc(l)}</button>`).join('')}</div>
    <div class="dm-btab dm-btab-${tab}" role="tabpanel">${body}</div></div>`}
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
function dmCr(s){return {0.125:'⅛',0.25:'¼',0.5:'½'}[s]||String(s)}
function dmFoe(g){return `<div class="dm-foe">${dmDing(g)}<div><span><b>${esc(g.name)}</b>${g.anzahl>1?` <span class="pill">×${g.anzahl}</span>`:''}</span><small class="dm-iinfo">${esc(g.info||'')}</small>
  <small class="dm-fwerte" title="${esc(t('Die Stufe ist der Herausforderungsgrad aus dem Bestiarium (¼ ist ein leichter Gegner für Stufe 1).','The level is the challenge rating of the bestiary (¼ is an easy foe for level 1).'))}">${esc(t('Stufe','Level'))} ${dmCr(g.stufe)} · ${esc(t('Leben','Life'))} ${g.leben} · ${esc(t('RK','AC'))} ${g.rk} · ${esc(t('Angriff','Attack'))} ${g.angriff>=0?'+':''}${g.angriff} · ${esc(t('Schaden','Damage'))} ${esc(g.schaden)} · ${g.ep} ${esc(t('EP','XP'))}</small></div></div>`}
function dmBegegnung(e){return `<div class="dm-beg"><div class="dm-n">⚔ ${esc(t('Begegnung','Encounter'))} <span class="pill" data-gefahr="${esc(e.gefahr)}">${esc(DMGEF()[e.gefahr]||e.gefahr)}</span></div>${(e.gegner||[]).map(dmFoe).join('')}</div>`}
function dmAngriff(e,W){const res=e.treffer?`<b>${esc(e.krit?t('Kritischer Treffer!','Critical hit!'):t('Treffer','Hit'))}</b> −${e.schaden} ${esc(t('Leben','life'))}`:`<b>${esc(t('daneben','miss'))}</b>`;
  return e.von_gegner?`<div class="dm-wurf dm-gzug ${e.treffer?'bad':'ok'}"><span class="dm-d20">${e.w}</span>${esc(e.gegner)} → ${esc(e.name)} · ${dmBo(e.bonus)} = <b>${e.gesamt}</b> ${esc(t('gegen RK','vs AC'))} ${e.rk} · ${res}</div>`
    :`<div class="dm-wurf ${e.treffer?'ok':'bad'}"><span class="dm-d20">${e.w}</span>${dmVt(e)}${esc(e.name)} → ${esc(e.gegner)}${e.mit?' · '+esc(e.mit):''} · ${esc(W[e.wert]||e.wert)} ${dmBo(e.bonus)} = <b>${e.gesamt}</b> ${esc(t('gegen RK','vs AC'))} ${e.rk} · ${res}</div>`}
function dmKampf(v){const k=v.kampf;if(!k)return '';
  return `<div class="dm-kampf" role="status"><div class="dm-n">⚔ ${esc(t('Kampf','Fight'))} <span class="pill" data-gefahr="${esc(k.gefahr)}">${esc(DMGEF()[k.gefahr]||k.gefahr)}</span> <small class="mut">${esc(t(k.stehen+' stehen noch',k.stehen+' still standing'))}</small></div>
    <div class="dm-kgs">${k.gegner.map(g=>`<div class="dm-kg${g.aus?' aus':''}">${dmDing(g)}<div><b>${esc(g.name)}</b>${g.aus?`<small class="mut">${esc(g.aus==='besiegt'?t('besiegt','defeated'):t('geflohen','fled'))}</small>`:`<span class="dm-line"><span></span><span>${g.leben} / ${g.max}</span></span>${dmBar(g.leben,g.max,g.leben*3<g.max?'low':'')}`}</div></div>`).join('')}</div></div>`}
function dmTable(w,v,mode){const fen=dmFenKeep(w),tk=dmTalkKeep(w),keep=w.querySelector('.dm-in'),kv=keep?keep.value:'',kf=!!keep&&document.activeElement===keep;
  const st=v.status==='ende'?t('beendet','ended'):v.dm?t('der Dungeon-Master erzählt …','the Dungeon Master is narrating …'):v.pause?t('Pause','paused'):'';
  const done=v.plaetze.filter(p=>!p.frei&&p.gehandelt).length,all=v.plaetze.filter(p=>!p.frei).length;
  const seats=v.plaetze.filter(p=>!p.frei),col=pid=>Math.max(0,seats.findIndex(p=>p.pid===pid))%5;
  const group=v.plaetze.map(p=>p.frei?`<div class="dm-seat free"><span class="dm-av">+</span><div><b>${esc(t('Platz frei','Free seat'))}</b><small class="mut">${esc(t('Link verschickt ','Link sent '))}${esc(dmWhen(p.made))}</small></div><button type="button" class="b" data-dmseatdel="${esc(p.pid)}">${esc(t('Zurücknehmen','Take back'))}</button></div>`
    :p.ich&&v.ich?`<div class="dm-seat dm-hero me dm-ichz">${dmAv(mode,v,p,col(p.pid))}<div><b>${esc(p.name)}</b> <small class="mut">${esc(t('du','you'))} · ${p.leben}/${p.leben_max}</small>${dmZust(p)}</div><small class="dm-state ${p.gehandelt?'ok':''}">${esc(p.gehandelt?t('hat gehandelt','acted'):t('denkt nach','thinking'))}</small></div>`
    :`<div class="dm-seat dm-hero${p.ich?' me':''}"><div class="dm-hhead">${dmAv(mode,v,p,col(p.pid))}<div><b>${esc(p.name)}</b> <i>${esc(p.volk)} ${esc(p.klasse)}</i><small class="mut">${dmErkBtn(mode,`s:${p.pid}:stufe`,esc(t('Stufe','Level'))+' '+p.stufe,t('Stufe erklären','Explain level'))}${p.gastgeber?' · '+esc(t('leitet','hosts')):p.gast?' · '+esc(t('Gast','guest')):''}</small>${dmZust(p)}</div>${mode==='p'&&v.gastgeber&&!p.gastgeber?dmSeatMenu(p):''}</div>${dmHelfen(v,p)}
      ${dmErkBtn(mode,`s:${p.pid}:leben`,`<span class="dm-line"><span>${esc(t('Leben','Life'))}</span><span>${p.leben} / ${p.leben_max}</span></span>${dmBar(p.leben,p.leben_max,p.leben*3<p.leben_max?'low':'')}`,t('Leben erklären','Explain life'))}
      ${p.karte?`<div class="dm-stats">${p.karte.werte.map(x=>dmErkBtn(mode,`s:${p.pid}:w:${x.kurz}`,`<small>${esc(x.kurz)}</small><b>${x.wert}</b><i>${dmBo(x.mod)}</i>`,x.name)).join('')}${dmErkBtn(mode,`s:${p.pid}:rk`,`<small>${esc(t('RK','AC'))}</small><b>${p.karte.rk}</b>`,t('Rüstungsklasse','Armour class'))}</div>
      ${p.karte.dinge.length?`<div class="dm-pills">${p.karte.dinge.map(d=>`<button type="button" class="dm-erkb dm-sding" data-dmsding="${esc(p.pid)}|${esc(d.platz)}" aria-label="${esc(d.name)}">${esc(d.name)}</button>`).join('')}</div>`:''}`:''}${dmErkBox(mode,`s:${p.pid}:`,dmErkSeat(p))}
      <small class="dm-state ${p.gehandelt?'ok':p.online?'':'away'}">${esc(p.gehandelt?t('hat gehandelt','acted'):p.online?t('denkt nach','thinking'):t('nicht da','away'))}</small></div>`).join('');
  const sc=v.szene&&(v.szene.ort||v.szene.stimmung)?`<div class="dm-scene"><i>${esc(t('Ort:','Place:'))}</i> ${esc([v.szene.ort,v.szene.stimmung].filter(Boolean).join(' · '))}</div>`:'';
  const wait=seats.filter(p=>!p.gehandelt&&!p.ruht&&!p.zustand&&!(p.ich&&v.meine_aktion)).map(p=>p.name);   // the own seat never waits once it acted
  const S=mode==='p'?DM:DG,sid=mode==='p'?'dmsend':'dgsend';
  // after „Handeln“ (Dominik 2026-10-24 „beim click auf handeln passiert nichts weiter“): the own action stands as a card with
  // ✓, who is still missing and „Ändern“; the field comes back on „Ändern“ or with the next turn
  const mine=!!v.meine_aktion&&!v.dm&&DMA.aendern[mode]!==v.zug,u=dmUhr(v,S);
  const plus=v.mehr_ich&&v.status==='laeuft'&&v.ich?`<button type="button" class="b dm-plus1" data-dmmehr="1">${esc(t('+1 Minute','+1 minute'))}</button>`:'';
  const uhr=v.dm||v.status==='ende'?'':`<div class="dm-zeitz"><small class="mut dm-left${u.warn?' dm-warn':''}">${esc(u.text)}</small>${plus}</div>`;
  const input=v.status==='ende'||!v.ich?'':v.ich.zustand?`<div class="dm-hint dm-zsatz" data-z="${esc(v.ich.zustand)}">${esc(dmZustSatz(v.ich))}</div>`:mine?dmMine(v,wait,S,plus):`${uhr}${wait.length&&!v.dm?`<small class="dm-wait">${esc(t('Warten auf: ','Waiting for: '))}<b>${esc(wait.join(', '))}</b></small>`:''}${dmTyping(v)}<div class="dm-inp"><textarea class="dm-in" rows="1" data-zeilen="4" data-senden="${sid}" maxlength="${v.text_max}" placeholder="${esc(t('Was macht ','What does ')+v.ich.name+t('? ',' do? '))}" aria-label="${esc(t('Deine Aktion','Your action'))}"${v.dm?' disabled':''}></textarea><button type="button" class="b dm-mic${DMA.rec&&DMA.mode===mode?' on':''}" data-dmmic="1" title="${esc(t('Sprechen statt tippen','Speak instead of typing'))}" aria-label="${esc(t('Sprechen statt tippen','Speak instead of typing'))}"${v.dm?' disabled':''}>${DMA.rec&&DMA.mode===mode?'● '+esc(t('Fertig','Done')):'🎤'}</button><button type="button" class="b p" id="${sid}" data-dmsend="1"${v.dm?' disabled':''}>${esc(t('Handeln','Act'))}</button></div>${dmMsg(S)}`;
  // the host's tab „Leiten“ (Dominik 2026-10-24 „wirkt unruhig“, „alles“): one main action, four tiles of the same
  // size with their state, invite and narrator voice as quiet rows, the rare ones behind „⋯ Mehr“
  const tile=(attr,ic,name,sub,on,off)=>`<button type="button" class="dm-tile${on?' on':''}" ${attr}${off?` disabled title="${esc(off)}"`:''}><span aria-hidden="true">${ic}</span><span><b>${esc(name)}</b><small>${esc(sub)}</small></span></button>`;
  const frei=v.max-all-v.plaetze.filter(p=>p.frei).length,erz=(v.erzaehler_liste||[]).find(x=>x.k===v.erzaehler_k),erzw=dmErzWahl(v);
  const host=mode==='p'&&v.gastgeber&&v.status!=='ende'?`<button type="button" class="dm-go" data-dmweiter="1"${done&&!v.dm?'':' disabled'}>▶ ${esc(t('Jetzt weiter','Go on now'))}${wait.length&&!v.dm?` <small>· ${esc(t('wartet auf '+wait.length,'waiting for '+wait.length))}</small>`:''}</button>
    <div class="dm-tiles">${tile(`data-dmpause="${v.pause?0:1}"`,v.pause?'▶':'⏸',v.pause?t('Weiter','Resume'):t('Pause','Pause'),v.pause?t('Zeit läuft wieder','time runs again'):t('Zeit anhalten','stop the clock'),v.pause)}${tile(`data-dmmarkt="${v.markt?0:1}"`,'⚖',t('Markt','Market'),v.markt?t('offen · schließen','open · close'):t('öffnen','open'),!!v.markt)}${tile(`data-dmvorlesen="${v.vorlesen?0:1}"`,'🔊',t('Vorlesen','Read aloud'),v.vorlesen?t('an','on'):t('aus','off'),v.vorlesen)}${v.bilder_an?tile('data-dmbild="1"','🖼',t('Szenenbild','Scene picture'),t('jetzt malen','paint now'),false,v.bild_grund):''}</div>
    ${frei>0?`<button type="button" class="dm-zeile" data-dminvite="1"><span>＋ ${esc(t('Einladen','Invite'))}</span><small>${esc(frei===1?t('1 Platz frei','1 seat free'):t(frei+' Plätze frei',frei+' seats free'))} ›</small></button>`:''}
    <label class="dm-zeile"><span>📜 ${esc(t('Erzählweise','Way of telling'))}</span>${dmWeise('',v.erzaehlweise||'normal','data-dmweise="1"')}</label>
    ${erzw?`<details class="dm-zeile-d" data-dmauf="erz"${DMA.auf==='erz'?' open':''}><summary class="dm-zeile"><span>🎙 ${esc(t('Stimme des Erzählers','Narrator\'s voice'))}</span><small>${esc(erz?erz.name:'')} ›</small></summary>${erzw}</details>`:''}
    <details class="dm-mehr" data-dmauf="mehr"${DMA.auf==='mehr'||DM.kap||DM.ende?' open':''}><summary>⋯ ${esc(t('Mehr','More'))}</summary><div class="dm-hostb"><button type="button" class="b" data-dmkap="1">${esc(DM.kap?t('Kapitel wirklich beenden?','Really end the chapter?'):t('Kapitel beenden','End chapter'))}</button><button type="button" class="b danger" data-dmend="1">${esc(DM.ende?t('Wirklich beenden?','Really end?'):t('Runde beenden','End round'))}</button></div></details>${v.bilder_an&&v.bild_grund&&!v.bild_malt?`<small class="mut dm-bgrund">🖼 ${esc(v.bild_grund)}</small>`:''}${dmPlanHost(v)}${dmTruth(v)}${dmThings(v)}
    ${DM.made?`<div class="mitmade"><div class="jqr">${DM.made.qr||''}</div><div class="sp"><input readonly value="${esc(DM.made.link)}" aria-label="${esc(t('Der Link','The link'))}"><small class="mut">${esc(t('Nur jetzt zu sehen. Wer ihn öffnet, sitzt auf diesem Platz: als Gast ohne Profil oder mit seinem Profil.','Shown only now. Whoever opens it takes this seat: as a guest without a profile or with their profile.'))}</small></div></div>`:''}`:'';
  v.mode=mode;const log=v.log.map(e=>dmLog(v,e,col)).join('');
  dmLook(w,v.farben);w.classList.toggle('dm-voll',DMA.voll);w.dataset.welt=v.welt_id||'';
  w.innerHTML=`<div class="dm-head">${mode==='p'?`<button type="button" class="b" data-dmback="1">${esc(t('← Runden','← Rounds'))}</button>`:''}<div class="dm-htitle"><h3>${esc(v.titel)}</h3>${sc}<small class="mut">${esc(v.welt)} · ${esc(v.ton)}${v.kapitel?' · '+esc(t('Kapitel','Chapter'))+' '+v.kapitel:''}${v.akte?' · '+esc(v.erzaehlt?t('Geschichte erzählt','story told'):t('Akt','Act')+' '+v.akt+'/'+v.akte):''} · ${esc(t('Zug','Turn'))} ${v.zug}${st?' · '+esc(st):''}</small></div>${dmLesKnopf(v,mode)}${v.ich?`<button type="button" class="b dm-help" data-dmhilfe="${DMA.hilfe===false?0:'zu'}">${esc('❔ '+t('So spielst du','How to play'))}</button>`:''}${dmModus()}<button type="button" class="b dm-full" data-dmvoll="${DMA.voll?0:1}">${esc(DMA.voll?'✕ '+t('Vollbild aus','Exit full screen'):'⛶ '+t('Vollbild','Full screen'))}</button></div>
    ${v.ich?dmHilfe():''}<div class="dm-grid" data-dmpane="${DMA.handy}"><div class="dm-col dm-group"><h5>${esc(t('Gruppe','Group'))} · ${all}/${v.max}</h5>${group}</div>
    <div class="dm-col dm-story">${dmBack(v)}${dmKampf(v)}<div class="dm-feed" aria-live="polite">${dmScene(v,mode)}${log}${dmMalt(v)}${dmWait(v)}</div>${input}${dmTalk(v,mode)}</div>
    <div class="dm-col dm-side">${dmAuftrag(v)}${dmMeKurz(v,mode)}${dmSeite(v,mode,host)}</div></div>${input?'':dmMsg(S)}${dmUnten(v,mode)}${dmFenster(v,mode)}`;
  fen();tk();
  if(mode==='g')dmImgFill(w);
  dmDingFill(w,mode);
  if(window.dmTon)dmTon(w,v,mode);   // music, sounds and the rolling d20 (dungeon-ton.js)
  dmWOthers(w,v);                    // another seat threw its die (dungeonwarten.js)
  const f=w.querySelector('.dm-feed');if(f)f.scrollTop=f.scrollHeight;
  const inp=w.querySelector('.dm-in');if(inp){if(kv)inp.value=kv;else if(DMA.aendern[mode]===v.zug&&v.meine_aktion)inp.value=v.meine_aktion;if(kf||!keep&&DMA.aendern[mode]===v.zug)inp.focus({preventScroll:true})}
  dmLeft(S);
  dmLesung(mode,v)}
// the admin's story of the round: only the host sees the plan, the players only the act's number
function dmPlanHost(v){const p=v.plan;if(!p)return '';const cur=v.erzaehlt?-1:v.akt-1;
  return `<details class="adv dm-plan"><summary>${esc(t('Geschichte: ','Story: ')+p.titel)} · ${esc(t('nur du siehst das','only you see this'))}</summary><small class="mut">${esc(t('Ziel: ','Goal: ')+p.ziel)}${p.gegner?' · '+esc(t('Gegenspieler: ','Foe: ')+p.gegner):''}</small>
    <ol>${p.akte.map((a,i)=>`<li class="${i===cur?'on':i<cur||cur<0?'mut':''}"><b>${esc(a.titel)}</b> <small>${esc(a.inhalt)}</small><small class="mut">${esc(t('Wendepunkt: ','Turning point: ')+a.wende)} · ${a.zuege} ${esc(t('Züge','turns'))}</small></li>`).join('')}</ol>
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
  const main=!hier?'':!A.frei?`<button type="button" class="b dm-hear dm-tonan" data-dmhear="frei">${esc(t('🔊 Ton an','🔊 Sound on'))}</button>`
    :A.laeuft||v.liest?`<button type="button" class="b dm-hear" data-dmhear="stopp">${esc(t('⏹ Vorlesen stoppen','⏹ Stop reading'))}</button>`
    :`<button type="button" class="b dm-hear" data-dmhear="nochmal"${v.lesung?'':' disabled'}>${esc(t('🔊 Nochmal hören','🔊 Listen again'))}</button>`;
  return `${main}<button type="button" class="ic-ib dm-tonhier" data-dmhear="${hier?'aus':'an'}" aria-pressed="${hier}" title="${esc(hier?t('Auf diesem Gerät nicht vorlesen','Do not read aloud on this device'):t('Auf diesem Gerät vorlesen','Read aloud on this device'))}" aria-label="${esc(hier?t('Auf diesem Gerät nicht vorlesen','Do not read aloud on this device'):t('Auf diesem Gerät vorlesen','Read aloud on this device'))}">${hier?'🔈':'🔇'}</button>`}
function dmLesung(mode,v){const A=DMLES[mode],T=v.lesung;if(!T)return;
  if(A.n===null){A.n=T.n;A.k=T.k;return}
  if(T.n!==A.n){A.n=T.n;A.k=0}
  dmLesWeiter(mode)}
// the tap unlocks the player: only a refusal of the browser (NotAllowedError) keeps it locked, any other error of the
// silent file does not (Dominik 2026-10-24 „passiert aber nichts“ after „Tippe noch einmal auf 🔊 Ton an“)
async function dmLesFrei(mode){const A=DMLES[mode];if(!A.el){A.el=new Audio();A.el.setAttribute('playsinline','')}A.el.src=dmStill();
  try{const AC=window.AudioContext||window.webkitAudioContext;if(AC){DMLES.ac=DMLES.ac||new AC();DMLES.ac.resume()}}catch(e){}
  try{await A.el.play();A.frei=true}catch(e){A.frei=!(e&&e.name==='NotAllowedError')}}
async function dmLesWeiter(mode){const A=DMLES[mode],S=mode==='p'?DM:DG,T=S.v&&S.v.lesung;
  if(!T||A.laeuft||!A.frei||!dmLesHier()||!S.v.vorlesen||T.n!==A.n||A.k>=T.k)return;
  const n=A.n,k=A.k;A.laeuft=true;let gone=true;
  try{let r;if(mode==='p')r=await api(`/api/profile/dungeon/${DM.rid}/ton/${n}/${k}`);
    else r=await /*raw: public route of a guest seat*/fetch('/api/dungeon/ton',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:DG.code,zug:n,k})});
    if(r.ok){if(A.url)URL.revokeObjectURL(A.url);A.url=URL.createObjectURL(await r.blob());A.el.src=A.url;
      await new Promise((ok,no)=>{A.el.onended=ok;A.el.onerror=ok;A.el.play().catch(no)})}}
  catch(e){if(e&&e.name==='NotAllowedError'){A.frei=false;gone=false}}      // the browser locked the sound again: a tap
  A.laeuft=false;if(gone&&A.n===n&&A.k===k)A.k=k+1;
  const now=S.v&&S.v.lesung;if(now&&A.k<now.k&&now.n===A.n)dmLesWeiter(mode);else{if(now&&!now.fertig)S.at=0;mode==='p'?dmDraw():dgDraw()}}
function dmLesStopp(mode){const A=DMLES[mode],S=mode==='p'?DM:DG;if(A.el)A.el.pause();const T=S.v&&S.v.lesung;if(T){A.n=T.n;A.k=99999}A.laeuft=false}
async function dmHear(mode,was){const A=DMLES[mode],S=mode==='p'?DM:DG,T=S.v&&S.v.lesung;
  if(was==='aus'){try{localStorage.setItem('dm-ton','0')}catch(e){}dmLesStopp(mode)}
  else if(was==='stopp')dmLesStopp(mode);
  else{if(was==='an'){try{localStorage.setItem('dm-ton','1')}catch(e){}}
    await dmLesFrei(mode);if(was==='nochmal'&&T){A.n=T.n;A.k=0}
    if(!A.frei)dmSay(S,t('Der Browser lässt den Ton gerade nicht zu. Tippe noch einmal auf „🔊 Ton an“.','The browser does not allow sound right now. Tap "🔊 Sound on" once more.'),false);
    dmLesWeiter(mode)}
  mode==='p'?dmDraw():dgDraw()}
// speak instead of type: up to 30 s, the panel's speech recognition writes it into the own field, sending stays a tap
async function dmMic(mode){const S=mode==='p'?DM:DG;
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
      if(ta&&d.text){ta.value=(ta.value.trim()?ta.value.trim()+' ':'')+d.text;ta.focus()}dmSay(S,d.text?'':t('Nichts verstanden.','Nothing understood.'),false)}
    catch(e){dmSay(S,mode==='p'?t('Das hat nicht geklappt.','That did not work.'):dgErr(e),true)}};
  rec.start();mode==='p'?dmDraw():dgDraw()}
// the open page asks every poll seconds while it is to be seen; a redraw only when something changed (typing stays)
function dmSig(v){return v?[v.zug,v.log.length,v.dm,v.pause,v.status,v.vorlesen,v.liest,v.spricht,v.lesung?[v.lesung.n,v.lesung.k,v.lesung.fertig].join():'',v.akt,v.erzaehlt,v.plaetze.map(p=>[p.pid,p.gehandelt,p.online,p.leben,p.stufe,p.zustand,p.noch].join()).join('|'),v.meine_aktion,JSON.stringify(v.ich),JSON.stringify(v.angebote||[]),JSON.stringify(v.markt||null),(v.boden||[]).map(x=>x.i).join(),v.plaetze.map(p=>(p.tasche||[]).map(x=>x.i).join()).join('|'),(v.bilder||[]).map(x=>x.b).join(),v.bild_malt,v.bild_hint,v.bild_grund,v.portraet_malt,v.portraet_hint,JSON.stringify(v.karte||null),v.plaetze.map(p=>p.bild).join(),v.termin,v.melden,JSON.stringify(v.musik||null),(v.faeden||[]).join('|'),JSON.stringify(v.auftrag||null),JSON.stringify(v.daumen||{}),JSON.stringify(v.wahrheit||null),JSON.stringify(v.dinge||null),(v.tisch||[]).length,(v.tippt||[]).join(),JSON.stringify(v.warten||null)].join('#'):''}
setInterval(async()=>{if(document.visibilityState!=='visible')return;
  if(DM.v&&$('dmview')&&$('dungeon').classList.contains('on')&&!DM.busy&&Date.now()-DM.at>=DM.v.poll*1000){const old=dmSig(DM.v);DM.at=Date.now();
    const {r,d}=await apiTry('/api/profile/dungeon/'+DM.rid);if(r.ok&&DM.v){DM.v=d;DM.at=Date.now();if(dmSig(d)!==old)dmDraw();else dmLeft(DM)}}
  else if(DM.v)dmLeft(DM);
  else if(!DM.v&&DM.data&&(DM.data.kampagnen||[]).some(k=>k.schreibt)&&$('dmview')&&Date.now()-DM.at>=3000){DM.at=Date.now();dmLoad()}
  const m=$('dgmodal');if(DG.v&&m&&m.style.display==='grid'&&!DG.busy&&Date.now()-DG.at>=DG.v.poll*1000){const old=dmSig(DG.v);DG.at=Date.now();
    try{const d=await dgPub('/api/dungeon/lage',{code:DG.code});DG.v=d;DG.at=Date.now();if(dmSig(d)!==old)dgDraw()}
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
    <div class="dm-mein-k"><button type="button" class="b" data-dmaendern="1">${esc(t('Ändern','Change'))}</button>${plus||''}</div></div>${dmMsg(S)}`}
document.body.addEventListener('click',e=>{const b=e.target.closest('#dmview [data-dmaendern],#dgcard [data-dmaendern]');if(!b)return;const g=!!b.closest('#dgcard'),v=g?DG.v:DM.v;if(!v)return;
  DMA.aendern[g?'g':'p']=v.zug;g?dgDraw():dmDraw()});
// the turn's clock (Dominik 2026-10-24 „die interaktion geht zu schnell weg“, „1-5“): first the reading time, then the
// turn's time; after the last action GNADE_S to change it; red from warn_s on, a phone vibrates once per turn
const dmMS=s=>Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
function dmUhr(v,S){const el=(Date.now()-S.at)/1000,lese=Math.max(0,Math.round(v.lesen-el)),gn=Math.max(0,Math.round(v.gnade-el));
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
const dmHeroBody2=B=>({was:B.dmhero,i:B.i,wert:B.wert,id:B.id,platz:B.platz,mit:B.mit,an:B.an});
async function dmHeroDo(mode,b){if(mode==='g'){await dgAct('/api/dungeon/held',b);return}
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/held`,b,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()}
document.body.addEventListener('dragstart',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmdrag],#dgcard [data-dmdrag]');if(!el)return;
  e.dataTransfer.setData('text/plain','dm:'+el.dataset.dmdrag);e.dataTransfer.effectAllowed='move'});
document.body.addEventListener('dragover',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmslot],#dmview [data-dmbag],#dgcard [data-dmslot],#dgcard [data-dmbag]');if(el)e.preventDefault()});
document.body.addEventListener('drop',e=>{const el=e.target.closest&&e.target.closest('#dmview [data-dmslot],#dmview [data-dmbag],#dgcard [data-dmslot],#dgcard [data-dmbag]');if(!el)return;
  const x=(e.dataTransfer.getData('text/plain')||'');if(!x.startsWith('dm:'))return;e.preventDefault();const id=x.slice(3),mode=el.closest('#dgcard')?'g':'p';
  if(el.dataset.dmslot&&id.startsWith('i'))dmHeroDo(mode,{was:'anlegen',i:id,platz:el.dataset.dmslot});
  else if(el.dataset.dmbag&&!id.startsWith('i'))dmHeroDo(mode,{was:'ablegen',platz:id})});
async function dmSend(path,b,S,x){if(S.busy)return null;S.busy=true;
  const o=x?xjson(x.method,Object.assign({lang:dmLang()},x.body||{})):b===null?{method:'DELETE'}:xjson('POST',Object.assign({lang:dmLang()},b||{}));const {r,d}=await apiTry(path,o);S.busy=false;
  if(!r.ok){dmSay(S,dmErr(r.status,d.detail),true);return null}S.msg='';S.err=false;return d}
// ---------------------------------------------------------------- clicks of the own page
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmopen],#dmview [data-dmback],#dmview [data-dmmake],#dmview [data-dmseg],#dmview [data-dmgs],#dmview [data-dmsend],#dmview [data-dmhero],#dmview [data-dmweiter],#dmview [data-dmpause],#dmview [data-dmmarkt],#dmview [data-dminvite],#dmview [data-dmsitz],#dmview [data-dmseatdel],#dmview [data-dmend],#dmview [data-dmdelhero],#dmview [data-dmwipe],#dmview [data-dmtx],#dmview [data-dmvorlesen],#dmview [data-dmkap],#dmview [data-dmhear],#dmview [data-dmvoll],#dmview [data-dmhilfe],#dmview [data-dmprobe],#dmview [data-dmerzprobe],#dmview [data-dmerzneu],#dmview [data-dmmic],#dmview [data-dmkweiter],#dmview [data-dmkedit],#dmview [data-dmksave],#dmview [data-dmkneu],#dmview [data-dmkdel],#dmview [data-dmbild],#dmview [data-dmportraet],#dmview [data-dmtermin],#dmview [data-dmmelden],#dmview [data-dmmehr],#dmview [data-dmhide]');
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
    d=await dmSend(`/api/profile/dungeon/${rid}/aktion`,{text,zug:DM.v.zug},DM);if(d){if(ta)ta.value='';DMA.aendern.p=0;dmSent()}}
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
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmerz],#dmview [data-dmweise]');if(!s||!DM.rid)return;
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/erzaehler`,s.dataset.dmweise?{weise:s.value}:{k:s.value},DM);if(d){DM.v=d;DM.at=Date.now();dmDraw()}});
document.body.addEventListener('change',async e=>{const s=e.target.closest('#dmview [data-dmgive],#dgcard [data-dmgive]');if(!s||!s.value)return;
  const body={was:'schenken',i:s.dataset.dmgive,an:s.value};
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
window.dmHash=()=>{const m=/^#spiel=([A-Za-z0-9_-]{32})$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);DG.code=m[1];dgStart();return true};
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
function dgDraw(){const box=dgBox();if(!DG.v)return;let w=box.querySelector('.dm');if(!w){box.innerHTML=dgHead()+'<div class="dm"></div><div class="dg-konto" data-wo="tisch"></div>';w=box.querySelector('.dm')}dmTable(w,DG.v,'g');
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
    await dgAct('/api/dungeon/aktion',{text,zug:DG.v.zug});const t2=box.querySelector('.dm-in');if(!DG.err){if(t2)t2.value='';DMA.aendern.g=0;dmSent();dgDraw()}return}
  if(B.dmhero){await dgAct('/api/dungeon/held',dmHeroBody2(B));return}
  if(B.dmportraet){await dgAct('/api/dungeon/portraet/malen',{});return}
  if(B.dmtx){const m=await dmTx(B,'g',async b2=>{await dgAct('/api/dungeon/held',b2);return !DG.err});if(typeof m==='string')dmSay(DG,m,true);dgDraw();return}
  if(B.dmfigur){if(DG.busy)return;DG.busy=true;try{const d=await dgPub('/api/dungeon/figur',{code:DG.code});DG.figur=d.figur;dgDraw()}catch(e){dmSay(DG,dgErr(e),true)}DG.busy=false}});
// ---------------------------------------------------------------- the admin's rules: the tab „Regeln“ (dungeon_regelseite.py)
// Dominik 2026-10-24 „die regel seite sollte für den admin hier sein“, „unübersichtlich“: the sections on the left,
// the chosen one on the right; a part of the catalog as a list with picture, values and the balance mark, the
// detail below it. Without a profile (admin only) the same page opens as a card from Funktionen.
const DMR={teil:'geschichten',k:{},sel:'',q:'',f:'alle',m:'alle',edit:null,err:'',neu:{},busy:'',v:Date.now(),welt:{}};
const DMRKAT=['gegenstaende','gegner','klassen','voelker','hintergruende','welten','toene','zustaende'];
const dmRNamen=()=>({geschichten:t('Geschichten','Stories'),gegenstaende:t('Gegenstände','Items'),gegner:t('Gegner (Bestiarium)','Foes (bestiary)'),klassen:t('Klassen','Classes'),
  voelker:t('Völker','Peoples'),hintergruende:t('Hintergründe','Backgrounds'),welten:t('Welten','Worlds'),toene:t('Töne','Tones'),zustaende:t('Zustände','Conditions'),
  stimmen:t('Stimmen','Voices'),bilder:t('Bilder','Pictures'),musik:t('Musik','Music'),gaeste:t('Gäste mit E-Mail','Guests with e-mail'),ankommt:t('Wie es ankommt','How it lands'),json:t('Für Fortgeschrittene (JSON)','Advanced (JSON)')});
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
  for(const k of DMRKAT)if(DMR.k[k])n[k]=DMR.k[k].zeilen.length;
  const nb=k=>`<button type="button" class="${DMR.teil===k?'on':''}" data-dmrteil="${k}"${DMR.teil===k?' aria-current="true"':''}><span>${esc(N[k])}</span>${n[k]!=null?`<small>${n[k]}</small>`:''}</button>`;
  const nav=`<nav class="dm-rnav" aria-label="${esc(t('Teile der Regeln','Parts of the rules'))}">${nb('geschichten')}${DMRKAT.map(nb).join('')}<hr>${['stimmen','bilder','musik','gaeste','ankommt'].map(nb).join('')}<hr>${nb('json')}</nav>`;
  c.innerHTML=`<div class="dm-rhead"><h2>${esc(t('Dungeon-Master: Regeln','Dungeon Master: rules'))}</h2>${tab?'':`<button type="button" class="b" data-dmadm="close">${esc(t('Schließen','Close'))}</button>`}</div>
    <div class="dm-rlay">${nav}<div class="dm-rin">${dmRTeil(d,err)}</div></div>`;
  if(DMR.teil==='musik'&&window.dmMusikAdm)dmMusikAdm();
  if(DMRKAT.includes(DMR.teil)&&!DMR.k[DMR.teil])dmKatLoad(DMR.teil)}
function dmRTeil(d,err){const k=DMR.teil,N=dmRNamen(),h=`<h3 class="sec">${esc(N[k])}</h3>`,E=err?`<div class="err dm-adm-err">${err}</div>`:'';
  if(k==='geschichten')return DMP.g?dmPlanForm(d):dmPlans(d)+E;
  if(DMRKAT.includes(k))return dmKat(k);
  if(k==='stimmen')return h+`<div class="fh">${esc(t('Drei feste Stimmen, alle verschieden: der Erzähler, NPCs (Männer) und NPCs (Frauen). Sie sprechen, wenn keine beschriebene Stimme (VoiceDesign) da ist; wörtliche Rede in der Erzählung spricht immer die Figur, nie der Erzähler.','Three fixed voices, all different: the narrator, NPCs (men) and NPCs (women). They speak when no described voice (VoiceDesign) is there; quoted speech in the narration is always spoken by the character, never by the narrator.'))}</div>
    <div class="dm-two">${[['erzaehler',t('Stimme des Erzählers','Narrator voice')],['npc',t('NPCs (Männer)','NPCs (men)')],['npc_w',t('NPCs (Frauen)','NPCs (women)')]].map(([v,nm])=>{const cur=((d.eigene||{}).stimmen||{})[v]||'',grund=((d.standard||{}).stimmen||{})[v]||'';
      return `<div><label>${esc(nm)}</label><select class="dmadm-voice" data-k="${v}"><option value="">${esc(grund?t('Voreinstellung','Preset')+' ('+grund+')':t('Standardstimme','Default voice'))}</option>${[...new Set([cur,...(DMA.voices||[])].filter(Boolean))].map(x=>`<option${x===cur?' selected':''}>${esc(x)}</option>`).join('')}</select></div>`}).join('')}</div>
    ${E}<div class="row"><button type="button" class="b p" data-dmadm="save">${esc(t('Speichern','Save'))}</button></div>`;
  if(k==='bilder')return dmThumbsPics(d);
  if(k==='musik')return '<div id="dmmusikadm"></div>';
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
const DMRSTAND=()=>({grund:t('Grundregel','Base'),srd:'SRD',eigen:t('eigen','own'),geaendert:t('geändert','changed'),aus:t('ausgeblendet','hidden')});
function dmRFilter(teil){if(teil==='gegenstaende')return [['alle',t('Alle','All')],['waffe',t('Waffen','Weapons')],['ruestung',t('Rüstung','Armour')],['zauber',t('Zauber','Spells')],['trank',t('Tränke','Potions')],['werkzeug',t('Werkzeug','Tools')],['schatz',t('Schätze','Treasure')]];
  if(teil==='gegner')return [['alle',t('Alle','All')],['s0',t('Stufe 0-4','Level 0-4')],['s5',t('Stufe 5-10','Level 5-10')],['s11',t('Stufe 11+','Level 11+')]];return null}
function dmRPass(x){const f=DMR.f,q=DMR.q.trim().toLowerCase();
  if(q&&!(x.name.toLowerCase().includes(q)||String(x.id).toLowerCase().includes(q)))return false;
  if(DMR.m!=='alle'&&!(x.marke&&(DMR.m==='stark'?['stark','zu_stark'].includes(x.marke.marke):x.marke.marke===DMR.m)))return false;
  if(f==='alle')return true;
  if(f==='zauber')return ['zauber','rolle'].includes(x.art);if(f==='schatz')return ['schatz','schmuck'].includes(x.art);
  if(f[0]==='s'&&x.stufe!=null){const s=+x.stufe;return f==='s0'?s<5:f==='s5'?s>=5&&s<=10:s>10}
  return x.art===f}
const dmRImg=n=>`<img alt="" loading="lazy" src="/api/admin/dungeon/bild/${encodeURIComponent(n)}?v=${DMR.v}">`;
// an item's picture in its rarity's frame, as in the bag (DMSEL; Dominik 2026-10-24 „farblich anders umrandet“)
function dmRThumb(x,K){const s=x.selten?' '+(DMSEL[x.selten]||''):'selten' in x?' dm-sx':'';
  if(!K.bilder_an&&!x.bild||!('bild' in x))return `<span class="dm-rth dm-dz${s}" aria-hidden="true">${esc(x.zeichen||'·')}</span>`;
  return x.bild?`<span class="dm-rth${s}">${dmRImg(x.bild)}</span>`:`<span class="dm-rth dm-rno${s}" aria-hidden="true">${esc(x.zeichen||'')}</span>`}
function dmKat(teil){const K=DMR.k[teil],N=dmRNamen(),St=DMRSTAND();
  if(!K)return `<h3 class="sec">${esc(N[teil])}</h3><div class="mut">${esc(t('Lade …','Loading …'))}</div>`;
  if(K.fehler)return `<h3 class="sec">${esc(N[teil])}</h3><div class="err">${esc(K.fehler)}</div>`;
  const F=dmRFilter(teil),hasM=K.zeilen.some(x=>x.marke),rows=K.zeilen.filter(dmRPass),MAX=200;
  const nm={alle:t('Alle','All'),stark:t('stark und zu stark','strong and too strong'),zu_stark:t('zu stark','too strong'),schwach:t('schwach','weak')};
  const list=rows.slice(0,MAX).map(x=>{const m=x.marke&&x.marke.marke!=='ok'?`<span class="pill ${DMRMARKE[x.marke.marke]}" title="${esc(x.marke.grund)}">${esc(x.marke.name)}</span>`:'';
    return `<div class="dm-rrow${String(x.id)===DMR.sel?' on':''}${x.stand==='aus'?' dm-raus':''}${x.selten?' dm-rsel '+(DMSEL[x.selten]||''):'selten' in x?' dm-rsel dm-sx':''}"><button type="button" class="dm-rmain" data-dmrsel="${esc(x.id)}">${dmRThumb(x,K)}<span class="dm-rtxt"><b>${esc(x.name)}</b><small>${esc(x.zeile)}</small></span></button>
      <span class="dm-rpills">${m}${x.stand!=='grund'&&x.stand!=='srd'?`<span class="pill">${esc(St[x.stand])}</span>`:''}${x.neu?`<span class="pill warn">${esc(t('neues Bild','new picture'))}</span>`:''}</span>
      ${'bild' in x&&!x.bild&&K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(t('Malen','Paint'))}</button>`:''}</div>`}).join('');
  const wsel=K.welten?`<select class="dmr-w" aria-label="${esc(t('Bilder in der Welt','Pictures in the world'))}">${K.welten.map(w=>`<option value="${esc(w.id)}"${w.id===K.welt?' selected':''}>${esc(t('Bilder in: ','Pictures in: ')+w.name)}</option>`).join('')}</select>`:'';
  return `<h3 class="sec">${esc(N[teil])} · ${K.zeilen.length}</h3>
    <div class="dm-rsrch">${wsel}<input type="search" class="dmr-q" value="${esc(DMR.q)}" placeholder="${esc(t('Suchen …','Search …'))}" aria-label="${esc(t('Suchen','Search'))}">
      ${F?`<div class="lseg dm-rseg">${F.map(([v,l])=>`<button type="button" class="${DMR.f===v?'on':''}" data-dmrf="${v}">${esc(l)}</button>`).join('')}</div>`:''}
      ${hasM?`<select class="dmr-m" aria-label="${esc(t('Gleichgewicht','Balance'))}">${['alle','stark','zu_stark','schwach'].map(v=>`<option value="${v}"${DMR.m===v?' selected':''}>${esc(v==='alle'?t('Gleichgewicht: alle','Balance: all'):nm[v])}</option>`).join('')}</select>`:''}</div>
    ${K.seltenheiten?dmRSelLeg(K):''}<div class="dm-rkat"><div class="dm-rlist" role="list">${list||`<div class="ic-empty">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`}${rows.length>MAX?`<div class="mut dm-rmehr">${esc(t(`${rows.length-MAX} weitere, bitte genauer suchen`,`${rows.length-MAX} more, please search more closely`))}</div>`:''}</div>
    <div class="dm-rdet" id="dmrdet">${dmRDet(teil)}</div></div>`}
// the rarities as frames: a fixed one shows its colour, a rolled item (most of them) gets it when it is found
function dmRSelLeg(K){return `<div class="dm-rsleg" aria-label="${esc(t('Seltenheit','Rarity'))}">${K.seltenheiten.map(s=>`<span class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(s.name)}</span>`).join('')}<span class="dm-rsl"><i class="dm-rth dm-sx"></i>${esc(t('gewürfelt beim Fund','rolled when found'))}</span></div>`}
function dmRSelLadder(K,x){if(!K.seltenheiten)return '';
  if(x.selten){const s=K.seltenheiten.find(z=>z.id===x.selten);return s?`<div class="fh dm-rsfest"><i class="dm-rth ${DMSEL[s.id]||''}"></i>${esc(t(`Immer ${s.name}: +${s.bonus}, Preis ×${s.preis}`,`Always ${s.name}: +${s.bonus}, price ×${s.preis}`))}</div>`:''}
  return `<div class="dm-rsleiter"><div class="fh">${esc(t('Die Seltenheit wird beim Fund gewürfelt (W100 plus zweimal die Stufe) und gibt den Rahmen:','The rarity is rolled when it is found (d100 plus twice the level) and gives the frame:'))}</div>
    ${K.seltenheiten.map(s=>`<div class="dm-rsl"><i class="dm-rth ${DMSEL[s.id]||''}"></i><b>${esc(s.name)}</b><small>${esc(t(`ab ${s.ab||1} · +${s.bonus} · Preis ×${s.preis}${s.stufe>1?` · ab Stufe ${s.stufe}`:''}`,`from ${s.ab||1} · +${s.bonus} · price ×${s.preis}${s.stufe>1?` · from level ${s.stufe}`:''}`))}</small></div>`).join('')}</div>`}
function dmRDet(teil){const K=DMR.k[teil],x=K.zeilen.find(z=>String(z.id)===DMR.sel),St=DMRSTAND();
  if(!x)return `<div class="ic-empty">${esc(t('Tippe links einen Eintrag an.','Tap an entry on the left.'))}</div>`;
  const e=K.eintraege[String(x.id)]||{},li=L==='en'?1:0,tx=v=>Array.isArray(v)?v[li]||v[0]:v||'';
  if(DMR.edit)return `<b class="dm-rname">${esc(DMR.edit.kopie?t('Eigene Kopie','Own copy'):t('Ändern','Edit'))}: ${esc(x.name)}</b>
    <div class="fh">${esc(t('Der ganze Eintrag; das Panel prüft ihn wie alle Regeln. „Zu stark“ ist nur ein Hinweis.','The whole entry; the panel checks it like every rule. "Too strong" is only a hint.'))}</div>
    <textarea class="mono dmr-txt" rows="16" data-fest spellcheck="false">${esc(JSON.stringify(DMR.edit.e,null,2))}</textarea>${DMR.err?`<div class="err dm-adm-err">${DMR.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmrdo="setzen">${esc(t('Prüfen und speichern','Check and save'))}</button><button type="button" class="b" data-dmrdo="abbrechen">${esc(t('Abbrechen','Cancel'))}</button></div>`;
  const m=x.marke,neu=DMR.neu[String(x.id)]||x.neu,b='bild' in x;
  const pic=b?`<div class="dm-rbild${x.selten?' '+(DMSEL[x.selten]||''):''}">${neu?`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(t('jetzt','now'))}</figcaption></figure><figure>${dmRImg(neu)}<figcaption>${esc(t('neu gemalt','painted again'))}</figcaption></figure></div>
      <div class="row"><button type="button" class="b p" data-dmrbild="neu" data-id="${esc(x.id)}">${esc(t('Neues behalten','Keep the new one'))}</button><button type="button" class="b" data-dmrbild="alt" data-id="${esc(x.id)}">${esc(t('Altes behalten','Keep the old one'))}</button></div>`
      :`<div class="dm-rvgl"><figure>${x.bild?dmRImg(x.bild):`<span class="dm-rno">${esc(x.zeichen||'')}</span>`}<figcaption>${esc(x.bild?t('jetzt','now'):t('noch kein Bild','no picture yet'))}</figcaption></figure></div>`}
      <div class="row">${K.bilder_an?`<button type="button" class="b" data-dmrbild="malen" data-id="${esc(x.id)}"${DMR.busy?' disabled':''}>🖌 ${esc(DMR.busy===String(x.id)?t('Malt gerade …','Painting …'):x.bild?t('Nochmal malen','Paint again'):t('Malen','Paint'))}</button>`:`<small class="mut">${esc(t('Die Bilder sind aus; einschalten im Abschnitt „Bilder“.','Pictures are off; switch them on in the part "Pictures".'))}</small>`}</div></div>`:'';
  return `<div class="dm-rdkopf"><div><b class="dm-rname">${esc(x.zeichen||'')} ${esc(x.name)}</b> <span class="pill">${esc(St[x.stand])}</span>${m?` <span class="pill ${DMRMARKE[m.marke]}">${esc(m.name)}</span>`:''}</div></div>
    <div class="dm-rdgrid"><div><div class="dm-rzeile">${esc(x.zeile)}</div>${(x.werte||[]).length?`<dl class="dm-rwerte">${x.werte.map(([a,v])=>`<dt>${esc(a)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:''}${dmRSelLadder(K,x)}${m&&m.grund?`<div class="fh dm-rgrund">${esc(m.grund)}</div>`:''}${tx(e.info||e.satz)?`<p class="dm-rinfo">${esc(tx(e.info||e.satz))}</p>`:''}
      <div class="row"><button type="button" class="b" data-dmrdo="aendern">${esc(t('Ändern','Edit'))}</button><button type="button" class="b" data-dmrdo="kopie">${esc(t('Eigene Kopie','Own copy'))}</button>
      ${x.stand==='aus'||x.stand==='geaendert'?`<button type="button" class="b" data-dmrdo="zurueck">${esc(t('Zurück auf mitgeliefert','Back to shipped'))}</button>`:''}
      ${x.stand==='eigen'?`<button type="button" class="b danger" data-dmrdo="zurueck">${esc(t('Eigenen Eintrag löschen','Delete own entry'))}</button>`:x.stand!=='aus'?`<button type="button" class="b" data-dmrdo="aus">${esc(t('Ausblenden','Hide'))}</button>`:''}</div></div>${pic}</div>`}
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
  const s=e.target.closest('#dmadmcard .dmr-m');if(!s)return;DMR.m=s.value;dmRDraw()});
document.body.addEventListener('click',async e=>{const c=e.target.closest('#dmadmcard');if(!c)return;const teil=DMR.teil;
  const nb=e.target.closest('[data-dmrteil]');if(nb){DMR.teil=nb.dataset.dmrteil;DMR.sel='';DMR.q='';DMR.f='alle';DMR.m='alle';DMR.edit=null;DMR.err='';DMP.g=null;dmRDraw();return}
  const fb=e.target.closest('[data-dmrf]');if(fb){DMR.f=fb.dataset.dmrf;dmRDraw();return}
  const sb=e.target.closest('[data-dmrsel]');if(sb){DMR.sel=sb.dataset.dmrsel;DMR.edit=null;DMR.err='';dmRPick();const d=$('dmrdet');if(d&&window.innerWidth<900)d.scrollIntoView({block:'start',behavior:'smooth'});return}
  const db=e.target.closest('[data-dmrdo]');if(db){const K=DMR.k[teil],x=K&&K.zeilen.find(z=>String(z.id)===DMR.sel);if(!x)return;const was=db.dataset.dmrdo;
    if(was==='abbrechen'){DMR.edit=null;DMR.err='';dmRDraw();return}
    if(was==='aendern'||was==='kopie'){const e0=JSON.parse(JSON.stringify(K.eintraege[String(x.id)]||{}));
      if(was==='kopie'){const ids=new Set(K.zeilen.map(z=>String(z.id)));let n=2;while(ids.has(`${x.id}_${n}`))n++;e0.id=typeof x.id==='number'?Math.max(...K.zeilen.map(z=>+z.id||0))+1:`${x.id}_${n}`;}
      DMR.edit={e:e0,kopie:was==='kopie'};DMR.err='';dmRDraw();return}
    if(was==='setzen'){let ent;try{ent=JSON.parse(c.querySelector('.dmr-txt').value)}catch{DMR.edit.e=c.querySelector('.dmr-txt').value;DMR.err=esc(t('Das ist kein gültiges JSON.','This is not valid JSON.'));dmRDraw();return}
      DMR.edit.e=ent;await dmRDo(teil,'setzen',String(ent.id),ent);return}
    if(db.classList.contains('danger')&&db.dataset.sure!=='1'){db.dataset.sure='1';db.textContent=t('Wirklich löschen?','Really delete?');return}
    await dmRDo(teil,was,String(x.id));return}
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
    <div class="dm-sum"><span class="pill">${esc(t('heute','today'))} ${x.heute}</span> <span class="pill">${esc(t('Fundstücke','Finds'))} ${x.funde}</span>${x.abgelehnt?` <span class="pill warn">${esc(t('abgelehnt','refused'))} ${x.abgelehnt}</span>`:''}${x.laeuft?` <span class="pill on">${esc(x.grund==='alle'?t('malt alle, ohne Tageslimit','painting all, no day limit'):t('malt gerade','painting now'))} · ${x.gemalt} · ${esc(t('noch','left'))} ${x.von-x.fertig}</span>`:L0.ende?` <span class="pill">${esc(t('zuletzt','last'))} ${esc(new Date(L0.ende*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}))} · ${L0.gemalt} · ${esc(warum[L0.warum]||L0.warum||'')}</span>`:''}</div>
    <div class="row">${x.laeuft?`<button type="button" class="b" data-dmding="stop">${esc(x.grund==='alle'?t('Abbrechen','Cancel'):t('Anhalten','Stop'))}</button>`:`<button type="button" class="b p" data-dmding="start"${!x.an||!x.bilder||x.fertig>=x.von?' disabled':''}>${esc(t('Bilder jetzt erstellen','Create pictures now'))}</button>
      <button type="button" class="b" data-dmding="alle" title="${esc(t('Malt alle fehlenden Bilder (Gegenstände, Zauber, Gegner, Orts- und Raumarten, Völker, Klassen) ohne Tageslimit, eins nach dem anderen über die Warteschlange.','Paints every missing picture (items, spells, foes, kinds of places and rooms, peoples, classes) without the day limit, one after the other through the queue.'))}"${!x.an||!x.bilder||x.fertig>=x.von?' disabled':''}>${esc(t('Alle Bilder malen','Paint all pictures'))} · ${x.von-x.fertig}</button>`}</div></div>`}
let DMDT=0;
async function dmDingLook(){clearTimeout(DMDT);const box=$('dmding');if(!box)return;const {r,d}=await apiTry('/api/admin/dungeon/dingbilder');
  if(!r.ok||!$('dmding'))return;$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmding [data-dmding]');if(!b)return;b.disabled=true;
  const k=b.dataset.dmding,{r,d}=await apiTry('/api/admin/dungeon/dingbilder',k==='stop'?{method:'DELETE'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alle:k==='alle'})});
  if(!r.ok){b.disabled=false;sayToast(dmErr(r.status,d.detail));return}$('dmding').outerHTML=dmDingAdmin(d);if(d.laeuft)DMDT=setTimeout(dmDingLook,5000)});
// ---------------------------------------------------------------- the admin's stories (Geschichten-Planer)
// a story: idea, goal, foe, places, taboos and 3 to 5 acts with a turning point; „Vorschlag erzeugen“ lets the model
// write all of it from keywords, „↻“ one act again; the panel checks both like typed text before anything is kept
const DMP={d:null,g:null,gid:'',err:'',stich:'',hint:'',busy:false};
function dmPlans(d){const gs=d.geschichten||[],P=d.planer;
  return `<h3 class="sec">${esc(t('Geschichten','Stories'))} · ${gs.length}/${P.max}</h3>
    <div class="fh">${esc(t('Lege fest, wie eine Geschichte verläuft. Wer eine Runde anlegt, wählt sie aus; den Plan sehen nur du und der Gastgeber.','Set how a story runs. Whoever starts a round picks it; only you and the host see the plan.'))}</div>
    ${gs.length?`<div class="ic-list">${gs.map(g=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(g.titel)}</span><small class="ic-meta">${esc(g.welt_name)} · ${esc(g.ton_name)} · ${g.akte.length} ${esc(t('Akte','acts'))}</small></div><button type="button" class="b" data-dmadm="gedit" data-gid="${esc(g.gid)}">${esc(t('Bearbeiten','Edit'))}</button></div>`).join('')}</div>`:''}
    <div class="row"><button type="button" class="b"${gs.length>=P.max?' disabled':''} data-dmadm="gneu">${esc(t('Neue Geschichte','New story'))}</button></div>`}
function dmPlanForm(d){const g=DMP.g,P=d.planer,w=d.wahl;
  const opt=(a,cur)=>a.map(x=>`<option value="${esc(x.id)}"${String(x.id)===String(cur)?' selected':''}>${esc(x.name)}</option>`).join('');
  const nums=[];for(let n=P.akte[0];n<=P.akte[1];n++)nums.push(n);
  const akt=(a,i)=>`<div class="dmp-akt" data-i="${i}"><div class="dm-khead"><b>${esc(t('Akt','Act'))} ${i+1}</b><span><button type="button" class="b" data-dmadm="gakt" data-n="${i+1}"${DMP.busy?' disabled':''} title="${esc(t('Diesen Akt vom Modell neu schreiben lassen','Let the model write this act again'))}">↻ ${esc(t('Neu schreiben','Write again'))}</button>${g.akte.length>P.akte[0]?`<button type="button" class="b" data-dmadm="gminus" data-n="${i}">${esc(t('Entfernen','Remove'))}</button>`:''}</span></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-at" maxlength="60" value="${esc(a.titel||'')}">
    <label>${esc(t('Was geschieht','What happens'))}</label><textarea class="dmp-ai" rows="3" maxlength="${P.inhalt}">${esc(a.inhalt||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Wendepunkt am Ende','Turning point at the end'))}</label><input class="dmp-aw" maxlength="${P.wende}" value="${esc(a.wende||'')}"></div>
    <div><label>${esc(t('Geplante Züge','Planned turns'))}</label><input class="dmp-az" type="number" min="${P.zuege[0]}" max="${P.zuege[1]}" value="${a.zuege||6}"></div></div></div>`;
  return `<h2>${esc(DMP.gid?t('Geschichte bearbeiten','Edit the story'):t('Neue Geschichte','New story'))}</h2><div class="dm-form dmp-form">
    <div class="dm-k"><div class="lbl">✨ ${esc(t('Vom Sprachmodell entwerfen lassen','Let the language model draft it'))}</div>
      <textarea class="dmp-stich" rows="2" maxlength="${P.stichworte}" placeholder="${esc(t('verfluchtes Bergdorf, ein Drache, der nur bewacht, eher düster','a cursed mountain village, a dragon that only guards, rather dark'))}">${esc(DMP.stich)}</textarea>
      <div class="row"><select class="dmp-n" aria-label="${esc(t('Akte','Acts'))}">${nums.map(n=>`<option value="${n}"${n===g.akte.length?' selected':''}>${n} ${esc(t('Akte','acts'))}</option>`).join('')}</select><button type="button" class="b p" data-dmadm="gvor"${DMP.busy?' disabled':''}>${esc(DMP.busy?t('Das Modell schreibt …','The model is writing …'):t('Vorschlag erzeugen','Create a proposal'))}</button></div>
      <small class="mut">${esc(t('Das Modell füllt alle Felder; das Panel prüft Länge, Ton und Tabus. Erst „Speichern“ behält die Geschichte.','The model fills every field; the panel checks length, tone and taboos. Only "Save" keeps the story.'))}</small></div>
    <label>${esc(t('Titel','Title'))}</label><input class="dmp-titel" maxlength="60" value="${esc(g.titel||'')}">
    <div class="dm-two"><div><label>${esc(t('Welt','World'))}</label><select class="dmp-welt">${opt(w.welten,g.welt)}</select></div><div><label>${esc(t('Ton','Tone'))}</label><select class="dmp-ton">${opt(w.toene,g.ton)}</select></div></div>
    <label>${esc(t('Grundidee','Idea'))}</label><textarea class="dmp-idee" rows="3" maxlength="${P.idee}">${esc(g.idee||'')}</textarea>
    <div class="dm-two"><div><label>${esc(t('Ziel der Helden','The heroes\' goal'))}</label><input class="dmp-ziel" maxlength="${P.ziel}" value="${esc(g.ziel||'')}"></div><div><label>${esc(t('Gegenspieler','Foe'))}</label><input class="dmp-gegner" maxlength="${P.ziel}" value="${esc(g.gegner||'')}"></div></div>
    <label>${esc(t('Schauplätze (mit Komma, bis zu '+P.orte+')','Places (comma separated, up to '+P.orte+')'))}</label><input class="dmp-orte" value="${esc((g.orte||[]).join(', '))}">
    <label>${esc(t('Tabus: kommt nie vor (mit Komma, bis zu '+P.tabus+')','Taboos: never happens (comma separated, up to '+P.tabus+')'))}</label><input class="dmp-tabus" value="${esc((g.tabus||[]).join(', '))}" placeholder="${esc(t('Spinnen, Folter','spiders, torture'))}">
    ${g.akte.map(akt).join('')}
    ${g.akte.length<P.akte[1]?`<div class="row"><button type="button" class="b" data-dmadm="gplus">${esc(t('Akt dazu','Add an act'))}</button></div>`:''}
    <label>${esc(t('Hinweis fürs Neuschreiben eines Akts (frei)','Hint for writing an act again (optional)'))}</label><input class="dmp-hint" maxlength="${P.stichworte}" value="${esc(DMP.hint)}" placeholder="${esc(t('mehr Rätsel, weniger Kampf','more riddles, less fighting'))}">
    ${DMP.err?`<div class="err dm-adm-err">${DMP.err}</div>`:''}
    <div class="row"><button type="button" class="b p" data-dmadm="gsave"${DMP.busy?' disabled':''}>${esc(t('Prüfen und speichern','Check and save'))}</button>${DMP.gid?`<button type="button" class="b danger" data-dmadm="gdel">${esc(t('Löschen','Delete'))}</button>`:''}<button type="button" class="b" data-dmadm="gback">${esc(t('Zurück','Back'))}</button></div></div>`}
function dmPlanRead(){const c=$('dmadmcard'),q=x=>(c.querySelector(x)||{}).value||'',list=x=>q(x).split(',').map(s=>s.trim()).filter(Boolean);
  DMP.stich=q('.dmp-stich');DMP.hint=q('.dmp-hint');
  const ton=q('.dmp-ton');
  return {titel:q('.dmp-titel').trim(),welt:q('.dmp-welt'),ton:/^\d+$/.test(ton)?+ton:ton,lang:dmLang(),idee:q('.dmp-idee').trim(),ziel:q('.dmp-ziel').trim(),
    gegner:q('.dmp-gegner').trim(),orte:list('.dmp-orte'),tabus:list('.dmp-tabus'),
    akte:[...c.querySelectorAll('.dmp-akt')].map(a=>({titel:a.querySelector('.dmp-at').value.trim(),inhalt:a.querySelector('.dmp-ai').value.trim(),
      wende:a.querySelector('.dmp-aw').value.trim(),zuege:Math.floor(+a.querySelector('.dmp-az').value||0)}))}}
const dmPlanErr=(r,d)=>Array.isArray(d.detail)?d.detail.map(x=>esc(x)).join('<br>')
  :d.detail==='kein vorschlag'?esc(t('Das Modell hat keinen brauchbaren Vorschlag geliefert. Bitte noch einmal oder mit anderen Stichworten.','The model gave no usable proposal. Please try again or with other keywords.'))
  :d.detail==='sprachmodell pausiert'?esc(t('Das Sprachmodell ist gerade pausiert.','The language model is paused right now.')):esc(dmErr(r.status,d.detail));
async function dmPlanClick(b,k){const d=DMP.d,w=d.wahl;if(DMP.busy)return;
  if(k==='gneu'){DMP.gid='';DMP.err='';DMP.stich='';DMP.hint='';DMP.g={titel:'',welt:w.welten[0].id,ton:(w.toene[1]||w.toene[0]).id,idee:'',ziel:'',gegner:'',orte:[],tabus:[],
    akte:Array.from({length:d.planer.akte[0]},()=>({titel:'',inhalt:'',wende:'',zuege:6}))};dmRulesDraw(d,'');return}
  if(k==='gedit'){const g=(d.geschichten||[]).find(x=>x.gid===b.dataset.gid);if(!g)return;DMP.gid=g.gid;DMP.err='';DMP.stich='';DMP.hint='';DMP.g=JSON.parse(JSON.stringify(g));dmRulesDraw(d,'');return}
  if(k==='gback'){DMP.g=null;dmRulesDraw(d,'');return}
  const g=dmPlanRead();DMP.g=g;
  if(k==='gplus'){g.akte.push({titel:'',inhalt:'',wende:'',zuege:6});dmRulesDraw(d,'');return}
  if(k==='gminus'){g.akte.splice(+b.dataset.n,1);dmRulesDraw(d,'');return}
  if(k==='gdel'){if(b.dataset.sure!=='1'){b.dataset.sure='1';b.textContent=t('Wirklich löschen?','Really delete?');return}
    const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+DMP.gid+'?lang='+dmLang(),{method:'DELETE'});if(r.ok){DMP.g=null;dmRulesDraw(x,'')}return}
  if(k==='gsave'){const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+(DMP.gid||'neu')+'?lang='+dmLang(),xjson('PUT',g));
    if(r.ok){DMP.g=null;dmRulesDraw(x,'');sayToast(t('Geschichte gespeichert','Story saved'));return}DMP.err=dmPlanErr(r,x);dmRulesDraw(d,'');return}
  const n=Math.floor(+((($('dmadmcard').querySelector('.dmp-n'))||{}).value||g.akte.length));
  const body=k==='gvor'?{welt:g.welt,ton:g.ton,akte:n,stichworte:DMP.stich,tabus:g.tabus,lang:g.lang}:{plan:g,n:+b.dataset.n,hinweis:DMP.hint};
  if(k==='gvor'&&DMP.stich.trim().length<3){DMP.err=esc(t('Bitte ein paar Stichworte eingeben.','Please enter a few keywords.'));dmRulesDraw(d,'');return}
  DMP.busy=true;DMP.err='';dmRulesDraw(d,'');
  const {r,d:x}=await apiTry('/api/admin/dungeon/geschichte/'+(k==='gvor'?'vorschlag':'akt'),xjson('POST',body));DMP.busy=false;
  if(r.ok&&x.plan){DMP.g=Object.assign(x.plan,{lang:g.lang})}else DMP.err=dmPlanErr(r,x);
  if(DMP.g&&$('dmadmcard'))dmRulesDraw(DMP.d,'')}
