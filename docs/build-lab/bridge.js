'use strict';
(()=>{
  const base=new URL('.',document.currentScript.src);
  const worker=new Worker(new URL('worker.mjs',base),{type:'module'});
  const requests=new Map();let sequence=0,icons={};
  const iconsReady=fetch(new URL('icons.json',base)).then(r=>{if(!r.ok)throw Error('아이콘 목록을 불러오지 못했습니다.');return r.json();}).then(v=>icons=v);
  const SAVE_KEY='cte2-public-saved-builds-v1';
  worker.onmessage=event=>{const row=requests.get(event.data.id);if(!row)return;requests.delete(event.data.id);clearTimeout(row.timer);event.data.error?row.reject(Error(event.data.error)):row.resolve(event.data.result);};
  worker.onerror=()=>{for(const row of requests.values()){clearTimeout(row.timer);row.reject(Error('계산기를 시작하지 못했습니다. 페이지를 새로고침해 주세요.'));}requests.clear();};
  function rpc(path,data){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{requests.delete(id);reject(Error('계산기 준비가 오래 걸리고 있습니다. 인터넷 연결을 확인한 뒤 새로고침해 주세요.'));},180000);requests.set(id,{resolve,reject,timer});worker.postMessage({id,path,data});});}
  window.CTE_ASSET_URL=src=>{
    if(!src)return new URL('fallback.png',base).href;
    if(src.startsWith('/api/icon?')){const item=new URL(src,location.origin).searchParams.get('item');return new URL(icons[item]||'fallback.png',base).href;}
    if(src.startsWith('/assets/'))return new URL(src.slice(1),base).href;
    return src;
  };
  function saved(){try{const rows=JSON.parse(localStorage.getItem(SAVE_KEY)||'[]');return Array.isArray(rows)?rows:[];}catch{return [];}}
  function download(document){const raw=JSON.stringify(document,null,2);if(raw.length>8*1024*1024)throw Error('빌드 파일은 8MB 이하여야 합니다.');const blob=new Blob([raw],{type:'application/json'}),url=URL.createObjectURL(blob),a=documentObject.createElement('a');a.href=url;a.download=(document.a?.name||'CTE2-빌드').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,60)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  const documentObject=document;
  window.CTE_DOWNLOAD_BUILD=download;
  window.CTE_WEB_API=async(path,data)=>{
    await iconsReady;
    const url=new URL(path,location.origin);
    if(url.pathname==='/api/builds'&&data===undefined)return saved().map(({document,...entry})=>entry);
    if(url.pathname==='/api/build'){const row=saved().find(r=>r.id===url.searchParams.get('id'));if(!row)throw Error('이 브라우저에서 저장한 빌드를 찾지 못했습니다.');return row.document;}
    if(url.pathname==='/api/builds'){
      const valid=await rpc(path,data);const raw=JSON.stringify(valid);if(raw.length>8*1024*1024)throw Error('빌드 파일은 8MB 이하여야 합니다.');
      const id=crypto.randomUUID(),entry={id,name:String(valid.a.name||'A 빌드'),comparison:String(valid.b.name||'B 빌드'),modified:Date.now()/1000,filename:String(valid.a.name||'CTE2-빌드')+'.json',folder:'이 브라우저',document:valid};
      const rows=[entry,...saved()];try{localStorage.setItem(SAVE_KEY,JSON.stringify(rows));if(!saved().some(r=>r.id===id))throw Error('저장 확인 실패');}catch{throw Error('브라우저 저장 공간이 부족합니다. JSON 내보내기로 빌드를 보관하세요.');}
      const {document:ignored,...metadata}=entry;return metadata;
    }
    return rpc(path,data);
  };
})();
