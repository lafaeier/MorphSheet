/**
 * MorphSheet - Vanilla JS (Tab UI + Conversation Memory)
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
    // Conversation memory: keep all instructions for iterative refinement
    conversationHistory: [],
  };

  var $ = function (id) { return document.getElementById(id); };
  var dom = {};
  function cacheDom() {
    dom.uploadArea     = $('uploadArea');
    dom.uploadIcon     = $('uploadIcon');
    dom.uploadText     = $('uploadText');
    dom.fileInput      = $('fileInput');
    dom.targetFmt      = $('targetFormat');
    dom.targetEnc      = $('targetEncoding');
    dom.btnConvert     = $('btnConvert');
    dom.chatMsgs       = $('chatMessages');
    dom.chatInput      = $('chatInput');
    dom.btnSend        = $('btnSend');
    dom.diffSummary    = $('diffSummary');
    dom.sourceTable    = $('sourceTable');
    dom.targetTable    = $('targetTable');
    dom.btnExport      = $('btnExport');
    dom.btnCancel      = $('btnCancel');
    dom.statusSteps    = $('statusSteps');
    dom.confirmModal   = $('confirmModal');
    dom.modalBody      = $('modalBody');
    dom.toastContainer = $('toastContainer');
    dom.themeToggle    = $('themeToggle');
    dom.codePanelBody  = $('codePanelBody');
    dom.mainTabBar     = $('mainTabBar');
    dom.saveSkillLabel = $('saveSkillLabel');
    dom.saveSkillCheck = $('saveSkillCheck');
    dom.saveSkillName  = $('saveSkillName');
    dom.filePreviewTable = $('filePreviewTable');
  }

  // ============================================================
  // Toast
  // ============================================================
  function toast(msg, type) {
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = msg;
    dom.toastContainer.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  // ============================================================
  // Tab Navigation
  // ============================================================
  function switchTab(name) {
    state.activeTab = name;
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.view === name);
    });
    document.querySelectorAll('.tab-view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'view-' + name);
    });
  }

  function enableTab(name) {
    var b = dom.mainTabBar.querySelector('[data-view="' + name + '"]');
    if (b) b.disabled = false;
  }

  // ============================================================
  // Chat
  // ============================================================
  function addMsg(role, text) {
    var d = document.createElement('div');
    d.className = 'message ' + role;
    var inner = document.createElement('div');
    inner.className = 'message-content';
    inner.innerHTML = text.replace(/\n/g, '<br>');
    d.appendChild(inner);
    dom.chatMsgs.appendChild(d);
    dom.chatMsgs.scrollTop = dom.chatMsgs.scrollHeight;
  }

  function setLoading(v) {
    state.chatLoading = v;
    dom.btnSend.disabled = v || !state.currentFile;
    dom.chatInput.disabled = v || !state.currentFile;
    dom.btnConvert.disabled = v || !state.currentFile || !state.targetFormat;
  }

  // ============================================================
  // Status Steps
  // ============================================================
  var stepOrder = ['uploaded','analyzing','generating','executing','diffing','awaiting'];
  function setStep(phase) {
    state.taskPhase = phase;
    var found = false;
    stepOrder.forEach(function (k) {
      var el = dom.statusSteps.querySelector('[data-step="' + k + '"]');
      if (!el) return;
      el.className = 'step pending';
      if (k === phase) { el.className = 'step active'; found = true; }
      else if (!found) { el.className = 'step done'; }
    });
    dom.statusSteps.querySelectorAll('.step-icon').forEach(function (i) {
      var p = i.parentElement;
      if (p.classList.contains('done')) i.textContent = '●';
      else if (p.classList.contains('active')) i.textContent = '◉';
      else i.textContent = '○';
    });
  }

  // ============================================================
  // File Upload + Preview Tab
  // ============================================================
  function handleFile(file) {
    var ext = file.name.split('.').pop().toLowerCase();
    if (['xlsx','xls','csv'].indexOf(ext) === -1) { toast('不支持: .' + ext, 'error'); return; }
    setStep('uploaded');
    dom.uploadText.textContent = '上传中...';
    dom.uploadIcon.textContent = '⏳';

    API.upload(file).then(function (data) {
      state.currentFile = data;
      state.conversationHistory = [];
      dom.uploadText.textContent = file.name + ' (' + data.schema_info.row_count + '行)';
      dom.uploadIcon.textContent = '✅';
      dom.chatInput.disabled = false; dom.btnSend.disabled = false;
      dom.btnConvert.disabled = !state.targetFormat;
      addMsg('system', '已上传: <b>' + file.name + '</b><br>列: ' + data.schema_info.columns.join(', '));
      // File preview tab
      loadFilePreview(data.preview);
      enableTab('preview');
    }).catch(function (e) {
      toast('上传失败: ' + e.message, 'error');
      dom.uploadText.textContent = '拖拽文件到此处，或点击选择';
      dom.uploadIcon.textContent = '📂'; setStep('idle');
    });
  }

  function loadFilePreview(preview) {
    if (!preview || !preview.columns) return;
    var h = '<table><thead><tr>';
    preview.columns.forEach(function (c) { h += '<th>' + esc(String(c)) + '</th>'; });
    h += '</tr></thead><tbody>';
    (preview.rows || []).forEach(function (row) {
      h += '<tr>';
      row.forEach(function (c) { h += '<td>' + (c != null ? esc(String(c)) : '') + '</td>'; });
      h += '</tr>';
    });
    h += '</tbody></table>';
    dom.filePreviewTable.innerHTML = h;
  }

  // ============================================================
  // Convert (with conversation memory)
  // ============================================================
  function doConvert(extraInstruction) {
    var text = extraInstruction || dom.chatInput.value.trim();
    if (!text) { toast('请输入清洗指令', 'warning'); return; }
    if (!state.currentFile) { toast('请先上传文件', 'warning'); return; }
    if (!state.targetFormat) { toast('请选择目标格式', 'warning'); return; }

    // Build conversation context
    if (!extraInstruction) {
      state.conversationHistory.push(text);
    }
    var fullInstructions = state.conversationHistory.join('; ');

    addMsg('user', text);
    if (!extraInstruction) dom.chatInput.value = '';
    setLoading(true);
    setStep('analyzing');
    hideExportButtons();

    API.setTarget(state.currentFile.file_id, state.targetFormat, state.targetEncoding).then(function () {
      setStep('generating');
      return API.convert(state.currentFile.file_id, fullInstructions);
    }).then(function (result) {
      setLoading(false);
      handleConvertResult(result);
    }).catch(function (e) {
      setLoading(false); setStep('idle');
      addMsg('system', '❌ 转换失败: ' + e.message);
      toast('转换失败: ' + e.message, 'error');
    });
  }

  function handleConvertResult(result) {
    if (result.status === 'awaiting_confirmation') {
      state.currentTask = result;
      setStep('awaiting');
      loadDiff(result);
      loadCode(result);
      enableTab('diff'); enableTab('code');
      showExportButtons();
      switchTab('diff');
      addMsg('system', '✅ 转换完成！点击标签页查看详情。如不满意可在对话区继续输入指令调整。');
    } else if (result.status === 'awaiting_human_confirmation') {
      state.currentTask = result;
      setStep('awaiting');
      showModal(result.detected_issues || []);
      addMsg('system', '⚠ 发现 <b>' + (result.detected_issues || []).length + '</b> 个异常数据，请处理。');
    } else if (result.status === 'failed') {
      setStep('idle');
      addMsg('system', '❌ 转换失败: ' + (result.error || '未知错误'));
      toast('转换失败', 'error');
    }
  }

  // ============================================================
  // Export Controls
  // ============================================================
  function showExportButtons() {
    dom.btnExport.style.display = ''; dom.btnCancel.style.display = '';
    dom.saveSkillLabel.style.display = '';
  }
  function hideExportButtons() {
    dom.btnExport.style.display = 'none'; dom.btnCancel.style.display = 'none';
    dom.saveSkillLabel.style.display = 'none';
    dom.saveSkillCheck.checked = false;
    dom.saveSkillName.style.display = 'none'; dom.saveSkillName.value = '';
  }

  // ============================================================
  // Diff View
  // ============================================================
  function loadDiff(task) {
    var diff = task.diff || {};
    var preview = task.preview || {};
    var src = task.source_preview || state.currentFile.preview || {};
    dom.diffSummary.textContent = '原始 ' + (diff.row_counts && diff.row_counts.original || '?') +
      ' 行 → 转换后 ' + (diff.row_counts && diff.row_counts.transformed || '?') + ' 行';

    function ec(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function ecv(v) { return v == null ? '' : String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    var removedSet = {};
    (diff.removed_rows || []).forEach(function (r) { removedSet[r] = true; });

    function makeTable(cols, rows, useRemoved) {
      var h = '<table><thead><tr>';
      cols.forEach(function (c) { h += '<th>' + ec(String(c)) + '</th>'; });
      h += '</tr></thead><tbody>';
      rows.forEach(function (row, ri) {
        h += '<tr' + (useRemoved && removedSet[ri] ? ' class="row-removed"' : '') + '>';
        row.forEach(function (c) { h += '<td>' + ecv(c) + '</td>'; });
        h += '</tr>';
      });
      h += '</tbody></table>';
      return h;
    }

    dom.sourceTable.innerHTML = makeTable(src.columns || [], src.rows || [], true);
    dom.targetTable.innerHTML = makeTable(preview.columns || [], preview.rows || [], false);
  }

  // ============================================================
  // AI Code
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

  function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ============================================================
  // Export
  // ============================================================
  function doExport() {
    if (!state.currentTask) return;
    var saveSkill = dom.saveSkillCheck.checked;
    var skillName = saveSkill ? (dom.saveSkillName.value.trim() || '未命名技能') : null;

    API.exportTask(state.currentTask.task_id, saveSkill, skillName).then(function (r) {
      var msg = '导出成功: ' + r.file_path;
      if (r.skill_saved) msg += ' | 技能已保存 ✅';
      toast(msg, 'success'); addMsg('system', msg);
      window.open(API.getDownloadUrl(state.currentTask.task_id), '_blank');
      resetAfterExport();
    }).catch(function (e) { toast('导出失败: ' + e.message, 'error'); });
  }

  function cancelConvert() { resetAfterExport(); }

  function resetAfterExport() {
    setStep('idle'); state.currentTask = null; hideExportButtons();
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (b) {
      if (b.dataset.view === 'diff' || b.dataset.view === 'code') b.disabled = true;
    });
    switchTab('chat');
  }

  // ============================================================
  // Dirty Data Modal
  // ============================================================
  function showModal(issues) {
    var html = '';
    issues.forEach(function (iss) {
      html += '<div class="issue-item">';
      html += '<div class="issue-row"><strong>行 ' + iss.row + '</strong> · ' + esc(String(iss.column)) + '</div>';
      html += '<div class="issue-value">原始值: <code>' + esc(String(iss.value || '').substring(0, 60)) + '</code></div>';
      html += '<div class="issue-error">' + esc(String(iss.error)) + '</div>';
      html += '<div class="issue-suggestion">💡 ' + esc(String(iss.suggested_action || '')) + '</div>';
      html += '</div>';
    });
    dom.modalBody.innerHTML = html;
    dom.confirmModal.style.display = '';
  }

  function hideModal() { dom.confirmModal.style.display = 'none'; }

  function doAcceptSuggestion() {
    hideModal();
    if (!state.currentTask) return;
    addMsg('system', '🔧 采纳建议，移除异常行...');
    API.confirmAction(state.currentTask.task_id, 'accept_suggestion').then(function (r) {
      if (r.status === 'awaiting_confirmation') {
        state.currentTask = r;
        loadDiff(r); loadCode(r);
        enableTab('diff'); enableTab('code');
        showExportButtons();
        switchTab('diff');
        addMsg('system', '✅ 已移除异常行，请查看结果。');
      }
    }).catch(function (e) { toast('操作失败: ' + e.message, 'error'); });
  }

  function doSkipRow() {
    hideModal();
    if (!state.currentTask) return;
    addMsg('system', '⏭ 跳过异常行...');
    API.confirmAction(state.currentTask.task_id, 'skip_row').then(function (r) {
      if (r.status === 'awaiting_confirmation') {
        state.currentTask = r;
        loadDiff(r); loadCode(r);
        enableTab('diff'); enableTab('code');
        showExportButtons();
        switchTab('diff');
        addMsg('system', '✅ 已跳过异常行，请查看结果。');
      }
    }).catch(function (e) { toast('操作失败: ' + e.message, 'error'); });
  }

  function doAbort() {
    hideModal();
    if (!state.currentTask) return;
    API.confirmAction(state.currentTask.task_id, 'abort').then(function () {
      resetAfterExport();
      addMsg('system', '转换已取消。');
    }).catch(function () { resetAfterExport(); });
  }

  // ============================================================
  // Event Bindings
  // ============================================================
  function bindEvents() {
    dom.themeToggle.addEventListener('click', function () {
      var h = document.documentElement;
      h.setAttribute('data-theme', h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });

    // Main tabs
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (b) {
      b.addEventListener('click', function () { if (!b.disabled) switchTab(b.dataset.view); });
    });

    // Save skill checkbox → name input
    dom.saveSkillCheck.addEventListener('change', function () {
      dom.saveSkillName.style.display = dom.saveSkillCheck.checked ? '' : 'none';
    });

    // Sidebar
    document.querySelectorAll('.sidebar .tab-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        document.querySelectorAll('.sidebar .tab-btn').forEach(function (x) { x.classList.remove('active'); });
        document.querySelectorAll('.sidebar .tab-panel').forEach(function (p) { p.classList.remove('active'); });
        b.classList.add('active');
        var p = document.getElementById('panel-' + b.getAttribute('data-tab'));
        if (p) p.classList.add('active');
      });
    });

    // File upload
    dom.uploadArea.addEventListener('click', function () { dom.fileInput.click(); });
    dom.fileInput.addEventListener('change', function () { if (dom.fileInput.files[0]) handleFile(dom.fileInput.files[0]); });
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
    dom.btnSend.addEventListener('click', function () { doConvert(); });
    dom.chatInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') doConvert(); });
    dom.btnConvert.addEventListener('click', function () { doConvert(); });

    // Export
    dom.btnExport.addEventListener('click', doExport);
    dom.btnCancel.addEventListener('click', cancelConvert);

    // Modal
    $('btnAccept').addEventListener('click', doAcceptSuggestion);
    $('btnSkip').addEventListener('click', doSkipRow);
    $('btnAbort').addEventListener('click', doAbort);
  }

  function init() { cacheDom(); bindEvents(); console.log('MorphSheet ready'); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
