'use strict';
const $ = id => document.getElementById(id);
const node = (tag, className, text) => { const e = document.createElement(tag); if(className) e.className=className; if(text!==undefined) e.textContent=text; return e; };
let currentJob=null, displayedJob=null, bundledResearch=null, timer=null, token='', busy=false, connected=false;
let pollFailures=0, viewGeneration=0;
const completedResearch=new Map();
const demoEnabled=()=>$('demo-protection').checked;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const labels={stronger_evidence:'Stronger ecosystem evidence',emerging_evidence:'Emerging ecosystem evidence',limited_evidence:'Limited evidence',location_review:'NJ connection needs review',outside_scope:'Outside NJ scope'};
const locationLabels={headquarters:'NJ headquarters',operations:'NJ operations',ecosystem_only:'NJ ecosystem ties',unclear:'Location unconfirmed',outside_nj:'Outside New Jersey',conflicting:'Conflicting locations'};
const pretty = value => (value||'unknown').replaceAll('_',' ');
const dateLabel = value => { if(!value) return 'Date unconfirmed'; if(value.length<10)return value; const date=new Date(value.slice(0,10)+'T12:00:00'); return Number.isNaN(date.valueOf())?'Date unconfirmed':date.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}); };
function notice(message){$('notice').textContent=message||'';$('notice').hidden=!message;}
function setBusy(value){busy=value;$('find-button').disabled=value||(!connected&&!bundledResearch);$('sample-button').disabled=value;$('sector').disabled=value;$('count').disabled=value;}
async function api(path,options={}) {
  const headers={...options.headers}; if(token)headers.Authorization='Bearer '+token;
  for(let attempt=0;attempt<3;attempt++){
    try{
      const response=await fetch('/api/reputation'+path,{...options,headers,signal:AbortSignal.timeout(12000)});
      const data=await response.json();
      if(!response.ok){const error=new Error(data.error||'The request could not be completed.');error.data=data;error.status=response.status;error.retryAfter=Number(response.headers.get('Retry-After')||0);throw error;}
      return data;
    }catch(error){
      if(attempt===2||(error.status&&![408,429,500,502,503,504].includes(error.status))||error.retryAfter>10)throw error;
      await pause(Math.max(1000*2**attempt,(error.retryAfter||0)*1000));
    }
  }
}
function savedFor(sector=$('sector').value,count=Number($('count').value)){
  const cached=completedResearch.get(sector+'|'+count);
  if(cached)return {...cached,mode:'cached',stage:'Saved results ready'};
  if(!bundledResearch)return null;
  const matches=c=>sector==='All sectors'||c.sector===sector;
  const cards=bundledResearch.cards.filter(matches).slice(0,count),review=bundledResearch.review_cards.filter(matches);
  const warnings=[...bundledResearch.warnings];
  if(!cards.length&&!review.length)warnings.push('No saved examples are available for this sector. Choose All sectors to present the saved demo.');
  return {...bundledResearch,id:bundledResearch.id+'-'+sector+'-'+count,sector,requested_count:count,cards,review_cards:review,qualified_count:cards.length,warnings};
}
function showSaved(){const saved=savedFor();if(saved){currentJob=null;render(saved);notice('');}return saved;}
function refreshUnavailable(message='Live refresh is temporarily unavailable. Dated, saved research remains available.'){
  if(demoEnabled()&&(displayedJob?.cards.length||displayedJob?.review_cards.length||showSaved())){
    notice('');$('progress-title').textContent='Saved results ready';$('progress-detail').textContent=message;$('progress-indicator').classList.add('done');
  }else notice(message);
  setBusy(false);
}
function safeLink(url,text){const a=node('a','',text);try{const parsed=new URL(url);if(!['https:','http:'].includes(parsed.protocol))return node('span','',text);a.href=parsed.href;a.target='_blank';a.rel='noopener noreferrer';}catch{return node('span','',text);}return a;}
function evidenceDetail(evidence,title='Read source evidence'){
  const detail=node('details','evidence-detail');detail.append(node('summary','',title));
  for(const e of evidence){const source=node('div','source');source.append(safeLink(e.url,(e.title||new URL(e.url).hostname)+' ↗'),node('blockquote','',e.quote),node('small','',`Published: ${dateLabel(e.published_at)} · Retrieved: ${dateLabel(e.observed_at)} · Source: ${e.source_family}`));detail.append(source);}
  return detail;
}
function companyCard(c,index,review=false){
  const article=node('article','company-card'),head=node('div','card-head'),title=node('div','card-title');
  head.append(node('div','company-monogram',c.name.split(/\s+/).slice(0,2).map(x=>x[0]).join('')));
  title.append(node('h3','',(review?'':`${index+1}. `)+c.name));
  if(c.official_domain)title.append(safeLink('https://'+c.official_domain,c.official_domain+' ↗'));
  const tags=node('div','card-tags');tags.append(node('span','tag',c.sector),node('span','tag',locationLabels[c.nj_presence.status]));title.append(tags);
  head.append(title,node('span','assessment'+(review?' review':''),labels[c.assessment]));article.append(head);
  const body=node('div','card-body');if(c.description)body.append(node('p','description',c.description));body.append(node('div','reason',c.why_surfaced));
  const stats=node('div','evidence-stats');for(const [value,label] of [[c.evidence_summary.external_organizations,'external organizations'],[c.evidence_summary.source_families,'source families'],[c.evidence_summary.recent_signals,'recent signals']]){const s=node('span');s.append(node('strong','',value),document.createTextNode(label));stats.append(s);}body.append(stats);
  if(c.nj_presence.evidence.length)body.append(evidenceDetail(c.nj_presence.evidence,'NJ connection · '+(c.nj_presence.location||locationLabels[c.nj_presence.status])));
  body.append(node('div','timeline-title','THE SIGNALS BEHIND THE COMPANY'));
  const timeline=node('ol','timeline');
  const signals=[...c.signals].sort((a,b)=>(b.event_date||b.evidence[0]?.published_at||'').localeCompare(a.event_date||a.evidence[0]?.published_at||''));
  for(const s of signals){
    const item=node('li','signal'),meta=node('div','signal-meta');
    const published=s.evidence.find(e=>e.published_at)?.published_at;
    meta.append(node('strong','',s.organization||pretty(s.type)),node('span','',s.event_date?dateLabel(s.event_date):published?'Reported '+dateLabel(published):'Event date unconfirmed'),node('span','',pretty(s.type)));
    if(s.status==='announced')meta.append(node('strong','','Proposed / announced'));
    item.append(meta,node('p','',s.statement),evidenceDetail(s.evidence,`${s.evidence.length} source${s.evidence.length===1?'':'s'} · ${pretty(s.source_role)}`));timeline.append(item);
  }
  if(!signals.length)timeline.append(node('li','description','No signal met the source-verification checks.'));
  body.append(timeline);
  if(c.limitations.length){const limits=node('details','limitations'),list=node('ul');limits.append(node('summary','',`Evidence limits (${c.limitations.length})`));c.limitations.forEach(l=>list.append(node('li','',l)));limits.append(list);body.append(limits);}
  article.append(body);return article;
}
function render(job){
  if(currentJob?.id===job.id && currentJob?.updated_at===job.updated_at)return;
  currentJob=job;const running=['queued','running'].includes(job.status);setBusy(running);
  if(job.mode==='live'&&job.status==='completed'&&job.cards.length)completedResearch.set(job.sector+'|'+job.requested_count,job);
  const saved=demoEnabled()&&job.mode==='live'&&!job.cards.length?savedFor(job.sector,job.requested_count):null;
  const backup=!!saved;const liveJob=job;job=saved||job;displayedJob=job;
  $('empty-state').hidden=true;$('progress').hidden=false;$('progress-title').textContent=backup&&!running?'Saved results ready':liveJob.stage;$('progress-indicator').classList.toggle('done',!running);
  $('run-mode').textContent=backup?'SAVED RESULTS · LIVE REFRESH':job.mode==='sample'||job.mode==='cached'?'SAVED RESEARCH':'LIVE RESEARCH';
  $('progress-detail').textContent=backup?(running?'Saved research stays visible while we search for live updates. Temporary interruptions retry automatically.':'Live refresh could not produce a new shortlist. Showing dated, saved research; no fresh results are being claimed.'):
    running?'Checking public sources and resolving gaps. Temporary interruptions retry automatically.':`${job.cards.length} shortlisted · ${job.review_cards.length} need review · ${job.sources.length} source pages · ${dateLabel(job.updated_at)}`;
  const activity=$('activity-list');activity.replaceChildren();liveJob.events.forEach(e=>activity.append(node('li','',e.message)));
  if(liveJob.error)activity.append(node('li','',liveJob.error));
  notice(backup?'':liveJob.error);$('results').hidden=false;$('results-kicker').textContent=job.mode==='sample'?'SAVED PUBLIC RESEARCH · SEPTEMBER 25, 2026':(job.mode==='cached'?'SAVED RESULTS · ':'YOUR RESEARCH · ')+dateLabel(job.created_at).toUpperCase();
  const summary=$('summary');summary.replaceChildren();for(const [count,label] of [[job.cards.length,'Shortlisted companies'],[job.sources.length,'Source pages read'],[job.review_cards.length,'Companies needing review']]){const stat=node('div','stat');stat.append(node('strong','',count),node('span','',label));summary.append(stat);}
  const clusters={};job.cards.forEach(c=>clusters[c.sector]=(clusters[c.sector]||0)+1);$('clusters').replaceChildren(...Object.entries(clusters).map(([s,n])=>node('span','cluster',`${s} · ${n}`)));
  $('cards').replaceChildren(...job.cards.map((c,i)=>companyCard(c,i)));
  if(!job.cards.length)$('cards').append(node('p','description',running?'Assessing candidates…':'No company met the shortlist criteria in this run. Review the evidence gaps below or try another sector.'));
  $('review-section').hidden=!job.review_cards.length;$('review-cards').replaceChildren(...job.review_cards.map((c,i)=>companyCard(c,i,true)));
  $('warnings').replaceChildren(...job.warnings.map(w=>node('p','',w)));
}
async function loadJob(id,generation=++viewGeneration){
  clearTimeout(timer);
  try{const job=await api('/jobs/'+id);if(generation!==viewGeneration)return;pollFailures=0;render(job);if(['queued','running'].includes(job.status))timer=setTimeout(()=>loadJob(id,generation),2500);else await loadHistory();}
  catch(error){if(generation!==viewGeneration)return;pollFailures++;refreshUnavailable('Connection interrupted. The results already shown are retained; reconnecting automatically.');if(pollFailures<=3)timer=setTimeout(()=>loadJob(id,generation),Math.min(2000*2**pollFailures,15000));else refreshUnavailable('Connection is still unavailable. Saved research remains ready; Find NJ startups will reconnect.');}
}
async function start(mode){
  clearTimeout(timer);viewGeneration++;pollFailures=0;notice('');
  if(mode==='sample'){if(showSaved())return;}
  if(demoEnabled())showSaved();setBusy(true);
  if(demoEnabled()&&displayedJob){$('progress-title').textContent='Refreshing live research';$('progress-detail').textContent='Your saved results stay available while the live search runs.';}
  try{const result=await api('/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:Number($('count').value),sector:$('sector').value,mode,request_id:crypto.randomUUID()})});await loadJob(result.id);}
  catch(error){if(error.status===409&&error.data.id){await loadJob(error.data.id);}else{refreshUnavailable(demoEnabled()?'Live refresh is unavailable. Your saved research is ready to present.':error.message);}}
}
async function loadHistory(){
  try{const data=await api('/jobs');$('history-section').hidden=!data.jobs.length;$('history-list').replaceChildren(...data.jobs.map(j=>{const button=node('button','',`${j.mode==='sample'?'Saved preview':'Live research'} · ${j.qualified_count} qualified · ${pretty(j.status)} · ${dateLabel(j.created_at)}`);button.type='button';button.addEventListener('click',()=>loadJob(j.id));return button;}));return data.jobs;}
  catch(error){if(error.status!==401&&!demoEnabled())notice(error.message);return [];}
}
async function initialize(){
  try{const response=await fetch('/reputation/demo.json');if(!response.ok)throw new Error();bundledResearch=await response.json();if(demoEnabled())showSaved();}
  catch{notice('Saved research could not be loaded. Live research is still available when connected.');}
  try{const status=await api('/status');connected=status.gemini_configured&&status.search_configured;$('access-form').hidden=!status.access_token_required;$('connection').textContent=connected?'Live research ready · Allow a few minutes per run':'Live research needs backend configuration. Saved research is available.';setBusy(false);const history=await loadHistory();const active=history.find(j=>['queued','running'].includes(j.status));if(active)await loadJob(active.id);}
  catch(error){connected=false;setBusy(false);refreshUnavailable('Live service is unavailable. Saved research is ready to present.');$('connection').textContent='Saved research ready · Live connection unavailable';}
}
$('search-form').addEventListener('submit',e=>{e.preventDefault();start('live');});
$('sample-button').addEventListener('click',()=>start('sample'));
$('demo-protection').addEventListener('change',()=>{const job=currentJob;currentJob=null;if(demoEnabled())showSaved();else if(job)render(job);});
for(const id of ['sector','count'])$(id).addEventListener('change',()=>{if(demoEnabled()&&!busy)showSaved();});
$('access-form').addEventListener('submit',async e=>{e.preventDefault();token=$('access-token').value;$('access-token').value='';try{await api('/jobs');notice('');$('access-form').hidden=true;await loadHistory();}catch(error){notice(error.message);}});
$('download-button').addEventListener('click',()=>{if(!displayedJob)return;const url=URL.createObjectURL(new Blob([JSON.stringify(displayedJob,null,2)],{type:'application/json'})),a=node('a');a.href=url;a.download=`nj-reputation-${displayedJob.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
initialize();
