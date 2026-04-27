/**
 * MCP Feedback Enhanced - Multi-Session Store (Phase 3)
 * ===================================================
 *
 * 存儲所有會話的全局狀態，並提供訂閱機制。
 *
 * 設計原則：
 * - 單一數據源：所有會話的快照都通過這個 Store 讀寫
 * - 只讀暴露：外部通過 getSessions()/getActiveSessionId() 讀取
 * - 細粒度事件：change / active_changed / session_added / session_updated / session_removed
 * - 冪等：applySnapshot() 可以隨時被調用以全量重建
 * - 解耦：Store 不知道 WebSocket，也不知道 DOM；由外部 wire
 *
 * 數據結構 SessionRecord（與後端 build_sessions_snapshot 對齊）：
 *   {
 *     session_id:         string
 *     title:              string
 *     project_directory:  string
 *     summary:            string
 *     status:             "waiting" | "active" | "feedback_submitted" | "completed"
 *                        | "expired" | "timeout" | "canceled" | "error"
 *     status_message:     string
 *     created_at:         number (unix ms)
 *     last_activity:      number (unix ms)
 *     feedback_completed: boolean
 *     is_current:         boolean
 *     user_messages:      Array<any>
 *     // 前端派生字段（不由後端提供，由 WS 事件/本地邏輯維護）：
 *     has_pending_notification: boolean
 *   }
 */

(function () {
    'use strict';

    window.MCPFeedback = window.MCPFeedback || {};

    var logger = (window.MCPFeedback && window.MCPFeedback.logger) ||
        { debug: function(){}, info: function(){}, warn: console.warn, error: console.error };

    /**
     * 可訂閱事件類型
     */
    var EVENTS = {
        CHANGE: 'change',                     // 任何變化都會觸發（兜底用）
        ACTIVE_CHANGED: 'active_changed',     // activeSessionId 變化
        SESSION_ADDED: 'session_added',       // 新增會話
        SESSION_UPDATED: 'session_updated',   // 某個會話的字段更新
        SESSION_REMOVED: 'session_removed',   // 會話被刪除/歸檔
        SNAPSHOT_APPLIED: 'snapshot_applied'  // 全量快照到達後
    };

    /**
     * 終止態（不再變化、可被清理）
     */
    var TERMINAL_STATUSES = [
        'feedback_submitted', 'completed',
        'expired', 'timeout', 'canceled', 'error'
    ];

    function isTerminal(status) {
        return TERMINAL_STATUSES.indexOf(status) !== -1;
    }

    /**
     * 拷貝一份記錄，避免外部修改內部狀態
     */
    function cloneRecord(rec) {
        if (!rec) return null;
        return {
            session_id: rec.session_id,
            title: rec.title || '',
            project_directory: rec.project_directory || '',
            summary: rec.summary || '',
            status: rec.status || 'waiting',
            status_message: rec.status_message || '',
            created_at: rec.created_at || 0,
            last_activity: rec.last_activity || 0,
            feedback_completed: !!rec.feedback_completed,
            is_current: !!rec.is_current,
            user_messages: Array.isArray(rec.user_messages) ? rec.user_messages.slice() : [],
            ai_summaries: Array.isArray(rec.ai_summaries) ? rec.ai_summaries.slice() : [],
            has_pending_notification: !!rec.has_pending_notification
        };
    }

    /**
     * 淺合併，僅覆蓋定義過的字段
     */
    function mergeRecord(oldRec, patch) {
        var out = cloneRecord(oldRec) || { session_id: patch.session_id };
        Object.keys(patch).forEach(function (k) {
            if (patch[k] !== undefined) {
                out[k] = patch[k];
            }
        });
        return out;
    }

    function MultiSessionStore() {
        this._sessions = Object.create(null); // session_id -> SessionRecord
        this._activeSessionId = null;
        this._listeners = Object.create(null); // type -> [fn]
    }

    // --------- 訂閱 / 派發 ---------

    MultiSessionStore.prototype.on = function (type, fn) {
        if (!this._listeners[type]) this._listeners[type] = [];
        this._listeners[type].push(fn);
        var self = this;
        return function off() {
            var arr = self._listeners[type] || [];
            var idx = arr.indexOf(fn);
            if (idx !== -1) arr.splice(idx, 1);
        };
    };

    MultiSessionStore.prototype._emit = function (type, payload) {
        var arr = this._listeners[type] || [];
        for (var i = 0; i < arr.length; i++) {
            try {
                arr[i](payload);
            } catch (e) {
                logger.error('[SessionStore] listener 異常 (' + type + '):', e);
            }
        }
        if (type !== EVENTS.CHANGE) {
            var cArr = this._listeners[EVENTS.CHANGE] || [];
            for (var j = 0; j < cArr.length; j++) {
                try {
                    cArr[j]({ type: type, payload: payload });
                } catch (e) {
                    logger.error('[SessionStore] change listener 異常:', e);
                }
            }
        }
    };

    // --------- 讀取 API ---------

    MultiSessionStore.prototype.getSessions = function () {
        var out = [];
        var keys = Object.keys(this._sessions);
        for (var i = 0; i < keys.length; i++) {
            out.push(cloneRecord(this._sessions[keys[i]]));
        }
        return out;
    };

    MultiSessionStore.prototype.getSession = function (sessionId) {
        if (!sessionId) return null;
        return cloneRecord(this._sessions[sessionId] || null);
    };

    MultiSessionStore.prototype.getActiveSessionId = function () {
        return this._activeSessionId;
    };

    MultiSessionStore.prototype.getActiveSession = function () {
        return this.getSession(this._activeSessionId);
    };

    MultiSessionStore.prototype.size = function () {
        return Object.keys(this._sessions).length;
    };

    MultiSessionStore.prototype.countByStatus = function () {
        var keys = Object.keys(this._sessions);
        var stats = {
            total: keys.length,
            waiting: 0,
            active: 0,
            feedback_submitted: 0,
            completed: 0,
            expired: 0,
            timeout: 0,
            canceled: 0,
            error: 0,
            terminal: 0,
            nonTerminal: 0
        };
        for (var i = 0; i < keys.length; i++) {
            var s = this._sessions[keys[i]].status || 'waiting';
            if (stats[s] !== undefined) stats[s]++;
            if (isTerminal(s)) stats.terminal++;
            else stats.nonTerminal++;
        }
        return stats;
    };

    // --------- 寫入 API ---------

    /**
     * 應用一份完整的會話快照（來自後端 sessions_snapshot / GET /api/sessions）
     * 策略：全量替換 _sessions；保持 _activeSessionId（除非後端明確指定）
     */
    MultiSessionStore.prototype.applySnapshot = function (sessions, activeSessionId) {
        var newMap = Object.create(null);
        if (Array.isArray(sessions)) {
            for (var i = 0; i < sessions.length; i++) {
                var rec = sessions[i];
                if (rec && rec.session_id) {
                    newMap[rec.session_id] = cloneRecord(rec);
                }
            }
        }
        this._sessions = newMap;

        if (activeSessionId !== undefined && activeSessionId !== null) {
            this._activeSessionId = activeSessionId;
        } else if (this._activeSessionId && !this._sessions[this._activeSessionId]) {
            this._activeSessionId = this._pickFallbackActive();
        } else if (!this._activeSessionId) {
            this._activeSessionId = this._pickFallbackActive();
        }

        this._emit(EVENTS.SNAPSHOT_APPLIED, {
            sessions: this.getSessions(),
            active_session_id: this._activeSessionId
        });
    };

    /**
     * 新增或更新一個會話（SERVER → CLIENT 推送時用）
     */
    MultiSessionStore.prototype.upsertSession = function (record) {
        if (!record || !record.session_id) {
            logger.warn('[SessionStore] upsertSession 收到無效記錄');
            return;
        }
        var sid = record.session_id;
        var existing = this._sessions[sid];
        if (existing) {
            this._sessions[sid] = mergeRecord(existing, record);
            this._emit(EVENTS.SESSION_UPDATED, { session: cloneRecord(this._sessions[sid]), prev: existing });
        } else {
            this._sessions[sid] = cloneRecord(record);
            this._emit(EVENTS.SESSION_ADDED, { session: cloneRecord(this._sessions[sid]) });

            if (!this._activeSessionId) {
                this.setActiveSessionId(sid);
            }
        }
    };

    /**
     * 局部更新一個會話的某些字段（如狀態變化、 summary 更新）
     */
    MultiSessionStore.prototype.patchSession = function (sessionId, patch) {
        if (!sessionId) return;
        var existing = this._sessions[sessionId];
        if (!existing) {
            var seed = Object.assign({ session_id: sessionId }, patch || {});
            this.upsertSession(seed);
            return;
        }
        var merged = mergeRecord(existing, patch || {});
        this._sessions[sessionId] = merged;
        this._emit(EVENTS.SESSION_UPDATED, { session: cloneRecord(merged), prev: existing });
    };

    /**
     * 移除（歸檔）一個會話
     */
    MultiSessionStore.prototype.removeSession = function (sessionId) {
        if (!sessionId || !this._sessions[sessionId]) return;
        var removed = this._sessions[sessionId];
        delete this._sessions[sessionId];
        this._emit(EVENTS.SESSION_REMOVED, { session_id: sessionId, removed: cloneRecord(removed) });

        if (this._activeSessionId === sessionId) {
            this.setActiveSessionId(this._pickFallbackActive());
        }
    };

    /**
     * 批量移除所有終止態會話
     */
    MultiSessionStore.prototype.removeAllTerminal = function () {
        var keys = Object.keys(this._sessions);
        var removed = [];
        for (var i = 0; i < keys.length; i++) {
            var sid = keys[i];
            if (isTerminal(this._sessions[sid].status)) {
                removed.push(sid);
            }
        }
        for (var j = 0; j < removed.length; j++) {
            this.removeSession(removed[j]);
        }
        return removed;
    };

    /**
     * 切換當前 active 會話
     */
    MultiSessionStore.prototype.setActiveSessionId = function (sessionId) {
        if (this._activeSessionId === sessionId) return;
        var prev = this._activeSessionId;
        if (sessionId && !this._sessions[sessionId]) {
            logger.warn('[SessionStore] 嘗試切到不存在的 session: ' + sessionId);
            return;
        }
        this._activeSessionId = sessionId || null;
        this._emit(EVENTS.ACTIVE_CHANGED, {
            prev: prev,
            current: this._activeSessionId,
            session: this.getActiveSession()
        });
    };

    /**
     * 當 active 會話被移除後，選一個後備（優先 waiting > active > 其他 > null）
     */
    MultiSessionStore.prototype._pickFallbackActive = function () {
        var keys = Object.keys(this._sessions);
        if (keys.length === 0) return null;

        var byStatus = { waiting: [], active: [], other: [] };
        for (var i = 0; i < keys.length; i++) {
            var s = this._sessions[keys[i]].status || 'waiting';
            if (s === 'waiting') byStatus.waiting.push(keys[i]);
            else if (s === 'active') byStatus.active.push(keys[i]);
            else if (!isTerminal(s)) byStatus.other.push(keys[i]);
        }
        if (byStatus.waiting.length) return byStatus.waiting[0];
        if (byStatus.active.length)  return byStatus.active[0];
        if (byStatus.other.length)   return byStatus.other[0];

        return keys[0];
    };

    /**
     * 重置（測試/登出用）
     */
    MultiSessionStore.prototype.reset = function () {
        this._sessions = Object.create(null);
        this._activeSessionId = null;
        this._emit(EVENTS.SNAPSHOT_APPLIED, { sessions: [], active_session_id: null });
    };

    // --------- 單例 + 暴露 ---------

    var storeInstance = new MultiSessionStore();

    window.MCPFeedback.SessionStore = {
        EVENTS: EVENTS,
        isTerminal: isTerminal,
        instance: storeInstance,
        _MultiSessionStore: MultiSessionStore
    };

    window.MCPFeedback.sessionStore = storeInstance;

    logger.info('[SessionStore] MultiSessionStore initialized');
})();
