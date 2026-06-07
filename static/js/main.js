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
    dom.uploadArea    = $('uploadArea');
    dom.uploadIcon    = $('uploadIcon');
    dom.uploadText    = $('uploadText');
    dom.fileInput     = $('fileInput');
    dom.targetFmt     = $('targetFormat');
    dom.targetEnc     = $('targetEncoding');
    dom.btnConvert    = $('btnConvert');
    dom.chatView      = $('chatView');
    dom.diffView      = $('diffView');
    dom.chatMsgs      = $('chatMessages');
    dom.chatInput     = $('chatInput');
    dom.btnSend       = $('btnSend');
    dom.diffSummary   = $('diffSummary');
    dom.sourceTable   = $('sourceTable');
    dom.targetTable   = $('targetTable');
    dom.btnExport     = $('btnExport');
    dom.btnCancel     = $('btnCancel');
    dom.statusSteps   = $('statusSteps');
    dom.confirmModal  = $('confirmModal');
    dom.modalBody     = $('modalBody');
    dom.toastContainer = $('toastContainer');
    dom.themeToggle   = $('themeToggle');
    dom.codePanel     = $('codePanel');
    dom.codePanelBody = $('codePanelBody');
    dom.codePanelToggle = $('codePanelToggle');
    dom.codePanelHeader = $('codePanelHeader');
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
  // View Switching
  // ============================================================
  function showChat() {
    dom.chatView.classList.remove('hidden');
    dom.diffView.classList.add('hidden');
  }

  function showDiffView() {
    dom.chatView.classList.add('hidden');
    dom.diffView.classList.remove('hidden');
  }

  // ============================================================
  // AI Code Panel
  // ============================================================
  function showCode(code, explanation, retries) {
    var html = '';
    if (explanation) {
      html += '<span class="comment"># ' + esc(explanation) + '</span>\n';
      html += '<span class="comment"># 重试次数: ' + retries + '</span>\n\n';
    }
    html += highlightPython(esc(code));
    dom.codePanelBody.innerHTML = html;
    dom.codePanel.classList.add('visible');
    dom.codePanelToggle.textContent = '收起';
    dom.codePanelBody.style.display = '';
  }

  function highlightPython(code) {
    // Simple syntax highlighting
    var lines = code.split('\n');
    return lines.map(function (line) {
      // Comments
      if (/^\s*#/.test(line)) return '<span class="comment">' + line + '</span>';
      // Keywords
      line = line.replace(/\b(def|import|from|return|if|else|elif|for|while|in|as|try|except|pass|continue|break|and|or|not|True|False|None)\b/g,
        '<span class="keyword">$1</span>');
      // Strings
      line = line.replace(/(["'])(?:(?!\1)[^\\]|\\.)*\1/g,
        '<span class="string">$&</span>');
      // Numbers
      line = line.replace(/\b(\d+\.?\d*)\b/g,
        '<span class="number">$1</span>');
      return line;
    }).join('\n');
  }

  function toggleCodePanel() {
    if (dom.codePanelBody.style.display === 'none') {
      dom.codePanelBody.style.display = '';
      dom.codePanelToggle.textContent = '收起';
    } else {
      dom.codePanelBody.style.display = 'none';
      dom.codePanelToggle.textContent = '展开';
    }
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
    dom.codePanel.classList.remove('visible');

    API.setTarget(state.currentFile.file_id, state.targetFormat, state.targetEncoding).then(function () {
      setStep('generating');
      return API.convert(state.currentFile.file_id, instructions);
    }).then(function (result) {
      setLoading(false);
      if (result.status === 'awaiting_confirmation') {
        state.currentTask = result;
        setStep('awaiting');
        showDiff(result);
        if (result.code) {
          showCode(result.code, result.explanation || '', result.retries || 0);
        }
        addMsg('system', '✅ 转换完成！请查看 Diff 视图确认结果。');
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
    showDiffView();
    var diff = task.diff || {};
    var preview = task.preview || {};
    var srcPreview = task.source_preview || state.currentFile.preview || {};

    dom.diffSummary.textContent = '原始 ' + (diff.row_counts && diff.row_counts.original || '?') + ' 行 → 转换后 ' + (diff.row_counts && diff.row_counts.transformed || '?') + ' 行';

    // Escape HTML in column names and cell values
    function escCol(col) { return String(col).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function escCell(val) {
      if (val === null || val === undefined) return '';
      return String(val).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // Source table
    renderTable(dom.sourceTable, (srcPreview.columns || []).map(escCol), srcPreview.rows || [], diff.removed_rows || [], escCell);

    // Target table
    renderTable(dom.targetTable, (preview.columns || []).map(escCol), preview.rows || [], [], escCell);
  }

  function renderTable(container, columns, rows, removedRows, cellFn) {
    var removedSet = {};
    (removedRows || []).forEach(function (r) { removedSet[r] = true; });

    var html = '<table><thead><tr>';
    columns.forEach(function (c) { html += '<th>' + c + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function (row, ri) {
      var cls = removedSet[ri] ? ' class="row-removed"' : '';
      html += '<tr' + cls + '>';
      row.forEach(function (cell) {
        html += '<td>' + cellFn(cell) + '</td>';
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
      showChat();
      dom.codePanel.classList.remove('visible');
      state.currentTask = null;
    }).catch(function (e) {
      toast('导出失败: ' + e.message, 'error');
    });
  }

  function cancelDiff() {
    showChat();
    state.currentTask = null;
    setStep('idle');
    dom.codePanel.classList.remove('visible');
  }

  // ============================================================
  // Modal
  // ============================================================
  function showModal(issues) {
    var html = '';
    issues.forEach(function (issue) {
      html += '<div class="issue-item">';
      html += '<div class="issue-row"><strong>行 ' + issue.row + '</strong> · 列: ' + esc(String(issue.column)) + '</div>';
      html += '<div class="issue-value">当前值: <code>' + esc(String(issue.value)) + '</code></div>';
      html += '<div class="issue-error">' + esc(String(issue.error)) + '</div>';
      html += '<div class="issue-suggestion">💡 建议: ' + esc(String(issue.suggested_action || '')) + '</div>';
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

    // Code panel toggle
    dom.codePanelHeader.addEventListener('click', toggleCodePanel);

    // Sidebar tabs
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
        document.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
        btn.classList.add('active');
        var panel = document.getElementById('panel-' + btn.getAttribute('data-tab'));
        if (panel) panel.classList.add('active');
      });
    });

    // File upload
    dom.uploadArea.addEventListener('click', function () { dom.fileInput.click(); });
    dom.fileInput.addEventListener('change', function () {
      if (dom.fileInput.files[0]) handleFile(dom.fileInput.files[0]);
    });
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
    dom.targetEnc.addEventListener('change', function () { state.targetEncoding = dom.targetEnc.value; });

    // Chat send
    dom.btnSend.addEventListener('click', doConvert);
    dom.chatInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') doConvert(); });
    dom.btnConvert.addEventListener('click', doConvert);

    // Diff
    dom.btnExport.addEventListener('click', doExport);
    dom.btnCancel.addEventListener('click', cancelDiff);

    // Modal
    $('btnAccept').addEventListener('click', hideModal);
    $('btnSkip').addEventListener('click', hideModal);
    $('btnAbort').addEventListener('click', function () { hideModal(); setStep('idle'); });
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
