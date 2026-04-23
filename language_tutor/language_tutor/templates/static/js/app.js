// Language Tutor — Frontend
'use strict';

// ── State ─────────────────────────────────────────────────────────
let currentLanguage   = null;
let currentSessionId  = sessionStorage.getItem('sessionId') || null;
let sessionActive     = false;
let exchangeCount     = 0;
let correctionsCount  = 0;
let vocabCount        = 0;
let planningTimer     = null;
let _checkErrors      = [];

const LANGUAGE_NAMES = { spanish: 'Spanish (Español)', latin: 'Latin (Latina)' };
const PLANNING_MESSAGES = [
    'Planning your lesson…',
    'Reviewing past sessions…',
    'Identifying areas to practice…',
    'Building your personalized plan…',
    'Almost ready…',
];

// ── DOM refs ──────────────────────────────────────────────────────
const el = {
    // pre-session
    presessionTitle:  document.getElementById('presession-title'),
    startControls:    document.getElementById('start-controls'),
    planningProgress: document.getElementById('planning-progress'),
    planningMessage:  document.getElementById('planning-message'),
    btnStartSession:  document.getElementById('btn-start-session'),
    btnChangeLang:    document.getElementById('btn-change-language'),
    // session header
    activeLangLabel:  document.getElementById('active-language-label'),
    statCorrections:  document.getElementById('stat-corrections'),
    statVocab:        document.getElementById('stat-vocab'),
    statExchanges:    document.getElementById('stat-exchanges'),
    btnEndSession:    document.getElementById('btn-end-session'),
    btnDrillTab:      document.getElementById('btn-drill-tab'),
    btnMemory:        document.getElementById('btn-memory'),
    btnHandsfree:     document.getElementById('btn-handsfree'),
    handsfreeIndicator: document.getElementById('handsfree-indicator'),
    // plan bar
    planBar:          document.getElementById('plan-bar'),
    planFocus:        document.getElementById('plan-focus'),
    btnClosePlan:     document.getElementById('btn-close-plan'),
    // chat
    chatMessages:     document.getElementById('chat-messages'),
    feedbackFeed:     document.getElementById('feedback-feed'),
    userInput:        document.getElementById('user-input'),
    btnSend:          document.getElementById('btn-send'),
    btnCheckInput:    document.getElementById('btn-check-input'),
    btnMic:           document.getElementById('btn-mic'),
    micStatus:        document.getElementById('mic-status'),
    checkResults:     document.getElementById('check-results'),
    handsfreeBar:     document.getElementById('handsfree-bar'),
    handsfreeState:   document.getElementById('handsfree-state'),
    btnHandsfreeStop: document.getElementById('btn-handsfree-stop'),
    // modals
    summaryOverlay:   document.getElementById('summary-overlay'),
    summaryStats:     document.getElementById('summary-stats'),
    summaryText:      document.getElementById('summary-text'),
    btnNewSession:    document.getElementById('btn-new-session'),
    btnChangeLangEnd: document.getElementById('btn-change-language-end'),
    confirmOverlay:   document.getElementById('confirm-overlay'),
    btnConfirmEnd:    document.getElementById('btn-confirm-end'),
    btnCancelEnd:     document.getElementById('btn-cancel-end'),
};

// ── View switching ─────────────────────────────────────────────────
const views = {
    language:   document.getElementById('view-language'),
    presession: document.getElementById('view-presession'),
    session:    document.getElementById('view-session'),
};
function showView(name) {
    Object.values(views).forEach(v => v.classList.add('hidden'));
    views[name].classList.remove('hidden');
}

// ── Utilities ──────────────────────────────────────────────────────
function esc(s) {
    return String(s || '')
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function showError(msg) {
    const d = document.createElement('div');
    d.className = 'error-toast';
    d.textContent = msg;
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 5000);
}
function showModal(id) { document.getElementById(id+'-overlay').classList.remove('hidden'); }
function hideModal(id) { document.getElementById(id+'-overlay').classList.add('hidden'); }
function scrollChat()  { el.chatMessages.scrollTop = el.chatMessages.scrollHeight; }
function setInputEnabled(on) {
    el.userInput.disabled = !on;
    el.btnSend.disabled   = !on;
}

// ── Language selection ─────────────────────────────────────────────
document.getElementById('btn-spanish').addEventListener('click', () => selectLanguage('spanish'));
document.getElementById('btn-latin').addEventListener('click',   () => selectLanguage('latin'));
el.btnChangeLang.addEventListener('click', () => showView('language'));
el.btnChangeLangEnd.addEventListener('click', () => { hideModal('summary'); showView('language'); });

function selectLanguage(lang) {
    currentLanguage = lang;
    el.presessionTitle.textContent = LANGUAGE_NAMES[lang] + ' Session';
    showView('presession');
    el.startControls.classList.remove('hidden');
    el.planningProgress.classList.add('hidden');
}

// ── Session start ──────────────────────────────────────────────────
el.btnStartSession.addEventListener('click', startSession);

async function startSession() {
    el.startControls.classList.add('hidden');
    el.planningProgress.classList.remove('hidden');

    let i = 0;
    el.planningMessage.textContent = PLANNING_MESSAGES[0];
    planningTimer = setInterval(() => {
        i = (i + 1) % PLANNING_MESSAGES.length;
        el.planningMessage.textContent = PLANNING_MESSAGES[i];
    }, 8000);

    try {
        const res = await fetch('/api/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: currentLanguage, duration_minutes: 30 }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || res.statusText);
        }
        const data = await res.json();

        clearInterval(planningTimer);
        currentSessionId = data.session_id;
        sessionStorage.setItem('sessionId', currentSessionId);

        // Reset state
        exchangeCount = correctionsCount = vocabCount = 0;
        el.statCorrections.textContent = el.statVocab.textContent = el.statExchanges.textContent = '0';
        el.chatMessages.innerHTML = '';
        el.feedbackFeed.innerHTML = '';
        el.planBar.classList.add('hidden');
        sessionActive = true;

        el.activeLangLabel.textContent = LANGUAGE_NAMES[currentLanguage] || currentLanguage;

        // Show voice if enabled
        if (data.voice_enabled) {
            el.btnMic.classList.remove('hidden');
        } else {
            el.btnMic.classList.add('hidden');
        }

        showView('session');
        addMessage('assistant', data.greeting);
        renderPlan(data.plan);

    } catch (err) {
        clearInterval(planningTimer);
        el.startControls.classList.remove('hidden');
        el.planningProgress.classList.add('hidden');
        showError('Failed to start session: ' + err.message);
    }
}

// ── Plan display ───────────────────────────────────────────────────
function renderPlan(plan) {
    if (!plan || Object.keys(plan).length === 0) return;
    const parts = [];
    if (plan.warmup_topic)
        parts.push(`<div class="plan-section"><span class="plan-label">Warmup</span> ${esc(plan.warmup_topic)}</div>`);
    if (plan.focus_areas && plan.focus_areas.length)
        parts.push(`<div class="plan-section"><span class="plan-label">Focus</span> ${plan.focus_areas.map(a=>`<span class="plan-tag">${esc(a)}</span>`).join('')}</div>`);
    if (plan.drill_type)
        parts.push(`<div class="plan-section"><span class="plan-label">Drill</span> <span class="plan-tag plan-tag-drill">${esc(plan.drill_type.replace(/_/g,' '))}</span></div>`);
    if (parts.length === 0) return;
    el.planFocus.innerHTML = parts.join('');
    el.planBar.classList.remove('hidden');
}
el.btnClosePlan.addEventListener('click', () => el.planBar.classList.add('hidden'));

// ── Send message ───────────────────────────────────────────────────
el.btnSend.addEventListener('click', sendMessage);
el.userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

async function sendMessage() {
    const text = el.userInput.value.trim();
    if (!text || !sessionActive) return;
    addMessage('user', text);
    el.userInput.value = '';
    el.checkResults.classList.add('hidden');
    _checkErrors = [];
    setInputEnabled(false);
    showTypingIndicator();

    try {
        const res = await fetch('/api/conversation/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, message: text }),
        });
        removeTypingIndicator();

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            if (res.status === 404) {
                sessionStorage.removeItem('sessionId');
                currentSessionId = null;
                sessionActive = false;
                addMessage('assistant', '⚠️ Session expired. Please start a new session.');
                showView('presession');
                return;
            }
            throw new Error(err.detail || res.statusText);
        }

        const data = await res.json();
        addMessage('assistant', data.message);

        exchangeCount++;
        el.statExchanges.textContent = exchangeCount;

        if (data.corrections && data.corrections.length) {
            correctionsCount += data.corrections.length;
            el.statCorrections.textContent = correctionsCount;
            data.corrections.forEach(c => addFeedbackCard('correction', c));
        }
        if (data.new_vocabulary && data.new_vocabulary.length) {
            vocabCount += data.new_vocabulary.length;
            el.statVocab.textContent = vocabCount;
            data.new_vocabulary.forEach(v => addFeedbackCard('vocab', v));
        }
    } catch (err) {
        removeTypingIndicator();
        addMessage('assistant', 'Lo siento, hubo un problema. Please try again.');
        console.error('sendMessage:', err);
    } finally {
        setInputEnabled(true);
        el.userInput.focus();
    }
}

// ── Chat helpers ───────────────────────────────────────────────────
function addMessage(role, content) {
    const d = document.createElement('div');
    d.className = `message ${role}`;
    d.textContent = content;
    el.chatMessages.appendChild(d);
    scrollChat();
}
function showTypingIndicator() {
    if (document.getElementById('typing-indicator')) return;
    const d = document.createElement('div');
    d.id = 'typing-indicator';
    d.className = 'message assistant typing-indicator';
    d.innerHTML = '<span></span><span></span><span></span>';
    el.chatMessages.appendChild(d);
    scrollChat();
}
function removeTypingIndicator() {
    const t = document.getElementById('typing-indicator');
    if (t) t.remove();
}

// ── Feedback cards ─────────────────────────────────────────────────
function addFeedbackCard(type, item) {
    const card = document.createElement('div');
    card.className = `feedback-card feedback-${type}`;

    if (type === 'correction') {
        card.innerHTML = `
            <span class="feedback-icon">✏️</span>
            <div class="feedback-body">
                <span class="feedback-error">${esc(item.error||'')}</span>
                <span class="feedback-arrow">→</span>
                <span class="feedback-correct">${esc(item.correction||'')}</span>
                ${item.explanation ? `<p class="feedback-explanation">${esc(item.explanation)}</p>` : ''}
                <div class="feedback-explain-row">
                    <button class="btn-explain">❓ Explain</button>
                    <span class="explain-loading hidden">Explaining…</span>
                    <p class="explain-text hidden"></p>
                </div>
            </div>
            <button class="feedback-dismiss" aria-label="Dismiss">×</button>`;

        const btnEx  = card.querySelector('.btn-explain');
        const loading = card.querySelector('.explain-loading');
        const expText = card.querySelector('.explain-text');
        btnEx.addEventListener('click', async () => {
            btnEx.disabled = true;
            loading.classList.remove('hidden');
            try {
                const res = await fetch('/api/conversation/explain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: currentSessionId,
                        text: `${item.error||''} → ${item.correction||''}`,
                        question: item.explanation || null,
                    }),
                });
                const d = await res.json();
                expText.textContent = d.explanation || 'No explanation available.';
                expText.classList.remove('hidden');
                btnEx.classList.add('hidden');
            } catch (_) {
                expText.textContent = 'Could not load explanation.';
                expText.classList.remove('hidden');
            } finally {
                loading.classList.add('hidden');
                btnEx.disabled = false;
            }
        });
    } else {
        card.innerHTML = `
            <span class="feedback-icon">📖</span>
            <div class="feedback-body">
                <span class="feedback-word">${esc(item.word||'')}</span>
                <span class="feedback-arrow">—</span>
                <span class="feedback-translation">${esc(item.translation||'')}</span>
                ${item.part_of_speech ? `<span class="feedback-pos">${esc(item.part_of_speech)}</span>` : ''}
            </div>
            <button class="feedback-dismiss" aria-label="Dismiss">×</button>`;
    }

    card.querySelector('.feedback-dismiss').addEventListener('click', () => card.remove());
    el.feedbackFeed.prepend(card);
    setTimeout(() => card.remove(), 30000);
}

// ── End session ────────────────────────────────────────────────────
el.btnEndSession.addEventListener('click', () => showModal('confirm'));
el.btnCancelEnd.addEventListener('click',  () => hideModal('confirm'));
el.btnConfirmEnd.addEventListener('click', confirmEndSession);

async function confirmEndSession() {
    hideModal('confirm');
    if (handsFreeModeActive) toggleHandsfree();
    el.btnEndSession.disabled = true;
    setInputEnabled(false);
    addMessage('assistant', '⏳ Generating session summary…');

    try {
        const res = await fetch('/api/session/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const data = await res.json();
        sessionActive = false;
        sessionStorage.removeItem('sessionId');

        const stats = data.statistics || {};
        el.summaryStats.innerHTML = `
            <div class="stat-grid">
                <div class="stat-item"><span class="stat-num">${stats.exchanges||0}</span><span class="stat-lbl">Exchanges</span></div>
                <div class="stat-item"><span class="stat-num">${stats.corrections_made||0}</span><span class="stat-lbl">Corrections</span></div>
                <div class="stat-item"><span class="stat-num">${stats.new_vocabulary||0}</span><span class="stat-lbl">New Words</span></div>
                <div class="stat-item"><span class="stat-num">${stats.session_duration||'—'}</span><span class="stat-lbl">Duration</span></div>
            </div>`;
        el.summaryText.textContent = data.summary || '';
        showModal('summary');
    } catch (err) {
        el.btnEndSession.disabled = false;
        setInputEnabled(true);
        showError('Failed to end session: ' + err.message);
    }
}

el.btnNewSession.addEventListener('click', () => {
    hideModal('summary');
    el.btnEndSession.disabled = false;
    selectLanguage(currentLanguage);
});

// ── Memory button ──────────────────────────────────────────────────
el.btnMemory.addEventListener('click', () => {
    window.open(`/memory?session_id=${currentSessionId}`, '_blank');
});

// ── Session history ────────────────────────────────────────────────
const historyEl = {
    toggle:  document.getElementById('btn-toggle-history'),
    content: document.getElementById('history-content'),
    list:    document.getElementById('history-list'),
    arrow:   document.getElementById('history-arrow'),
};
let historyLoaded = false;

if (historyEl.toggle) {
    historyEl.toggle.addEventListener('click', () => {
        const hidden = historyEl.content.classList.toggle('hidden');
        historyEl.arrow.textContent = hidden ? '▼' : '▲';
        if (!hidden && !historyLoaded) { historyLoaded = true; loadHistory(); }
    });
}

async function loadHistory() {
    if (!currentLanguage) return;
    try {
        const res = await fetch(`/api/session/history/${currentLanguage}?limit=5`);
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        const sessions = data.sessions || [];
        if (!sessions.length) {
            historyEl.list.innerHTML = '<p class="history-loading">No previous sessions yet.</p>';
            return;
        }
        historyEl.list.innerHTML = sessions.map(s => {
            const date = new Date(s.started_at||s.date||'').toLocaleDateString();
            const dur  = s.duration_minutes ? `${s.duration_minutes}m` : '—';
            return `<div class="history-item">
                <span class="history-date">${date} (${dur})</span>
                ${s.exchanges != null ? `<span class="history-stat">💬 ${s.exchanges}</span>` : ''}
                ${s.corrections_made != null ? `<span class="history-stat">✏️ ${s.corrections_made}</span>` : ''}
                ${s.vocab_learned != null ? `<span class="history-stat">📖 ${s.vocab_learned}</span>` : ''}
            </div>`;
        }).join('');
    } catch (_) {
        historyEl.list.innerHTML = '<p class="history-loading">Could not load history.</p>';
    }
}

// ── Word lookup (right-click) ──────────────────────────────────────
const lookupMenu  = document.getElementById('lookup-menu');
const lookupPopup = document.getElementById('lookup-popup');
const lookupWordEl = document.getElementById('lookup-word');
const lookupBody  = document.getElementById('lookup-body');
let _lookupTarget = '', _lookupCtx = '';

[document.getElementById('chat-messages'), document.getElementById('user-input')]
    .forEach(el2 => el2.addEventListener('contextmenu', handleContextMenu));

function handleContextMenu(e) {
    const selected = window.getSelection().toString().trim();
    if (!selected || !currentSessionId) return;
    e.preventDefault();
    _lookupTarget = selected;
    _lookupCtx = (window.getSelection().anchorNode?.textContent || '').slice(0, 300);
    lookupMenu.style.left = `${Math.min(e.clientX, window.innerWidth-180)}px`;
    lookupMenu.style.top  = `${Math.min(e.clientY, window.innerHeight-60)}px`;
    lookupMenu.classList.remove('hidden');
}
document.getElementById('lookup-menu-btn').addEventListener('click', () => {
    lookupMenu.classList.add('hidden');
    showLookup(_lookupTarget, _lookupCtx);
});
document.addEventListener('click', e => { if (!lookupMenu.contains(e.target)) lookupMenu.classList.add('hidden'); });

async function showLookup(word, context) {
    lookupWordEl.textContent = word;
    lookupBody.innerHTML = '<div class="spinner spinner-sm"></div>';
    lookupPopup.style.left = `${Math.min(window.innerWidth-310, window.innerWidth*0.6)}px`;
    lookupPopup.style.top  = '110px';
    lookupPopup.classList.remove('hidden');
    try {
        const res = await fetch('/api/conversation/lookup', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, word, context: context||null }),
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || res.statusText);
        const alts = (d.alternatives||[]).filter(Boolean);
        lookupBody.innerHTML = `
            <div class="lookup-translation">${esc(d.translation||'')}</div>
            ${alts.length ? `<div class="lookup-alts">Also: ${esc(alts.join(', '))}</div>` : ''}
            ${d.part_of_speech ? `<span class="lookup-pos">${esc(d.part_of_speech)}</span>` : ''}
            ${d.notes   ? `<div class="lookup-notes">${esc(d.notes)}</div>` : ''}
            ${d.example ? `<div class="lookup-example">${esc(d.example)}</div>` : ''}`;
    } catch (err) {
        lookupBody.innerHTML = `<p style="color:var(--danger)">${esc(err.message)}</p>`;
    }
}
document.getElementById('lookup-close').addEventListener('click', () => lookupPopup.classList.add('hidden'));

// ── Grammar check ──────────────────────────────────────────────────
el.btnCheckInput.addEventListener('click', runCheck);
document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.shiftKey && e.key === 'K') { e.preventDefault(); runCheck(); }
});
el.userInput.addEventListener('input', () => {
    _checkErrors = [];
    el.checkResults.classList.add('hidden');
});

async function runCheck() {
    const text = el.userInput.value.trim();
    if (!text || !currentSessionId) return;
    el.btnCheckInput.disabled = true;
    el.btnCheckInput.textContent = '…';
    try {
        const res = await fetch('/api/conversation/check', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, text }),
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || res.statusText);
        _checkErrors = d.errors || [];

        if (_checkErrors.length === 0) {
            el.checkResults.innerHTML = '<span class="check-ok">✓ No errors found</span>';
            el.checkResults.classList.remove('hidden');
            setTimeout(() => el.checkResults.classList.add('hidden'), 3000);
        } else {
            el.checkResults.innerHTML = _checkErrors.map(e => `
                <div class="check-error-row">
                    <span class="check-type">${esc(e.type||'error')}</span>
                    <span class="check-original">${esc(e.error||'')}</span>
                    ${e.suggestion ? `<span class="check-arrow">→</span>
                    <button class="check-apply"
                            data-suggestion="${esc(e.suggestion)}"
                            data-start="${e.start||0}"
                            data-end="${e.end||0}">${esc(e.suggestion)}</button>` : ''}
                    ${e.hint ? `<span class="check-hint">${esc(e.hint)}</span>` : ''}
                </div>`).join('');
            el.checkResults.classList.remove('hidden');

            el.checkResults.querySelectorAll('.check-apply').forEach(btn => {
                btn.addEventListener('click', () => {
                    const sug   = btn.dataset.suggestion;
                    const start = parseInt(btn.dataset.start)||0;
                    const end   = parseInt(btn.dataset.end)||0;
                    const orig  = btn.closest('.check-error-row').querySelector('.check-original').textContent;
                    if (sug && end > start) {
                        el.userInput.value = el.userInput.value.slice(0,start) + sug + el.userInput.value.slice(end);
                    } else if (sug) {
                        el.userInput.value = el.userInput.value.replace(orig, sug);
                    }
                    btn.closest('.check-error-row').style.opacity = '0.4';
                    el.userInput.focus();
                });
            });
        }
    } catch (err) {
        showError('Check failed: ' + err.message);
    } finally {
        el.btnCheckInput.disabled = false;
        el.btnCheckInput.textContent = '✓ Check';
    }
}

// ── Duolingo import ────────────────────────────────────────────────
const importPanel    = document.getElementById('import-panel');
const importTextarea = document.getElementById('import-textarea');
const importStatus   = document.getElementById('import-status');
const importResults  = document.getElementById('import-results');

function openImport() { importPanel.classList.remove('hidden'); importTextarea.focus(); }
document.getElementById('btn-open-import').addEventListener('click', openImport);
document.getElementById('btn-open-import-session').addEventListener('click', openImport);
document.getElementById('import-close').addEventListener('click', () => importPanel.classList.add('hidden'));
document.getElementById('btn-import-submit').addEventListener('click', runImport);

async function runImport() {
    const text = importTextarea.value.trim();
    if (!text || !currentSessionId) {
        importStatus.textContent = 'Start a session first so the tutor can enrich your words.';
        return;
    }
    const btn = document.getElementById('btn-import-submit');
    btn.disabled = true;
    importStatus.textContent = 'Parsing and enriching…';
    importResults.classList.add('hidden');
    try {
        const res = await fetch('/api/conversation/import/vocabulary', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, text }),
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || res.statusText);
        importStatus.textContent = `✓ Imported ${d.imported} new words, ${d.skipped} already known.`;
        const words = d.words || [];
        if (words.length) {
            importResults.innerHTML = words.map((w, i) => `
                <div class="import-word-row">
                    <span class="import-word">${esc(w.word)}</span>
                    <span class="import-trans">${esc(w.translation)}</span>
                    <span class="${i < d.imported ? 'import-badge-new' : 'import-badge-skip'}">${i < d.imported ? '✓ new' : 'exists'}</span>
                </div>`).join('');
            importResults.classList.remove('hidden');
        }
    } catch (err) {
        importStatus.textContent = 'Import failed: ' + err.message;
    } finally {
        btn.disabled = false;
    }
}

// ── Drill panel ────────────────────────────────────────────────────
const drill = {
    panel:        document.getElementById('drill-panel'),
    sessionBody:  document.getElementById('session-body'),
    typeLabel:    document.getElementById('drill-type-label'),
    typeSelect:   document.getElementById('drill-type-select'),
    loading:      document.getElementById('drill-loading'),
    questionDiv:  document.getElementById('drill-question'),
    resultDiv:    document.getElementById('drill-result'),
    prompt:       document.getElementById('drill-prompt'),
    context:      document.getElementById('drill-context'),
    hint:         document.getElementById('drill-hint'),
    answer:       document.getElementById('drill-answer'),
    btnSubmit:    document.getElementById('btn-drill-submit'),
    btnClose:     document.getElementById('btn-close-drill'),
    btnNext:      document.getElementById('btn-drill-next'),
    btnConverse:  document.getElementById('btn-drill-converse'),
    resultIcon:   document.getElementById('drill-result-icon'),
    feedback:     document.getElementById('drill-feedback'),
    correctAnswer: document.getElementById('drill-correct-answer'),
    accuracyText: document.getElementById('drill-accuracy-text'),
    recordRow:    document.getElementById('drill-record-row'),
    textRow:      document.getElementById('drill-text-row'),
    btnRecord:    document.getElementById('btn-drill-record'),
    recordStatus: document.getElementById('drill-record-status'),
    btnReplay:    document.getElementById('btn-drill-replay'),
};

const DRILL_TYPE_LABELS = {
    auto: 'Auto', mixed_review: 'Mixed Review',
    vocabulary_review: 'Vocabulary Review', translation: 'Translation',
    pronunciation: 'Pronunciation',
    irregular_verbs_preterite: 'Preterite', irregular_verbs_imperfect: 'Imperfect',
    irregular_verbs_present: 'Present', irregular_verbs_perfect: 'Perfect',
    reflexive_verbs: 'Reflexive Verbs', noun_declensions: 'Noun Declensions',
    prepositions: 'Prepositions', sentence_dictation: 'Dictation',
    listening_comprehension: 'Listening',
};

let _currentDrillExpected = '';
let _drillOpen = false;

el.btnDrillTab.addEventListener('click', () => {
    if (_drillOpen) closeDrillPanel(); else openDrillPanel();
});

async function openDrillPanel() {
    _drillOpen = true;
    el.btnDrillTab.classList.add('active');
    drill.panel.classList.remove('hidden');
    drill.sessionBody.classList.add('drill-open');
    showDrillState('loading');
    await populateDrillTypeSelect();
    loadDrillQuestion();
}

function closeDrillPanel() {
    _drillOpen = false;
    el.btnDrillTab.classList.remove('active');
    drill.panel.classList.add('hidden');
    drill.sessionBody.classList.remove('drill-open');
}

function showDrillState(state) {
    drill.loading.classList.add('hidden');
    drill.questionDiv.classList.add('hidden');
    drill.resultDiv.classList.add('hidden');
    if (state === 'loading')  drill.loading.classList.remove('hidden');
    if (state === 'question') drill.questionDiv.classList.remove('hidden');
    if (state === 'result')   drill.resultDiv.classList.remove('hidden');
}

async function populateDrillTypeSelect() {
    try {
        const res = await fetch(`/api/conversation/drill/types?language=${currentLanguage}`);
        if (!res.ok) return;
        const data = await res.json();
        drill.typeSelect.innerHTML = data.types
            .map(t => `<option value="${esc(t.id)}">${esc(t.label)}</option>`)
            .join('');
        data.types.forEach(t => { DRILL_TYPE_LABELS[t.id] = t.label; });
    } catch (_) {}
}

async function loadDrillQuestion() {
    const drillType = drill.typeSelect.value || 'auto';
    drill.typeLabel.textContent = DRILL_TYPE_LABELS[drillType] || drillType;
    showDrillState('loading');
    drill.recordRow.classList.add('hidden');
    drill.textRow.classList.remove('hidden');
    drill.btnReplay.classList.add('hidden');
    drill.recordStatus.textContent = '';

    try {
        const res = await fetch('/api/conversation/drill', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, drill_type: drillType }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const q = await res.json();

        _currentDrillExpected = q.correct_answer || '';
        drill.prompt.textContent = q.prompt || '';

        const isListening = ['sentence_dictation','listening_comprehension'].includes(q.drill_type);
        const isPronun    = q.drill_type === 'pronunciation';

        if (q.context && !isListening && !isPronun) {
            drill.context.textContent = q.context;
            drill.context.classList.remove('hidden');
        } else if (isListening || isPronun) {
            drill.context.textContent = isPronun
                ? '🔊 Listen first, then record yourself'
                : '🔊 Listen and type what you hear';
            drill.context.classList.remove('hidden');
        } else {
            drill.context.classList.add('hidden');
        }

        if (q.hint) { drill.hint.textContent = `💡 ${q.hint}`; drill.hint.classList.remove('hidden'); }
        else { drill.hint.classList.add('hidden'); }

        if (isPronun) {
            drill.textRow.classList.add('hidden');
            drill.recordRow.classList.remove('hidden');
        } else {
            drill.textRow.classList.remove('hidden');
            drill.recordRow.classList.add('hidden');
        }

        if ((isListening || isPronun) && q.audio_b64) {
            playBase64Wav(q.audio_b64);
            drill.panel.dataset.currentAudio = q.audio_b64;
            drill.btnReplay.classList.remove('hidden');
        } else {
            drill.panel.dataset.currentAudio = '';
        }

        drill.answer.value = '';
        showDrillState('question');
        if (!isPronun) drill.answer.focus();
    } catch (err) {
        showDrillState('question');
        drill.prompt.textContent = 'Could not load question: ' + err.message;
    }
}

async function submitDrillAnswer() {
    const answer = drill.answer.value.trim();
    if (!answer) return;
    drill.btnSubmit.disabled = true;
    try {
        const res = await fetch('/api/conversation/drill/check', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, user_answer: answer }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const r = await res.json();
        drill.resultIcon.textContent = r.correct ? '✅' : '❌';
        drill.feedback.textContent   = r.feedback || '';
        if (!r.correct) {
            drill.correctAnswer.textContent = `Correct: ${r.correct_answer}`;
            drill.correctAnswer.classList.remove('hidden');
        } else {
            drill.correctAnswer.classList.add('hidden');
        }
        const stats = r.drill_stats || {};
        const pct   = Math.round((stats.accuracy||0)*100);
        drill.accuracyText.textContent = `Accuracy: ${pct}% (${stats.correct||0}/${stats.attempts||0})`;
        showDrillState('result');
    } catch (err) {
        drill.feedback.textContent = 'Error: ' + err.message;
        showDrillState('result');
    } finally {
        drill.btnSubmit.disabled = false;
    }
}

drill.btnClose.addEventListener('click', closeDrillPanel);
drill.btnConverse.addEventListener('click', closeDrillPanel);
drill.btnNext.addEventListener('click', loadDrillQuestion);
drill.btnSubmit.addEventListener('click', submitDrillAnswer);
drill.typeSelect.addEventListener('change', loadDrillQuestion);
drill.answer.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); submitDrillAnswer(); }
});
drill.btnReplay.addEventListener('click', () => {
    const b64 = drill.panel.dataset.currentAudio;
    if (b64) playBase64Wav(b64);
});

// Pronunciation record
let _drillRecording = false, _drillRecorder = null, _drillChunks = [];
drill.btnRecord.addEventListener('click', async () => {
    if (_drillRecording) {
        if (_drillRecorder && _drillRecorder.state !== 'inactive') _drillRecorder.stop();
        return;
    }
    try {
        const stream   = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus' : 'audio/webm';
        _drillRecorder = new MediaRecorder(stream, { mimeType });
        _drillChunks   = [];
        _drillRecorder.addEventListener('dataavailable', e => { if (e.data.size>0) _drillChunks.push(e.data); });
        _drillRecorder.addEventListener('stop', async () => {
            stream.getTracks().forEach(t => t.stop());
            _drillRecording = false;
            drill.btnRecord.textContent = '🎙️ Record';
            drill.btnRecord.classList.remove('btn-recording');
            drill.recordStatus.textContent = 'Scoring…';
            const blob = new Blob(_drillChunks, { type: mimeType });
            await scorePronunciationDrill(blob);
        });
        _drillRecorder.start();
        _drillRecording = true;
        drill.btnRecord.textContent = '⏹ Stop';
        drill.btnRecord.classList.add('btn-recording');
        drill.recordStatus.textContent = '🔴 Recording…';
    } catch (err) {
        drill.recordStatus.textContent = 'Mic error: ' + err.message;
    }
});

async function scorePronunciationDrill(blob) {
    const expected = _currentDrillExpected;
    if (!expected) { drill.recordStatus.textContent = ''; return; }
    try {
        const fd = new FormData();
        fd.append('session_id', currentSessionId);
        fd.append('expected_text', expected);
        fd.append('audio', blob, 'pron.webm');
        const res  = await fetch('/api/conversation/audio/pronunciation', { method: 'POST', body: fd });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const r = await res.json();
        drill.resultIcon.textContent  = r.score >= 75 ? '✅' : r.score >= 50 ? '⚠️' : '❌';
        drill.feedback.textContent    = `Score: ${r.score}/100 — ${r.feedback}`;
        drill.correctAnswer.textContent = `You said: "${r.detected_text}"\nExpected: "${r.expected_text}"`;
        drill.correctAnswer.classList.remove('hidden');
        drill.accuracyText.textContent = `Phonetic: ${r.phonetic_accuracy.toFixed(0)}%  ·  Fluency: ${r.fluency_score.toFixed(0)}%`;
        showDrillState('result');
        drill.recordStatus.textContent = '';
    } catch (err) {
        drill.recordStatus.textContent = 'Scoring failed: ' + err.message;
    }
}

// ── Voice / Mic recording ──────────────────────────────────────────
(function() {
    let mediaRecorder = null, audioChunks = [], recording = false;

    function setMicStatus(msg) {
        el.micStatus.textContent = msg;
        el.micStatus.classList.toggle('hidden', !msg);
    }

    async function startRecording() {
        if (!navigator.mediaDevices?.getUserMedia) {
            setMicStatus('Microphone not supported.');
            return;
        }
        try {
            const stream   = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks    = [];
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus' : '';
            mediaRecorder  = mimeType
                ? new MediaRecorder(stream, { mimeType })
                : new MediaRecorder(stream);
            mediaRecorder.addEventListener('dataavailable', e => { if (e.data.size>0) audioChunks.push(e.data); });
            mediaRecorder.addEventListener('stop', sendAudio);
            mediaRecorder.start();
            recording = true;
            el.btnMic.classList.add('active');
            setMicStatus('Recording… click 🎙️ again to send.');
        } catch (err) {
            setMicStatus('Could not access microphone: ' + err.message);
        }
    }

    function stopRecording() {
        if (mediaRecorder && recording) {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(t => t.stop());
            recording = false;
            el.btnMic.classList.remove('active');
            setMicStatus('Processing…');
        }
    }

    async function sendAudio() {
        if (!audioChunks.length || !currentSessionId) { setMicStatus(''); return; }
        const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType||'audio/webm' });
        const fd   = new FormData();
        fd.append('session_id', currentSessionId);
        fd.append('audio', blob, 'recording.webm');
        setInputEnabled(false);
        try {
            const res  = await fetch('/api/conversation/audio', { method: 'POST', body: fd });
            if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
            const data = await res.json();
            addMessage('user', `🎙️ ${data.transcription}`);
            addMessage('assistant', data.message);
            exchangeCount++;
            el.statExchanges.textContent = exchangeCount;
            if (data.corrections?.length) {
                correctionsCount += data.corrections.length;
                el.statCorrections.textContent = correctionsCount;
                data.corrections.forEach(c => addFeedbackCard('correction', c));
            }
            if (data.new_vocabulary?.length) {
                vocabCount += data.new_vocabulary.length;
                el.statVocab.textContent = vocabCount;
                data.new_vocabulary.forEach(v => addFeedbackCard('vocab', v));
            }
            if (data.audio_response) playBase64Wav(data.audio_response);
            setMicStatus('');
        } catch (err) {
            setMicStatus('Voice error: ' + err.message);
        } finally {
            setInputEnabled(true);
            audioChunks = [];
        }
    }

    if (el.btnMic) {
        el.btnMic.addEventListener('click', () => {
            if (!sessionActive) return;
            if (recording) stopRecording(); else startRecording();
        });
    }
})();

function playBase64Wav(b64) {
    try {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const url   = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
        const audio = new Audio(url);
        audio.addEventListener('ended', () => URL.revokeObjectURL(url));
        audio.play().catch(() => {});
    } catch (_) {}
}

// ── Hands-free mode ────────────────────────────────────────────────
let handsFreeModeActive = false, handsFreeListening = false;
let _hfTTSPlaying = false, _hfPaused = false;
let _hfRecorder = null, _hfChunks = [], _hfSilenceTimer = null;
const HF_SILENCE_MS = 1800;
const TRANSCRIPT_DELAY_MS = 1500;

el.btnHandsfree.addEventListener('click', toggleHandsfree);
el.btnHandsfreeStop.addEventListener('click', () => {
    _hfPaused = !_hfPaused;
    el.btnHandsfreeStop.textContent = _hfPaused ? 'Resume' : 'Pause';
    if (_hfPaused) { setHFState('⏸ Paused'); stopHFListening(); }
    else startHFListening();
});

function toggleHandsfree() {
    if (!sessionActive) return;
    handsFreeModeActive = !handsFreeModeActive;
    el.btnHandsfree.classList.toggle('active', handsFreeModeActive);
    el.btnHandsfree.textContent = handsFreeModeActive ? '🎙️ Auto: ON' : '🎙️ Auto';
    el.handsfreeBar.classList.toggle('hidden', !handsFreeModeActive);
    el.handsfreeIndicator.classList.toggle('hidden', !handsFreeModeActive);
    _hfPaused = false;
    el.btnHandsfreeStop.textContent = 'Pause';
    if (handsFreeModeActive) startHFListening();
    else { stopHFListening(); setHFState(''); }
}

function setHFState(msg) {
    el.handsfreeState.textContent = msg;
    el.handsfreeIndicator.textContent = msg;
}

async function startHFListening() {
    if (!handsFreeModeActive || _hfPaused || _hfTTSPlaying || handsFreeListening) return;
    setHFState('🎙️ Listening…');
    handsFreeListening = true;
    try {
        const stream   = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus' : 'audio/webm';
        _hfRecorder = new MediaRecorder(stream, { mimeType });
        _hfChunks   = [];
        _hfRecorder.addEventListener('dataavailable', e => {
            if (e.data.size > 0) _hfChunks.push(e.data);
            clearTimeout(_hfSilenceTimer);
            _hfSilenceTimer = setTimeout(stopHFListening, HF_SILENCE_MS);
        });
        _hfRecorder.addEventListener('stop', onHFStop);
        _hfRecorder.start(200);
        setTimeout(() => { if (handsFreeListening) stopHFListening(); }, 30000);
    } catch (err) {
        setHFState('Mic error: ' + err.message);
        handsFreeListening = false;
    }
}

function stopHFListening() {
    clearTimeout(_hfSilenceTimer);
    if (_hfRecorder && _hfRecorder.state !== 'inactive') {
        _hfRecorder.stream.getTracks().forEach(t => t.stop());
        _hfRecorder.stop();
    }
    handsFreeListening = false;
}

async function onHFStop() {
    if (!_hfChunks.length) {
        if (handsFreeModeActive && !_hfPaused) setTimeout(startHFListening, 500);
        return;
    }
    setHFState('🧠 Thinking…');
    const blob = new Blob(_hfChunks, { type: _hfRecorder.mimeType||'audio/webm' });
    const fd   = new FormData();
    fd.append('session_id', currentSessionId);
    fd.append('audio', blob, 'hf.webm');
    try {
        const res  = await fetch('/api/conversation/audio', { method: 'POST', body: fd });
        if (!res.ok) throw new Error((await res.json()).detail||res.statusText);
        const d = await res.json();
        exchangeCount++;
        el.statExchanges.textContent = exchangeCount;
        if (d.corrections?.length) {
            correctionsCount += d.corrections.length;
            el.statCorrections.textContent = correctionsCount;
            d.corrections.forEach(c => addFeedbackCard('correction', c));
        }
        if (d.new_vocabulary?.length) {
            vocabCount += d.new_vocabulary.length;
            el.statVocab.textContent = vocabCount;
            d.new_vocabulary.forEach(v => addFeedbackCard('vocab', v));
        }
        addMessage('user', `🎙️ ${d.transcription}`);
        if (d.audio_response) {
            _hfTTSPlaying = true;
            setHFState('🔊 Speaking…');
            await playBase64WavAsync(d.audio_response, () => {
                _hfTTSPlaying = false;
                setTimeout(() => {
                    addMessage('assistant', d.message);
                    if (handsFreeModeActive && !_hfPaused) setTimeout(startHFListening, 600);
                }, TRANSCRIPT_DELAY_MS);
            });
        } else {
            addMessage('assistant', d.message);
            setHFState('🎙️ Listening…');
            if (handsFreeModeActive && !_hfPaused) setTimeout(startHFListening, 600);
        }
    } catch (err) {
        addMessage('assistant', 'Lo siento, no te entendí. Intenta de nuevo.');
        setHFState('🎙️ Listening…');
        if (handsFreeModeActive && !_hfPaused) setTimeout(startHFListening, 1000);
    }
}

function playBase64WavAsync(b64, onEnded) {
    return new Promise(resolve => {
        try {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const url   = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
            const audio = new Audio(url);
            const done  = () => { URL.revokeObjectURL(url); if (onEnded) onEnded(); resolve(); };
            audio.addEventListener('ended', done);
            audio.addEventListener('error', done);
            audio.play().catch(() => done());
        } catch (_) { resolve(); if (onEnded) onEnded(); }
    });
}

// ── Resume on page load ────────────────────────────────────────────
(async function resumeIfNeeded() {
    if (!currentSessionId) return;
    try {
        const res = await fetch(`/api/session/status/${currentSessionId}`);
        if (res.ok) {
            const data = await res.json();
            if (data.active) {
                currentLanguage = data.language;
                sessionActive   = true;
                el.activeLangLabel.textContent = LANGUAGE_NAMES[currentLanguage] || currentLanguage;
                if (data.voice_enabled) el.btnMic.classList.remove('hidden');
                showView('session');
                addMessage('assistant', '(Session resumed — continue where you left off.)');
                return;
            }
        }
    } catch (_) {}
    sessionStorage.removeItem('sessionId');
    currentSessionId = null;
})();
