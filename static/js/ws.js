/**
 * MorphSheet WebSocket Client
 */
const AgentWS = {
  _ws: null,
  _listeners: [],

  connect(taskId) {
    this.disconnect();
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws/agent-status/${taskId}`;

    this._ws = new WebSocket(url);

    this._ws.onopen = () => {
      console.log('[WS] Connected:', taskId);
    };

    this._ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        this._listeners.forEach((fn) => {
          try { fn(data); } catch (_) { /* ignore listener errors */ }
        });
      } catch (_) {
        // ignore parse errors
      }
    };

    this._ws.onclose = () => {
      console.log('[WS] Disconnected');
    };

    this._ws.onerror = (e) => {
      console.error('[WS] Error:', e);
    };
  },

  onMessage(fn) {
    this._listeners.push(fn);
  },

  disconnect() {
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._listeners = [];
  },

  send(msg) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  },
};
