const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function check(days,expected,start='2026-10-08',expired=false){
 const downloaded=[],progress=[],notices=[],badges=[];let reportDate;const stored={running:true};
 const context=vm.createContext({URL,Date,Promise,Set,Error,setTimeout:fn=>{fn()},chrome:{
  runtime:{onMessage:{addListener(){}},onStartup:{addListener(){}}},
  action:{setBadgeText:async value=>badges.push(value.text),setBadgeBackgroundColor:async()=>{}},
  notifications:{onClicked:{addListener(){}},clear:async()=>{},create:async(id,value)=>notices.push({id,...value})},
  storage:{local:{get:async()=>({...stored}),set:async value=>{Object.assign(stored,value);if(value.status)progress.push(value.status)}}},
  tabs:{query:async()=>[{id:1}],create:async()=>({id:2}),remove:async()=>{}},
  debugger:{attach:async()=>{},detach:async()=>{},sendCommand:async(_,method,params)=>{
   if(method==='Page.navigate')reportDate=new URL(params.url).searchParams.get('startDate');
   if(method==='Runtime.evaluate'){const d=new Date(reportDate+' 12:00:00');return {result:{value:JSON.stringify({url:expired?'https://app.hotschedules.com/hs/login.jsp':'https://app.hotschedules.com/hs/report.hs',ready:'complete',text:'Labor Card for '+d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'})+' Total [Day]'})}}}
   if(method==='Page.printToPDF')return {data:'JVBERtest'};
  }},
  downloads:{download:async opts=>{downloaded.push(opts.filename);return downloaded.length},search:async()=>[{state:'complete'}]}
 }});
 vm.runInContext(fs.readFileSync(__dirname+'/worker.js','utf8'),context);
 await context.start(start,days);
 assert.deepEqual(downloaded.map(name=>name.match(/labor-card-(.*)\.pdf/)[1]),expected);
 if(expected.length)assert(progress.at(-1).startsWith('Saved '+expected.length+' PDF'));
 if(expired){assert.equal(notices.length,1);assert.equal(notices[0].title,'HotSchedules login expired');assert.equal(badges.at(-1),'!');assert.equal(stored.running,false);}else assert.equal(notices.length,0);
 return progress;
}
(async()=>{
 await check([1,2,3],['2026-10-09','2026-10-10','2026-10-11']);
 await check(undefined,Array.from({length:7},(_,i)=>'2026-10-'+String(8+i).padStart(2,'0')));
 await check([6,1,1],['2026-10-30','2026-11-04'],'2026-10-29');
 assert((await check([],[])).at(-1).includes('valid day'));
 assert((await check([7],[])).at(-1).includes('valid day'));
 await check([1,2,3],[],'2026-10-08',true);
 console.log('Passed: recovery from stale running state, weekend selection, default full week, month boundary, duplicates, and empty/invalid selection.');
})().catch(e=>{console.error(e);process.exitCode=1});
