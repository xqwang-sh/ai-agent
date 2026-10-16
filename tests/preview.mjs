import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runJob } from '../netlify/lib/jobs.mjs';
import { runTrial } from '../netlify/lib/workflow.mjs';
import { history, memoryStore, modelFixture, windowText } from './fixtures.mjs';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const store = memoryStore();
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.json':'application/json','.txt':'text/plain; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.pdf':'application/pdf','.zip':'application/zip'};
createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/api/run' && req.method === 'POST') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw);
    res.writeHead(202); res.end();
    runJob(body, {store, history, loadWindow:async () => windowText, execute:(args) => runTrial({...args, fetchImpl:modelFixture(args.approach)})});
    return;
  }
  if (url.pathname === '/api/run-status') {
    res.writeHead(200, {'content-type':'application/json'});
    res.end(JSON.stringify({ok:true, ...(await store.get(url.searchParams.get('job')) || {status:'pending'})}));
    return;
  }
  try {
    let path = resolve(root, `.${decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname)}`);
    if (!path.startsWith(`${root}/`)) throw new Error('path');
    if (!extname(path)) path += '.html';
    let data = await readFile(path);
    if (path.endsWith('/demo.html')) data = Buffer.from(data.toString().replace('<body>', '<body><aside role="status" style="padding:8px 20px;background:#f4ead3;color:#62543a;font:12px sans-serif">本地检查预览：Run 使用测试响应，不消耗 API 额度。</aside>'));
    res.writeHead(200, {'content-type':mime[extname(path)] || 'application/octet-stream'}); res.end(data);
  } catch { res.writeHead(404); res.end('Not found'); }
}).listen(8766, '127.0.0.1', () => process.stdout.write('Fixture preview: http://127.0.0.1:8766/demo.html\nNo paid model requests.\n'));
