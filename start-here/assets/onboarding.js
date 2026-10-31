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
    ? '已选择：' + selected.map(tool => tool.parentElement.textContent.trim()).join('、') + '。OpenCode＋DeepSeek 安装说明已隐藏，可直接到下一节建立工作目录，再用自己的工具打开。'
    : noTool.checked
      ? '建议使用 OpenCode＋DeepSeek。请先展开下面的安装说明，完成软件安装和 DeepSeek API Key 配置，再到下一节建立工作目录。'
      : '如果已有可用工具，请在上面选择。尚未使用过的老师，请先展开下面的安装说明，安装 OpenCode 并配置 DeepSeek API Key，然后再建立工作目录。';
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
