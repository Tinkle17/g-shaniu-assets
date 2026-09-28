import "jsr:@supabase/functions-js@2.4.4/edge-runtime.d.ts";

const OWNER="Tinkle17";
const REPO="g-shaniu-assets";
const REF="main";
const ALLOWED_SERIES=new Set(["hundred-cities"]);
const EP=/^[0-9]{3}$/;
const FILE=/^(manifest\.json|bundle\.zip)$/;
const HEX=/^[0-9a-f]{64}$/;
const PART=/^bundle\.b64\.\d{3}$/;
const MAX_BUNDLE=25*1024*1024;

function reply(status:number,body:string|Uint8Array,headers:Record<string,string>={}){
  return new Response(body,{status,headers:{"cache-control":"no-store",...headers}});
}
function rawUrl(series:string,episode:string,file:string){
  return "https://raw.githubusercontent.com/"+OWNER+"/"+REPO+"/"+REF+"/"+series+"/"+episode+"/"+file;
}
async function fetchText(url:string,max:number){
  const r=await fetch(url,{redirect:"error",headers:{"user-agent":"G-ShaNiu-Asset-Mirror/2.0","accept":"*/*"}});
  if(!r.ok) return {status:r.status,text:""};
  const t=await r.text();
  if(t.length>max) throw new Error("text_too_large");
  return {status:r.status,text:t};
}
async function sha256(data:Uint8Array){
  const h=await crypto.subtle.digest("SHA-256",data);
  return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,"0")).join("");
}
function decodeB64(s:string){
  const raw=atob(s.replace(/\s+/g,""));
  const out=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) out[i]=raw.charCodeAt(i);
  return out;
}

Deno.serve(async(req:Request)=>{
  try{
    if(req.method!=="GET") return reply(405,"method_not_allowed");
    const u=new URL(req.url);
    const series=String(u.searchParams.get("series")||"");
    const episode=String(u.searchParams.get("episode")||"");
    const file=String(u.searchParams.get("file")||"");
    if(!ALLOWED_SERIES.has(series)||!EP.test(episode)||!FILE.test(file)) return reply(400,"invalid_asset_path");

    if(file==="manifest.json"){
      const r=await fetch(rawUrl(series,episode,file),{redirect:"error",headers:{"user-agent":"G-ShaNiu-Asset-Mirror/2.0"}});
      if(r.status===404) return reply(404,"asset_not_found");
      if(!r.ok||!r.body) return reply(502,"upstream_failed");
      const len=Number(r.headers.get("content-length")||"0");
      if(len>1024*1024) return reply(502,"manifest_too_large");
      const h:Record<string,string>={"content-type":"application/json; charset=utf-8","cache-control":"public, max-age=300","x-asset-source":"github:"+OWNER+"/"+REPO+"@"+REF};
      if(len>0) h["content-length"]=String(len);
      return new Response(r.body,{status:200,headers:h});
    }

    const direct=await fetch(rawUrl(series,episode,"bundle.zip"),{redirect:"error",headers:{"user-agent":"G-ShaNiu-Asset-Mirror/2.0"}});
    if(direct.ok&&direct.body){
      const len=Number(direct.headers.get("content-length")||"0");
      if(len>MAX_BUNDLE) return reply(502,"bundle_too_large");
      const h:Record<string,string>={"content-type":"application/zip","cache-control":"public, max-age=300","x-asset-source":"github:"+OWNER+"/"+REPO+"@"+REF};
      if(len>0) h["content-length"]=String(len);
      return new Response(direct.body,{status:200,headers:h});
    }
    if(direct.status!==404) return reply(502,"upstream_failed");

    const idxr=await fetchText(rawUrl(series,episode,"bundle.b64.json"),128*1024);
    if(idxr.status===404) return reply(404,"asset_not_found");
    if(idxr.status!==200) return reply(502,"index_upstream_failed");
    const idx=JSON.parse(idxr.text);
    if(idx?.schema!==1||idx?.encoding!=="base64-concat"||!Array.isArray(idx?.parts)||idx.parts.length<1||idx.parts.length>64) return reply(502,"invalid_bundle_index");
    if(!Number.isSafeInteger(idx.size_bytes)||idx.size_bytes<1||idx.size_bytes>MAX_BUNDLE||!HEX.test(String(idx.sha256||""))) return reply(502,"invalid_bundle_index");
    let joined="";
    for(const name of idx.parts){
      if(typeof name!=="string"||!PART.test(name)) return reply(502,"invalid_part_name");
      const pr=await fetchText(rawUrl(series,episode,name),512*1024);
      if(pr.status!==200) return reply(502,"part_upstream_failed");
      joined+=pr.text.replace(/\s+/g,"");
      if(joined.length>Math.ceil(MAX_BUNDLE*4/3)+1024) return reply(502,"encoded_bundle_too_large");
    }
    const data=decodeB64(joined);
    if(data.length!==idx.size_bytes) return reply(502,"bundle_size_mismatch");
    if(await sha256(data)!==String(idx.sha256).toLowerCase()) return reply(502,"bundle_sha_mismatch");
    return new Response(data,{status:200,headers:{
      "content-type":"application/zip","content-length":String(data.length),
      "cache-control":"public, max-age=300","x-content-sha256":String(idx.sha256).toLowerCase(),
      "x-asset-source":"github:"+OWNER+"/"+REPO+"@"+REF+":base64-bootstrap"
    }});
  }catch(e){
    console.error("github_asset_mirror",String(e));
    return reply(500,"mirror_error");
  }
});