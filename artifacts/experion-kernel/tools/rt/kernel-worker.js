// @artifact dev
// Private child-process NDJSON protocol. No HTTP listener, model calls, or DB access.
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const K=require('../../src/plant-kernel'),Projection=require('../../src/plant-projection');
const manifestPath=path.resolve(process.argv[2]);const manifest=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
const root=path.dirname(manifestPath);
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
for(const [name,expected] of Object.entries(manifest.files)){
 const p=path.resolve(root,name);if(!p.startsWith(root+path.sep)||hash(fs.readFileSync(p))!==expected)throw Error('artifact_hash_mismatch');
}
if(process.versions.node.split('.').slice(0,2).join('.')!==manifest.node_runtime)throw Error('runtime_mismatch');
let buffer=Buffer.alloc(0);
function stateResult(state){const bytes=K.stable(state);return {state_bytes:bytes,state_hash:hash('peb:plant-state:v1\0'+bytes),tick:state.tick};}
function run(q){
 switch(q.operation){
 case 'hello':return {protocol:'peb.kernel.v1',manifest_hash:hash(fs.readFileSync(manifestPath)),model_id:manifest.model_id,node_runtime:manifest.node_runtime};
 case 'restore':return stateResult(q.state_bytes?K.capture(K.restore(JSON.parse(q.state_bytes))):K.create(q.initial||{}));
 case 'compute_tick':{if(hash('peb:plant-state:v1\0'+q.state_bytes)!==q.expected_hash)throw Error('input_hash_mismatch');const result=K.advance(JSON.parse(q.state_bytes),.5,q.commands||[]);return {...stateResult(result.state),outcomes:result.outcomes,board:Projection.project(result.state,'operator'),subject:Projection.project(result.state,'subject')};}
 case 'project':return Projection.project(JSON.parse(q.state_bytes),q.role,q.ownership);
 case 'shutdown':process.exitCode=0;process.stdin.pause();return {stopped:true};
 default:throw Error('unknown_operation');
 }
}
process.stdin.on('data',chunk=>{
 buffer=Buffer.concat([buffer,chunk]);if(buffer.length>64*1024*1024)process.exit(2);
 let i;while((i=buffer.indexOf(10))>=0){const line=buffer.subarray(0,i).toString('utf8');buffer=buffer.subarray(i+1);let q;
 try{q=JSON.parse(line);process.stdout.write(JSON.stringify({id:q.id,ok:true,result:run(q)})+'\n');}
 catch(e){process.stdout.write(JSON.stringify({id:q&&q.id,ok:false,error:String(e.message).slice(0,120)})+'\n');}
 }
});
