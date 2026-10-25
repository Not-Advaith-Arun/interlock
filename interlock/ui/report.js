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
