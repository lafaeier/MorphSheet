/**
 * MorphSheet - 主入口脚本 (Phase 0: 骨架版)
 */

document.addEventListener('DOMContentLoaded', () => {
  // ---- DOM refs ----
  const uploadArea = document.getElementById('uploadArea');
  const fileInput = document.getElementById('fileInput');
  const targetFormat = document.getElementById('targetFormat');
  const targetEncoding = document.getElementById('targetEncoding');
  const btnConvert = document.getElementById('btnConvert');
  const chatInput = document.getElementById('chatInput');
  const btnSend = document.getElementById('btnSend');
  const chatMessages = document.getElementById('chatMessages');
  const diffContainer = document.getElementById('diffContainer');
  const confirmModal = document.getElementById('confirmModal');

  // ---- Sidebar tabs ----
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`panel-${btn.dataset.tab}`).classList.add('active');
    });
  });

  // ---- File upload: click ----
  uploadArea.addEventListener('click', () => fileInput.click());

  // ---- File upload: drag & drop ----
  uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
  });
  uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('drag-over');
  });
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // ---- File upload: file input change ----
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) handleFile(file);
  });

  function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['xlsx', 'xls', 'csv'];
    if (!allowed.includes(ext)) {
      alert(`不支持的文件格式: .${ext}\n请上传 .xlsx / .xls / .csv 文件`);
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      alert('文件大小超过 50MB 限制');
      return;
    }
    // Update UI
    uploadArea.querySelector('p').textContent = `已选择: ${file.name}`;
    chatInput.disabled = false;
    btnSend.disabled = false;
    btnConvert.disabled = false;
    console.log('File selected:', file.name, file.size);
  }

  // ---- Target format change ----
  targetFormat.addEventListener('change', () => {
    targetEncoding.style.display = targetFormat.value === 'csv' ? 'inline' : 'none';
  });

  // ---- Chat send ----
  btnSend.addEventListener('click', () => sendMessage());
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });

  function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    addMessage('user', text);
    chatInput.value = '';
    // Phase 0: just echo back
    setTimeout(() => {
      addMessage('system', `收到指令："${text}"\n\n（Agent 核心将在 Phase 2 实现）`);
    }, 500);
  }

  function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `<div class="message-content">${content.replace(/\n/g, '<br>')}</div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // ---- Convert button (placeholder) ----
  btnConvert.addEventListener('click', () => {
    addMessage('system', '转换功能将在 Phase 2 实现。\n请先在对话区输入清洗指令。');
    updateStatusStep(0, 'active'); // simulate
  });

  // ---- Status step helpers ----
  function updateStatusStep(index, state) {
    const steps = document.querySelectorAll('#statusSteps .step');
    if (steps[index]) {
      steps[index].className = `step ${state}`;
      const icon = state === 'done' ? '●' : state === 'active' ? '◉' : '○';
      steps[index].querySelector('.step-icon').textContent = icon;
    }
  }

  // ---- Modal close ----
  document.getElementById('btnAbort')?.addEventListener('click', () => {
    confirmModal.style.display = 'none';
  });

  // ---- Theme toggle (click on title) ----
  document.querySelector('.sidebar-title').addEventListener('click', () => {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
  });

  console.log('MorphSheet Phase 0 initialized');
});
