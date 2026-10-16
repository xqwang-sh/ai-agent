'use strict';
const status = document.getElementById('copy-status');
let clearMessage;
function announce(message) {
  status.textContent = message;
  status.classList.add('visible');
  clearTimeout(clearMessage);
  clearMessage = setTimeout(() => status.classList.remove('visible'), 3200);
}
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      const previous = button.textContent;
      button.textContent = '已复制';
      announce('已复制完整 Prompt，请粘贴到 OpenCode。');
      setTimeout(() => { button.textContent = previous; }, 1800);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(document.getElementById(button.dataset.copy));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      announce('浏览器未允许自动复制，已选中文字，请按系统复制快捷键。');
    }
  });
}
const checks = [...document.querySelectorAll('[data-complete]')];
function updateCount() {
  document.getElementById('completion-count').textContent = checks.filter(c => c.checked).length + ' / ' + checks.length + ' 步';
}
for (const check of checks) {
  try { check.checked = localStorage.getItem('earnings-lesson2.' + check.dataset.complete) === 'done'; } catch {}
  check.addEventListener('change', () => {
    try { localStorage.setItem('earnings-lesson2.' + check.dataset.complete, check.checked ? 'done' : ''); } catch {}
    updateCount();
  });
}
updateCount();
