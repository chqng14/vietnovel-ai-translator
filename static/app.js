/**
 * app.js — Novel Translator Frontend Logic
 * Kết nối API, SSE streaming, live editor, glossary CRUD, export.
 */

// ──────────────────────────────────────────────
//  State
// ──────────────────────────────────────────────
const state = {
  taskId: null,
  status: 'idle', // idle, scraping, translating, paused, completed, cancelled, error
  paragraphsOriginal: [],
  paragraphsTranslated: [],
  sourceLang: 'en',
  title: '',
  eventSource: null,
  viewMode: 'compare',   // 'compare' = đối chiếu | 'preview' = đọc bản dịch
  autoSwitched: false,   // true khi tab preview được mở tự động lúc tạm dừng
};

// ──────────────────────────────────────────────
//  Tab Switching
// ──────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.input-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.input-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  document.getElementById(`panel-${tab}`).classList.add('active');
}

// ──────────────────────────────────────────────
//  Toast Notifications
// ──────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> ${message}`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ──────────────────────────────────────────────
//  API Helpers
// ──────────────────────────────────────────────
//  API Helpers
// ──────────────────────────────────────────────
// Nếu mở trực tiếp bằng file://, API sẽ chỏ đến localhost:8000
// Địa chỉ server API. Trang có thể được mở theo 3 cách:
//   1. http://localhost:8000  — do chính app.py phục vụ  -> dùng đường dẫn tương đối
//   2. http://127.0.0.1:5500  — Live Server của VS Code   -> phải trỏ về cổng 8000,
//      vì Live Server chỉ phục vụ file tĩnh: /api/* sẽ trả 404 hoặc 405
//   3. file:///...            — mở thẳng file             -> cũng trỏ về cổng 8000
const API_PORT = '8000';
const API_BASE = (() => {
  if (window.location.protocol === 'file:') return `http://localhost:${API_PORT}`;
  const isLocal = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
  if (isLocal && window.location.port !== API_PORT) {
    return `http://${window.location.hostname}:${API_PORT}`;
  }
  return '';
})();

async function apiPost(url, data) {
  const res = await fetch(API_BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API Error');
  }
  return res.json();
}

async function apiGet(url) {
  const res = await fetch(API_BASE + url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API Error');
  }
  return res.json();
}

async function apiDelete(url, data) {
  const res = await fetch(API_BASE + url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API Error');
  }
  return res.json();
}

// ──────────────────────────────────────────────
//  Scrape from URL
// ──────────────────────────────────────────────
async function handleScrape() {
  const url = document.getElementById('input-url').value.trim();
  if (!url) {
    showToast('Vui lòng nhập URL chương truyện', 'warning');
    return;
  }

  const btnScrape = document.getElementById('btn-scrape');
  const spinner = document.getElementById('spinner-scrape');

  btnScrape.disabled = true;
  spinner.classList.remove('hidden');

  try {
    showToast('Đang trích xuất nội dung...', 'info');
    const data = await apiPost('/api/scrape', { url });

    state.taskId = data.task_id;
    state.title = data.title;
    state.paragraphsOriginal = data.paragraphs;
    state.sourceLang = data.source_lang;
    state.paragraphsTranslated = new Array(data.paragraphs.length).fill('');

    showToast(`Đã trích xuất "${data.title}" — ${data.total} đoạn văn`, 'success');

    // Hiển thị nội dung và bắt đầu dịch
    renderOriginalParagraphs();
    showTranslationSection();
    startTranslation();

  } catch (err) {
    showToast(`Lỗi trích xuất: ${err.message}`, 'error');
  } finally {
    btnScrape.disabled = false;
    spinner.classList.add('hidden');
  }
}

// ──────────────────────────────────────────────
//  Parse Direct Text
// ──────────────────────────────────────────────
async function handleParseText() {
  const text = document.getElementById('input-text').value.trim();
  if (!text) {
    showToast('Vui lòng nhập nội dung cần dịch', 'warning');
    return;
  }

  const title = document.getElementById('input-title').value.trim() || 'Direct Input';
  const lang = document.getElementById('input-lang').value;

  const btnParse = document.getElementById('btn-parse-text');
  const spinner = document.getElementById('spinner-parse');

  btnParse.disabled = true;
  spinner.classList.remove('hidden');

  try {
    const data = await apiPost('/api/parse-text', { text, title, lang });

    state.taskId = data.task_id;
    state.title = data.title;
    state.paragraphsOriginal = data.paragraphs;
    state.sourceLang = data.source_lang;
    state.paragraphsTranslated = new Array(data.paragraphs.length).fill('');

    showToast(`Đã xử lý "${data.title}" — ${data.total} đoạn văn`, 'success');

    renderOriginalParagraphs();
    showTranslationSection();
    startTranslation();

  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  } finally {
    btnParse.disabled = false;
    spinner.classList.add('hidden');
  }
}

// ──────────────────────────────────────────────
//  Render Original Paragraphs
// ──────────────────────────────────────────────
// ──────────────────────────────────────────────
//  Chế độ xem: Đối chiếu / Đọc bản dịch
// ──────────────────────────────────────────────
function switchView(view) {
  state.viewMode = view;

  document.querySelectorAll('.view-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.view === view));
  document.querySelectorAll('.view-panel').forEach(p =>
    p.classList.toggle('active', p.id === `view-${view}`));

  if (view === 'preview') renderPreview();
}

// Đoạn chỉ gồm ký tự phân cách (***, ---, ※ ※ ※) — canh giữa cho dễ đọc.
// Dùng \p{L}/\p{N} chứ KHÔNG dùng \W: trong JS, \w luôn chỉ là ASCII kể cả
// khi có cờ u, nên "「Ơ?」" hay cả đoạn tiếng Nhật đều bị nhận nhầm là phân cách.
function isSeparator(text) {
  const t = text.trim();
  return t.length > 0 && !/[\p{L}\p{N}]/u.test(t);
}

function renderPreview() {
  const box = document.getElementById('preview-content');
  if (!box) return;

  const total = state.paragraphsOriginal.length;
  const done = state.paragraphsTranslated.filter(p => p && p.trim()).length;

  const meta = document.getElementById('view-meta');
  if (meta) meta.textContent = total ? `${done}/${total} đoạn` : '';

  if (!done) {
    box.innerHTML = '<div class="preview-empty">Chưa có đoạn nào được dịch xong.</div>';
    return;
  }

  const body = state.paragraphsTranslated
    .map((text, idx) => {
      if (!text || !text.trim()) return '';
      const cls = isSeparator(state.paragraphsOriginal[idx] || '')
        ? 'preview-para separator' : 'preview-para';
      return `<p class="${cls}">${escapeHtml(text)}</p>`;
    })
    .join('');

  const remaining = total - done;
  const tail = remaining > 0
    ? `<div class="preview-remaining">Còn ${remaining} đoạn chưa dịch xong…</div>`
    : '';

  box.innerHTML = `<div class="preview-doc">
      <div class="preview-title">${escapeHtml(state.title || 'Bản dịch')}</div>
      <div class="preview-subtitle">${done}/${total} đoạn · dịch tự động, nên đọc soát lại</div>
      ${body}${tail}
    </div>`;
}

async function copyPreview() {
  const text = state.paragraphsTranslated.filter(p => p && p.trim()).join('\n\n');
  if (!text) {
    showToast('Chưa có gì để sao chép', 'warning');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast('Đã sao chép bản dịch vào clipboard', 'success');
  } catch (err) {
    // clipboard API cần ngữ cảnh bảo mật; localhost đạt, nhưng vẫn phòng hờ
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(ok ? 'Đã sao chép bản dịch' : 'Không sao chép được', ok ? 'success' : 'error');
  }
}

function renderOriginalParagraphs() {
  const pane = document.getElementById('pane-original');
  const langBadge = document.getElementById('source-lang-badge');

  langBadge.textContent = state.sourceLang.toUpperCase();

  pane.innerHTML = state.paragraphsOriginal.map((text, idx) =>
    `<div class="paragraph" data-index="${idx}" id="orig-${idx}">
      ${escapeHtml(text)}
      <span class="index-badge">#${idx + 1}</span>
    </div>`
  ).join('');

  // Render translated pane (empty initially)
  const translatedPane = document.getElementById('pane-translated');
  translatedPane.innerHTML = state.paragraphsOriginal.map((_, idx) =>
    `<div class="paragraph pending editable" data-index="${idx}" id="trans-${idx}"
          onclick="startInlineEdit(${idx})" title="Click để chỉnh sửa">
      <span class="text-muted" style="font-style: italic;">Đang chờ dịch...</span>
      <span class="index-badge">#${idx + 1}</span>
    </div>`
  ).join('');
}

function showTranslationSection() {
  document.getElementById('translation-section').classList.add('visible');
  document.getElementById('progress-section').classList.add('visible');
}

// ──────────────────────────────────────────────
//  Start Translation (SSE Stream)
// ──────────────────────────────────────────────
async function startTranslation() {
  if (!state.taskId) return;

  const modelName = document.getElementById('select-model').value;
  const storyContext = document.getElementById('input-story-context').value.trim();

  // Đánh dấu task sẵn sàng
  await apiPost('/api/translate/start', { 
    task_id: state.taskId,
    model_name: modelName,
    story_context: storyContext
  });

  state.status = 'translating';
  updateStatusBadge('running', 'Đang dịch...');

  // Kết nối SSE stream — stream sẽ trigger translation trên server
  connectSSE();
}

function connectSSE() {
  if (state.eventSource) {
    state.eventSource.close();
  }

  const es = new EventSource(`${API_BASE}/api/translate/stream/${state.taskId}`);
  state.eventSource = es;

  es.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    handleProgressUpdate(data);
  });

  es.addEventListener('done', (event) => {
    const data = JSON.parse(event.data);
    handleTranslationDone(data);
    es.close();
  });

  es.onerror = (err) => {
    console.error('SSE error:', err);
    // Don't show error toast for normal close
    if (es.readyState === EventSource.CLOSED) return;
    showToast('Mất kết nối SSE. Đang thử kết nối lại...', 'warning');
  };
}

// ──────────────────────────────────────────────
//  Handle Progress Updates
// ──────────────────────────────────────────────
function handleProgressUpdate(data) {
  const { total, completed, percentage, index, original, translated, speed, eta, status, error, message } = data;

  // Model chưa nạp xong — báo cho người dùng biết thay vì để giao diện đứng im.
  // Lần đầu nạp model 1.7B có thể mất vài phút.
  if (status === 'loading') {
    updateStatusBadge('running', message || 'Đang nạp model...');
    showToast(
      message || 'Đang chuẩn bị công cụ dịch...',
      'info',
      10000
    );
    return;
  }

  // Update state
  if (translated && index !== undefined) {
    state.paragraphsTranslated[index] = translated;
  }

  // Update progress bar
  document.getElementById('progress-bar').style.width = `${percentage}%`;
  document.getElementById('progress-percent').textContent = `${percentage}%`;
  document.getElementById('stat-completed').textContent = completed;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-speed').textContent = speed.toFixed(2);
  document.getElementById('stat-eta').textContent = formatETA(eta);

  // Update translated paragraph in UI
  if (translated && index !== undefined) {
    updateTranslatedParagraph(index, translated);
  }

  // Highlight current translating paragraph
  highlightCurrentParagraph(index);

  // Update status
  if (status === 'paused') {
    updateStatusBadge('paused', 'Tạm dừng');
  } else if (status === 'running') {
    updateStatusBadge('running', 'Đang dịch...');
  } else if (status === 'error') {
    updateStatusBadge('error', 'Lỗi');
  }

  if (error) {
    showToast(`Lỗi đoạn #${index + 1}: ${error}`, 'warning');
  }
}

function handleTranslationDone(data) {
  state.status = 'completed';
  updateStatusBadge('completed', 'Hoàn thành!');

  document.getElementById('progress-bar').style.width = '100%';
  document.getElementById('progress-percent').textContent = '100%';

  // Show export section
  document.getElementById('export-section').classList.add('visible');

  // Hide pause/cancel buttons
  document.getElementById('btn-pause').classList.add('hidden');
  document.getElementById('btn-resume').classList.add('hidden');
  document.getElementById('btn-cancel').classList.add('hidden');

  showToast('🎉 Dịch hoàn thành! Bạn có thể chỉnh sửa và xuất file.', 'success', 6000);

  // Remove all "translating" highlights
  document.querySelectorAll('.paragraph.translating').forEach(el => {
    el.classList.remove('translating');
    el.classList.add('completed');
  });
}

function updateTranslatedParagraph(index, translated) {
  const el = document.getElementById(`trans-${index}`);
  if (!el) return;

  el.innerHTML = `${escapeHtml(translated)}<span class="index-badge">#${index + 1}</span>`;
  el.classList.remove('pending');
  el.classList.add('completed', 'fade-in');
  el.setAttribute('title', 'Click để chỉnh sửa');

  // Tab đọc bản dịch cập nhật trực tiếp theo
  if (state.viewMode === 'preview') renderPreview();

  // Scroll translated pane to show latest
  const pane = document.getElementById('pane-translated');
  if (el.offsetTop > pane.scrollTop + pane.clientHeight - 100) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // Also scroll original pane
  const origEl = document.getElementById(`orig-${index}`);
  if (origEl) {
    const origPane = document.getElementById('pane-original');
    if (origEl.offsetTop > origPane.scrollTop + origPane.clientHeight - 100) {
      origEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}

function highlightCurrentParagraph(index) {
  // Remove previous highlights
  document.querySelectorAll('.paragraph.translating').forEach(el => {
    el.classList.remove('translating');
  });

  // Add highlight to current
  const origEl = document.getElementById(`orig-${index}`);
  const transEl = document.getElementById(`trans-${index}`);
  if (origEl) origEl.classList.add('translating');
  if (transEl && transEl.classList.contains('pending')) {
    transEl.classList.add('translating');
  }
}

// ──────────────────────────────────────────────
//  Pause / Resume / Cancel
// ──────────────────────────────────────────────
async function pauseTranslation() {
  if (!state.taskId) return;
  try {
    await apiPost(`/api/translate/pause/${state.taskId}`);
    state.status = 'paused';
    updateStatusBadge('paused', 'Tạm dừng');
    document.getElementById('btn-pause').classList.add('hidden');
    document.getElementById('btn-resume').classList.remove('hidden');

    // Tạm dừng là để đọc lại — mở luôn tab bản dịch
    if (state.viewMode !== 'preview') {
      state.autoSwitched = true;
      switchView('preview');
    } else {
      renderPreview();
    }
    showToast('Đã tạm dừng — xem bản dịch ở tab “Đọc bản dịch”', 'info');
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

async function resumeTranslation() {
  if (!state.taskId) return;
  try {
    await apiPost(`/api/translate/resume/${state.taskId}`);
    state.status = 'translating';
    updateStatusBadge('running', 'Đang dịch...');
    document.getElementById('btn-resume').classList.add('hidden');
    document.getElementById('btn-pause').classList.remove('hidden');

    // Chỉ tự quay lại tab đối chiếu nếu trước đó chính ta đã tự chuyển đi
    if (state.autoSwitched) {
      state.autoSwitched = false;
      switchView('compare');
    }
    showToast('Tiếp tục dịch...', 'info');
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

async function cancelTranslation() {
  if (!state.taskId) return;
  if (!confirm('Bạn có chắc muốn hủy quá trình dịch?')) return;

  try {
    await apiPost(`/api/translate/cancel/${state.taskId}`);
    state.status = 'cancelled';
    updateStatusBadge('error', 'Đã hủy');

    if (state.eventSource) {
      state.eventSource.close();
    }

    document.getElementById('btn-pause').classList.add('hidden');
    document.getElementById('btn-resume').classList.add('hidden');
    document.getElementById('btn-cancel').classList.add('hidden');

    // Still show export if some paragraphs are translated
    const translatedCount = state.paragraphsTranslated.filter(p => p).length;
    if (translatedCount > 0) {
      document.getElementById('export-section').classList.add('visible');
      showToast(`Đã hủy. ${translatedCount} đoạn đã dịch vẫn có thể xuất file.`, 'warning');
    } else {
      showToast('Đã hủy quá trình dịch.', 'warning');
    }
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

// ──────────────────────────────────────────────
//  Status Badge
// ──────────────────────────────────────────────
function updateStatusBadge(type, text) {
  const badge = document.getElementById('status-badge');
  badge.className = `status-badge ${type}`;
  document.getElementById('status-text').textContent = text;
}

// ──────────────────────────────────────────────
//  Inline Edit
// ──────────────────────────────────────────────
function startInlineEdit(index) {
  const el = document.getElementById(`trans-${index}`);
  if (!el || el.classList.contains('pending')) return;

  // Skip if already editing
  if (el.classList.contains('editing')) return;

  const currentText = state.paragraphsTranslated[index] || '';
  el.classList.add('editing');
  el.setAttribute('contenteditable', 'true');
  el.textContent = currentText;
  el.focus();

  // Save on blur
  const handleBlur = async () => {
    el.removeEventListener('blur', handleBlur);
    el.removeEventListener('keydown', handleKeydown);
    el.classList.remove('editing');
    el.setAttribute('contenteditable', 'false');

    const newText = el.textContent.trim();
    if (newText !== currentText && newText) {
      state.paragraphsTranslated[index] = newText;
      el.innerHTML = `${escapeHtml(newText)}<span class="index-badge">#${index + 1}</span>`;

      // Sync with server
      try {
        await apiPost(`/api/translate/edit/${state.taskId}`, { index, text: newText });
      } catch (err) {
        console.warn('Failed to sync edit:', err);
      }
    } else {
      el.innerHTML = `${escapeHtml(currentText)}<span class="index-badge">#${index + 1}</span>`;
    }
  };

  const handleKeydown = (e) => {
    if (e.key === 'Escape') {
      el.textContent = currentText;
      el.blur();
    }
    // Ctrl+Enter to confirm
    if (e.key === 'Enter' && e.ctrlKey) {
      el.blur();
    }
  };

  el.addEventListener('blur', handleBlur);
  el.addEventListener('keydown', handleKeydown);
}

// ──────────────────────────────────────────────
//  Glossary Management
// ──────────────────────────────────────────────
function toggleGlossary() {
  const section = document.getElementById('glossary-section');
  const isVisible = section.style.display !== 'none';

  if (isVisible) {
    section.style.display = 'none';
  } else {
    section.style.display = 'block';
    section.style.animation = 'fadeSlideIn 0.3s var(--ease)';
    loadGlossary();
  }
}

async function loadGlossary() {
  try {
    const data = await apiGet('/api/glossary');
    renderGlossaryTable(data.entries);
    document.getElementById('glossary-count').textContent = data.count;
  } catch (err) {
    console.error('Failed to load glossary:', err);
  }
}

function renderGlossaryTable(entries) {
  const tbody = document.getElementById('glossary-tbody');
  if (!entries || entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-muted text-center" style="padding: 20px;">Chưa có thuật ngữ nào</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(e =>
    `<tr>
      <td class="source-term">${escapeHtml(e.source)}</td>
      <td class="target-term">${escapeHtml(e.target)}</td>
      <td><button class="btn btn-danger btn-sm btn-icon" onclick="removeGlossaryEntry('${escapeHtml(e.source)}')" title="Xóa">×</button></td>
    </tr>`
  ).join('');
}

async function addGlossaryEntry() {
  const source = document.getElementById('glossary-source').value.trim();
  const target = document.getElementById('glossary-target').value.trim();

  if (!source || !target) {
    showToast('Vui lòng nhập cả thuật ngữ gốc và bản dịch', 'warning');
    return;
  }

  try {
    await apiPost('/api/glossary', { source, target });
    document.getElementById('glossary-source').value = '';
    document.getElementById('glossary-target').value = '';
    showToast(`Đã thêm: ${source} → ${target}`, 'success');
    loadGlossary();
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

async function removeGlossaryEntry(source) {
  try {
    await apiDelete('/api/glossary', { source });
    showToast(`Đã xóa: ${source}`, 'info');
    loadGlossary();
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

async function clearGlossary() {
  if (!confirm('Xóa toàn bộ thuật ngữ?')) return;
  try {
    await apiDelete('/api/glossary/all', {});
    showToast('Đã xóa tất cả thuật ngữ', 'info');
    loadGlossary();
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

function importGlossary() {
  document.getElementById('glossary-file-input').click();
}

async function handleGlossaryImport(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/api/glossary/import`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    showToast(`Đã import ${data.imported} thuật ngữ (tổng: ${data.total})`, 'success');
    loadGlossary();
  } catch (err) {
    showToast(`Lỗi import: ${err.message}`, 'error');
  }

  event.target.value = '';
}

async function exportGlossary(fmt) {
  try {
    const res = await fetch(`${API_BASE}/api/glossary/export/${fmt}`);
    const blob = await res.blob();
    downloadBlob(blob, `glossary.${fmt}`);
    showToast(`Đã xuất glossary.${fmt}`, 'success');
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, 'error');
  }
}

// ──────────────────────────────────────────────
//  Export Files
// ──────────────────────────────────────────────
async function exportFile(fmt) {
  if (!state.taskId) {
    showToast('Chưa có bản dịch để xuất', 'warning');
    return;
  }

  const bilingual = document.getElementById('export-bilingual').checked;
  const defaultName = state.title || 'ban_dich';
  let requestedName = window.prompt(
    `Đặt tên cho file ${fmt.toUpperCase()}:`,
    defaultName
  );

  if (requestedName === null) return;
  requestedName = requestedName.trim();
  if (!requestedName) {
    showToast('Tên file không được để trống', 'warning');
    return;
  }

  const extensionPattern = new RegExp(`\\.${fmt}$`, 'i');
  requestedName = requestedName.replace(extensionPattern, '');
  const query = new URLSearchParams({
    bilingual: String(bilingual),
    filename: requestedName,
  });

  try {
    showToast(`Đang tạo file ${fmt.toUpperCase()}...`, 'info');
    const res = await fetch(`${API_BASE}/api/export/${state.taskId}/${fmt}?${query}`);

    if (!res.ok) {
      throw new Error('Export failed');
    }

    const blob = await res.blob();
    const filename = getFilenameFromResponse(res) || `${sanitizeFilename(requestedName)}.${fmt}`;
    downloadBlob(blob, filename);

    showToast(`✅ Đã tải file ${filename}`, 'success');
  } catch (err) {
    showToast(`Lỗi xuất file: ${err.message}`, 'error');
  }
}

// ──────────────────────────────────────────────
//  Utility Functions
// ──────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatETA(seconds) {
  if (!seconds || seconds <= 0) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 60) {
    const hrs = Math.floor(mins / 60);
    const remainMins = mins % 60;
    return `${hrs}h ${remainMins}m`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function sanitizeFilename(name) {
  return name.replace(/[<>:"/\\|?*]/g, '').replace(/\s+/g, '_').slice(0, 80) || 'untitled';
}

function getFilenameFromResponse(res) {
  const cd = res.headers.get('content-disposition');
  if (!cd) return null;
  const utf8Match = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch (_) {
      return utf8Match[1];
    }
  }
  const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
  return match ? match[1].replace(/['"]/g, '') : null;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ──────────────────────────────────────────────
//  Keyboard Shortcuts
// ──────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  // Enter on URL input → scrape
  if (e.key === 'Enter' && document.activeElement.id === 'input-url') {
    e.preventDefault();
    handleScrape();
  }

  // Enter on glossary inputs → add
  if (e.key === 'Enter' && (
    document.activeElement.id === 'glossary-source' ||
    document.activeElement.id === 'glossary-target'
  )) {
    e.preventDefault();
    addGlossaryEntry();
  }
});

// ──────────────────────────────────────────────
//  Sync scroll between panes
// ──────────────────────────────────────────────
(function setupSyncScroll() {
  const origPane = document.getElementById('pane-original');
  const transPane = document.getElementById('pane-translated');
  let syncing = false;

  if (origPane && transPane) {
    origPane.addEventListener('scroll', () => {
      if (syncing) return;
      syncing = true;
      const ratio = origPane.scrollTop / (origPane.scrollHeight - origPane.clientHeight || 1);
      transPane.scrollTop = ratio * (transPane.scrollHeight - transPane.clientHeight || 1);
      requestAnimationFrame(() => syncing = false);
    });

    transPane.addEventListener('scroll', () => {
      if (syncing) return;
      syncing = true;
      const ratio = transPane.scrollTop / (transPane.scrollHeight - transPane.clientHeight || 1);
      origPane.scrollTop = ratio * (origPane.scrollHeight - origPane.clientHeight || 1);
      requestAnimationFrame(() => syncing = false);
    });
  }
})();

// ──────────────────────────────────────────────
//  Init
// ──────────────────────────────────────────────
async function loadRuntimeConfig() {
  try {
    const config = await apiGet('/api/config');
    const select = document.getElementById('select-model');
    const downloadedModels = new Set(config.downloaded_ai_models || []);
    const restrictToDownloaded = downloadedModels.size > 0;

    select.querySelectorAll('[data-runtime="ai"]').forEach(option => {
      option.disabled = !config.ai_available || (
        restrictToDownloaded && !downloadedModels.has(option.value)
      );
      if (option.disabled && config.ai_available && restrictToDownloaded) {
        option.title = 'Model chưa được tải. Dùng setup_and_run.bat để tải.';
      }
    });
    select.querySelectorAll('[data-runtime="library"]').forEach(option => {
      option.disabled = !config.deep_translator_available;
    });

    const defaultOption = Array.from(select.options).find(
      option => option.value === config.default_provider && !option.disabled
    );
    if (defaultOption) select.value = defaultOption.value;

    if (!config.ai_available && config.deep_translator_available) {
      select.title = 'AI local chưa được cài; Google Translate được chọn mặc định.';
    }
  } catch (error) {
    console.warn('Không đọc được cấu hình provider:', error);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadRuntimeConfig();
  loadGlossary();
  console.log('📖 Novel Translator ready');
});
