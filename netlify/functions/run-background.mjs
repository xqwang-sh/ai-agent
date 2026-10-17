import { getStore } from '@netlify/blobs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { REPORT_INPUT } from '../../assets/lesson-one-workflow.mjs';
import { runJob, STORE } from '../lib/jobs.mjs';

export const config = {background:true};
export const loadReport = () => readFile(join(process.env.LAMBDA_TASK_ROOT || process.cwd(), 'netlify/data', REPORT_INPUT.file), 'utf8');

export default async (request) => {
  if (request.method !== 'POST') return new Response(null, {status:405});
  const body = await request.json();
  await runJob(body, {
    store:getStore({name:STORE, consistency:'strong'}), loadReport,
  });
  return new Response(null, {status:202});
};
