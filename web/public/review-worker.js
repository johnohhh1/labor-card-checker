importScripts('/runtime/pyodide.js');
let engine;
async function ready(){
  if(!engine)engine=(async()=>{
    postMessage({progress:'Preparing the reviewer for this browser…'});
    const py=await loadPyodide({indexURL:'/runtime/'});
    await py.loadPackage(['micropip','pillow','cryptography']);
    const manifest=await (await fetch('/wheels.json')).json();
    py.globals.set('wheel_urls',manifest.map(file=>new URL('/wheels/'+file,self.location.href).href));
    await py.runPythonAsync('import micropip\nawait micropip.install(wheel_urls.to_py(),deps=False)');
    for(const file of ['analyzer.py','browser_bridge.py'])py.FS.writeFile('/home/pyodide/'+file,await(await fetch('/'+file)).text());
    py.runPython('from browser_bridge import execute');
    return py;
  })().catch(e=>{engine=null;throw e});
  return engine;
}
self.onmessage=async({data})=>{
  try{const py=await ready();postMessage({progress:data.body.action==='export'?'Preparing marked-up cards…':'Checking roster assignments…'});py.globals.set('payload',JSON.stringify(data.body));const result=py.runPython('execute(payload)');postMessage({id:data.id,result});}
  catch(e){postMessage({id:data.id,error:String(e.message||e).split('\n').slice(-3).join(' ')});}
};
