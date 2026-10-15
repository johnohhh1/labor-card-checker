const run=document.querySelector('#run'),status=document.querySelector('#status');
const days=[...document.querySelectorAll('.days input')];let running=false;
function refresh(){const count=days.filter(day=>day.checked).length;run.textContent=count===7?'Download seven PDFs':`Download ${count} PDF${count===1?'':'s'}`;run.disabled=running||!count;}
const today=new Date();today.setDate(today.getDate()-((today.getDay()-4+7)%7));document.querySelector('#start').value=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
chrome.storage.local.get(['status','running','start'],s=>{status.textContent=s.status||'';running=!!s.running;if(s.start)document.querySelector('#start').value=s.start;refresh();});
chrome.storage.onChanged.addListener(s=>{if(s.status)status.textContent=s.status.newValue;if(s.running){running=!!s.running.newValue;refresh();}});
for(const day of days)day.onchange=refresh;
document.querySelector('#all').onclick=()=>{days.forEach(day=>day.checked=true);refresh();};
document.querySelector('#varsity').onclick=()=>{days.forEach(day=>day.checked=[1,2,3].includes(Number(day.value)));refresh();};
run.onclick=async()=>{const start=document.querySelector('#start').value;const d=new Date(start+'T12:00:00');if(!start||d.getDay()!==4){status.textContent='Choose a Thursday.';return;}const selectedDays=days.filter(day=>day.checked).map(day=>Number(day.value));if(!selectedDays.length){status.textContent='Choose at least one day.';return;}running=true;refresh();status.textContent='Starting your download…';try{const reply=await chrome.runtime.sendMessage({type:'run',start,days:selectedDays});if(!reply?.started)throw Error('The extension did not start. Reload Weekly Labor Cards in chrome://extensions.');const state=await chrome.storage.local.get(['running','status']);running=!!state.running;if(state.status)status.textContent=state.status;refresh();}catch(e){running=false;refresh();status.textContent=e.message;}};
