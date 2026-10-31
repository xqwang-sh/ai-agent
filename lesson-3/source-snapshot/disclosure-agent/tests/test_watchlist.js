const test=require('node:test');
const assert=require('node:assert/strict');
const W=require('../disclosure_agent/watchlist.js');
const XLSX=require('../disclosure_agent/xlsx.mini.min.js');
const fs=require('node:fs');
const path=require('node:path');
const directory={rows:[
 {code:'001301',name:'合成甲',org_id:'a'},
 {code:'833874',name:'合成甲旧名',org_id:'a'},
 {code:'600001',name:'同名测试',org_id:'b'},
 {code:'600002',name:'同名测试',org_id:'c'},
 {code:'600003',name:'无当期事件测试',org_id:'d'},
]};
function storage(){const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};}
test('identities preserve zeroes; alias and duplicate rows collapse to one issuer',()=>{
 const list=W.createWatchlist(directory,storage());
 assert.equal(list.replaceRows([{row:2,code:1301},{row:3,name:'合成甲旧名'}]).count,1);
 assert.equal(list.includes('001301'),true);assert.equal(list.includes('833874'),true);assert.equal(list.includes('600003'),false);
});
test('name collision, mismatch or unknown row reject the whole batch and preserve prior scope',()=>{
 const list=W.createWatchlist(directory,storage());list.replaceRows([{row:2,code:'001301'}]);
 for(const rows of [[{row:2,name:'同名测试'}],[{row:2,name:'合成甲',code:'600001'}],[{row:2,code:'600003'},{row:3,code:'999999'}]]) {
  assert.equal(list.replaceRows(rows).ok,false);assert.equal(list.includes('001301'),true);assert.equal(list.includes('600003'),false);
 }
 assert.equal(list.replaceRows([{row:2,name:'同名测试',code:'600001'}]).ok,true);
});
test('known companies without any event are retained and selection survives a new controller',()=>{
 const saved=storage();const list=W.createWatchlist(directory,saved);
 list.replaceRows([{row:2,name:'无当期事件测试'}]);
 const reload=W.createWatchlist(directory,saved);assert.equal(reload.snapshot().companies.length,1);assert.equal(reload.includes('600003'),true);assert.equal(reload.includes('001301'),false);
 assert.equal(reload.clear().ok,true);assert.equal(W.createWatchlist(directory,saved).snapshot().active,false);
});
test('restored identities cannot silently follow a reassigned code',()=>{
 const saved=storage();W.createWatchlist(directory,saved).replaceRows([{row:2,code:'600003'}]);
 const next={rows:directory.rows.map(row=>row.code==='600003'?{...row,org_id:'different'}:row)};
 const list=W.createWatchlist(next,saved);assert.equal(list.includes('600003'),false);assert.match(list.snapshot().warning,/未匹配/);
});
test('unreadable saved scope fails visibly closed; unsuccessful clear preserves scope',()=>{
 const list=W.createWatchlist(directory,{getItem:()=>'{bad',removeItem:()=>{throw Error('denied');}});
 assert.equal(list.snapshot().active,true);assert.equal(list.includes('001301'),false);assert.match(list.snapshot().warning,/无法恢复/);assert.equal(list.clear().ok,false);
});
test('template is a real workbook and preserves six-digit text; formula identities fail',()=>{
 const bytes=fs.readFileSync(path.join(__dirname,'../disclosure_agent/watchlist-example.xlsx'));
 const book=XLSX.read(bytes,{type:'buffer',cellFormula:true,cellDates:true});
 assert.equal(book.Sheets[book.SheetNames[0]].B4.v,'001301');
 const rows=W.readRows(book,XLSX);assert.equal(rows.length,4);assert.equal(rows[2].code,'001301');
 book.Sheets[book.SheetNames[0]].B4.f='1+1300';assert.throws(()=>W.readRows(book,XLSX),/勿使用公式/);
});
test('bad files never replace the current list; storage write failure is explicit',async()=>{
 const saved=storage();const list=W.createWatchlist(directory,saved);list.replaceRows([{row:2,code:'001301'}]);
 const bad={name:'bad.xlsx',size:3,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer};
 assert.equal((await list.replaceWorkbook(bad,XLSX)).ok,false);assert.equal(list.includes('001301'),true);
 const temporary=W.createWatchlist(directory,{getItem:()=>null,setItem:()=>{throw Error('quota');}});
 assert.equal(temporary.replaceRows([{row:2,code:'600003'}]).remembered,false);assert.match(temporary.snapshot().warning,/未能保存/);
});
