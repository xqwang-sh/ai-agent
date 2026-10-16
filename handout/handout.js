const store = 'lesson-one-workflow-progress-v1';
let saved = [];
try {
  const value = JSON.parse(localStorage.getItem(store) || '[]');
  if (Array.isArray(value)) saved = value;
} catch {}

document.querySelectorAll('[data-check]').forEach((input) => {
  input.checked = saved.includes(input.dataset.check);
  input.addEventListener('change', () => {
    saved = [...document.querySelectorAll('[data-check]:checked')].map((item) => item.dataset.check);
    try { localStorage.setItem(store, JSON.stringify(saved)); } catch {}
  });
});

const toast = document.querySelector('#toast');
document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch {
      const field = document.createElement('textarea');
      field.value = text;
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.append(field);
      field.select();
      try { copied = document.execCommand('copy'); } catch {}
      field.remove();
    }
    toast.textContent = copied ? 'Prompt 已复制，粘贴到 OpenCode' : '请在下方文本中手动选择并复制';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2200);
  });
});

let printDetails = [];
window.addEventListener('beforeprint', () => {
  printDetails = [...document.querySelectorAll('details:not([open])')];
  printDetails.forEach((item) => { item.open = true; });
});
window.addEventListener('afterprint', () => {
  printDetails.forEach((item) => { item.open = false; });
});
document.querySelector('#print').addEventListener('click', () => window.print());

if ('IntersectionObserver' in window) {
  const links = [...document.querySelectorAll('[data-nav]')];
  const observer = new IntersectionObserver((entries) => {
    const active = entries.filter((item) => item.isIntersecting)
      .sort((a,b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
    if (!active) return;
    links.forEach((link) => link.setAttribute('aria-current', link.dataset.nav === active.target.id));
  }, {rootMargin:'-18% 0px -65% 0px'});
  document.querySelectorAll('main > [id]').forEach((section) => observer.observe(section));
}
