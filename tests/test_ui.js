// View-generation and expression regression checks without browser dependencies.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let code=fs.readFileSync(require('path').join(__dirname,'../web/app.js'),'utf8');
code+='\n'+fs.readFileSync(require('path').join(__dirname,'../web/studio.js'),'utf8');
code+='\n'+fs.readFileSync(require('path').join(__dirname,'../web/advanced.js'),'utf8');
for(let f of ['workspace.js','graphics.js','music_engine.js','music.js','workflow14.js'])code+='\n'+fs.readFileSync(require('path').join(__dirname,'../web/'+f),'utf8');
let mock={innerHTML:'',textContent:'',style:{},hidden:true,addEventListener(){},querySelector(){return null}};
let ctx=vm.createContext({console,document:{querySelector(){return mock},querySelectorAll(){return[]},addEventListener(){},activeElement:{tagName:'BODY'}},window:{addEventListener(){}},localStorage:{getItem(){return null}},setTimeout,clearTimeout,setInterval,clearInterval,URL,structuredClone});vm.runInContext(code,ctx);
ctx.project=JSON.parse(fs.readFileSync(require('path').join(__dirname,'../projects/demo/project.json'),'utf8'));
vm.runInContext('P = project; assets=[{name:"anna.png",size:100},{name:"court.png",size:100}];',ctx);
for(let name of ['homeView','importView','storyView','charactersView','assetsView','artView','cinemaView','interfaceView','minigamesView','steamView','exportView','audioView','builderView','graphicsView','musicView','helpView']){let html=vm.runInContext(name+'()',ctx);assert(html.length>100,name);assert(!html.includes('undefined'),name+' undefined');console.log('PASS view',name)}
for(let [expr,expected] of [['trust >= 2 and not day == 3',true],['trust + 2 * 4',11],['1 < trust < 5',true],['"привет"', 'привет'],['not False or False',true]])assert.strictEqual(vm.runInContext('evalExpr('+JSON.stringify(expr)+', {trust:3,day:1})',ctx),expected);
for(let expr of ['window.alert(1)','trust.constructor','__import__("os")'])assert.throws(()=>vm.runInContext('evalExpr('+JSON.stringify(expr)+', {trust:3})',ctx));
console.log('PASS safe expression interpreter');
vm.runInContext('P.minigames.push({id:"search",title:"Search",kind:"hotspot",target:3,seconds:20,objects:[{label:"Key",x:100,y:200,width:100,height:100,points:1}]})',ctx);let custom=vm.runInContext('minigamesView()',ctx);assert(!custom.includes('undefined'));assert(custom.includes('data-miniobject'));console.log('PASS visual mini-game constructor');

vm.runInContext('P.graphicsDocuments=[{id:"g",name:"Canvas",width:800,height:600,layers:[{id:"l",name:"Text",kind:"text",x:20,y:20,width:300,height:80,text:"Hello",fontSize:48,color:"#ffffff"}]}];P.musicProjects=[{id:"song",name:"Song",bpm:120,bars:2,tracks:[newMusicTrack()]}];',ctx);
for(let name of ['graphicsView','musicView']){let html=vm.runInContext(name+'()',ctx);assert(!html.includes('undefined'),name+' populated undefined');console.log('PASS populated',name)}

vm.runInContext('render=()=>{};changed=()=>{};P.scenes=[{id:"first",name:"First",events:[{type:"return"}]}];sceneIndex=0;eventIndex=0;addBuilderEvent({type:"say",character:"",text:"Inserted"});',ctx);assert.strictEqual(vm.runInContext('P.scenes[0].events[0].type',ctx),'say');assert.strictEqual(vm.runInContext('P.scenes[0].events[1].type',ctx),'return');console.log('PASS builder inserts before terminating return');
