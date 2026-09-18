const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('app/desktop/static/index.html','utf8').replace(/\r\n/g,'\n');
const script=html.slice(html.indexOf('const taskScreen ='),html.indexOf('(async () => {\n  const snapshot = await refreshSetup();'));
class Element{constructor(){this.value='';this.children=[];}append(...v){this.children.push(...v);}replaceChildren(){this.children=[];}}
const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
let profile='identity-a';const posts=[];let serial=0;
const records=[{task_id:'task-a',revision:1,kind:'draft_text',summary:'A',status:'accepted',request_text:'edit-a',content:''},{task_id:'task-b',revision:1,kind:'draft_text',summary:'B',status:'deferred',request_text:'edit-b',content:''}];
const context=vm.createContext({document:{getElementById:get,createElement:()=>new Element()},crypto:{randomUUID:()=> '01234567-89ab-cdef-0123-'+String(++serial).padStart(12,'0')},refreshState:async()=>true,
fetch:async(url,options)=>{if(options){posts.push(JSON.parse(options.body));return {json:async()=>({ok:true,changed:true,message:'accepted'})};}return {json:async()=>({ok:true,enabled:true,profile_id:profile,tasks:records})};}});
vm.runInContext(script,context);
(async()=>{await context.refreshTasks();let cards=get('task-list').children;cards[1].children[2].onclick();await cards[0].children[3].onclick();await get('task-submit').onclick();assert.equal(posts[1].action,'revise');assert.equal(posts[1].task_id,'task-a');console.log('unrelated cancellation keeps edit context');})().catch(e=>{console.error(e);process.exitCode=1;});
