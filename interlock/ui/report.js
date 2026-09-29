"use strict";
const search=document.getElementById('find'),group=document.getElementById('group'),rows=Array.from(document.querySelectorAll('.report-card')),count=document.getElementById('matches');
function filter(){let shown=0;for(const row of rows){row.hidden=!(row.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!group.value||row.dataset.group===group.value));if(!row.hidden)shown++;}count.textContent=shown+' of '+rows.length+' report rows shown';document.getElementById('empty').hidden=shown!==0;}
search.addEventListener('input',filter);group.addEventListener('change',filter);document.getElementById('theme').addEventListener('click',event=>{const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';event.currentTarget.textContent=dark?'Light theme':'Dark theme';event.currentTarget.setAttribute('aria-pressed',String(dark));});document.getElementById('download').addEventListener('click',()=>{const text=document.getElementById('report-data').textContent,url=URL.createObjectURL(new Blob([text],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='review-report.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});filter();

// A focused display export excludes the complete payload and editable draft inputs.
document.getElementById('download-view').addEventListener('click',()=>{
  const visible=rows.filter(row=>!row.hidden),output=document.implementation.createHTMLDocument(document.title+' — Visible rows');
  const charset=output.createElement('meta');charset.setAttribute('charset','utf-8');
  const viewport=output.createElement('meta');viewport.name='viewport';viewport.content='width=device-width,initial-scale=1';
  const policy=output.createElement('meta');policy.httpEquiv='Content-Security-Policy';policy.content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
  const style=output.createElement('style');style.textContent=document.querySelector('style').textContent;output.head.append(charset,viewport,policy,style);
  const main=output.createElement('main'),title=output.createElement('h1'),notice=output.createElement('p');title.textContent=document.title;
  notice.textContent=visible.length+' of '+rows.length+' captured rows included. Other rows are omitted. Static display only; not native evidence JSON or fresh verification. Draft inputs are excluded.';
  main.append(title,notice);
  for(const scope of document.querySelectorAll('.critical-summary,.scope'))main.append(scope.cloneNode(true));
  for(const row of visible){const copy=row.cloneNode(true);copy.hidden=false;main.append(copy);}
  output.body.append(main);
  const blob=new Blob(['<!doctype html>'+output.documentElement.outerHTML],{type:'text/html;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='captured-visible-rows.html';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

// Presentation ordering only: native evidence and explicit saved search/group views stay unchanged.
(()=>{
  const section=document.querySelector('section[aria-label="Report results"]');
  const original=[...rows],positions=new Map(original.map((row,index)=>[row,index]));
  const panel=document.createElement('details');panel.className='saved-review-views';
  const summary=document.createElement('summary');summary.textContent='Order captured cards';
  const controls=document.createElement('div');controls.className='review-view-controls';
  const label=document.createElement('label'),choice=document.createElement('select');
  choice.setAttribute('aria-label','Order report cards by');label.append(document.createTextNode('Order report cards by'),choice);
  const initial=document.createElement('option');initial.value='';initial.textContent='Captured order';choice.append(initial);
  for(const [index,term] of [...(original[0]?.querySelectorAll('dt')||[])].entries()){
    const option=document.createElement('option');option.value=String(index);option.textContent=term.textContent;choice.append(option);
  }
  const reverse=document.createElement('button');reverse.type='button';reverse.textContent='Reverse card order';reverse.disabled=true;reverse.setAttribute('aria-pressed','false');
  const note=document.createElement('p');note.textContent='Natural text order of displayed values only, not numeric analysis, evidence priority or fresh verification. Equal values retain captured order. Search/group presets do not capture card order; native JSON keeps original order.';
  let descending=false;const collator=new Intl.Collator('en',{numeric:true,sensitivity:'variant'});
  function order(){
    reverse.disabled=choice.value==='';reverse.setAttribute('aria-pressed',String(descending));
    const index=Number(choice.value);
    rows.sort((one,two)=>{if(choice.value==='')return positions.get(one)-positions.get(two);
      const values=[one,two].map(row=>row.querySelectorAll('dd')[index]?.textContent||'');
      return collator.compare(values[0],values[1])*(descending?-1:1)||positions.get(one)-positions.get(two);});
    for(const row of rows)section.append(row);filter();
  }
  choice.addEventListener('change',()=>{descending=false;order();});reverse.addEventListener('click',()=>{descending=!descending;order();});
  window.addEventListener('pageshow',order);controls.append(label,reverse);panel.append(summary,controls,note);section.before(panel);
})();
