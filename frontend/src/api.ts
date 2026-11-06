export class ApiError extends Error { constructor(public status:number,message:string){super(message)} }
export async function api<T>(path:string, options:RequestInit = {}):Promise<T> {
  const csrf = document.cookie.split('; ').find(x=>x.startsWith('sd_csrf='))?.split('=').slice(1).join('=')
  const headers:Record<string,string> = {'Content-Type':'application/json'}
  if(csrf) headers['X-CSRF-Token']=decodeURIComponent(csrf)
  const response=await fetch('/api'+path,{...options,headers:{...headers,...options.headers},credentials:'same-origin'})
  const body=await response.json().catch(()=>({detail:'Réponse du service illisible.'}))
  if(!response.ok){
    if(response.status===401 && path!='/auth/login' && path!='/auth/me') window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(response.status,typeof body.detail==='string'?body.detail:'Une erreur est survenue.')
  }
  return body as T
}
export const send = (method:string, data?:unknown):RequestInit=>({method,body:data===undefined?undefined:JSON.stringify(data)})
