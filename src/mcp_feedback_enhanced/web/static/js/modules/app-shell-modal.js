/**
 * MCP Feedback Enhanced - 應用外殼模態管理器
 * =========================================================
 *
 * 統一管理「設定 / 關於 / 會話歷史」三個應用級模態的開關。
 *
 * 使用方式（HTML 聲明式）：
 *   <button data-modal-open="settingsModal">⚙️ 設定</button>
 *   <div id="settingsModal" class="app-modal" hidden>
 *     <div class="modal-backdrop" data-modal-dismiss="settingsModal"></div>
 *     <div class="modal-content">
 *       <button data-modal-dismiss="settingsModal">×</button>
 *       ...
 *     </div>
 *   </div>
 *
 * - 點擊 [data-modal-open="id"] 打開對應模態
 * - 點擊 [data-modal-dismiss="id"] 或 backdrop 關閉
 * - 按 Esc 關閉當前打開的模態
 * - 一次只開一個；打開新模態會關閉已打開的
 * - body 加上 .app-modal-open 類以鎖定頁面滾動
 *
 * 程式化 API：
 *   window.MCPFeedback.AppShellModal.open('settingsModal');
 *   window.MCPFeedback.AppShellModal.close('settingsModal');
 *   window.MCPFeedback.AppShellModal.closeAll();
 */
(function() {
    'use strict';

    window.MCPFeedback = window.MCPFeedback || {};

    var BODY_CLASS = 'app-modal-open';
    var MODAL_SELECTOR = '.app-modal';
    var OPEN_ATTR = 'data-modal-open';
    var DISMISS_ATTR = 'data-modal-dismiss';

    var currentOpenId = null;

    function getModal(id) {
        if (!id) return null;
        var el = document.getElementById(id);
        if (!el || !el.classList.contains('app-modal')) return null;
        return el;
    }

    function open(id) {
        var modal = getModal(id);
        if (!modal) {
            console.warn('[AppShellModal] modal not found:', id);
            return false;
        }
        if (currentOpenId && currentOpenId !== id) {
            close(currentOpenId, { silent: true });
        }
        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add(BODY_CLASS);
        currentOpenId = id;

        // 初始焦點：優先關閉按鈕，退而求其次 modal 本身
        var firstFocusable = modal.querySelector('.modal-close, [autofocus]');
        if (firstFocusable && typeof firstFocusable.focus === 'function') {
            try { firstFocusable.focus({ preventScroll: true }); } catch (e) { /* noop */ }
        }

        modal.dispatchEvent(new CustomEvent('app-modal:opened', { bubbles: true, detail: { id: id } }));
        return true;
    }

    function close(id, options) {
        options = options || {};
        var modal = getModal(id);
        if (!modal) return false;
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        if (currentOpenId === id) {
            currentOpenId = null;
        }
        if (!currentOpenId) {
            document.body.classList.remove(BODY_CLASS);
        }
        if (!options.silent) {
            modal.dispatchEvent(new CustomEvent('app-modal:closed', { bubbles: true, detail: { id: id } }));
        }
        return true;
    }

    function closeAll() {
        var modals = document.querySelectorAll(MODAL_SELECTOR);
        modals.forEach(function(m) {
            if (!m.hidden) close(m.id, { silent: true });
        });
        currentOpenId = null;
        document.body.classList.remove(BODY_CLASS);
    }

    function getCurrent() {
        return currentOpenId;
    }

    function onDocumentClick(event) {
        var target = event.target;
        if (!target || !(target instanceof Element)) return;

        var opener = target.closest('[' + OPEN_ATTR + ']');
        if (opener) {
            var openId = opener.getAttribute(OPEN_ATTR);
            if (openId) {
                event.preventDefault();
                open(openId);
                return;
            }
        }

        var dismisser = target.closest('[' + DISMISS_ATTR + ']');
        if (dismisser) {
            var dismissId = dismisser.getAttribute(DISMISS_ATTR);
            if (dismissId) {
                event.preventDefault();
                close(dismissId);
                return;
            }
        }
    }

    function onKeyDown(event) {
        if (event.key !== 'Escape' && event.keyCode !== 27) return;
        if (!currentOpenId) return;
        // 若有更高層模態（如 .session-details-modal）在場，讓它自己處理
        var higherModal = document.querySelector('.session-details-modal, .prompt-modal');
        if (higherModal && !higherModal.hidden) return;
        event.preventDefault();
        close(currentOpenId);
    }

    function init() {
        if (init.__done) return;
        init.__done = true;
        document.addEventListener('click', onDocumentClick, false);
        document.addEventListener('keydown', onKeyDown, false);
        console.log('✅ AppShellModal initialized');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }

    window.MCPFeedback.AppShellModal = {
        open: open,
        close: close,
        closeAll: closeAll,
        getCurrent: getCurrent
    };
})();
