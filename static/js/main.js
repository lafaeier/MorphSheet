/**
 * MorphSheet - Vanilla JS Application
 */
(function () {
  'use strict';

  // ============================================================
  // State
  // ============================================================
  var state = {
    currentFile: null,
    targetFormat: '',
    targetEncoding: 'utf-8',
    currentTask: null,
    taskPhase: 'idle',
    chatLoading: false,
  };

  // ============================================================
  // DOM Refs
  // ============================================================
  var $ = function (id) { return document.getElementById(id); };

  var dom = {};
  function cacheDom() {
    dom.uploadArea   = $('uploadArea');
    dom.uploadIcon   = $('uploadIcon');
    dom.uploadText   = $('uploadText');
    dom.fileInput    = $('fileInput');
    dom.targetFmt    = $('targetFormat');
    dom.targetEnc    = $('targetEncoding');
    dom.btnConvert   = $('btnConvert');
    dom.chatView     = $('chatView');
    dom.diffView     = $('diffView');
    dom.chatMsgs     = $('chatMessages');
    dom.chatInput    = $('chatInput');
    dom.btnSend      = $('btnSend');
    dom.diffSummary  = $('diffSummary');
    dom.sourceTable  = $('sourceTable');
    dom.targetTable  = $('targetTable');
    dom.btnExport    = $('btnExport');
    dom.btnCancel    = $('btnCancel');
    dom.statusSteps  = $('statusSteps');
    dom.confirmModal = $('confirmModal');
    dom.modalBody    = $('modalBody');
    dom.toastContainer = $('toastContainer');
    dom.themeToggle  = $('themeToggle');
  }

  // ============================================================
  // Toast
  // ============================================================
  function toast(msg, type) {
    type = type || 'info';
    var el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    dom.toastContainer.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  // ============================================================
  // Chat
  // ============================================================
  function addMsg(role, text) {
    var div = document.createElement('div');
    div.className = 'message ' + role;
    var inner = document.createElement('div');
    inner.className = 'message-content';
    inner.innerHTML = text.replace(/\n/g, '<br>');
    div.appendChild(inner);
    dom.chatMsgs.appendChild(div);
    dom.chatMsgs.scrollTop = dom.chatMsgs.scrollHeight;
  }

  function setLoading(loading) {
    state.chatLoading = loading;
    dom.btnSend.disabled = loading || !state.currentFile;
    dom.chatInput.disabled = loading || !state.currentFile;
    dom.btnConvert.disabled = loading || !state.currentFile || !state.targetFormat;
  }

  // ============================================================
  // Status Steps
  // ============================================================
  var stepOrder = ['uploaded', 'analyzing', 'generating', 'executing', 'diffing', 'awaiting'];

  function setStep(phase) {
    state.taskPhase = phase;
    var found = false;
    stepOrder.forEach(function (key) {
      var el = dom.statusSteps.querySelector('[data-step="' + key + '"]');
      if (!el) return;
      el.className = 'step pending';
      if (key === phase) { el.className = 'step active'; found = true; }
      else if (!found) { el.className = 'step done'; }
    });
    // Update icons
    dom.statusSteps.querySelectorAll('.step-icon').forEach(function (icon) {
      var parent = icon.parentElement;
      if (parent.classList.contains('done')) icon.textContent = '●';
      else if (parent.classList.contains('active')) icon.textContent = '◉';
      else icon.textContent = '○';
    });
  }

  // ============================================================
  // File Upload
  // ============================================================
  function handleFile(file) {
    var ext = file.name.split('.').pop().toLowerCase();
    if (['xlsx','xls','csv'].indexOf(ext) === -1) {
      toast('不支持的文件格式: .' + ext, 'error'); return;
    }
    setStep('uploaded');
    dom.uploadText.textContent = '上传中...';
    dom.uploadIcon.textContent = '⏳';

    API.upload(file).then(function (data) {
      state.currentFile = data;
      dom.uploadText.textContent = file.name + ' (' + data.schema_info.row_count + '行, ' + data.schema_info.columns.length + '列)';
      dom.uploadIcon.textContent = '✅';
      dom.chatInput.disabled = false;
      dom.btnSend.disabled = false;
      dom.btnConvert.disabled = !state.targetFormat;
      addMsg('system', '文件已上传: <b>' + file.name + '</b><br>列: ' + data.schema_info.columns.join(', '));
    }).catch(function (e) {
      toast('上传失败: ' + e.message, 'error');
      dom.uploadText.textContent = '拖拽文件到此处，或点击选择';
      dom.uploadIcon.textContent = '📂';
      setStep('idle');
    });
  }

  // ============================================================
  // Convert
  // ============================================================
  function doConvert() {
    var instructions = dom.chatInput.value.trim();
    if (!instructions) { toast('请输入清洗指令', 'warning'); return; }
    if (!state.currentFile) { toast('请先上传文件', 'warning'); return; }
    if (!state.targetFormat) { toast('请选择目标格式', 'warning'); return; }

    addMsg('user', instructions);
    dom.chatInput.value = '';
    setLoading(true);
    setStep('analyzing');

    API.setTarget(state.currentFile.file_id, state.targetFormat, state.targetEncoding).then(function () {
      setStep('generating');
      return API.convert(state.currentFile.file_id, instructions);
    }).then(function (result) {
      setLoading(false);
      if (result.status === 'awaiting_confirmation') {
        state.currentTask = result;
        setStep('awaiting');
        showDiff(result);
        addMsg('system', '✅ 转换完成！请在下方 Diff 视图中确认结果。');
      } else if (result.status === 'failed') {
        setStep('idle');
        addMsg('system', '❌ 转换失败: ' + (result.error || '未知错误'));
        toast('转换失败', 'error');
      }
    }).catch(function (e) {
      setLoading(false);
      setStep('idle');
      addMsg('system', '❌ 转换失败: ' + e.message);
      toast('转换失败: ' + e.message, 'error');
    });
  }

  // ============================================================
  // Diff View
  // ============================================================
  function showDiff(task) {
    dom.chatView.style.display = 'none';
    dom.diffView.style.display = '';

    var diff = task.diff || {};
    var preview = task.preview || {};
    var srcPreview = task.source_preview || state.currentFile.preview || {};

    dom.diffSummary.textContent = '原始 ' + (diff.row_counts ? diff.row_counts.original : '?') + ' 行 → 转换后 ' + (diff.row_counts ? diff.row_counts.transformed : '?') + ' 行';

    // Source table
    renderTable(dom.sourceTable, srcPreview.columns || [], srcPreview.rows || [], diff.removed_rows || []);

    // Target table
    renderTable(dom.targetTable, preview.columns || [], preview.rows || [], []);
  }

  function renderTable(container, columns, rows, removedRows) {
    var removedSet = {};
    (removedRows || []).forEach(function (r) { removedSet[r] = true; });

    var html = '<table><thead><tr>';
    columns.forEach(function (c) { html += '<th>' + esc(c) + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function (row, ri) {
      var cls = removedSet[ri] ? ' class="row-removed"' : '';
      html += '<tr' + cls + '>';
      row.forEach(function (cell) {
        html += '<td>' + (cell != null ? esc(String(cell)) : '') + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ============================================================
  // Export
  // ============================================================
  function doExport() {
    if (!state.currentTask) return;
    API.exportTask(state.currentTask.task_id, false, null).then(function (result) {
      toast('导出成功: ' + result.file_path, 'success');
      addMsg('system', '文件已导出: ' + result.file_path);
      window.open(API.getDownloadUrl(state.currentTask.task_id), '_blank');
      setStep('idle');
      dom.chatView.style.display = '';
      dom.diffView.style.display = 'none';
      state.currentTask = null;
    }).catch(function (e) {
      toast('导出失败: ' + e.message, 'error');
    });
  }

  function cancelDiff() {
    dom.chatView.style.display = '';
    dom.diffView.style.display = 'none';
    state.currentTask = null;
    setStep('idle');
  }

  // ============================================================
  // Modal
  // ============================================================
  function showModal(issues) {
    var html = '';
    issues.forEach(function (issue) {
      html += '<div class="issue-item">';
      html += '<div class="issue-row"><strong>行 ' + issue.row + '</strong> · 列: ' + esc(issue.column) + '</div>';
      html += '<div class="issue-value">当前值: <code>' + esc(String(issue.value)) + '</code></div>';
      html += '<div class="issue-error">' + esc(issue.error) + '</div>';
      html += '<div class="issue-suggestion">💡 建议: ' + esc(issue.suggested_action) + '</div>';
      html += '</div>';
    });
    dom.modalBody.innerHTML = html;
    dom.confirmModal.style.display = '';
  }

  function hideModal() {
    dom.confirmModal.style.display = 'none';
  }

  // ============================================================
  // Event Bindings
  // ============================================================
  function bindEvents() {
    // Theme toggle
    dom.themeToggle.addEventListener('click', function () {
      var html = document.documentElement;
      var cur = html.getAttribute('data-theme');
      html.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    });

    // Sidebar tabs
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
        document.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
        btn.classList.add('active');
        var panelId = 'panel-' + btn.getAttribute('data-tab');
        var panel = document.getElementById(panelId);
        if (panel) panel.classList.add('active');
      });
    });

    // File upload - click
    dom.uploadArea.addEventListener('click', function () { dom.fileInput.click(); });
    dom.fileInput.addEventListener('change', function () {
      if (dom.fileInput.files[0]) handleFile(dom.fileInput.files[0]);
    });

    // File upload - drag & drop
    dom.uploadArea.addEventListener('dragover', function (e) { e.preventDefault(); dom.uploadArea.classList.add('drag-over'); });
    dom.uploadArea.addEventListener('dragleave', function () { dom.uploadArea.classList.remove('drag-over'); });
    dom.uploadArea.addEventListener('drop', function (e) {
      e.preventDefault();
      dom.uploadArea.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });

    // Target format
    dom.targetFmt.addEventListener('change', function () {
      state.targetFormat = dom.targetFmt.value;
      dom.targetEnc.style.display = state.targetFormat === 'csv' ? '' : 'none';
      dom.btnConvert.disabled = !state.currentFile || !state.targetFormat;
    });
    dom.targetEnc.addEventListener('change', function () {
      state.targetEncoding = dom.targetEnc.value;
    });

    // Chat
    dom.btnSend.addEventListener('click', doConvert);
    dom.chatInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') doConvert();
    });

    // Convert button
    dom.btnConvert.addEventListener('click', doConvert);

    // Diff
    dom.btnExport.addEventListener('click', doExport);
    dom.btnCancel.addEventListener('click', cancelDiff);

    // Modal
    $('btnAccept').addEventListener('click', hideModal);
    $('btnSkip').addEventListener('click', hideModal);
    $('btnAbort').addEventListener('click', function () {
      hideModal();
      setStep('idle');
    });
  }

  // ============================================================
  // Init
  // ============================================================
  function init() {
    cacheDom();
    bindEvents();
    console.log('MorphSheet initialized');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
