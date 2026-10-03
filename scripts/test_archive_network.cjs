const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/archive.js','utf8');
const requestSource=source.slice(source.indexOf('async function request('),source.indexOf('function normalize('));
async function test(){
 let calls=0;const context=vm.createContext({api:'https://server.example',setTimeout:fn=>fn(),fetch:async()=>{calls++;if(calls<3)throw new TypeError('Failed to fetch');return {ok:true,status:200,json:async()=>({ok:true})}}});
 vm.runInContext(requestSource,context);
 assert.equal((await vm.runInContext("request('/api/archive')",context)).ok,true);assert.equal(calls,3);
 calls=0;context.fetch=async()=>{calls++;throw new TypeError('Failed to fetch')};
 await assert.rejects(()=>vm.runInContext("request('/possessions',{method:'POST',body:'{}'})",context),/проверьте результат операции/);assert.equal(calls,1);
 calls=0;context.fetch=async(_url,options)=>{calls++;assert(!options.headers['Content-Type']);return {ok:false,status:410,json:async()=>({error:'Ссылка истекла'})}};
 await assert.rejects(()=>vm.runInContext("request('/portal/invalid')",context),/Ссылка истекла/);assert.equal(calls,1);
 console.log('Archive network: transient GET retries, no POST retry, no unnecessary preflight and preserved authentication errors OK');
}
test().catch(error=>{console.error(error);process.exitCode=1});
