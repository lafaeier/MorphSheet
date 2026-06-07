/**
 * MorphSheet - Vue 3 Application
 */

const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

// ============================================================
// Global State
// ============================================================
const state = reactive({
  // File
  currentFile: null,

  // Target
  targetFormat: '',
  targetEncoding: 'utf-8',

  // Conversion
  currentTask: null,
  taskPhase: 'idle', // idle | uploading | analyzing | generating | executing | awaiting | done | error
  statusMessages: [],

  // UI
  theme: 'dark',
  activeView: 'chat', // chat | diff
  showModal: false,
  modalIssues: [],
  toasts: [],

  // History & Skills
  history: [],
  skills: [],
  matchedSkills: [],
  sidebarTab: 'history',

  // Chat
  chatMessages: [],
  chatLoading: false,

  // Upload
  uploading: false,
  fileHighlight: false,
});

// ============================================================
// Status Steps Definition
// ============================================================
const STATUS_STEPS = [
  { key: 'uploaded', label: '文件已上传' },
  { key: 'analyzing_schema', label: '分析 Schema' },
  { key: 'generating_code', label: '生成转换代码' },
  { key: 'executing', label: '沙箱执行中' },
  { key: 'computing_diff', label: '生成 Diff 对比' },
  { key: 'awaiting_confirmation', label: '等待导出确认' },
];

// ============================================================
// Root App
// ============================================================
const App = {
  setup() { return { state }; },
  template: `
    <sidebar-panel></sidebar-panel>
    <div class="workspace">
      <upload-bar></upload-bar>
      <div v-if="state.activeView === 'chat'" class="chat-container">
        <chat-panel></chat-panel>
      </div>
      <div v-else class="diff-container">
        <diff-view></diff-view>
      </div>
    </div>
    <status-panel></status-panel>
    <confirm-modal></confirm-modal>
    <toast-container></toast-container>
  `,
};

// ============================================================
// Sidebar Component
// ============================================================
const SidebarPanel = {
  setup() { return { state }; },
  template: `
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2 class="sidebar-title" @click="toggleTheme" title="点击切换主题">MorphSheet</h2>
      </div>
      <div class="sidebar-tabs">
        <button class="tab-btn" :class="{active: state.sidebarTab==='history'}" @click="state.sidebarTab='history'">历史记录</button>
        <button class="tab-btn" :class="{active: state.sidebarTab==='skills'}" @click="state.sidebarTab='skills'">技能库</button>
      </div>
      <div class="sidebar-content">
        <div v-if="state.sidebarTab==='history'">
          <div v-if="state.history.length===0" class="placeholder-text">暂无转换记录</div>
          <div v-for="h in state.history" :key="h.task_id" class="history-item" @click="loadHistory(h)">
            <div class="history-name">{{ truncate(h.source_filename, 20) }}</div>
            <div class="history-meta">{{ formatDate(h.created_at) }}</div>
            <span class="history-status" :class="h.status">{{ statusLabel(h.status) }}</span>
          </div>
        </div>
        <div v-if="state.sidebarTab==='skills'">
          <div v-if="state.skills.length===0" class="placeholder-text">暂无保存的技能</div>
          <div v-for="s in state.skills" :key="s.skill_id" class="skill-card"
               :class="{matched: isMatched(s.skill_id)}"
               @click="applySkill(s)">
            <div class="skill-name">{{ s.name }}</div>
            <div class="skill-desc">{{ truncate(s.description, 40) }}</div>
            <div class="skill-meta">使用 {{ s.usage_count }} 次 · {{ s.target_format }}</div>
          </div>
        </div>
      </div>
    </aside>
  `,
  methods: {
    toggleTheme() {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', state.theme);
    },
    truncate(s, n) { return Utils.truncate(s, n); },
    formatDate(d) { return Utils.formatDate(d); },
    statusLabel(s) { return Utils.statusLabel(s); },
    isMatched(id) { return state.matchedSkills.some(m => m.skill_id === id); },
    loadHistory(h) { /* open past task details */ },
    applySkill(s) {
      if (!state.currentFile) {
        addToast('请先上传文件', 'warning');
        return;
      }
      doConvert(state.currentFile.file_id, state.chatInput || '', s.skill_id);
    },
  },
};

// ============================================================
// Upload Bar Component
// ============================================================
const UploadBar = {
  setup() { return { state }; },
  template: `
    <div class="top-bar">
      <div class="upload-area" :class="{'drag-over': state.fileHighlight}"
           @click="openFilePicker"
           @dragover.prevent="state.fileHighlight=true"
           @dragleave="state.fileHighlight=false"
           @drop.prevent="onDrop">
        <div class="upload-icon">📂</div>
        <p v-if="!state.currentFile">拖拽文件到此处，或点击选择</p>
        <p v-else>已选择: {{ state.currentFile.filename }}</p>
        <p class="upload-hint">支持 .xlsx / .xls / .csv</p>
        <input type="file" ref="fileInput" accept=".xlsx,.xls,.csv" hidden @change="onFilePicked">
      </div>
      <div class="target-selector">
        <label>目标格式：</label>
        <select v-model="state.targetFormat" @change="onTargetChange">
          <option value="">选择格式...</option>
          <option value="xlsx">.xlsx (Excel 2007+)</option>
          <option value="xls">.xls (Excel 97-2003)</option>
          <option value="csv">.csv (CSV)</option>
        </select>
        <select v-if="state.targetFormat==='csv'" v-model="state.targetEncoding">
          <option value="utf-8">UTF-8</option>
          <option value="gbk">GBK</option>
          <option value="gb2312">GB2312</option>
        </select>
      </div>
      <button class="btn-primary" :disabled="!canConvert" @click="onConvert">开始转换</button>
    </div>
  `,
  computed: {
    canConvert() {
      return state.currentFile && state.targetFormat && state.taskPhase === 'idle';
    },
  },
  methods: {
    openFilePicker() { this.$refs.fileInput.click(); },
    onFilePicked(e) {
      const file = e.target.files[0];
      if (file) this.processFile(file);
    },
    onDrop(e) {
      state.fileHighlight = false;
      const file = e.dataTransfer.files[0];
      if (file) this.processFile(file);
    },
    async processFile(file) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['xlsx', 'xls', 'csv'].includes(ext)) {
        addToast('不支持的文件格式: .' + ext, 'error');
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        addToast('文件大小超过 50MB 限制', 'error');
        return;
      }
      state.uploading = true;
      state.taskPhase = 'uploading';
      try {
        const data = await API.upload(file);
        state.currentFile = data;
        state.taskPhase = 'uploaded';
        addSystemMsg('文件已上传: ' + file.name + ' (' + data.schema_info.row_count + ' 行, ' + data.schema_info.columns.length + ' 列)');
        addSystemMsg('检测到列: ' + data.schema_info.columns.join(', '));
        // Match skills
        try {
          const match = await API.matchSkills(data.file_id);
          if (match.matches && match.matches.length > 0) {
            state.matchedSkills = match.matches;
            addSystemMsg('💡 检测到 ' + match.matches.length + ' 个相似历史转换模板，可在左侧技能库中一键应用');
          }
        } catch (_) { /* ignore */ }
      } catch (e) {
        addToast('上传失败: ' + e.message, 'error');
        state.taskPhase = 'idle';
      }
      state.uploading = false;
    },
    onTargetChange() {
      if (state.currentFile && state.targetFormat) {
        API.setTarget(state.currentFile.file_id, state.targetFormat, state.targetEncoding).catch(() => {});
      }
    },
    async onConvert() {
      const instructions = state.chatInput || '';
      if (!instructions.trim()) {
        addToast('请在对话区输入清洗指令', 'warning');
        return;
      }
      await doConvert(state.currentFile.file_id, instructions);
    },
  },
};

// ============================================================
// Chat Panel Component
// ============================================================
const ChatPanel = {
  setup() { return { state }; },
  template: `
    <div>
      <div class="chat-messages" ref="msgContainer">
        <div v-for="(msg, i) in state.chatMessages" :key="i" class="message" :class="msg.role">
          <div class="message-content">
            <div v-for="(line, j) in msg.lines" :key="j" v-html="line"></div>
          </div>
        </div>
        <div v-if="state.chatLoading" class="message system">
          <div class="message-content">⏳ Agent 思考中...</div>
        </div>
      </div>
      <div class="chat-input">
        <input type="text" ref="chatInput" v-model="state.chatInput"
               placeholder="输入数据清洗指令，如：删除所有金额小于0的行..."
               :disabled="!state.currentFile || state.chatLoading"
               @keydown.enter="sendMessage">
        <button :disabled="!state.chatInput || !state.currentFile || state.chatLoading"
                @click="sendMessage">发送</button>
      </div>
    </div>
  `,
  mounted() {
    state.chatInput = '';
  },
  methods: {
    sendMessage() {
      const text = state.chatInput.trim();
      if (!text || !state.currentFile || state.chatLoading) return;
      addUserMsg(text);
      state.chatInput = '';
      doConvert(state.currentFile.file_id, text);
    },
  },
};

// ============================================================
// Diff View Component
// ============================================================
const DiffView = {
  setup() { return { state }; },
  template: `
    <div>
      <div class="diff-header">
        <span>数据对比预览</span>
        <div class="diff-actions">
          <button class="btn-primary" @click="onExport">确认导出</button>
          <button class="btn-secondary" @click="onCancel">返回修改</button>
        </div>
      </div>
      <div class="diff-panels">
        <div class="diff-panel left">
          <h3>源数据 ({{ (diff.row_counts && diff.row_counts.original) || 0 }} 行)</h3>
          <div class="diff-table-wrapper">
            <table>
              <thead><tr><th v-for="c in sourceColumns" :key="c">{{ c }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, ri) in sourceRows" :key="ri" :class="rowClass(ri)">
                  <td v-for="(cell, ci) in row" :key="ci"
                      :class="cellClass(ri, sourceColumns[ci])">{{ cell || '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="diff-panel right">
          <h3>转换后 ({{ (diff.row_counts && diff.row_counts.transformed) || 0 }} 行)</h3>
          <div class="diff-table-wrapper">
            <table>
              <thead><tr><th v-for="c in targetColumns" :key="c"
                             :class="{ added: isAddedCol(c) }">{{ c }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, ri) in targetRows" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci"
                      :class="cellClassT(ri, targetColumns[ci], cell)">{{ cell || '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
  data() {
    return {
      diff: { row_counts: {} },
      sourceColumns: [],
      targetColumns: [],
      sourceRows: [],
      targetRows: [],
      removedRows: new Set(),
      modifiedCells: new Map(),
      addedCols: new Set(),
      removedCols: new Set(),
    };
  },
  mounted() {
    this.loadDiff();
  },
  methods: {
    loadDiff() {
      const task = state.currentTask;
      if (!task) return;
      this.diff = task.diff || {};
      // Build source display
      if (task.source_preview) {
        this.sourceColumns = task.source_preview.columns || [];
        this.sourceRows = task.source_preview.rows || [];
      }
      // Build target display
      if (task.preview) {
        this.targetColumns = task.preview.columns || [];
        this.targetRows = task.preview.rows || [];
      }
      // Parse diff metadata
      if (this.diff) {
        (this.diff.removed_rows || []).forEach(r => this.removedRows.add(r));
        (this.diff.modified_cells || []).forEach(c => {
          this.modifiedCells.set(c.row + ':' + c.col, c);
        });
        (this.diff.added_columns || []).forEach(c => this.addedCols.add(c));
        (this.diff.removed_columns || []).forEach(c => this.removedCols.add(c));
      }
    },
    isAddedCol(c) { return this.addedCols.has(c); },
    rowClass(ri) {
      return this.removedRows.has(ri) ? 'row-removed' : '';
    },
    cellClass(ri, col) {
      const key = ri + ':' + col;
      return this.modifiedCells.has(key) ? 'cell-modified' : '';
    },
    cellClassT(ri, col) {
      return this.isAddedCol(col) ? 'cell-added' : '';
    },
    async onExport() {
      if (!state.currentTask) return;
      try {
        const result = await API.exportTask(state.currentTask.task_id);
        addSystemMsg('导出成功: ' + result.file_path);
        state.taskPhase = 'done';
        // Trigger download
        const url = API.getDownloadUrl(state.currentTask.task_id);
        window.open(url, '_blank');
        addToast('文件已导出', 'success');
      } catch (e) {
        addToast('导出失败: ' + e.message, 'error');
      }
    },
    onCancel() {
      state.activeView = 'chat';
      state.currentTask = null;
      state.taskPhase = 'idle';
    },
  },
};

// ============================================================
// Status Panel Component
// ============================================================
const StatusPanel = {
  setup() { return { state }; },
  template: `
    <aside class="statusbar">
      <div class="status-header">
        <h3>Agent 状态</h3>
      </div>
      <div class="status-steps">
        <div v-for="(step, i) in steps" :key="step.key" class="step" :class="step.state">
          <span class="step-icon">{{ iconFor(step.state) }}</span>
          <span class="step-label">{{ step.label }}</span>
        </div>
        <div v-if="state.statusMessages.length > 0" class="status-log">
          <div v-for="(m, i) in state.statusMessages" :key="i" class="status-log-item">
            {{ m.message || m }}
          </div>
        </div>
      </div>
    </aside>
  `,
  computed: {
    steps() {
      const phase = state.taskPhase;
      return STATUS_STEPS.map((s, i) => {
        const keys = STATUS_STEPS.map(x => x.key);
        const currentIdx = keys.indexOf(phase);
        let stepState = 'pending';
        if (i < currentIdx) stepState = 'done';
        else if (i === currentIdx) stepState = 'active';
        else if (phase === 'error' && i === currentIdx + 1) stepState = 'error';
        return { key: s.key, label: s.label, state: stepState };
      });
    },
  },
  methods: {
    iconFor(st) {
      if (st === 'done') return '●';
      if (st === 'active') return '◉';
      if (st === 'error') return '✕';
      return '○';
    },
  },
};

// ============================================================
// Confirm Modal Component
// ============================================================
const ConfirmModal = {
  setup() { return { state }; },
  template: `
    <div v-if="state.showModal" class="modal-overlay" @click.self="/* no close */">
      <div class="modal-box">
        <div class="modal-header">
          <h3>⚠ 发现异常数据</h3>
        </div>
        <div class="modal-body">
          <div v-for="(issue, i) in state.modalIssues" :key="i" class="issue-item">
            <div class="issue-row"><strong>行 {{ issue.row }}</strong> · 列: {{ issue.column }}</div>
            <div class="issue-value">当前值: <code>{{ issue.value }}</code></div>
            <div class="issue-error">{{ issue.error }}</div>
            <div class="issue-suggestion">💡 建议: {{ issue.suggested_action }}</div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-primary" @click="accept">采纳建议</button>
          <button class="btn-secondary" @click="skip">跳过此行</button>
          <button class="btn-danger" @click="abort">终止转换</button>
        </div>
      </div>
    </div>
  `,
  methods: {
    async accept() {
      if (state.currentTask) {
        try {
          await API.confirmAction(state.currentTask.task_id, 'accept_suggestion');
        } catch (_) {}
      }
      state.showModal = false;
      state.modalIssues = [];
    },
    async skip() {
      if (state.currentTask) {
        try {
          await API.confirmAction(state.currentTask.task_id, 'skip_row');
        } catch (_) {}
      }
      state.showModal = false;
      state.modalIssues = [];
    },
    async abort() {
      if (state.currentTask) {
        try {
          await API.confirmAction(state.currentTask.task_id, 'abort');
        } catch (_) {}
      }
      state.showModal = false;
      state.modalIssues = [];
      state.taskPhase = 'idle';
    },
  },
};

// ============================================================
// Toast Component
// ============================================================
const ToastContainer = {
  setup() { return { state }; },
  template: `
    <div class="toast-container">
      <div v-for="(t, i) in state.toasts" :key="i" class="toast" :class="t.type">
        {{ t.message }}
      </div>
    </div>
  `,
};

// ============================================================
// Helper Functions
// ============================================================
function addUserMsg(text) {
  state.chatMessages.push({ role: 'user', lines: [Utils.escapeHtml(text)] });
  scrollChat();
}

function addSystemMsg(text) {
  const lines = text.split('\n').map(l => Utils.escapeHtml(l));
  state.chatMessages.push({ role: 'system', lines });
  scrollChat();
}

function scrollChat() {
  nextTick(() => {
    const mc = document.querySelector('.chat-messages');
    if (mc) mc.scrollTop = mc.scrollHeight;
  });
}

function addToast(message, type = 'info') {
  state.toasts.push({ message, type });
  setTimeout(() => {
    state.toasts.shift();
  }, 3000);
}

async function doConvert(fileId, instructions, skillId = null) {
  if (!state.targetFormat) {
    addToast('请先选择目标格式', 'warning');
    return;
  }
  state.chatLoading = true;
  state.taskPhase = 'analyzing_schema';
  state.statusMessages = [];

  // Connect WebSocket for status updates
  try {
    AgentWS.connect('pending');
    AgentWS.onMessage((data) => {
      if (data.type === 'phase') {
        state.taskPhase = data.phase;
        state.statusMessages.push(data);
      } else if (data.type === 'blocking') {
        state.modalIssues = data.issues || [];
        state.showModal = true;
      } else if (data.type === 'completed') {
        state.statusMessages.push(data);
      } else if (data.type === 'error') {
        addToast(data.message, 'error');
        state.statusMessages.push(data);
      }
    });
  } catch (_) {
    // WebSocket optional in Phase 3
  }

  try {
    const result = await API.convert(fileId, instructions, skillId);

    if (result.status === 'awaiting_confirmation') {
      // Save source preview too for diff
      result.source_preview = state.currentFile ? state.currentFile.preview : null;
      state.currentTask = result;
      state.taskPhase = 'awaiting_confirmation';
      state.activeView = 'diff';
      addSystemMsg('✅ 转换完成！请查看 Diff 视图确认结果。');
    } else if (result.status === 'awaiting_human_confirmation') {
      state.currentTask = result;
      state.modalIssues = result.detected_issues || [];
      state.showModal = true;
      state.taskPhase = 'awaiting';
    } else if (result.status === 'failed') {
      addSystemMsg('❌ 转换失败: ' + (result.error || '未知错误'));
      addToast('转换失败', 'error');
      state.taskPhase = 'error';
    }
  } catch (e) {
    addSystemMsg('❌ 转换失败: ' + e.message);
    addToast('转换失败: ' + e.message, 'error');
    state.taskPhase = 'error';
  }

  state.chatLoading = false;
}

// ============================================================
// CSS additions for dynamic components
// ============================================================
const DYNAMIC_STYLES = `
.toast-container { position:fixed; top:16px; right:16px; z-index:9999; display:flex; flex-direction:column; gap:8px; }
.toast { padding:10px 20px; border-radius:8px; font-size:13px; color:#fff; animation:fadeIn 0.3s ease; max-width:360px; }
.toast.info { background:#4cc9f0; color:#1a1a2e; }
.toast.success { background:#06d6a0; color:#1a1a2e; }
.toast.warning { background:#ffd166; color:#1a1a2e; }
.toast.error { background:#ef476f; }
.history-item { padding:8px 12px; border-radius:6px; cursor:pointer; margin-bottom:4px; transition:var(--transition); }
.history-item:hover { background:var(--bg-tertiary); }
.history-name { font-size:13px; font-weight:500; }
.history-meta { font-size:11px; color:var(--text-secondary); }
.history-status { font-size:11px; padding:2px 6px; border-radius:4px; }
.history-status.completed { color:var(--success); }
.history-status.failed { color:var(--danger); }
.skill-card { padding:10px 12px; border:1px solid var(--border); border-radius:6px; margin-bottom:6px; cursor:pointer; transition:var(--transition); }
.skill-card:hover { border-color:var(--accent); }
.skill-card.matched { border-color:var(--success); box-shadow:0 0 0 1px var(--success); }
.skill-name { font-size:13px; font-weight:600; }
.skill-desc { font-size:12px; color:var(--text-secondary); margin-top:2px; }
.skill-meta { font-size:11px; color:var(--text-secondary); margin-top:4px; }
.issue-item { padding:12px; border:1px solid var(--border); border-radius:6px; margin-bottom:8px; }
.issue-row { font-size:13px; margin-bottom:4px; }
.issue-value { font-size:12px; color:var(--text-secondary); margin-bottom:4px; }
.issue-value code { background:var(--bg-tertiary); padding:1px 6px; border-radius:3px; font-size:12px; }
.issue-error { font-size:12px; color:var(--danger); margin-bottom:4px; }
.issue-suggestion { font-size:12px; color:var(--success); }
.status-log { margin-top:16px; padding-top:12px; border-top:1px solid var(--border); }
.status-log-item { font-size:11px; color:var(--text-secondary); padding:3px 0; }
td.cell-added { background:var(--diff-added); }
`;

// ============================================================
// Bootstrap
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  if (typeof Vue === 'undefined') {
    document.getElementById('loading-msg').style.display = 'flex';
    return;
  }

  // Inject dynamic styles
  const styleEl = document.createElement('style');
  styleEl.textContent = DYNAMIC_STYLES;
  document.head.appendChild(styleEl);

  // Create Vue app
  const app = createApp(App);
  app.component('SidebarPanel', SidebarPanel);
  app.component('UploadBar', UploadBar);
  app.component('ChatPanel', ChatPanel);
  app.component('DiffView', DiffView);
  app.component('StatusPanel', StatusPanel);
  app.component('ConfirmModal', ConfirmModal);
  app.component('ToastContainer', ToastContainer);

  // Global error handler
  app.config.errorHandler = function(err, vm, info) {
    console.error('Vue error:', err, info);
    const loading = document.getElementById('loading-msg');
    if (loading) {
      loading.style.display = 'flex';
      loading.innerHTML = '<div style="text-align:center"><h2>⚠ 应用初始化错误</h2>' +
        '<p style="font-size:12px;color:var(--text-secondary);max-width:500px;margin-top:8px">' +
        (err.message || String(err)) + '</p>' +
        '<p style="margin-top:12px;font-size:12px">请检查浏览器控制台 (F12) 获取详细信息</p></div>';
    }
  };

  try {
    app.mount('#app');
    document.getElementById('loading-msg').style.display = 'none';
    document.getElementById('app').style.display = '';
    console.log('MorphSheet mounted successfully');
  } catch (e) {
    console.error('Mount error:', e);
    document.getElementById('loading-msg').style.display = 'flex';
    document.getElementById('loading-msg').innerHTML =
      '<div style="text-align:center"><h2>⚠ 启动失败</h2>' +
      '<p style="font-size:12px;margin-top:8px">' + e.message + '</p></div>';
  }
});
