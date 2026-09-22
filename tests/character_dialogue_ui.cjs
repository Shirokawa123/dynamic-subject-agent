// Focused regression: successful delivery needs no second status request;
// an ambiguous delivery keeps its exact key and message for explicit replay.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/desktop/character_dialogue_lab.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
async function check(ambiguous) {
  const nodes = new Map();
  const element = () => ({value:'',checked:true,disabled:false,textContent:'',children:[],
    querySelector(){return null;},append(child){this.children.push(child);}});
  const get = id => {if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  let statusReads=0, ids=0;
  const sent=[];
  const sandbox={document:{getElementById:get,createElement:element},crypto:{randomUUID:()=>`key-${++ids}`},
    fetch:async(url,options)=>{
      if(url==='/plan')return {json:async()=>({plan:{character_context:{known_background:['test'],interaction_setup:'setup',expression_guidance:'style',unknown_context:'unknown'}},digest:'d'})};
      if(url==='/status'){
        if(++statusReads>1)throw Error('status is now unavailable');
        return {ok:true,json:async()=>({lab_id:'lab',revision:0,attempts:0,history_enabled:true})};
      }
      const body=JSON.parse(options.body);sent.push(body);
      if(ambiguous && sent.length===1)throw Error('delivery result unknown');
      return {ok:true,json:async()=>({status:'replied',reply_text:'reply',lab_id:'lab',
        revision:1,attempts:1,history_enabled:false})};
    }};
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  await new Promise(resolve=>setImmediate(resolve));
  get('message').value='hello';
  await get('form').onsubmit({preventDefault(){}});
  if(ambiguous){
    assert.equal(get('message').value,'hello');
    assert.equal(get('message').disabled,true);
    await get('form').onsubmit({preventDefault(){}});
    assert.deepEqual(sent[1],sent[0]);
  }
  assert.equal(statusReads,1);
  assert.equal(get('send').textContent,'发送');
  assert.equal(get('history').checked,false);
  assert.equal(get('message').value,'');
  get('message').value='next';
  await get('form').onsubmit({preventDefault(){}});
  assert.equal(sent.at(-1).revision,1);
  assert.equal(sent.at(-1).use_history,false);
}
async function checkBasis(status) {
  const nodes=new Map(), calls=[];
  const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'drawing-origins',checked:true,disabled:false,textContent:''});return nodes.get(id);};
  const sandbox={document:{getElementById:get},fetch:async(url,options)=>{
    calls.push(url);
    if(url==='/status')return {ok:true,json:async()=>({attempts:0,history_enabled:true})};
    if(url==='/plan')return {json:async()=>({plan:{character_context:{known_background:['test']}},digest:'d'})};
    assert.equal(url,'/basis-preview');
    assert.equal(get('basis-topic').disabled,true);
    assert.deepEqual(JSON.parse(options.body),{topic:'drawing-origins'});
    return {ok:true,json:async()=>({status,code:'basis-integrity-failed',
      selected:status==='ready'?[{title:'材料',text:'摘要',citations:['p1']}]:[],
      excluded:[{title:'另一项',reason:'wrong-subject'}]})};
  }};
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  await new Promise(resolve=>setImmediate(resolve));
  await get('preview-basis').onclick();
  assert.equal(get('basis-topic').disabled,false);
  assert.equal(get('preview-basis').disabled,false);
  assert.equal(calls.includes('/send'),false);
  if(status==='ready')assert.match(get('basis-result').textContent,/摘要[\s\S]*属于其他角色/);
  else if(status==='no-op')assert.match(get('basis-result').textContent,/未选择人物往事/);
  else assert.match(get('basis-result').textContent,/材料或出处已变化/);
}
(async()=>{await check(false);await check(true);for(const state of ['ready','no-op','failed-closed'])await checkBasis(state);console.log('character dialogue UI: 5 scenarios passed');})().catch(error=>{console.error(error);process.exitCode=1;});
