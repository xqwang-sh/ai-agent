import { getStore } from '@netlify/blobs';
import { JOB_ID, STORE } from '../lib/jobs.mjs';

export default async (request) => {
  const headers = {'content-type':'application/json', 'cache-control':'no-store'};
  if (request.method !== 'GET') return new Response(JSON.stringify({ok:false, error:'仅支持查询任务。'}), {status:405, headers});
  const job = new URL(request.url).searchParams.get('job') || '';
  if (!JOB_ID.test(job)) return new Response(JSON.stringify({ok:false, error:'任务编号无效。'}), {status:400, headers});
  const item = await getStore({name:STORE, consistency:'strong'}).get(job, {type:'json'});
  return new Response(JSON.stringify({ok:true, ...(item || {status:'pending'})}), {headers});
};
