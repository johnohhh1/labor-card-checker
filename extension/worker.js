const ORIGIN='https://app.hotschedules.com';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
// A reload ends the old worker, so its persisted running flag is stale.
const bootReady=chrome.storage.local.set({running:false});
const LOGIN_NOTICE='hotschedules-login-expired';
async function loginExpiredNotice(){
 await chrome.action.setBadgeBackgroundColor({color:'#b3261e'}).catch(()=>{});
 await chrome.action.setBadgeText({text:'!'}).catch(()=>{});
 await chrome.notifications.create(LOGIN_NOTICE,{type:'basic',iconUrl:'notification.png',title:'HotSchedules login expired',message:'Your labor-card download stopped. Sign in to HotSchedules, then run it again. Completed PDFs are still saved.',priority:2,requireInteraction:true}).catch(()=>{});
}
chrome.notifications.onClicked.addListener(id=>{if(id===LOGIN_NOTICE){chrome.tabs.create({url:ORIGIN+'/hs/login.jsp'});chrome.notifications.clear(id);}});
chrome.runtime.onMessage.addListener((m,s,reply)=>{if(m.type==='run'){start(m.start,m.days).catch(async e=>{await chrome.storage.local.set({running:false,status:'Stopped: '+e.message});});reply({started:true});}});
async function start(date,selectedDays){
 await bootReady;
 const state=await chrome.storage.local.get('running');if(state.running)return;
 const first=new Date(date+'T12:00:00');if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||first.getDay()!==4){await chrome.storage.local.set({status:'Choose a Thursday.'});return;}
 const requested=selectedDays===undefined?[0,1,2,3,4,5,6]:selectedDays;
 if(!Array.isArray(requested)||!requested.length||requested.some(day=>!Number.isInteger(day)||day<0||day>6)){await chrome.storage.local.set({status:'Choose at least one valid day.'});return;}
 const days=[...new Set(requested)].sort((a,b)=>a-b);
 await chrome.action.setBadgeText({text:''}).catch(()=>{});
 await chrome.notifications.clear(LOGIN_NOTICE).catch(()=>{});
 let tab,attached=false;
 await chrome.storage.local.set({running:true,start:date,status:'Preparing your reports…'});
 try{
  const existing=await chrome.tabs.query({url:ORIGIN+'/*'});
  if(!existing.length)throw Error('Open HotSchedules in Chrome and sign in, then try again.');
  tab=await chrome.tabs.create({url:ORIGIN+'/hs/menuParser.hs?screen=newReporting&sub_heading=scheduleReport&type=33',active:false});
  await chrome.debugger.attach({tabId:tab.id},'1.3');attached=true;
  const send=(method,params={})=>chrome.debugger.sendCommand({tabId:tab.id},method,params);
  await send('Page.enable');
  for(const [position,i] of days.entries()){
   const d=new Date(first);d.setDate(d.getDate()+i);
   const iso=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
   const display=(d.getMonth()+1)+'/'+d.getDate()+'/'+d.getFullYear();
   await chrome.storage.local.set({status:'Saving '+iso+' ('+(position+1)+' of '+days.length+')…'});
   const url=new URL(ORIGIN+'/hs/report.hs');
   for(const [k,v]of Object.entries({blank:'true',reportType:'33',newReportUI:'1',startDate:display,endDate:display,svrid:'13',timestamp:String(Date.now())}))url.searchParams.set(k,v);
   await send('Page.navigate',{url:url.href});
   let ready=false;
   for(let n=0;n<60;n++){
    await sleep(500);
    const result=await send('Runtime.evaluate',{expression:`JSON.stringify({url:location.href,ready:document.readyState,text:document.body?.innerText||''})`,returnByValue:true});
    if(!result.result.value)continue;
    const page=JSON.parse(result.result.value);
    if(/login|signin/i.test(page.url)){const error=Error('Your HotSchedules session expired. Sign in and try again.');error.code='LOGIN_EXPIRED';throw error;}
    const expected=d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});
    if(page.ready==='complete'&&page.text.includes('Labor Card for')&&page.text.includes(expected)&&page.text.includes('Total [Day]')){ready=true;break;}
   }
   if(!ready)throw Error('The report for '+iso+' did not load or did not match the expected date.');
   await send('Emulation.setEmulatedMedia',{media:'print'});
   const pdf=await send('Page.printToPDF',{landscape:true,printBackground:true,paperWidth:8.5,paperHeight:11,marginTop:0.25,marginBottom:0.25,marginLeft:0.25,marginRight:0.25,scale:0.75,preferCSSPageSize:false});
   if(!pdf.data?.startsWith('JVBER'))throw Error('Invalid PDF returned for '+iso);
   const download=await chrome.downloads.download({url:'data:application/pdf;base64,'+pdf.data,filename:'Labor Cards/'+date+'/labor-card-'+iso+'.pdf',saveAs:false,conflictAction:'uniquify'});
   let finished=false;
   for(let n=0;n<60;n++){const [item]=await chrome.downloads.search({id:download});if(item?.state==='complete'){finished=true;break;}if(item?.state==='interrupted')throw Error('Download failed for '+iso+': '+item.error);await sleep(500);}
   if(!finished)throw Error('Download did not finish for '+iso+'. Check Chrome Downloads.');
  }
  await chrome.storage.local.set({status:'Saved '+days.length+' PDF'+(days.length===1?'':'s')+' in Downloads/Labor Cards/'+date+'.'});
 }catch(e){await chrome.storage.local.set({status:'Stopped: '+e.message+'\nCompleted files stay in your Downloads folder.'});if(e.code==='LOGIN_EXPIRED')await loginExpiredNotice();}
 finally{if(attached)await chrome.debugger.detach({tabId:tab.id}).catch(()=>{});if(tab)await chrome.tabs.remove(tab.id).catch(()=>{});await chrome.storage.local.set({running:false});}
}
chrome.runtime.onStartup.addListener(()=>chrome.storage.local.set({running:false}));
