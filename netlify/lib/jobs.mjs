import { createHash } from 'node:crypto';
import { APPROACHES, REPORT_INPUT, requirePrevious } from '../../assets/lesson-one-workflow.mjs';
import { runTrial } from './workflow.mjs';

export const JOB_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const STORE = 'ai-agent-lesson-one-jobs';

export async function runJob(body, {store, loadReport, execute = runTrial}) {
  const jobId = String(body?.jobId || '');
  if (!JOB_ID.test(jobId)) return;
  if (await store.get(jobId, {type:'json'})) return;
  const startedAt = new Date().toISOString();
  await store.setJSON(jobId, {status:'running', startedAt});
  try {
    if (!APPROACHES.includes(body.approach)) throw new Error('未知运行方法。');
    if (typeof body.apiKey !== 'string' || !body.apiKey.trim() || body.apiKey.length > 512) throw new Error('请填写自己的硅基流动 API Key。');
    let previous = null;
    if (!body.approach.startsWith('locator')) {
      if (!JOB_ID.test(String(body.parentJobId || ''))) throw new Error('没有本轮已通过的前序结果，请先运行第02或04步。');
      const parent = await store.get(body.parentJobId, {type:'json'});
      if (parent?.status !== 'complete' || parent.result?.report_sha256 !== REPORT_INPUT.sha256) throw new Error('前序任务尚未完成或原文版本不一致，请从全文重新运行02。');
      previous = parent.result;
      requirePrevious(body.approach, previous);
    }
    const reportText = await loadReport();
    if (createHash('sha256').update(reportText).digest('hex') !== REPORT_INPUT.sha256) throw new Error('财报全文指纹不一致，已停止运行。');
    const result = await execute({approach:body.approach, apiKey:body.apiKey, previous, reportText, reportSha256:REPORT_INPUT.sha256});
    result.job_id = jobId;
    result.parent_job_id = body.parentJobId || null;
    result.input_source = body.approach.startsWith('locator') ? 'report_full_text' : 'current';
    result.input_report = REPORT_INPUT;
    await store.setJSON(jobId, {status:'complete', result, startedAt, finishedAt:new Date().toISOString()});
  } catch (error) {
    const secret = typeof body.apiKey === 'string' ? body.apiKey.trim() : '';
    const message = String(error.message || '本次运行失败。');
    const safe = secret ? message.split(secret).join('[已隐藏]') : message;
    await store.setJSON(jobId, {status:'error', error:safe, usage:error.usage || null, elapsed_seconds:error.elapsed_seconds ?? null, startedAt, finishedAt:new Date().toISOString()});
  }
}
