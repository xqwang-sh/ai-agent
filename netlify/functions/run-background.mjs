import { getStore } from '@netlify/blobs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import history from '../../assets/lesson-one-history.json' with {type:'json'};
import { runJob, STORE } from '../lib/jobs.mjs';

export const config = {background:true};

export default async (request) => {
  if (request.method !== 'POST') return new Response(null, {status:405});
  const body = await request.json();
  await runJob(body, {
    store:getStore({name:STORE, consistency:'strong'}), history,
    loadWindow:() => readFile(join(process.env.LAMBDA_TASK_ROOT || process.cwd(), 'netlify/data/report-pages-60-75.txt'), 'utf8'),
  });
  return new Response(null, {status:202});
};
