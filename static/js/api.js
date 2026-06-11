/**
 * MorphSheet API Client
 */

async function _safeError(res, fallback) {
  try {
    const text = await res.text();
    const err = JSON.parse(text);
    return new Error(err.detail || err.message || fallback);
  } catch (_) {
    return new Error(fallback + ' (HTTP ' + res.status + ')');
  }
}

const API = {
  async upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!res.ok) throw await _safeError(res, '上传失败');
    return res.json();
  },

  async setTarget(fileId, targetFormat, targetEncoding = 'utf-8') {
    const res = await fetch('/api/set-target', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: fileId,
        target_format: targetFormat,
        target_encoding: targetEncoding,
      }),
    });
    if (!res.ok) throw await _safeError(res, '设置目标格式失败');
    return res.json();
  },

  async convert(fileId, instructions, skillId = null) {
    const res = await fetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: fileId,
        instructions,
        use_skill_id: skillId,
      }),
    });
    if (!res.ok) throw await _safeError(res, '转换失败');
    return res.json();
  },

  async confirmAction(taskId, action, overrides = null) {
    const res = await fetch('/api/confirm-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, action, overrides }),
    });
    if (!res.ok) throw await _safeError(res, '操作失败');
    return res.json();
  },

  async exportTask(taskId, saveAsSkill = false, skillName = null) {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        save_as_skill: saveAsSkill,
        skill_name: skillName,
      }),
    });
    if (!res.ok) throw await _safeError(res, '导出失败');
    return res.json();
  },

  async getHistory(limit = 20, offset = 0) {
    const res = await fetch(`/api/history?limit=${limit}&offset=${offset}`);
    return res.json();
  },

  async getSkills(limit = 20) {
    const res = await fetch(`/api/skills?limit=${limit}`);
    return res.json();
  },

  async matchSkills(fileId) {
    const res = await fetch('/api/match-skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId }),
    });
    return res.json();
  },

  async deleteSkill(skillId) {
    const res = await fetch(`/api/skills/${skillId}`, { method: 'DELETE' });
    return res.json();
  },

  getDownloadUrl(taskId) {
    return `/api/download/${taskId}`;
  },
};
