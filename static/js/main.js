/**
 * MorphSheet - Vanilla JS (Tab UI + Sidebar + Lazy Diff)
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
    conversationHistory: [],
    // Diff lazy loading
    allSourceRows: [],
    allTargetRows: [],
    diffBatchSize: 50,
    diffLoadedCount: 0,
  };

  var $ = function (id) { return document.getElementById(id); };
  var dom = {};
  function cacheDom() {
    dom.uploadArea      = $('uploadArea');
    dom.uploadIcon      = $('uploadIcon');
    dom.uploadText      = $('uploadText');
    dom.fileInput       = $('fileInput');
    dom.targetFmt       = $('targetFormat');
    dom.targetEnc       = $('targetEncoding');
    dom.btnConvert      = $('btnConvert');
    dom.chatMsgs        = $('chatMessages');
    dom.chatInput       = $('chatInput');
    dom.btnSend         = $('btnSend');
    dom.diffSummary     = $('diffSummary');
    dom.sourceTable     = $('sourceTable');
    dom.targetTable     = $('targetTable');
    dom.btnExport       = $('btnExport');
    dom.btnCancel       = $('btnCancel');
    dom.statusSteps     = $('statusSteps');
    dom.confirmModal    = $('confirmModal');
    dom.modalBody       = $('modalBody');
    dom.toastContainer  = $('toastContainer');
    dom.themeToggle     = $('themeToggle');
    dom.codePanelBody   = $('codePanelBody');
    dom.mainTabBar      = $('mainTabBar');
    dom.saveSkillLabel  = $('saveSkillLabel');
    dom.saveSkillCheck  = $('saveSkillCheck');
    dom.saveSkillName   = $('saveSkillName');
    dom.filePreviewTable = $('filePreviewTable');
    dom.panelHistory    = $('panel-history');
    dom.panelSkills     = $('panel-skills');
    dom.alertArea       = $('alertArea');
    dom.alertList       = $('alertList');
    dom.alertAccept     = $('alertAccept');
    dom.alertChat       = $('alertChat');
    dom.alertSkip       = $('alertSkip');
    dom.btnRefresh      = $('btnRefresh');
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
  // Sidebar: Load Skills & History
  // ============================================================
  function loadSkills() {
    API.getSkills(50).then(function (data) {
      var skills = data.skills || [];
      if (skills.length === 0) {
        dom.panelSkills.innerHTML = '<p class="placeholder-text">暂无保存的技能</p>';
        return;
      }
      var html = '';
      skills.forEach(function (s) {
        html += '<div class="skill-card" data-skill-id="' + s.skill_id + '">';
        html += '<div class="skill-card-top">';
        html += '<span class="skill-name" title="点击查看详情">' + esc(s.name) + '</span>';
        html += '<button class="skill-del" data-del="' + s.skill_id + '" title="删除此技能">×</button>';
        html += '</div>';
        html += '<div class="skill-desc">' + esc(s.source_schema_summary || '') + '</div>';
        html += '<div class="skill-meta">使用 ' + s.usage_count + ' 次 · ' + esc(s.target_format || '') + '</div>';
        html += '</div>';
      });
      dom.panelSkills.innerHTML = html;

      // Click skill name → show detail
      dom.panelSkills.querySelectorAll('.skill-name').forEach(function (nameEl) {
        nameEl.addEventListener('click', function (e) {
          e.stopPropagation();
          e.preventDefault();
          var card = nameEl.closest('.skill-card');
          if (!card) { console.error('No parent .skill-card found'); return; }
          var sid = card.getAttribute('data-skill-id');
          console.log('Skill name clicked, id:', sid);
          if (!sid) { console.error('No skill-id attribute'); return; }
          showSkillDetail(sid);
        });
      });

      // Click skill card → apply
      dom.panelSkills.querySelectorAll('.skill-card').forEach(function (card) {
        card.addEventListener('click', function (e) {
          if (e.target.classList.contains('skill-del') || e.target.classList.contains('skill-name')) return;
          var sid = card.dataset.skillId;
          if (!state.currentFile) { toast('请先上传文件', 'warning'); return; }
          addMsg('system', '🔄 应用技能: ' + card.querySelector('.skill-name').textContent);
          doConvertWithSkill(sid);
        });
      });

      // Delete button
      dom.panelSkills.querySelectorAll('.skill-del').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var sid = btn.dataset.del;
          if (confirm('确定删除此技能？')) {
            API.deleteSkill(sid).then(function () {
              toast('技能已删除', 'success');
              loadSkills();
            }).catch(function () { toast('删除失败', 'error'); });
          }
        });
      });
    }).catch(function () {});
  }

  function showSkillDetail(skillId) {
    console.log('showSkillDetail called with:', skillId);
    try {
      var cards = dom.panelSkills.querySelectorAll('.skill-card');
      console.log('Found', cards.length, 'skill cards');
      var skill = null;
      cards.forEach(function (c) {
        var cid = c.getAttribute('data-skill-id');
        if (cid === skillId) {
          var nameEl = c.querySelector('.skill-name');
          var descEl = c.querySelector('.skill-desc');
          var metaEl = c.querySelector('.skill-meta');
          if (nameEl && descEl && metaEl) {
            skill = {
              name: nameEl.textContent,
              desc: descEl.textContent,
              meta: metaEl.textContent,
            };
          }
        }
      });
      if (!skill) { console.error('Skill not found for id:', skillId); return; }
      console.log('Showing detail for:', skill.name);

      var titleEl = $('skillDetailTitle');
      var bodyEl = $('skillDetailBody');
      var modalEl = $('skillDetailModal');
      console.log('Modal elements:', !!titleEl, !!bodyEl, !!modalEl);

      if (!titleEl || !bodyEl || !modalEl) {
        console.error('Modal elements missing!');
        return;
      }

      titleEl.textContent = skill.name;
      var html = '';
      html += '<p style="font-size:13px;color:var(--text-secondary);margin-bottom:6px">' + esc(skill.desc) + '</p>';
      html += '<p style="font-size:12px;color:var(--text-secondary)">' + esc(skill.meta) + '</p>';
      html += '<p style="font-size:11px;color:var(--text-secondary);margin-top:10px">💡 点击技能卡片空白区域可应用此技能。</p>';
      bodyEl.innerHTML = html;
      modalEl.style.display = '';
      console.log('Modal should be visible now');
    } catch (err) {
      console.error('showSkillDetail error:', err.message, err.stack);
    }
  }

  function loadHistory() {
    API.getHistory(50).then(function (data) {
      var tasks = data.tasks || [];
      if (tasks.length === 0) {
        dom.panelHistory.innerHTML = '<p class="placeholder-text">暂无转换记录</p>';
        return;
      }
      var html = '';
      tasks.forEach(function (t) {
        var cls = 'history-status ' + (t.status || '');
        html += '<div class="history-item">';
        html += '<div class="history-name">' + esc(t.source_filename || '') + '</div>';
        html += '<div class="history-meta">' + esc(t.created_at || '').substring(0, 16) + '</div>';
        html += '<span class="' + cls + '">' + statusLabel(t.status) + '</span>';
        html += '</div>';
      });
      dom.panelHistory.innerHTML = html;
    }).catch(function () {});
  }

  function statusLabel(s) {
    var map = { completed: '已完成', failed: '失败', cancelled: '已取消', in_progress: '进行中' };
    return map[s] || s || '';
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
    // Lazy-load more diff rows when switching to diff tab
    if (name === 'diff' && state.currentTask) {
      ensureDiffScroll();
    }
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
      loadFilePreview(data.preview);
      enableTab('preview');
      // Refresh skills (might have matched ones)
      loadSkills();
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
  // Convert
  // ============================================================
  function doConvert(extraInstruction) {
    var text = extraInstruction || dom.chatInput.value.trim();
    if (!text) { toast('请输入清洗指令', 'warning'); return; }
    if (!state.currentFile) { toast('请先上传文件', 'warning'); return; }
    if (!state.targetFormat) { toast('请选择目标格式', 'warning'); return; }

    if (!extraInstruction) state.conversationHistory.push(text);
    var fullInstructions = state.conversationHistory.join('; ');

    addMsg('user', text);
    if (!extraInstruction) dom.chatInput.value = '';
    setLoading(true); setStep('analyzing'); hideExportButtons();

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

  function doConvertWithSkill(skillId) {
    if (!state.currentFile || !state.targetFormat) return;
    setLoading(true); setStep('analyzing'); hideExportButtons();
    API.setTarget(state.currentFile.file_id, state.targetFormat, state.targetEncoding).then(function () {
      setStep('generating');
      return API.convert(state.currentFile.file_id, '', skillId);
    }).then(function (result) {
      setLoading(false);
      handleConvertResult(result);
    }).catch(function (e) {
      setLoading(false); setStep('idle');
      toast('技能应用失败: ' + e.message, 'error');
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
  // Diff View (with lazy loading on scroll)
  // ============================================================
  function loadDiff(task) {
    var diff = task.diff || {};
    var preview = task.preview || {};
    var src = task.source_preview || state.currentFile.preview || {};

    state.allSourceRows = src.rows || [];
    state.allTargetRows = preview.rows || [];
    state.diffLoadedCount = 0;
    state.sourceCols = (src.columns || []).map(function (c) { return esc(String(c)); });
    state.targetCols = (preview.columns || []).map(function (c) { return esc(String(c)); });
    state.removedSet = {};
    (diff.removed_rows || []).forEach(function (r) { state.removedSet[r] = true; });

    dom.diffSummary.textContent = '原始 ' + (diff.row_counts && diff.row_counts.original || state.allSourceRows.length) +
      ' 行 → 转换后 ' + (diff.row_counts && diff.row_counts.transformed || state.allTargetRows.length) + ' 行';

    // Init tables with headers
    initDiffTables(state.sourceCols, state.targetCols);

    // Load first batch
    appendDiffBatch();

    // Scroll handler for lazy loading
    function onScroll() {
      var st = dom.sourceTable;
      if (st.scrollTop + st.clientHeight >= st.scrollHeight - 50) {
        appendDiffBatch();
      }
    }
    dom.sourceTable.removeEventListener('scroll', onScroll);
    dom.sourceTable.addEventListener('scroll', onScroll);
    dom.targetTable.removeEventListener('scroll', onSync);
    dom.targetTable.addEventListener('scroll', onSync);

    function onSync() {
      // Sync scroll between source and target
      dom.sourceTable.scrollTop = dom.targetTable.scrollTop;
    }
  }

  function appendDiffBatch() {
    var start = state.diffLoadedCount;
    var end = Math.min(start + state.diffBatchSize, Math.max(state.allSourceRows.length, state.allTargetRows.length));
    if (start >= end) return;

    var maxRows = Math.max(state.allSourceRows.length, state.allTargetRows.length);
    var batchEnd = Math.min(start + state.diffBatchSize, maxRows);

    // Build source table batch
    var shtml = '';
    for (var i = start; i < batchEnd; i++) {
      var removed = state.removedSet[i];
      shtml += '<tr' + (removed ? ' class="row-removed"' : '') + '>';
      var srow = state.allSourceRows[i] || [];
      state.sourceCols.forEach(function (c, ci) {
        var v = srow[ci];
        shtml += '<td>' + (v != null ? esc(String(v)) : '') + '</td>';
      });
      shtml += '</tr>';
    }
    // Append to source table (keep thead)
    var st = dom.sourceTable.querySelector('tbody') || (function () {
      var tbody = document.createElement('tbody');
      dom.sourceTable.querySelector('table').appendChild(tbody);
      return tbody;
    })();
    st.insertAdjacentHTML('beforeend', shtml);

    // Build target table batch
    var thtml = '';
    for (var j = start; j < batchEnd; j++) {
      thtml += '<tr>';
      var trow = state.allTargetRows[j] || [];
      state.targetCols.forEach(function (c, ci) {
        var v = trow[ci];
        thtml += '<td>' + (v != null ? esc(String(v)) : '') + '</td>';
      });
      thtml += '</tr>';
    }
    var tt = dom.targetTable.querySelector('tbody') || (function () {
      var tbody = document.createElement('tbody');
      dom.targetTable.querySelector('table').appendChild(tbody);
      return tbody;
    })();
    tt.insertAdjacentHTML('beforeend', thtml);

    state.diffLoadedCount = batchEnd;

    // Show load status
    if (state.diffLoadedCount < maxRows) {
      var remaining = maxRows - state.diffLoadedCount;
      // Add a "loading more" indicator row
      var loadRow = '<tr><td colspan="99" style="text-align:center;color:var(--text-secondary);padding:8px;">↓ 向下滚动加载更多 (剩余 ' + remaining + ' 行)</td></tr>';
      st.insertAdjacentHTML('beforeend', loadRow);
      tt.insertAdjacentHTML('beforeend', loadRow);
    }
  }

  function ensureDiffScroll() {
    if (state.diffLoadedCount < Math.max(state.allSourceRows.length, state.allTargetRows.length)) {
      // Force load more if diff tab is active
    }
  }

  // Initialize source table with header
  function initDiffTables(srcCols, tgtCols) {
    var sh = '<table><thead><tr>';
    srcCols.forEach(function (c) { sh += '<th>' + c + '</th>'; });
    sh += '</tr></thead><tbody></tbody></table>';
    dom.sourceTable.innerHTML = sh;

    var th = '<table><thead><tr>';
    tgtCols.forEach(function (c) { th += '<th>' + c + '</th>'; });
    th += '</tr></thead><tbody></tbody></table>';
    dom.targetTable.innerHTML = th;
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
      if (r.skill_saved) { msg += ' | 技能已保存 ✅'; loadSkills(); }
      toast(msg, 'success'); addMsg('system', msg);
      window.open(API.getDownloadUrl(state.currentTask.task_id), '_blank');
      loadHistory();
      resetAfterExport();
    }).catch(function (e) { toast('导出失败: ' + e.message, 'error'); });
  }

  function cancelConvert() { resetAfterExport(); }

  function refreshChat() {
    state.conversationHistory = [];
    dom.chatMsgs.innerHTML = '<div class="message system"><div class="message-content">对话已刷新。请上传文件并输入清洗指令。</div></div>';
    hideAlert();
    hideExportButtons();
    setStep('idle');
    state.currentTask = null;
    toast('对话已刷新', 'info');
  }

  function resetAfterExport() {
    setStep('idle'); state.currentTask = null; hideExportButtons();
    hideAlert();
    state.allSourceRows = []; state.allTargetRows = []; state.diffLoadedCount = 0;
    dom.mainTabBar.querySelectorAll('.main-tab').forEach(function (b) {
      if (b.dataset.view === 'diff' || b.dataset.view === 'code') b.disabled = true;
    });
    switchTab('chat');
  }

  // ============================================================
  // Dirty Data Modal
  // ============================================================
  function showModal(issues) {
    // Also show in sidebar alert area
    showAlert(issues);
    // Keep modal for backward compatibility (will be removed once alert area is stable)
    var html = '';
    issues.forEach(function (iss) {
      html += '<div class="issue-item">';
      html += '<div class="issue-row"><strong>行 ' + iss.row + '</strong> · ' + esc(String(iss.column)) + '</div>';
      html += '<div class="issue-value">值: <code>' + esc(String(iss.value || '').substring(0, 60)) + '</code></div>';
      html += '<div class="issue-error">' + esc(String(iss.error)) + '</div>';
      html += '<div class="issue-suggestion">💡 ' + esc(String(iss.suggested_action || '')) + '</div>';
      html += '</div>';
    });
    dom.modalBody.innerHTML = html;
    dom.confirmModal.style.display = '';
  }

  function showAlert(issues) {
    var html = '';
    var maxShow = Math.min(issues.length, 8);
    for (var i = 0; i < maxShow; i++) {
      var iss = issues[i];
      html += '<div class="alert-item">';
      html += '<div class="alert-row"><b>行 ' + iss.row + '</b> ' + esc(String(iss.column)) + '</div>';
      html += '<div class="alert-detail">' + esc(String(iss.error).substring(0, 60)) + '</div>';
      html += '</div>';
    }
    if (issues.length > maxShow) {
      html += '<div class="alert-item" style="color:var(--text-secondary)">...还有 ' + (issues.length - maxShow) + ' 个问题</div>';
    }
    dom.alertList.innerHTML = html;
    dom.alertArea.style.display = '';
  }

  function hideAlert() {
    dom.alertArea.style.display = 'none';
    dom.alertList.innerHTML = '';
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
        showExportButtons(); switchTab('diff');
        addMsg('system', '✅ 已移除异常行。');
      }
    }).catch(function (e) { toast('操作失败: ' + e.message, 'error'); });
  }

  function doContinueChat() {
    hideModal();
    addMsg('system', '💬 请在对话区输入补充指令来修正脏数据，然后点击发送。');
    switchTab('chat');
    dom.chatInput.focus();
    dom.chatInput.placeholder = '输入修正指令，如：将99999999替换为空...';
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
        showExportButtons(); switchTab('diff');
        addMsg('system', '✅ 已跳过异常行。');
      }
    }).catch(function (e) { toast('操作失败: ' + e.message, 'error'); });
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

    // Save skill checkbox
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
    $('btnChat').addEventListener('click', doContinueChat);
    $('btnSkip').addEventListener('click', doSkipRow);

    // Alert area (sidebar)
    dom.alertAccept.addEventListener('click', doAcceptSuggestion);
    dom.alertChat.addEventListener('click', doContinueChat);
    dom.alertSkip.addEventListener('click', doSkipRow);

    // Skill detail modal
    $('btnSkillClose').addEventListener('click', function () {
      $('skillDetailModal').style.display = 'none';
    });
    $('skillDetailModal').addEventListener('click', function (e) {
      if (e.target === $('skillDetailModal')) {
        $('skillDetailModal').style.display = 'none';
      }
    });

    // Refresh chat
    dom.btnRefresh.addEventListener('click', refreshChat);
  }

  function init() {
    cacheDom();
    bindEvents();
    loadSkills();
    loadHistory();
    console.log('MorphSheet ready');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
