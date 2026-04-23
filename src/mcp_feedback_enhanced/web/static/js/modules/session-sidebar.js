/**
 * MCP Feedback Enhanced - Session Sidebar Component (Phase 3)
 * =========================================================
 *
 * 從 MultiSessionStore 渲染左側會話列表。
 *
 * 功能：
 * - 列表 / 空態 / 統計計數
 * - 點擊卡片切換 active
 * - 右上角按鈕：歸檔該會話
 * - 頭部操作：清除所有已完成會話、展開/折疊側欄
 * - 折疊狀態 localStorage 持久化
 *
 * 依賴：
 * - window.MCPFeedback.sessionStore
 * - window.MCPFeedback.Utils.StatusUtils / TimeUtils（可選，不存在時有兜底）
 */

(function () {
    'use strict';

    window.MCPFeedback = window.MCPFeedback || {};

    var logger = (window.MCPFeedback && window.MCPFeedback.logger) ||
        { debug: function(){}, info: function(){}, warn: console.warn, error: console.error };

    var COLLAPSE_KEY = 'mcp.sidebar.collapsed';

    // --------- 工具函數 ---------

    function fmtTitle(rec) {
        if (rec.title && rec.title.trim()) return rec.title;
        if (rec.summary) {
            var s = String(rec.summary).replace(/\s+/g, ' ').trim();
            return s.length > 40 ? s.slice(0, 40) + '…' : s;
        }
        return '會話 ' + (rec.session_id || '').slice(0, 8);
    }

    function fmtShortId(sid) {
        if (!sid) return '--';
        return sid.length > 8 ? sid.slice(0, 8) : sid;
    }

    function fmtRelative(unixMs) {
        if (!unixMs) return '';
        var now = Date.now();
        var diffSec = Math.max(0, (now - unixMs) / 1000);
        if (diffSec < 60)    return Math.floor(diffSec) + 's';
        if (diffSec < 3600)  return Math.floor(diffSec / 60) + 'm';
        if (diffSec < 86400) return Math.floor(diffSec / 3600) + 'h';
        return Math.floor(diffSec / 86400) + 'd';
    }

    function safeT(key, fallback) {
        try {
            var mgr = window.i18nManager;
            if (mgr && typeof mgr.t === 'function') {
                var v = mgr.t(key);
                if (v && v !== key) return v;
            }
        } catch (e) { /* ignore */ }
        return fallback;
    }

    function statusLabel(status) {
        var map = {
            waiting:            safeT('sessionStatus.waiting',             safeT('status.waiting.title',   '等待中')),
            active:             safeT('sessionStatus.active',              safeT('status.active.title',    '進行中')),
            feedback_submitted: safeT('sessionStatus.feedback_submitted',  safeT('status.submitted.title', '已提交')),
            completed:          safeT('sessionStatus.completed',           safeT('status.completed.title', '已完成')),
            expired:            safeT('sessionStatus.expired',             '已過期'),
            timeout:            safeT('sessionStatus.timeout',             '逾時'),
            canceled:           safeT('sessionStatus.canceled',            '已取消'),
            error:              safeT('sessionStatus.error',               '錯誤')
        };
        return map[status] || status;
    }

    // --------- Sidebar 類 ---------

    function SessionSidebar(opts) {
        opts = opts || {};
        this.store = opts.store || window.MCPFeedback.sessionStore;
        if (!this.store) {
            throw new Error('[SessionSidebar] 需要 MultiSessionStore 實例');
        }

        this.rootEl         = document.getElementById('sessionSidebar');
        this.listEl         = document.getElementById('sessionSidebarList');
        this.emptyEl        = document.getElementById('sidebarEmpty');
        this.waitingBadgeEl = document.getElementById('sidebarWaitingCount');
        this.activeBadgeEl  = document.getElementById('sidebarActiveCount');
        this.toggleBtnEl    = document.getElementById('sidebarToggleBtn');
        this.reopenBtnEl    = document.getElementById('sidebarReopenBtn');
        this.clearDoneBtnEl = document.getElementById('sidebarClearDoneBtn');

        if (!this.rootEl || !this.listEl) {
            logger.warn('[SessionSidebar] 找不到 DOM 錨點，跳過初始化');
            return;
        }

        this.onSessionActivate = typeof opts.onSessionActivate === 'function' ? opts.onSessionActivate : null;
        this.onArchiveRequest  = typeof opts.onArchiveRequest  === 'function' ? opts.onArchiveRequest  : null;
        this.onClearDoneRequest = typeof opts.onClearDoneRequest === 'function' ? opts.onClearDoneRequest : null;

        this._renderScheduled = false;

        this._bindEvents();
        this._applyCollapseState();
        this._subscribe();
        this.render();
    }

    SessionSidebar.prototype._bindEvents = function () {
        var self = this;

        this.listEl.addEventListener('click', function (ev) {
            var card = ev.target.closest('.session-card');
            if (!card) return;

            if (ev.target.closest('.session-card-action-btn')) {
                var actionBtn = ev.target.closest('.session-card-action-btn');
                var action = actionBtn.getAttribute('data-action');
                var sid = card.getAttribute('data-session-id');
                if (action === 'archive') {
                    self._handleArchive(sid);
                }
                ev.stopPropagation();
                return;
            }

            var sessionId = card.getAttribute('data-session-id');
            if (sessionId) {
                self._activateSession(sessionId);
            }
        });

        if (this.toggleBtnEl) {
            this.toggleBtnEl.addEventListener('click', function () { self.setCollapsed(true); });
        }
        if (this.reopenBtnEl) {
            this.reopenBtnEl.addEventListener('click', function () { self.setCollapsed(false); });
        }
        if (this.clearDoneBtnEl) {
            this.clearDoneBtnEl.addEventListener('click', function () { self._handleClearDone(); });
        }
    };

    SessionSidebar.prototype._subscribe = function () {
        var self = this;
        var S = window.MCPFeedback.SessionStore;
        var schedule = function () { self._scheduleRender(); };

        this.store.on(S.EVENTS.SNAPSHOT_APPLIED, schedule);
        this.store.on(S.EVENTS.SESSION_ADDED,    schedule);
        this.store.on(S.EVENTS.SESSION_UPDATED,  schedule);
        this.store.on(S.EVENTS.SESSION_REMOVED,  schedule);
        this.store.on(S.EVENTS.ACTIVE_CHANGED,   schedule);
    };

    SessionSidebar.prototype._scheduleRender = function () {
        if (this._renderScheduled) return;
        this._renderScheduled = true;
        var self = this;
        requestAnimationFrame(function () {
            self._renderScheduled = false;
            self.render();
        });
    };

    SessionSidebar.prototype._activateSession = function (sessionId) {
        if (!sessionId) return;
        if (this.store.getActiveSessionId() === sessionId) return;

        this.store.setActiveSessionId(sessionId);

        if (this.onSessionActivate) {
            try { this.onSessionActivate(sessionId); } catch (e) { logger.error(e); }
        }
    };

    SessionSidebar.prototype._handleArchive = function (sessionId) {
        if (!sessionId) return;
        if (this.onArchiveRequest) {
            try { this.onArchiveRequest(sessionId); } catch (e) { logger.error(e); }
        } else {
            fetch('/api/archive-session/' + encodeURIComponent(sessionId), { method: 'POST' })
                .catch(function (e) { logger.error('[SessionSidebar] archive 失敗', e); });
        }
    };

    SessionSidebar.prototype._handleClearDone = function () {
        if (this.onClearDoneRequest) {
            try { this.onClearDoneRequest(); } catch (e) { logger.error(e); }
        } else {
            fetch('/api/sessions?status=all_terminal', { method: 'DELETE' })
                .catch(function (e) { logger.error('[SessionSidebar] clear-done 失敗', e); });
        }
    };

    // --------- 折疊狀態 ---------

    SessionSidebar.prototype.setCollapsed = function (collapsed) {
        collapsed = !!collapsed;
        if (collapsed) {
            this.rootEl.classList.add('collapsed');
            if (this.reopenBtnEl) this.reopenBtnEl.style.display = '';
        } else {
            this.rootEl.classList.remove('collapsed');
            if (this.reopenBtnEl) this.reopenBtnEl.style.display = 'none';
        }
        try {
            localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (e) { /* ignore */ }
    };

    SessionSidebar.prototype._applyCollapseState = function () {
        try {
            var v = localStorage.getItem(COLLAPSE_KEY);
            if (v === '1') this.setCollapsed(true);
            else this.setCollapsed(false);
        } catch (e) {
            this.setCollapsed(false);
        }
    };

    // --------- 渲染 ---------

    SessionSidebar.prototype.render = function () {
        var sessions = this.store.getSessions();
        var activeId = this.store.getActiveSessionId();
        var stats    = this.store.countByStatus();

        sessions.sort(function (a, b) {
            var orderA = sortPriority(a.status);
            var orderB = sortPriority(b.status);
            if (orderA !== orderB) return orderA - orderB;
            return (b.last_activity || b.created_at || 0) - (a.last_activity || a.created_at || 0);
        });

        if (this.waitingBadgeEl) this.waitingBadgeEl.textContent = stats.waiting;
        if (this.activeBadgeEl)  this.activeBadgeEl.textContent  = stats.active;

        if (sessions.length === 0) {
            if (this.emptyEl) this.emptyEl.style.display = '';
            var cards = this.listEl.querySelectorAll('.session-card');
            for (var i = 0; i < cards.length; i++) cards[i].remove();
            return;
        }
        if (this.emptyEl) this.emptyEl.style.display = 'none';

        var desiredIds = sessions.map(function (s) { return s.session_id; });
        var existingCards = this.listEl.querySelectorAll('.session-card');
        for (var j = 0; j < existingCards.length; j++) {
            var sid = existingCards[j].getAttribute('data-session-id');
            if (desiredIds.indexOf(sid) === -1) {
                existingCards[j].remove();
            }
        }

        var frag = document.createDocumentFragment();
        for (var k = 0; k < sessions.length; k++) {
            var rec = sessions[k];
            var existing = this.listEl.querySelector(
                '.session-card[data-session-id="' + cssEscape(rec.session_id) + '"]'
            );
            if (existing) {
                updateCard(existing, rec, activeId);
            } else {
                var card = buildCard(rec, activeId);
                frag.appendChild(card);
            }
        }
        if (frag.childNodes.length > 0) {
            this.listEl.appendChild(frag);
        }

        reorderCards(this.listEl, desiredIds);
    };

    function sortPriority(status) {
        if (status === 'waiting')            return 0;
        if (status === 'active')             return 1;
        if (status === 'feedback_submitted') return 2;
        return 3;
    }

    function cssEscape(s) {
        if (window.CSS && window.CSS.escape) return window.CSS.escape(s);
        return String(s).replace(/["\\]/g, '\\$&');
    }

    function buildCard(rec, activeId) {
        var card = document.createElement('div');
        card.className = 'session-card';
        card.setAttribute('data-session-id', rec.session_id);
        card.setAttribute('role', 'listitem');
        card.setAttribute('tabindex', '0');

        card.innerHTML =
            '<div class="session-card-actions">' +
              '<button type="button" class="session-card-action-btn" data-action="archive" ' +
                'title="歸檔此會話" data-i18n-title="sessionList.archive" aria-label="archive">×</button>' +
            '</div>' +
            '<div class="session-card-title"></div>' +
            '<div class="session-card-meta">' +
              '<span class="session-card-status"></span>' +
              '<span class="session-card-id"></span>' +
              '<span class="session-card-time"></span>' +
            '</div>' +
            '<div class="session-card-summary"></div>';

        updateCard(card, rec, activeId);
        return card;
    }

    function updateCard(card, rec, activeId) {
        var statusKey = rec.status || 'waiting';

        card.classList.toggle('active',              rec.session_id === activeId);
        card.classList.toggle('waiting',             statusKey === 'waiting');
        card.classList.toggle('pulse',               statusKey === 'waiting' || rec.has_pending_notification);
        card.classList.toggle('active-status',       statusKey === 'active');
        card.classList.toggle('feedback-submitted',  statusKey === 'feedback_submitted');
        card.classList.toggle('completed',           statusKey === 'completed');
        card.classList.toggle('expired',             statusKey === 'expired');
        card.classList.toggle('timeout',             statusKey === 'timeout');
        card.classList.toggle('canceled',            statusKey === 'canceled');

        var titleEl  = card.querySelector('.session-card-title');
        var statusEl = card.querySelector('.session-card-status');
        var idEl     = card.querySelector('.session-card-id');
        var timeEl   = card.querySelector('.session-card-time');
        var sumEl    = card.querySelector('.session-card-summary');

        if (titleEl)  titleEl.textContent  = fmtTitle(rec);
        if (statusEl) {
            statusEl.textContent = statusLabel(statusKey);
            statusEl.className   = 'session-card-status ' + statusKey;
        }
        if (idEl)     idEl.textContent     = fmtShortId(rec.session_id);
        if (timeEl)   timeEl.textContent   = fmtRelative(rec.last_activity || rec.created_at);

        var preview = rec.summary || '';
        if (sumEl) sumEl.textContent = preview;

        var pdPrefix = rec.project_directory ? (rec.project_directory.split('/').pop() || '') : '';
        if (pdPrefix) card.title = pdPrefix + ' · ' + rec.session_id;
    }

    function reorderCards(listEl, desiredIds) {
        var cards = Array.prototype.slice.call(listEl.querySelectorAll('.session-card'));
        for (var i = 0; i < desiredIds.length; i++) {
            var want = desiredIds[i];
            var node = cards.find(function (c) { return c.getAttribute('data-session-id') === want; });
            if (node && node.parentNode === listEl) {
                listEl.appendChild(node);
            }
        }
    }

    // --------- 暴露 ---------

    window.MCPFeedback.SessionSidebar = SessionSidebar;

    logger.info('[SessionSidebar] module loaded');
})();
