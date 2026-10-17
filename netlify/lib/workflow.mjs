import { MODEL, APPROACHES, METRICS, stateValues, parseJson, gradeOutput, resultForTrial, requirePrevious, toolDefinition, executeTool, promptFor } from '../../assets/lesson-one-workflow.mjs';

export async function runTrial({approach, apiKey, previous, reportText, reportSha256, fetchImpl = fetch, now = Date.now}) {
  if (!APPROACHES.includes(approach)) throw new Error('未知运行方法。');
  if (typeof apiKey !== 'string' || !apiKey.trim() || apiKey.length > 512) throw new Error('请填写自己的硅基流动 API Key。');
  const state = requirePrevious(approach, previous);
  const started = now();
  const ledger = {prompt_tokens:0, completion_tokens:0, total_tokens:0, complete:true, calls:[]};
  const prompt = promptFor(approach, state);
  const tools = approach === 'unit-api' ? toolDefinition('convert_units') : approach === 'yoy-api' ? toolDefinition('calculate_yoy') : null;
  const toolName = tools?.[0].function.name;
  const values = state ? stateValues(state, approach.startsWith('unit') ? 'raw_values':'unit_values') : null;
  const messages = [{role:'user', content:approach.startsWith('locator') ? `${prompt}\n\n${reportText}` : prompt}];
  const toolCalls = [];
  let finalText = '', finalSeen = false;
  try {
    for (let round = 0; round < (tools ? 8 : 1); round += 1) {
      const remaining = 720000 - (now() - started);
      if (remaining <= 0) throw new Error('已达到本次运行时限，请保留记录后重试。');
      const body = {model:MODEL, messages, stream:false, temperature:0, enable_thinking:approach === 'locator-thinking-api'};
      if (body.enable_thinking) body.thinking_budget = 4096;
      if (tools) { body.tools = tools; body.tool_choice = toolCalls.length ? 'auto' : {type:'function', function:{name:toolName}}; }
      else body.response_format = {type:'json_object'};
      const callStarted = now();
      const response = await fetchImpl('https://api.siliconflow.cn/v1/chat/completions', {method:'POST', headers:{Authorization:`Bearer ${apiKey.trim()}`, 'Content-Type':'application/json'}, body:JSON.stringify(body), signal:AbortSignal.timeout(Math.min(300000, remaining))});
      if (!response.ok) {
        ledger.complete = false; ledger.calls.push({http_status:response.status, usage:null});
        throw new Error(`硅基流动返回 HTTP ${response.status}。${response.status === 401 ? '请检查个人 API Key。' : response.status === 429 ? '当前账户限流，请稍后重试。' : '请检查账户权限、余额或服务状态。'}`);
      }
      const data = await response.json();
      const usage = data.usage || null;
      ledger.calls.push({model:data.model || MODEL, usage, elapsed_seconds:(now() - callStarted) / 1000});
      if (!Number.isInteger(usage?.total_tokens)) ledger.complete = false;
      for (const field of ['prompt_tokens','completion_tokens','total_tokens']) ledger[field] += Number.isInteger(usage?.[field]) ? usage[field] : 0;
      const message = data.choices?.[0]?.message || {};
      if (!message.tool_calls?.length) { finalText = message.content || ''; finalSeen = true; break; }
      if (!tools) throw new Error('本轮未提供工具，模型却返回了工具请求。');
      messages.push(message);
      for (const call of message.tool_calls) {
        const fn = call.function || {};
        const args = typeof fn.arguments === 'string' ? parseJson(fn.arguments) : fn.arguments || {};
        const result = fn.name === toolName ? executeTool(fn.name, args, values) : 'tool_error: 本轮不提供此工具';
        toolCalls.push({name:fn.name, arguments:args, result});
        messages.push({role:'tool', tool_call_id:call.id, content:result});
      }
    }
    if (!finalSeen) throw new Error('已达到8轮调用上限，模型尚未提交最终结果。');
    const parsed = parseJson(finalText);
    const grade = gradeOutput(approach, parsed);
    if (tools && !METRICS.every((metric) => toolCalls.some((call) => call.name === toolName && call.arguments.metric === metric && !call.result.startsWith('tool_error')))) grade.score = '0/5';
    const result = resultForTrial(approach, {grade}, previous);
    const workflowState = approach.startsWith('locator') ? {raw_values:parsed?.values || {}, raw_unit:(parsed?.location || parsed)?.unit} : {...state};
    if (approach.startsWith('unit')) workflowState.unit_values = parsed;
    if (approach.startsWith('yoy')) workflowState.yoy_values = parsed;
    workflowState.source_step = approach;
    return {...result, kind:'current', approach, model:MODEL, parsed, grade, workflowState, prompt, report_sha256:reportSha256,
      usage:ledger, tokens:ledger.complete ? `${ledger.total_tokens.toLocaleString()} tok` : `${ledger.total_tokens.toLocaleString()} tok · 用量不完整`,
      elapsed_seconds:(now() - started) / 1000, latency:`${((now() - started) / 1000).toFixed(2)}s`, tool_calls:toolCalls,
      note:'检查反映本次运行与本轮第02、04步的真实前序记录，结果仍需人工复核。'};
  } catch (error) {
    ledger.complete = false;
    const message = error.name === 'TimeoutError' || error.name === 'AbortError' ? '模型请求超时，已停止本次运行。' : error.message?.startsWith('硅基流动') || error.message?.startsWith('已达到') || error.message?.startsWith('本轮') ? error.message : '模型连接或响应异常，已停止本次运行。';
    const failure = new Error(message);
    failure.usage = ledger; failure.elapsed_seconds = (now() - started) / 1000;
    throw failure;
  }
}
