const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('app/desktop/static/index.html','utf8').replace(/\r\n/g,'\n');
const script=html.slice(html.indexOf('const taskScreen ='),html.indexOf('(async () => {\n  const snapshot = await refreshSetup();'));
class Element{constructor(){this.value='';this.children=[];this.hidden=true;}append(...v){this.children.push(...v);}replaceChildren(){this.children=[];}}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
let profile='identity-a',serial=0;const posts=[];
const record={task_id:'task-a',revision:1,kind:'save_text',summary:'A',status:'accepted',request_text:'保存正文',content:'exact\nbody'};
const context=vm.createContext({document:{getElementById:get,createElement:()=>new Element()},crypto:{randomUUID:()=>String(++serial)},refreshState:async()=>true,
fetch:async(url,options)=>{if(options){const p=JSON.parse(options.body);posts.push(p);return {json:async()=>p.action==='preview'?{ok:true,profile_id:profile,preview:{task_id:'task-a',revision:1,basis:'a'.repeat(64),directory:'managed',filename:'task.txt',content:record.content}}:{ok:true,message:'saved'}};}
return {json:async()=>({ok:true,enabled:true,effects_enabled:true,profile_id:profile,tasks:[record]})};}});
vm.runInContext(script,context);
(async()=>{
 await context.refreshTasks();await get('task-list').children[0].children[4].onclick();
 assert.deepEqual(posts.map(p=>p.action),['preview']);assert.equal(get('artifact-content').textContent,record.content);
 get('artifact-dismiss').onclick();assert.equal(get('artifact-preview').hidden,true);assert.equal(posts.length,1);
 await get('task-list').children[0].children[4].onclick();profile='identity-b';await context.refreshTasks();
 await get('artifact-confirm').onclick();assert.equal(posts.length,2);assert.equal(get('artifact-preview').hidden,true);
 profile='identity-a';await context.refreshTasks();await get('task-list').children[0].children[4].onclick();
 await get('artifact-confirm').onclick();assert.equal(posts[3].action,'approve');assert.equal(posts[3].expected_profile_id,'identity-a');
 assert.equal(posts[3].basis,'a'.repeat(64));assert.equal(posts[3].revision,1);assert.ok(posts[3].idempotency_key);
 console.log('preview requires explicit confirmation; dismissed and cross-identity previews cannot save');
})().catch(e=>{console.error(e);process.exitCode=1;});
