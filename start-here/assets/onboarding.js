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
const checks = [...document.querySelectorAll('[data-complete]')];
const progressKey = 'finance-start-here.2026-10-31.';
function updateCount() {
  document.getElementById('completion-count').textContent =
    checks.filter(item => item.checked).length + ' / ' + checks.length + ' 步';
}
for (const check of checks) {
  try { check.checked = localStorage.getItem(progressKey + check.dataset.complete) === 'checked'; } catch {}
  check.addEventListener('change', () => {
    try { localStorage.setItem(progressKey + check.dataset.complete, check.checked ? 'checked' : ''); } catch {}
    updateCount();
  });
}
updateCount();
document.getElementById('print-handout').addEventListener('click', () => window.print());
