/**
 * MorphSheet - Vanilla JS Application (Tab-based UI)
 */
(function () {
  'use strict';

  var state = {
    currentFile: null,
    targetFormat: '',
    targetEncoding: 'utf-8',
    currentTask: null,
    taskPhase: 'idle',
    chatLoading: false,
    activeTab: 'chat',
  };

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
    dom.codePanelBody = $('codePanelBody');
    dom.mainTabBar    = $('mainTabBar');
    dom.saveSkillLabel = $('saveSkillLabel');
    dom.saveSkillCheck = $('saveSkillCheck');
    dom.saveSkillName  = $('saveSkillName');
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
  // Tab Navigation (VS Code style)
  // ============================================================
  function switchTab(tabName) {
    state.activeTab = tabName;
    // Update tab buttons
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.view === tabName);
    });
    // Update tab views
    document.querySelectorAll('.tab-view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'view-' + tabName);
    });
  }

  function enableTab(tabName) {
    var btn = dom.mainTabBar.querySelector('[data-view="' + tabName + '"]');
    if (btn) btn.disabled = false;
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
      var p = icon.parentElement;
      if (p.classList.contains('done')) icon.textContent = '●';
      else if (p.classList.contains('active')) icon.textContent = '◉';
      else icon.textContent = '○';
    });
  }

  // ============================================================
  // File Upload
  // ============================================================
  function handleFile(file) {
    var ext = file.name.split('.').pop().toLowerCase();
    if (['xlsx','xls','csv'].indexOf(ext) === -1) {
      toast('不支持: .' + ext, 'error'); return;
    }
    setStep('uploaded');
    dom.uploadText.textContent = '上传中...';
    dom.uploadIcon.textContent = '⏳';

    API.upload(file).then(function (data) {
      state.currentFile = data;
      dom.uploadText.textContent = file.name + ' (' + data.schema_info.row_count + '行)';
      dom.uploadIcon.textContent = '✅';
      dom.chatInput.disabled = false;
      dom.btnSend.disabled = false;
      dom.btnConvert.disabled = !state.targetFormat;
      addMsg('system', '已上传: <b>' + file.name + '</b><br>列: ' + data.schema_info.columns.join(', '));
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
        loadDiff(result);
        loadCode(result);
        enableTab('diff');
        enableTab('code');
        showExportButtons();
        addMsg('system', '✅ 转换完成！点击上方 <b>Diff 对比</b> / <b>AI 代码</b> 标签查看详情。');
      } else if (result.status === 'awaiting_human_confirmation') {
        state.currentTask = result;
        setStep('awaiting');
        showModal(result.detected_issues || []);
        addMsg('system', '⚠ 发现异常数据，请在弹窗中处理。');
      } else if (result.status === 'failed') {
        setStep('idle');
        addMsg('system', '❌ 转换失败: ' + (result.error || '未知错误'));
        toast('转换失败', 'error');
      }
    }).catch(function (e) {
      setLoading(false); setStep('idle');
      addMsg('system', '❌ 转换失败: ' + e.message);
      toast('转换失败: ' + e.message, 'error');
    });
  }

  // ============================================================
  // Show/Hide Export Controls
  // ============================================================
  function showExportButtons() {
    dom.btnExport.style.display = '';
    dom.btnCancel.style.display = '';
    dom.saveSkillLabel.style.display = '';
  }

  function hideExportButtons() {
    dom.btnExport.style.display = 'none';
    dom.btnCancel.style.display = 'none';
    dom.saveSkillLabel.style.display = 'none';
    dom.saveSkillCheck.checked = false;
    dom.saveSkillName.style.display = 'none';
    dom.saveSkillName.value = '';
  }

  // ============================================================
  // Diff View
  // ============================================================
  function loadDiff(task) {
    var diff = task.diff || {};
    var preview = task.preview || {};
    var srcPreview = task.source_preview || state.currentFile.preview || {};

    dom.diffSummary.textContent = '原始 ' + (diff.row_counts && diff.row_counts.original || '?') +
      ' 行 → 转换后 ' + (diff.row_counts && diff.row_counts.transformed || '?') + ' 行';

    function ec(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function ecv(v) { return v == null ? '' : String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    var removedSet = {};
    (diff.removed_rows || []).forEach(function (r) { removedSet[r] = true; });

    var srcCols = (srcPreview.columns || []).map(ec);
    var tgtCols = (preview.columns || []).map(ec);
    var srcRows = srcPreview.rows || [];
    var tgtRows = preview.rows || [];

    // Source table
    var h1 = '<table><thead><tr>';
    srcCols.forEach(function (c) { h1 += '<th>' + c + '</th>'; });
    h1 += '</tr></thead><tbody>';
    srcRows.forEach(function (row, ri) {
      h1 += '<tr' + (removedSet[ri] ? ' class="row-removed"' : '') + '>';
      row.forEach(function (cell) { h1 += '<td>' + ecv(cell) + '</td>'; });
      h1 += '</tr>';
    });
    h1 += '</tbody></table>';
    dom.sourceTable.innerHTML = h1;

    // Target table
    var h2 = '<table><thead><tr>';
    tgtCols.forEach(function (c) { h2 += '<th>' + c + '</th>'; });
    h2 += '</tr></thead><tbody>';
    tgtRows.forEach(function (row) {
      h2 += '<tr>';
      row.forEach(function (cell) { h2 += '<td>' + ecv(cell) + '</td>'; });
      h2 += '</tr>';
    });
    h2 += '</tbody></table>';
    dom.targetTable.innerHTML = h2;
  }

  // ============================================================
  // AI Code View
  // ============================================================
  function loadCode(task) {
    var html = '';
    if (task.explanation) {
      html += '<span class="comment"># ' + esc(task.explanation) + '</span>\n';
      html += '<span class="comment"># Retries: ' + (task.retries || 0) + '</span>\n\n';
    }
    html += highlightPython(task.code || '(no code)');
    dom.codePanelBody.innerHTML = html;
  }

  function highlightPython(code) {
    return esc(code).split('\n').map(function (line) {
      if (/^\s*#/.test(line)) return '<span class="comment">' + line + '</span>';
      line = line.replace(/\b(def|import|from|return|if|else|elif|for|while|in|as|try|except|pass|continue|break|and|or|not|True|False|None)\b/g,
        '<span class="keyword">$1</span>');
      line = line.replace(/(["'])(?:(?!\1)[^\\]|\\.)*\1/g, '<span class="string">$&</span>');
      line = line.replace(/\b(\d+\.?\d*)\b/g, '<span class="number">$1</span>');
      return line;
    }).join('\n');
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ============================================================
  // Export with save-as-skill
  // ============================================================
  function doExport() {
    if (!state.currentTask) return;
    var saveAsSkill = dom.saveSkillCheck.checked;
    var skillName = saveAsSkill ? (dom.saveSkillName.value.trim() || '未命名技能') : null;

    API.exportTask(state.currentTask.task_id, saveAsSkill, skillName).then(function (result) {
      var msg = '导出成功: ' + result.file_path;
      if (result.skill_saved) msg += ' | 技能已保存 ✓';
      toast(msg, 'success');
      addMsg('system', msg);
      window.open(API.getDownloadUrl(state.currentTask.task_id), '_blank');
      resetAfterExport();
    }).catch(function (e) {
      toast('导出失败: ' + e.message, 'error');
    });
  }

  function cancelConvert() {
    resetAfterExport();
  }

  function resetAfterExport() {
    setStep('idle');
    state.currentTask = null;
    hideExportButtons();
    // Disable diff/code tabs
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (b) {
      if (b.dataset.view === 'diff' || b.dataset.view === 'code') b.disabled = true;
    });
    switchTab('chat');
  }

  // ============================================================
  // Modal (dirty data)
  // ============================================================
  function showModal(issues) {
    var html = '';
    issues.forEach(function (issue) {
      html += '<div class="issue-item">';
      html += '<div class="issue-row"><strong>行 ' + issue.row + '</strong> · ' + esc(String(issue.column)) + '</div>';
      html += '<div class="issue-value">值: <code>' + esc(String(issue.value).substring(0, 60)) + '</code></div>';
      html += '<div class="issue-error">' + esc(String(issue.error)) + '</div>';
      html += '<div class="issue-suggestion">' + esc(String(issue.suggested_action || '')) + '</div>';
      html += '</div>';
    });
    dom.modalBody.innerHTML = html;
    dom.confirmModal.style.display = '';
  }

  function hideModal() { dom.confirmModal.style.display = 'none'; }

  // ============================================================
  // Event Bindings
  // ============================================================
  function bindEvents() {
    // Theme toggle
    dom.themeToggle.addEventListener('click', function () {
      var html = document.documentElement;
      html.setAttribute('data-theme', html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });

    // Main tab navigation
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.disabled) return;
        switchTab(btn.dataset.view);
      });
    });

    // Save skill checkbox → show name input
    dom.saveSkillCheck.addEventListener('change', function () {
      dom.saveSkillName.style.display = dom.saveSkillCheck.checked ? '' : 'none';
    });

    // Sidebar tabs
    document.querySelectorAll('.sidebar .tab-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.sidebar .tab-btn').forEach(function (b) { b.classList.remove('active'); });
        document.querySelectorAll('.sidebar .tab-panel').forEach(function (p) { p.classList.remove('active'); });
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
      e.preventDefault(); dom.uploadArea.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });

    // Target
    dom.targetFmt.addEventListener('change', function () {
      state.targetFormat = dom.targetFmt.value;
      dom.targetEnc.style.display = state.targetFormat === 'csv' ? '' : 'none';
      dom.btnConvert.disabled = !state.currentFile || !state.targetFormat;
    });
    dom.targetEnc.addEventListener('change', function () { state.targetEncoding = dom.targetEnc.value; });

    // Chat
    dom.btnSend.addEventListener('click', doConvert);
    dom.chatInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') doConvert(); });
    dom.btnConvert.addEventListener('click', doConvert);

    // Export
    dom.btnExport.addEventListener('click', doExport);
    dom.btnCancel.addEventListener('click', cancelConvert);

    // Modal
    $('btnAccept').addEventListener('click', hideModal);
    $('btnSkip').addEventListener('click', hideModal);
    $('btnAbort').addEventListener('click', function () { hideModal(); resetAfterExport(); });
  }

  function init() {
    cacheDom();
    bindEvents();
    console.log('MorphSheet ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
