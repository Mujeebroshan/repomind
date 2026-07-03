/* ═══════════════════════════════════════════════════════════════
   RepoMind — Frontend Application
   ═══════════════════════════════════════════════════════════════ */

const state = {
  repoPath: '',
  indexed: false,
  analyzed: false,
  chatHistory: [],
  activeTab: 'chat',
};

/* ── Helpers ─────────────────────────────────────────────────── */

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function showToast(msg, type = 'info') {
  const container = $('#toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(40px)'; setTimeout(() => t.remove(), 300); }, 4000);
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Markdown renderer ───────────────────────────────────────── */

function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return `<pre><code class="lang-${lang || 'text'}">${escaped}</code></pre>`;
    })
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    // Lists
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
  // Wrap in paragraph
  html = '<p>' + html + '</p>';
  // Fix nested block elements
  html = html.replace(/<p>(<pre>)/g, '$1').replace(/(<\/pre>)<\/p>/g, '$1');
  html = html.replace(/<p>(<h[234]>)/g, '$1').replace(/(<\/h[234]>)<\/p>/g, '$1');
  html = html.replace(/<p>(<li>)/g, '<ul>$1').replace(/(<\/li>)<\/p>/g, '$1</ul>');
  return html;
}

/* ── Workspace ───────────────────────────────────────────────── */

async function openRepo() {
  const path = $('#repo-path-input').value.trim();
  if (!path) return showToast('Enter a repository path', 'error');
  try {
    const data = await api('POST', '/workspace', { repo_path: path });
    state.repoPath = data.repo_path;
    state.indexed = data.indexed;
    state.analyzed = data.analyzed || false;

    // Update sidebar
    const statusEl = $('#ws-status');
    statusEl.textContent = 'Ready';
    statusEl.className = 'badge badge-ready';
    $('#ws-indexed').textContent = state.indexed ? '✓' : '—';
    $('#ws-indexed').className = state.indexed ? 'badge badge-done' : 'badge';
    $('#ws-analyzed').textContent = state.analyzed ? '✓' : '—';
    $('#ws-analyzed').className = state.analyzed ? 'badge badge-done' : 'badge';

    // Enable buttons
    $('#index-btn').disabled = false;
    $('#analyze-btn').disabled = false;
    $('#send-btn').disabled = false;
    $('#gen-btn').disabled = false;
    $('#suggestions-btn').disabled = false;

    showToast('Repository opened', 'success');

    // Load stats
    try {
      const stats = await api('GET', `/stats?repo_path=${encodeURIComponent(state.repoPath)}`);
      $('#stat-local').textContent = stats.local_count || 0;
      $('#stat-cloud').textContent = stats.escalated_count || 0;
      $('#stat-saved').textContent = `$${(stats.estimated_savings_usd || 0).toFixed(2)}`;
    } catch (e) {}

    // If analyzed, load understanding
    if (state.analyzed) loadKnowledge();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ── Indexing ────────────────────────────────────────────────── */

async function startIndex() {
  if (!state.repoPath) return;
  try {
    await api('POST', '/index', { repo_path: state.repoPath });
    showToast('Indexing started...', 'info');
    const poll = setInterval(async () => {
      try {
        const s = await api('GET', `/index/status?repo_path=${encodeURIComponent(state.repoPath)}`);
        if (s.state === 'done') {
          clearInterval(poll);
          state.indexed = true;
          $('#ws-indexed').textContent = '✓';
          $('#ws-indexed').className = 'badge badge-done';
          showToast(`Indexed! ${s.chunks_indexed} chunks from ${s.files_done} files`, 'success');
        } else if (s.state === 'error') {
          clearInterval(poll);
          showToast(`Index error: ${s.error}`, 'error');
        }
      } catch (e) { clearInterval(poll); }
    }, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ── Analysis ────────────────────────────────────────────────── */

async function startAnalyze() {
  if (!state.repoPath) return;
  const progress = $('#analysis-progress');
  progress.style.display = 'block';
  try {
    await api('POST', '/analyze', { repo_path: state.repoPath, depth: 'standard' });
    showToast('Analysis started...', 'info');
    const poll = setInterval(async () => {
      try {
        const s = await api('GET', `/analyze/status?repo_path=${encodeURIComponent(state.repoPath)}`);
        $('#progress-phase').textContent = s.phase || s.state;
        const total = s.files_total || 1;
        const done = s.files_done || 0;
        const pct = s.state.startsWith('summarizing_dir') ? 60 + (s.directories_done / Math.max(s.directories_total, 1)) * 30
                  : s.state === 'summarizing_project' ? 92
                  : s.state === 'done' ? 100
                  : (done / total) * 60;
        $('#progress-bar').style.width = `${Math.min(pct, 100)}%`;
        $('#progress-detail').textContent = `${done}/${total} files`;

        if (s.state === 'done') {
          clearInterval(poll);
          state.analyzed = true;
          $('#ws-analyzed').textContent = '✓';
          $('#ws-analyzed').className = 'badge badge-done';
          showToast('Analysis complete!', 'success');
          setTimeout(() => { progress.style.display = 'none'; }, 2000);
          loadKnowledge();
          switchTab('understand');
        } else if (s.state === 'error') {
          clearInterval(poll);
          showToast(`Analysis error: ${s.error}`, 'error');
          progress.style.display = 'none';
        }
      } catch (e) { clearInterval(poll); progress.style.display = 'none'; }
    }, 2000);
  } catch (err) {
    showToast(err.message, 'error');
    progress.style.display = 'none';
  }
}

/* ── Chat ────────────────────────────────────────────────────── */

async function sendMessage() {
  const input = $('#chat-input');
  const question = input.value.trim();
  if (!question || !state.repoPath) return;
  input.value = '';
  autoResize(input);

  // Remove welcome message
  const welcome = $('.welcome-message');
  if (welcome) welcome.remove();

  // Add user bubble
  const msgArea = $('#chat-messages');
  const userDiv = document.createElement('div');
  userDiv.className = 'chat-msg chat-msg-user';
  userDiv.innerHTML = `<div class="chat-bubble">${renderMarkdown(question)}</div>`;
  msgArea.appendChild(userDiv);

  // Add assistant bubble (will be streamed into)
  const assistDiv = document.createElement('div');
  assistDiv.className = 'chat-msg chat-msg-assistant';
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.innerHTML = '<p style="color:var(--text-muted)">Thinking...</p>';
  assistDiv.appendChild(bubble);
  msgArea.appendChild(assistDiv);
  msgArea.scrollTop = msgArea.scrollHeight;

  state.chatHistory.push({ role: 'user', content: question });

  // SSE streaming
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: state.repoPath, question, history: state.chatHistory.slice(-6), mode: 'auto' }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.type === 'route') {
            const ri = $('#route-indicator');
            ri.textContent = ev.route === 'local' ? '🟢 local' : '🟡 cloud';
          } else if (ev.type === 'notice') {
            const noticeEl = document.createElement('div');
            noticeEl.className = 'chat-notice';
            noticeEl.textContent = ev.message;
            bubble.before(noticeEl);
          } else if (ev.type === 'token') {
            fullText += ev.text;
            bubble.innerHTML = renderMarkdown(fullText);
            msgArea.scrollTop = msgArea.scrollHeight;
          } else if (ev.type === 'done') {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'chat-meta';
            const routeClass = ev.route === 'local' ? 'local' : 'cloud';
            metaDiv.innerHTML = `<span class="chat-route ${routeClass}">${ev.route === 'local' ? '🟢 local' : '🟡 cloud'}</span>
              <span>${ev.provider_label || ev.provider || ''}</span>`;
            assistDiv.appendChild(metaDiv);
            // Update stats
            $('#stat-local').textContent = ev.local_count || 0;
            $('#stat-cloud').textContent = ev.escalated_count || 0;
            if (ev.estimated_savings_usd != null) {
              $('#stat-saved').textContent = `$${ev.estimated_savings_usd.toFixed(2)}`;
            }
          } else if (ev.type === 'error') {
            bubble.innerHTML = `<p style="color:var(--danger)">${ev.message}</p>`;
          }
        } catch (e) {}
      }
    }
    state.chatHistory.push({ role: 'assistant', content: fullText });
  } catch (err) {
    bubble.innerHTML = `<p style="color:var(--danger)">Error: ${err.message}</p>`;
  }
}

/* ── Knowledge / Understanding ───────────────────────────────── */

async function loadKnowledge() {
  if (!state.repoPath) return;
  try {
    const data = await api('GET', `/knowledge?repo_path=${encodeURIComponent(state.repoPath)}&level=project`);
    if (!data.data || !data.data.summary) return;

    $('#understand-empty').style.display = 'none';
    $('#understand-content').style.display = 'block';

    const d = data.data;
    $('#project-summary').innerHTML = renderMarkdown(d.summary || '');
    $('#architecture-info').innerHTML = renderMarkdown(d.architecture || 'No architecture info available.');

    // Tech stack tags
    const tagList = $('#tech-stack');
    tagList.innerHTML = '';
    (d.tech_stack || []).forEach(t => {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = t;
      tagList.appendChild(tag);
    });

    // Entry points
    const epEl = $('#entry-points');
    if (d.entry_points && d.entry_points.length) {
      epEl.innerHTML = '<h4 style="margin-top:10px;font-size:12px;color:var(--text-muted)">Entry Points</h4>';
      d.entry_points.forEach(ep => { epEl.innerHTML += `<div style="font-family:var(--mono);font-size:12px;color:var(--text-secondary)">→ ${ep}</div>`; });
    }

    // Patterns
    const patternsList = $('#patterns-list');
    patternsList.innerHTML = '';
    (data.patterns || []).forEach(p => {
      const div = document.createElement('div');
      div.className = 'pattern-item';
      div.innerHTML = `<div class="pattern-name">${p.name || '?'}</div><div class="pattern-desc">${p.description || ''}</div>`;
      patternsList.appendChild(div);
    });
    if (!data.patterns || !data.patterns.length) {
      patternsList.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Run deep analysis to extract patterns.</p>';
    }

    // Load repo map
    loadRepoMap();
  } catch (err) {
    showToast(`Knowledge load failed: ${err.message}`, 'error');
  }
}

async function loadRepoMap() {
  if (!state.repoPath) return;
  try {
    const data = await api('GET', `/repomap?repo_path=${encodeURIComponent(state.repoPath)}`);
    $('#repo-map').textContent = data.map || '(empty)';
  } catch (e) {}
}

/* ── Code Generation ─────────────────────────────────────────── */

async function generateCode() {
  const desc = $('#gen-description').value.trim();
  if (!desc || !state.repoPath) return;
  $('#gen-btn').disabled = true;
  $('#gen-btn').textContent = 'Generating...';
  try {
    const data = await api('POST', '/generate/code', { repo_path: state.repoPath, description: desc, target_path: $('#gen-target').value.trim() });
    const result = $('#gen-result');
    result.style.display = 'block';
    $('#gen-file-path').textContent = data.file_path || '';
    const code = data.content || '';
    $('#gen-code').textContent = code;
    $('#gen-explanation').innerHTML = renderMarkdown(data.explanation || '');
    showToast('Code generated!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    $('#gen-btn').disabled = false;
    $('#gen-btn').textContent = 'Generate';
  }
}

/* ── Suggestions ─────────────────────────────────────────────── */

async function loadSuggestions() {
  if (!state.repoPath) return;
  const btn = $('#suggestions-btn');
  btn.disabled = true;
  btn.textContent = 'Loading...';
  try {
    const data = await api('GET', `/suggestions?repo_path=${encodeURIComponent(state.repoPath)}`);
    const list = $('#suggestions-list');
    list.innerHTML = '';
    (data.suggestions || []).forEach(s => {
      const div = document.createElement('div');
      div.className = 'suggestion-item';
      div.innerHTML = `<div class="sugg-category">${s.category || 'general'}</div>
        <div class="sugg-message">${s.message || ''}</div>
        ${s.file_path ? `<div class="sugg-file">${s.file_path}</div>` : ''}`;
      list.appendChild(div);
    });
    if (!data.suggestions || !data.suggestions.length) {
      list.innerHTML = '<p style="color:var(--text-muted)">No suggestions found.</p>';
    }
    showToast('Suggestions loaded', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Load Suggestions';
  }
}

/* ── Settings ────────────────────────────────────────────────── */

async function loadSettings() {
  if (!state.repoPath) return;
  try {
    const data = await api('GET', `/settings?repo_path=${encodeURIComponent(state.repoPath)}`);
    $('#set-backend').value = data.local_backend || 'ollama';
    $('#set-ollama-host').value = data.ollama_host || '';
    $('#set-chat-model').value = data.local_chat_model || '';
    $('#set-embed-model').value = data.local_embed_model || '';
    $('#set-mode').value = data.default_mode || 'auto';

    // Escalation provider options
    const escSel = $('#set-escalation');
    escSel.innerHTML = '';
    const providers = data.providers || {};
    for (const [id, p] of Object.entries(providers)) {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = `${p.display_name} ${p.configured ? '✓' : ''}`;
      escSel.appendChild(opt);
    }
    escSel.value = data.default_escalation_provider || '';

    // Provider settings
    const provDiv = $('#provider-settings');
    provDiv.innerHTML = '';
    for (const [id, p] of Object.entries(providers)) {
      provDiv.innerHTML += `
        <div style="margin-bottom:8px;padding:8px;background:rgba(255,255,255,0.02);border-radius:6px;">
          <div style="font-size:12px;font-weight:600;margin-bottom:4px">${p.display_name} ${p.configured ? '<span style="color:var(--success)">✓</span>' : ''}</div>
          <label style="font-size:11px">API Key<input type="password" class="prov-key" data-id="${id}" value="${p.api_key_preview || ''}" placeholder="sk-..."></label>
          <label style="font-size:11px">Model<input type="text" class="prov-model" data-id="${id}" value="${p.model || ''}"></label>
        </div>`;
    }
  } catch (e) {}
}

async function saveSettings() {
  if (!state.repoPath) return;
  const providers = {};
  $$('.prov-key').forEach(el => {
    const id = el.dataset.id;
    const key = el.value;
    const modelEl = $(`.prov-model[data-id="${id}"]`);
    if (key && !key.includes('*')) providers[id] = { api_key: key, model: modelEl ? modelEl.value : '' };
    else if (modelEl && modelEl.value) providers[id] = { model: modelEl.value };
  });
  try {
    await api('POST', `/settings?repo_path=${encodeURIComponent(state.repoPath)}`, {
      ollama_host: $('#set-ollama-host').value,
      local_backend: $('#set-backend').value,
      local_chat_model: $('#set-chat-model').value,
      local_embed_model: $('#set-embed-model').value,
      default_mode: $('#set-mode').value,
      default_escalation_provider: $('#set-escalation').value,
      providers: Object.keys(providers).length ? providers : undefined,
    });
    showToast('Settings saved', 'success');
    $('#settings-modal').style.display = 'none';
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ── Tabs ────────────────────────────────────────────────────── */

function switchTab(tabId) {
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
  $$('.tab-content').forEach(tc => tc.classList.toggle('active', tc.id === `tab-${tabId}`));
  state.activeTab = tabId;
}

/* ── Auto-resize textarea ────────────────────────────────────── */

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

/* ── Event Listeners ─────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  // Open repo
  $('#open-repo-btn').addEventListener('click', openRepo);
  $('#repo-path-input').addEventListener('keydown', e => { if (e.key === 'Enter') openRepo(); });

  // Indexing & analysis
  $('#index-btn').addEventListener('click', startIndex);
  $('#analyze-btn').addEventListener('click', startAnalyze);

  // Chat
  $('#send-btn').addEventListener('click', sendMessage);
  $('#chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $('#chat-input').addEventListener('input', function () { autoResize(this); });

  // Tabs
  $$('.tab').forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));

  // Generate
  $('#gen-btn').addEventListener('click', generateCode);
  $('#suggestions-btn').addEventListener('click', loadSuggestions);

  // Settings modal
  $('#settings-btn').addEventListener('click', () => {
    $('#settings-modal').style.display = 'flex';
    loadSettings();
  });
  $('#close-settings').addEventListener('click', () => { $('#settings-modal').style.display = 'none'; });
  $('.modal-backdrop').addEventListener('click', () => { $('#settings-modal').style.display = 'none'; });
  $('#save-settings').addEventListener('click', saveSettings);
});
