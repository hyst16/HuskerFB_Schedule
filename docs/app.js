/* Global rendering for index.html (TV cycle) + checklist.html */

async function loadJSON(path){
  const res = await fetch(path + '?v=' + Date.now());
  return await res.json();
}

function fmtDate(g){
  try{
    if(g.date_iso){
      const d = new Date(g.date_iso);
      const wd = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
      const mo = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
      const day = String(d.getDate()).padStart(2,'0');
      return `${wd} • ${mo} ${day}`;
    }
  }catch(e){}
  return (g.weekday && g.date_str) ? `${g.weekday.split(' ')[0]} • ${g.date_str}` : (g.date_str || 'TBA');
}

function tvLogo(tv){
  if(!tv) return null;
  const file = {
    fox:'fox', fs1:'fs1', fs2:'fs2',
    btn:'btn', cbs:'cbs', nbc:'nbc', peacock:'peacock',
    abc:'abc', espn:'espn', espn2:'espn2', espnu:'espnu'
  }[tv];
  // Use PNGs for convenience; drop PNGs into docs/tv/
  return file ? `./tv/${file}.png` : null;
}

function stadiumBackground(slug){
  // Images must live under docs/assets/stadiums/
  return `./assets/stadiums/${slug || 'memorial-stadium-lincoln'}.jpg`;
}

// Prefer the remote logo URL from the scraper; fall back to optional local override
function opponentLogo(remoteUrl, slug){
  if (remoteUrl) return remoteUrl;                 // from opponent_logo_url
  if (slug) return `./assets/opponents/${slug}.png`; // optional local file (inside /docs)
  return './tv/opponent.svg';                      // final fallback icon
}

function ensureTwoColIfOverflow(container){
  const maxTries = 2;
  let tries = 0;
  while(tries++ < maxTries){
    if(container.scrollHeight > container.clientHeight){
      container.classList.add('two-col');
    } else {
      break;
    }
  }
}

async function renderTV(){
  const games = await loadJSON('./schedule.json');
  const missing = await loadJSON('./stadiums_missing.json').catch(()=>[]);

  // pick next game
  const now = new Date();
  let next = games.find(g => g.status !== 'final' && (!g.date_iso || new Date(g.date_iso) >= now)) || games[0];

  // HERO
  const hero = document.querySelector('#hero');
  const hbg = document.createElement('div'); hbg.className = 'bg';
  const bgPath = stadiumBackground(next.stadium_slug || 'memorial-stadium-lincoln');
  hbg.style.backgroundImage = `url('${bgPath}')`;

  const overlay = document.createElement('div'); overlay.className='overlay';
  const content = document.createElement('div'); content.className='content';
  const lock = document.createElement('div'); lock.className='lockup';

  const nlogo = document.createElement('img'); nlogo.className='nlogo'; nlogo.alt='Nebraska N'; nlogo.src='./tv/n-logo.svg';
  const va = document.createElement('div'); va.className='va'; va.textContent = next.va || (next.site==='home'?'vs.':'at');

  const opp = document.createElement('div'); opp.className='opp';
  const oimg = document.createElement('img');
  oimg.alt = next.opponent_name || 'Opponent';
  oimg.src = opponentLogo(next.opponent_logo_url, next.opponent_slug);
  const otext = document.createElement('div'); otext.className='title'; otext.textContent = (next.opponent_name || '').toUpperCase();
  opp.appendChild(oimg);

  lock.append(nlogo, va, opp, otext);

  const meta = document.createElement('div'); meta.className='meta';
  const dt = fmtDate(next);
  const tim = (next.tba ? 'TBA' : (next.time_local || 'TBA'));
  const loc = [next.location_city, next.location_venue].filter(Boolean).join(' / ');
  meta.innerHTML = `<strong>${dt}</strong> • ${tim}${loc ? ' • ' + loc : ''}`;

  const tvc = document.createElement('div'); tvc.className='tv';
  const tvp = tvLogo(next.tv_network);
  if(tvp){
    const tvi = document.createElement('img');
    tvi.src = tvp;
    tvi.alt = (next.tv_network || 'TV').toUpperCase();
    tvc.appendChild(tvi);
  } else {
    tvc.textContent = 'TBA';
    tvc.style.color = '#cbd5e1';
    tvc.style.fontWeight = '700';
  }

  content.append(lock, meta);
  hero.append(hbg, overlay, content, tvc);

  // FULL SEASON LIST
  const list = document.querySelector('#list');
  games.forEach(g => {
    const row = document.createElement('div'); row.className='row';
    if(g.status==='final') row.classList.add('past');

    const badge = document.createElement('div'); badge.className = `badge ${g.site||'home'}`; badge.textContent=(g.site||'HOME').toUpperCase();
    const date = document.createElement('div'); date.className='date'; date.textContent = fmtDate(g);
    const time = document.createElement('div'); time.className='time'; time.textContent = g.tba? 'TBA' : (g.time_local || 'TBA');
    const nmini = document.createElement('img'); nmini.className='nmini'; nmini.src='./tv/n-logo.svg'; nmini.alt='N';

    const match = document.createElement('div'); match.className='match';
    const va2 = document.createElement('div'); va2.className='va'; va2.textContent = g.va || (g.site==='home'?'vs.':'at');
    const oimg2 = document.createElement('img');
    oimg2.alt = g.opponent_name || 'Opponent';
    oimg2.src = opponentLogo(g.opponent_logo_url, g.opponent_slug);
    const owrap = document.createElement('div');
    const oname = document.createElement('div'); oname.style.fontWeight='800'; oname.style.letterSpacing='.02em'; oname.textContent = (g.opponent_name||'').toUpperCase();
    const sub = document.createElement('div'); sub.className='sub'; sub.textContent = [g.location_city, g.location_venue].filter(Boolean).join(' / ');
    owrap.append(oname, sub);
    match.append(va2, oimg2, owrap);

    const tvcell = document.createElement('div'); tvcell.className='tvcell';
    const tl = tvLogo(g.tv_network);
    if(tl){
      const tvi2 = document.createElement('img'); tvi2.src = tl; tvi2.alt=(g.tv_network||'TV').toUpperCase(); tvcell.appendChild(tvi2);
    } else {
      tvcell.textContent = 'TBA'; tvcell.style.color = '#cbd5e1'; tvcell.style.fontWeight='700';
    }

    row.append(badge, date, time, nmini, match, tvcell);
    list.appendChild(row);
  });

  // Two-col fallback if overflow
  ensureTwoColIfOverflow(list);

  // AUTO-CYCLE between HERO and FULL
  const cycleMs = (parseInt(new URLSearchParams(location.search).get('cycle')) || 12) * 1000;
  let showingHero = true;
  setInterval(()=>{
    showingHero = !showingHero;
    document.querySelector('#heroWrap').classList.toggle('hidden', !showingHero);
    document.querySelector('#fullWrap').classList.toggle('hidden', showingHero);
  }, cycleMs);
}

async function renderChecklist(){
  const needed = await loadJSON('./stadiums_needed.json');
  const missing = await loadJSON('./stadiums_missing.json');
  const setMissing = new Set(missing);
  const ul = document.querySelector('#needed');
  needed.forEach(slug => {
    const li = document.createElement('li');
    const present = !setMissing.has(slug);
    li.textContent = `${present ? '✅' : '❌'}  assets/stadiums/${slug}.jpg`;
    ul.appendChild(li);
  });
}

// entrypoints chosen per page
if(document.currentScript && document.currentScript.dataset.page === 'tv'){
  renderTV();
}
if(document.currentScript && document.currentScript.dataset.page === 'check'){
  renderChecklist();
}
