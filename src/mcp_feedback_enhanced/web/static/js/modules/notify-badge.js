/**
 * MCP Feedback Enhanced - Notify Badge (Phase 3)
 * =============================================
 *
 * 將「當前等待反饋的會話數」反映到：
 *   - 頁面標題 ``(N) 原標題``
 *   - Favicon 紅點（透過 canvas 動態生成 .ico）
 *   - 瀏覽器系統通知（可選，使用者允許後觸發）
 *   - 快捷鍵：Cmd/Ctrl + 1..9 切換到第 N 個會話（按側欄順序）
 *
 * 依賴：window.MCPFeedback.sessionStore
 */

(function () {
    'use strict';

    window.MCPFeedback = window.MCPFeedback || {};

    var logger = (window.MCPFeedback && window.MCPFeedback.logger) ||
        { debug: function(){}, info: function(){}, warn: console.warn, error: console.error };

    var store = null;
    var baseTitle = '';
    var lastWaitingCount = 0;
    // 頁面代碼其他地方會任意改寫 document.title（例如 app.js 在收到 session_updated
    // 時會把標題直接設為 "MCP Feedback - <projectName>"）。為了不讓 (N) 前綴被抹
    // 掉，我們會同步維護 baseTitle + lastWaitingCount，並用 MutationObserver 監聽
    // <title> 變化，在檢測到外部改寫時立即重新套上 (N) 前綴。
    var applyingBadge = false; // 用於區分 observer 觀察到的是「我們自己」還是「外部」改的

    // 記住哪些 session 已經發過系統通知，避免重複彈
    var notifiedSessionIds = Object.create(null);

    function getStore() {
        if (!store) store = window.MCPFeedback && window.MCPFeedback.sessionStore;
        return store;
    }

    // --------- Title + Favicon ---------

    function stripBadge(title) {
        return (title || '').replace(/^\(\d+\)\s*/, '');
    }

    function composeTitle(base, waiting) {
        if (!base) base = 'MCP Feedback';
        return waiting > 0 ? '(' + waiting + ') ' + base : base;
    }

    function applyTitleBadge() {
        var desired = composeTitle(baseTitle || 'MCP Feedback', lastWaitingCount);
        if (document.title !== desired) {
            applyingBadge = true;
            try {
                document.title = desired;
            } finally {
                applyingBadge = false;
            }
        }
    }

    function setupTitleObserver() {
        var titleEl = document.querySelector('title');
        if (!titleEl || typeof MutationObserver === 'undefined') return;

        var observer = new MutationObserver(function () {
            if (applyingBadge) return; // 忽略自己寫入的迴音
            var raw = document.title;
            var stripped = stripBadge(raw);
            if (stripped !== baseTitle) {
                baseTitle = stripped || 'MCP Feedback';
            }
            applyTitleBadge();
        });

        observer.observe(titleEl, {
            subtree: true,
            childList: true,
            characterData: true
        });
    }

    function updateTitle(waiting) {
        lastWaitingCount = waiting;
        if (!baseTitle) baseTitle = stripBadge(document.title) || 'MCP Feedback';
        applyTitleBadge();
    }

    var faviconCanvas = null;
    var faviconLink = null;

    function getFaviconLink() {
        if (faviconLink) return faviconLink;
        var link = document.querySelector("link[rel*='icon'][type='image/svg+xml']") ||
                   document.querySelector("link[rel*='icon']");
        if (!link) {
            link = document.createElement('link');
            link.rel = 'icon';
            document.head.appendChild(link);
        }
        faviconLink = link;
        return link;
    }

    function updateFavicon(waiting) {
        try {
            if (!faviconCanvas) {
                faviconCanvas = document.createElement('canvas');
                faviconCanvas.width = 32;
                faviconCanvas.height = 32;
            }
            var ctx = faviconCanvas.getContext('2d');
            ctx.clearRect(0, 0, 32, 32);

            // 底色圓形（淡藍）
            ctx.fillStyle = '#007acc';
            ctx.beginPath();
            ctx.arc(16, 16, 14, 0, Math.PI * 2);
            ctx.fill();

            // M 字或留白
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 20px -apple-system, Segoe UI, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('M', 16, 17);

            // 右上角紅點 + 數字
            if (waiting > 0) {
                ctx.fillStyle = '#ff5722';
                ctx.beginPath();
                ctx.arc(24, 8, 8, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = '#fff';
                ctx.font = 'bold 10px -apple-system, Segoe UI, sans-serif';
                ctx.fillText(waiting > 9 ? '9+' : String(waiting), 24, 9);
            }

            var link = getFaviconLink();
            link.type = 'image/png';
            link.href = faviconCanvas.toDataURL('image/png');
        } catch (e) {
            logger.warn('[NotifyBadge] favicon 更新失敗', e);
        }
    }

    // --------- 系統通知 ---------

    function maybeAskPermission() {
        if (!('Notification' in window)) return;
        if (Notification.permission === 'default') {
            // 延遲詢問：避免一進頁就彈（UX 較好）
            setTimeout(function () {
                try { Notification.requestPermission(); } catch (e) { /* noop */ }
            }, 3000);
        }
    }

    function maybeFireSystemNotification(rec) {
        if (!('Notification' in window)) return;
        if (Notification.permission !== 'granted') return;
        if (document.visibilityState === 'visible') return;

        if (notifiedSessionIds[rec.session_id]) return;
        notifiedSessionIds[rec.session_id] = true;

        try {
            var title = rec.title || 'MCP Feedback';
            var body = (rec.summary || '').slice(0, 120);
            var n = new Notification(title + ' · 等待反饋', {
                body: body,
                tag: 'mcp-' + rec.session_id,
                silent: false
            });
            n.onclick = function () {
                window.focus();
                var s = getStore();
                if (s) s.setActiveSessionId(rec.session_id);
                n.close();
            };
        } catch (e) {
            logger.warn('[NotifyBadge] 系統通知失敗', e);
        }
    }

    // --------- 主更新 ---------

    function recomputeAndApply() {
        var s = getStore();
        if (!s) return;

        var stats = s.countByStatus();
        var waiting = stats.waiting || 0;

        // updateTitle 自己會更新 lastWaitingCount，這裡不必做變化比較
        updateTitle(waiting);
        updateFavicon(waiting);
    }

    function handleNewWaiting(session) {
        if (!session) return;
        if (session.status === 'waiting' && !notifiedSessionIds[session.session_id]) {
            maybeFireSystemNotification(session);
        }
    }

    // --------- 快捷鍵：Cmd/Ctrl + 1..9 ---------

    function setupShortcuts() {
        document.addEventListener('keydown', function (ev) {
            var isAccel = ev.metaKey || ev.ctrlKey;
            if (!isAccel) return;
            if (ev.altKey || ev.shiftKey) return;
            var key = ev.key;
            if (!/^[1-9]$/.test(key)) return;

            var s = getStore();
            if (!s) return;

            // 與 sidebar 顯示順序保持一致：最新的在第 1 位，Cmd+1 → 列表第 1 張卡
            var sessions = s.getSessions().sort(function (a, b) {
                return (b.created_at || 0) - (a.created_at || 0);
            });
            var idx = parseInt(key, 10) - 1;
            if (idx < 0 || idx >= sessions.length) return;

            ev.preventDefault();
            s.setActiveSessionId(sessions[idx].session_id);
        }, false);
    }

    // --------- 啟動 ---------

    function init() {
        var s = getStore();
        if (!s) {
            logger.warn('[NotifyBadge] SessionStore 未載入，跳過');
            return;
        }

        baseTitle = stripBadge(document.title) || 'MCP Feedback';
        setupTitleObserver();
        maybeAskPermission();
        setupShortcuts();

        var S = window.MCPFeedback.SessionStore;

        s.on(S.EVENTS.SNAPSHOT_APPLIED, recomputeAndApply);
        s.on(S.EVENTS.SESSION_UPDATED, recomputeAndApply);
        s.on(S.EVENTS.SESSION_REMOVED, recomputeAndApply);

        s.on(S.EVENTS.SESSION_ADDED, function (ev) {
            recomputeAndApply();
            if (ev && ev.session) handleNewWaiting(ev.session);
        });

        s.on(S.EVENTS.SESSION_UPDATED, function (ev) {
            if (ev && ev.session && ev.session.status === 'waiting') {
                handleNewWaiting(ev.session);
            }
        });

        // 用戶切換到 tab 時，清除已通知標記（允許下次再提醒）
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') {
                notifiedSessionIds = Object.create(null);
            }
        });

        recomputeAndApply();
        logger.info('[NotifyBadge] initialized');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.MCPFeedback.notifyBadge = {
        _init: init,
        recompute: recomputeAndApply
    };
})();
