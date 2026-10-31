'use strict';
const message = document.getElementById('copy-status');
let messageTimer;
function announce(text) {
  message.textContent = text;
  message.classList.add('visible');
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => message.classList.remove('visible'), 3500);
}
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const source = document.getElementById(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(source.textContent);
      announce('文字已复制。按本段说明粘贴到对应位置。');
    } catch {
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      announce('已选中文字。Windows 按 Ctrl+C，Mac 按 Command+C 复制。');
    }
  });
}
const tools = [...document.querySelectorAll('input[name="existing-tool"]')];
const noTool = document.getElementById('no-existing-tool');
const guide = document.getElementById('opencode-install');
const route = document.getElementById('tool-route');
const selectionKey = 'finance-start-here.tools.v1';
try {
  const saved = JSON.parse(localStorage.getItem(selectionKey));
  if (Array.isArray(saved?.tools)) {
    tools.forEach(tool => { tool.checked = saved.tools.includes(tool.value); });
    noTool.checked = !tools.some(tool => tool.checked) && saved.noTool === true;
  }
} catch {}
function updateRoute() {
  const selected = tools.filter(tool => tool.checked);
  guide.hidden = selected.length > 0;
  if (guide.hidden) guide.open = false;
  route.textContent = selected.length
    ? '已选择：' + selected.map(tool => tool.parentElement.textContent.trim()).join('、') + '。OpenCode＋DeepSeek 安装说明已隐藏，继续用自己的工具打开工作目录即可。'
    : noTool.checked
      ? '建议从 OpenCode＋DeepSeek 起步。先建立下面的工作目录，再展开“打开自己的 Agent”中的安装说明。'
      : '如果已有可用工具，请在上面选择。尚未使用过的老师，先建立工作目录，再展开后面的 OpenCode＋DeepSeek 安装说明。';
  try {
    localStorage.setItem(selectionKey, JSON.stringify({ tools: selected.map(tool => tool.value), noTool: noTool.checked }));
  } catch {}
}
for (const tool of tools) {
  tool.addEventListener('change', () => {
    if (tool.checked) noTool.checked = false;
    updateRoute();
  });
}
noTool.addEventListener('change', () => {
  if (noTool.checked) tools.forEach(tool => { tool.checked = false; });
  updateRoute();
});
updateRoute();
document.getElementById('print-handout').addEventListener('click', () => window.print());
let printDetails = [];
window.addEventListener('beforeprint', () => {
  printDetails = [...document.querySelectorAll('details:not([hidden])')].map(detail => [detail, detail.open]);
  printDetails.forEach(([detail]) => { detail.open = true; });
});
window.addEventListener('afterprint', () => {
  printDetails.forEach(([detail, open]) => { detail.open = open; });
  printDetails = [];
});
