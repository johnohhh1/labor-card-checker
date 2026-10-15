import * as pdfjs from '/vendor/pdf.js';
pdfjs.GlobalWorkerOptions.workerSrc='/vendor/pdf.worker.js';
const worker=new Worker('/review-worker.js');
let nextId=0, busy=false, previewVersion=0;
const pending=new Map(), originals=[];
worker.onmessage=({data})=>{
  if(data.progress){document.getElementById('status').textContent=data.progress;return}
  const p=pending.get(data.id);if(!p)return;pending.delete(data.id);busy=false;
  if(data.error)p.reject(Error(data.error));else p.resolve(data.result);
};
worker.onerror=()=>{for(const p of pending.values())p.reject(Error('The reviewer could not start. Refresh the page and try again.'));pending.clear();busy=false};
function engineRequest(body){
  if(busy)return Promise.reject(Error('A review is still running. Please wait.'));
  busy=true;const id=++nextId;
  return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});worker.postMessage({id,body})});
}
async function prepareFiles(files){
  for(const pdf of originals)if(pdf)await pdf.destroy();originals.length=0;
  const result=await Promise.all(files.map(fileData));
  // Keep previews aligned with successfully parsed documents, including mixed-file errors.
  window.reviewSources=new Map(files.map((file,i)=>[file.name,result[i].data]));
  return result;
}
async function renderPreview(x){
  const version=++previewVersion;
  if(!originals[x.doc]){
    const source=window.reviewSources.get(review.documents[x.doc].name);
    const bytes=Uint8Array.from(atob(source),c=>c.charCodeAt(0));
    originals[x.doc]=await pdfjs.getDocument({data:bytes,standardFontDataUrl:'/vendor/standard_fonts/',isEvalSupported:false}).promise;
  }
  const page=await originals[x.doc].getPage(x.data.page+1);
  const viewport=page.getViewport({scale:1.6});
  const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;
  await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
  if(version===previewVersion)document.getElementById('preview').src=canvas.toDataURL('image/png');
}
document.getElementById('export').onclick=async event=>{
  event.preventDefault();if(!review||busy)return;
  const button=event.currentTarget;button.textContent='Preparing download…';
  try{
    const result=await engineRequest({action:'export',settings});
    const bytes=Uint8Array.from(atob(result),c=>c.charCodeAt(0));
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));
    const link=document.createElement('a');link.href=url;link.download='labor-card-review.pdf';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),60000);
    document.getElementById('status').textContent='Marked-up cards downloaded.';
  }catch(e){document.getElementById('status').textContent=e.message}
  finally{button.textContent='Download marked-up cards'}
};
