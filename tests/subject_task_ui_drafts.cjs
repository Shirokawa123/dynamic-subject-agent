const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('app/desktop/static/index.html','utf8').replace(/\r\n/g,'\n');
const script=html.slice(html.indexOf('const taskScreen ='),html.indexOf('(async () => {\n  const snapshot = await refreshSetup();'));
class Element{constructor(){this.value='';this.children=[];}append(...v){this.children.push(...v);}replaceChildren(){this.children=[];}}
const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
let profile='identity-a';const posts=[];
const context=vm.createContext({document:{getElementById:get,createElement:()=>new Element()},crypto:{randomUUID:()=> '01234567-89ab-cdef-0123-456789abcdef'},refreshState:async()=>true,
fetch:async(url,options)=>{if(options){posts.push(JSON.parse(options.body));return {json:async()=>({ok:true,message:'accepted'})};}return {json:async()=>({ok:true,enabled:true,profile_id:profile,tasks:[]})};}});
vm.runInContext(script,context);
(async()=>{await context.refreshTasks();get('task-kind').value='draft_text';get('task-message').value='draft-a';get('task-content').value='private-a';
profile='identity-b';await context.refreshTasks();assert.equal(get('task-message').value,'');assert.equal(get('task-content').value,'');
get('task-message').value='draft-b';await get('task-submit').onclick();assert.equal(posts[0].expected_profile_id,'identity-b');assert.equal(posts[0].content,'');
profile='identity-a';await context.refreshTasks();assert.equal(get('task-message').value,'draft-a');assert.equal(get('task-content').value,'private-a');console.log('identity draft isolation passed');})().catch(e=>{console.error(e);process.exitCode=1;});
