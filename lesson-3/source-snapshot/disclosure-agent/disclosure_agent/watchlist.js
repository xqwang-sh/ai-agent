'use strict';
const DisclosureWatchlist = (() => {
  const key = 'disclosure-agent.watchlist.v1';
  const normal = value => String(value ?? '').normalize('NFKC').trim();
  function codeValue(value) {
    if (typeof value === 'number') return Number.isSafeInteger(value) && value >= 0 && value <= 999999 ? String(value).padStart(6,'0') : '';
    const text=normal(value).toUpperCase();
    const found=/^(?:(?:SH|SZ|BJ)\.?)*(\d{6})(?:\.(?:SH|SZ|BJ))?$/.exec(text);
    return found ? found[1] : '';
  }
  function indexDirectory(directory) {
    const groups=new Map(), byCode=new Map(), byName=new Map();
    for(const row of directory?.rows || []) {
      const id=String(row.org_id), code=codeValue(row.code), name=normal(row.name);
      if(!code || !name) throw new Error('公司列表不完整，请重新运行后台更新。');
      if(!groups.has(id)) groups.set(id,{id,name,codes:new Set(),names:new Set()});
      const group=groups.get(id);group.codes.add(code);group.names.add(name);
      if(byCode.has(code) && byCode.get(code)!==group) throw new Error('公司代码存在身份冲突，请核对来源。');
      byCode.set(code,group);
      if(!byName.has(name)) byName.set(name,new Set());
      byName.get(name).add(group);
    }
    return {groups,byCode,byName};
  }
  function readRows(book, reader) {
    const sheet=book.Sheets[book.SheetNames[0]];
    if(!sheet?.['!ref']) throw new Error('第一张工作表为空，请按模板填写。');
    const range=reader.utils.decode_range(sheet['!ref']);
    if(range.e.r>10000 || range.e.c>100) throw new Error('请使用不超过一万行的公司名单。');
    const headers=new Map();
    for(let c=range.s.c;c<=range.e.c;c++) {
      const cell=sheet[reader.utils.encode_cell({r:0,c})];
      const name=normal(cell?.v);
      if(['公司简称','股票代码'].includes(name)) {
        if(cell.f || headers.has(name)) throw new Error('表头重复或含公式，请使用模板表头。');
        headers.set(name,c);
      }
    }
    if(!headers.size) throw new Error('第一行需有“公司简称”或“股票代码”。');
    const rows=[];
    for(let r=1;r<=range.e.r;r++) {
      const row={row:r+1};
      for(const [header,c] of headers) {
        const cell=sheet[reader.utils.encode_cell({r,c})];
        if(cell?.f || cell?.F || (cell && !['s','n','z'].includes(cell.t))) throw new Error(`第${r+1}行请填写名称或代码原值，勿使用公式、日期或错误值。`);
        row[header==='公司简称'?'name':'code']=cell?.v;
      }
      if(normal(row.name) || normal(row.code)) rows.push(row);
    }
    if(!rows.length) throw new Error('名单为空，现有关注名单未修改。');
    return rows;
  }
  function resolveRows(rows,index) {
    const selected=new Map(), errors=[];
    for(const row of rows) {
      const name=normal(row.name), rawCode=normal(row.code), code=rawCode?codeValue(row.code):'';
      const group=code?index.byCode.get(code):null, names=index.byName.get(name);
      let found;
      if(rawCode && !group) errors.push(`第${row.row}行：股票代码“${rawCode}”未匹配，请填写六位A股代码。`);
      else if(group && name && !group.names.has(name)) errors.push(`第${row.row}行：简称“${name}”与代码${code}不对应。`);
      else if(group) found=group;
      else if(names?.size===1) found=[...names][0];
      else if(names?.size>1) errors.push(`第${row.row}行：“${name}”对应多个主体，请补股票代码。`);
      else errors.push(`第${row.row}行：简称“${name}”未匹配，请核对或改填代码。`);
      if(found) selected.set(found.id,{id:found.id,name:found.name,codes:[...found.codes].sort()});
    }
    if(errors.length) throw new Error(errors.slice(0,5).join('\n')+(errors.length>5?`\n另有${errors.length-5}行需核对。`:''));
    return [...selected.values()];
  }
  function createWatchlist(directory, storage) {
    const index=indexDirectory(directory);
    let active=false, selected=[], codes=new Set(), warning='', remembered=true;
    const apply=items=>{selected=items;codes=new Set(items.flatMap(item=>item.codes));active=true;};
    try {
      storage=storage || globalThis.localStorage;
      const raw=storage.getItem(key);
      if(raw) {
        const saved=JSON.parse(raw);
        if(saved.version!==1 || !Array.isArray(saved.companies) || !saved.companies.length || saved.companies.length>10000) throw new Error('invalid saved list');
        let missing=0;
        const items=saved.companies.map(item=>{
          if(typeof item.id!=='string' || typeof item.name!=='string' || !Array.isArray(item.codes) || !item.codes.length || item.codes.some(code=>!/^\d{6}$/.test(code))) throw new Error('invalid company');
          const group=index.groups.get(item.id);
          if(group) return {id:group.id,name:group.name,codes:[...group.codes].sort()};
          missing++;
          return {...item,codes:item.codes.filter(code=>!index.byCode.has(code))};
        });
        apply(items);
        if(missing) warning=`${missing}家关注公司在本次公司列表中未匹配，原名单已保留，请核对。`;
      }
    } catch(error) { active=true;remembered=false;warning='关注名单无法恢复，请重新导入或清除名单。'; }
    function snapshot() { return {active,companies:selected.map(item=>({...item,codes:[...item.codes]})),warning,remembered}; }
    function replaceRows(rows) {
      let items;
      try {
        if(!Array.isArray(rows) || !rows.length) throw new Error('名单为空，现有关注名单未修改。');
        items=resolveRows(rows,index);
      } catch(error) {return {ok:false,error:error.message};}
      try {storage.setItem(key,JSON.stringify({version:1,companies:items}));remembered=true;warning='';}
      catch(error) {remembered=false;warning='本次名单已应用，但浏览器未能保存；刷新后请重新确认关注名单。';}
      apply(items);return {ok:true,count:items.length,remembered};
    }
    async function replaceWorkbook(file,reader) {
      try {
        if(!/\.xlsx$/i.test(file.name) || file.size>5*1024*1024) throw new Error('请上传5MB以内的.xlsx公司名单。');
        const bytes=await file.arrayBuffer();
        if(new Uint8Array(bytes)[0]!==0x50 || new Uint8Array(bytes)[1]!==0x4b) throw new Error('文件不是有效的.xlsx工作簿。');
        const book=reader.read(bytes,{type:'array',sheets:0,cellFormula:true,cellHTML:false,cellDates:true,sheetRows:10002});
        return replaceRows(readRows(book,reader));
      } catch(error) {return {ok:false,error:'未导入：'+error.message+'\n现有名单和筛选保持不变。'};}
    }
    function clear() {
      try {storage.removeItem(key);} catch(error) {return {ok:false,error:'浏览器未能清除已保存的名单，本次筛选保持不变。'};}
      active=false;selected=[];codes.clear();warning='';remembered=true;return {ok:true};
    }
    return {snapshot,replaceWorkbook,replaceRows,clear,includes:code=>!active||codes.has(code)};
  }
  return {createWatchlist,codeValue,readRows,indexDirectory,resolveRows};
})();
if(typeof module!=='undefined' && module.exports) module.exports=DisclosureWatchlist;
