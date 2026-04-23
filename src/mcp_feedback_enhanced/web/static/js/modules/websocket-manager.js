/**
 * MCP Feedback Enhanced - WebSocket 管理模組
 * =========================================
 * 
 * 處理 WebSocket 連接、訊息傳遞和重連邏輯
 */

(function() {
    'use strict';

    // 確保命名空間和依賴存在
    window.MCPFeedback = window.MCPFeedback || {};
    const Utils = window.MCPFeedback.Utils;

    /**
     * WebSocket 管理器建構函數
     */
    function WebSocketManager(options) {
        options = options || {};

        this.websocket = null;
        this.isConnected = false;
        this.connectionReady = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || Utils.CONSTANTS.MAX_RECONNECT_ATTEMPTS;
        this.reconnectDelay = options.reconnectDelay || Utils.CONSTANTS.DEFAULT_RECONNECT_DELAY;
        this.heartbeatInterval = null;
        this.heartbeatFrequency = options.heartbeatFrequency || Utils.CONSTANTS.DEFAULT_HEARTBEAT_FREQUENCY;

        // 事件回調
        this.onOpen = options.onOpen || null;
        this.onMessage = options.onMessage || null;
        this.onClose = options.onClose || null;
        this.onError = options.onError || null;
        this.onConnectionStatusChange = options.onConnectionStatusChange || null;

        // 標籤頁管理器引用
        this.tabManager = options.tabManager || null;

        // 連線監控器引用
        this.connectionMonitor = options.connectionMonitor || null;

        // 待處理的提交
        this.pendingSubmission = null;
        this.sessionUpdatePending = false;

        // 網路狀態檢測
        this.networkOnline = navigator.onLine;
        this.setupNetworkStatusDetection();
        
        // 會話超時計時器
        this.sessionTimeoutTimer = null;
        this.sessionTimeoutInterval = null; // 用於更新倒數顯示
        this.sessionTimeoutRemaining = 0; // 剩餘秒數
        this.sessionTimeoutSettings = {
            enabled: false,
            seconds: 3600
        };
    }

    /**
     * 建立 WebSocket 連接
     */
    WebSocketManager.prototype.connect = function() {
        if (!Utils.isWebSocketSupported()) {
            console.error('❌ 瀏覽器不支援 WebSocket');
            return;
        }

        // 確保 WebSocket URL 格式正確
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = protocol + '//' + host + '/ws';

        console.log('嘗試連接 WebSocket:', wsUrl);
        const connectingMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.connecting') : '連接中...';
        this.updateConnectionStatus('connecting', connectingMessage);

        try {
            // 如果已有連接，先關閉
            if (this.websocket) {
                this.websocket.close();
                this.websocket = null;
            }

            // 添加語言參數到 WebSocket URL
            const language = window.i18nManager ? window.i18nManager.getCurrentLanguage() : 'zh-TW';
            const wsUrlWithLang = wsUrl + (wsUrl.includes('?') ? '&' : '?') + 'lang=' + language;
            this.websocket = new WebSocket(wsUrlWithLang);
            this.setupWebSocketEvents();

        } catch (error) {
            console.error('WebSocket 連接失敗:', error);
            const connectionFailedMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.connectionFailed') : '連接失敗';
            this.updateConnectionStatus('error', connectionFailedMessage);
        }
    };

    /**
     * 設置 WebSocket 事件監聽器
     */
    WebSocketManager.prototype.setupWebSocketEvents = function() {
        const self = this;

        this.websocket.onopen = function() {
            self.handleOpen();
        };

        this.websocket.onmessage = function(event) {
            self.handleMessage(event);
        };

        this.websocket.onclose = function(event) {
            self.handleClose(event);
        };

        this.websocket.onerror = function(error) {
            self.handleError(error);
        };
    };

    /**
     * 處理連接開啟
     */
    WebSocketManager.prototype.handleOpen = function() {
        this.isConnected = true;
        this.connectionReady = false; // 等待連接確認
        const connectedMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.connected') : '已連接';
        this.updateConnectionStatus('connected', connectedMessage);
        console.log('WebSocket 連接已建立');

        // 重置重連計數器和延遲
        this.reconnectAttempts = 0;
        this.reconnectDelay = Utils.CONSTANTS.DEFAULT_RECONNECT_DELAY;

        // 通知連線監控器
        if (this.connectionMonitor) {
            this.connectionMonitor.startMonitoring();
        }

        // 開始心跳
        this.startHeartbeat();

        // 請求會話狀態
        this.requestSessionStatus();

        // 調用外部回調
        if (this.onOpen) {
            this.onOpen();
        }
    };

    /**
     * 處理訊息接收
     */
    WebSocketManager.prototype.handleMessage = function(event) {
        try {
            const data = Utils.safeJsonParse(event.data, null);
            if (data) {
                // 記錄訊息到監控器
                if (this.connectionMonitor) {
                    this.connectionMonitor.recordMessage();
                }

                this.processMessage(data);

                // 調用外部回調
                if (this.onMessage) {
                    this.onMessage(data);
                }
            }
        } catch (error) {
            console.error('解析 WebSocket 訊息失敗:', error);
        }
    };

    /**
     * 處理連接關閉
     */
    WebSocketManager.prototype.handleClose = function(event) {
        this.isConnected = false;
        this.connectionReady = false;
        console.log('WebSocket 連接已關閉, code:', event.code, 'reason:', event.reason);

        // 停止心跳
        this.stopHeartbeat();

        // 通知連線監控器
        if (this.connectionMonitor) {
            this.connectionMonitor.stopMonitoring();
        }

        // 處理不同的關閉原因
        if (event.code === 4004) {
            const noActiveSessionMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.noActiveSession') : '沒有活躍會話';
            this.updateConnectionStatus('disconnected', noActiveSessionMessage);
        } else {
            const disconnectedMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.disconnected') : '已斷開';
            this.updateConnectionStatus('disconnected', disconnectedMessage);
            this.handleReconnection(event);
        }

        // 調用外部回調
        if (this.onClose) {
            this.onClose(event);
        }
    };

    /**
     * 處理連接錯誤
     */
    WebSocketManager.prototype.handleError = function(error) {
        console.error('WebSocket 錯誤:', error);
        const connectionErrorMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.connectionError') : '連接錯誤';
        this.updateConnectionStatus('error', connectionErrorMessage);

        // 調用外部回調
        if (this.onError) {
            this.onError(error);
        }
    };

    /**
     * 處理重連邏輯
     */
    WebSocketManager.prototype.handleReconnection = function(event) {
        // 會話更新導致的正常關閉，立即重連
        if (event.code === 1000 && event.reason === '會話更新') {
            console.log('🔄 會話更新導致的連接關閉，立即重連...');
            this.sessionUpdatePending = true;
            const self = this;
            setTimeout(function() {
                self.connect();
            }, 200);
        }
        // 檢查是否應該重連
        else if (this.shouldAttemptReconnect(event)) {
            this.reconnectAttempts++;

            // 改進的指數退避算法：基礎延遲 * 2^重試次數，加上隨機抖動
            const baseDelay = Utils.CONSTANTS.DEFAULT_RECONNECT_DELAY;
            const exponentialDelay = baseDelay * Math.pow(2, this.reconnectAttempts - 1);
            const jitter = Math.random() * 1000; // 0-1秒的隨機抖動
            this.reconnectDelay = Math.min(exponentialDelay + jitter, 30000); // 最大 30 秒

            console.log(Math.round(this.reconnectDelay / 1000) + '秒後嘗試重連... (第' + this.reconnectAttempts + '次)');

            // 更新狀態為重連中
            const reconnectingTemplate = window.i18nManager ? window.i18nManager.t('connectionMonitor.reconnecting') : '重連中... (第{attempt}次)';
            const reconnectingMessage = reconnectingTemplate.replace('{attempt}', this.reconnectAttempts);
            this.updateConnectionStatus('reconnecting', reconnectingMessage);

            const self = this;
            setTimeout(function() {
                console.log('🔄 開始重連 WebSocket... (第' + self.reconnectAttempts + '次)');
                self.connect();
            }, this.reconnectDelay);
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('❌ 達到最大重連次數，停止重連');
            const maxReconnectMessage = window.i18nManager ? window.i18nManager.t('connectionMonitor.maxReconnectReached') : 'WebSocket 連接失敗，請刷新頁面重試';
            Utils.showMessage(maxReconnectMessage, Utils.CONSTANTS.MESSAGE_ERROR);
        }
    };

    /**
     * Phase 3: 將後端事件餵給多會話 Store（如果已加載）
     * 注意：此函數只更新 Store，不影響原有的 processMessage 控制流。
     */
    WebSocketManager.prototype._updateStore = function(data) {
        var store = window.MCPFeedback && window.MCPFeedback.sessionStore;
        if (!store || !data) return;

        try {
            switch (data.type) {
                case 'sessions_snapshot':
                    store.applySnapshot(
                        Array.isArray(data.sessions) ? data.sessions : [],
                        data.active_session_id || null
                    );
                    break;

                case 'session_created':
                    if (data.session && data.session.session_id) {
                        var newRec = data.session;
                        var prevActive = store.getActiveSessionId();
                        // 如果用戶當前正在看別的 session，給新 session 打上 pending
                        // 標記，讓側欄小黃點 + title 計數能正確反映「你還有新會話」。
                        if (prevActive && prevActive !== newRec.session_id) {
                            newRec = Object.assign({}, newRec, {
                                has_pending_notification: true
                            });
                        }
                        store.upsertSession(newRec);
                    }
                    break;

                case 'session_updated':
                    if (data.session && data.session.session_id) {
                        store.upsertSession(data.session);
                    } else if (data.session_info && data.session_info.session_id) {
                        // 舊前端相容路徑：reconnection 重放時也會走這條分支，
                        // 不代表使用者有新操作，因此不要把 last_activity 撥到 now，
                        // 讓側欄卡片上的相對時間保持原樣。
                        store.patchSession(data.session_info.session_id, {
                            project_directory: data.session_info.project_directory,
                            summary: data.session_info.summary,
                            status: data.session_info.status
                        });
                    } else if (data.session_id) {
                        // 只有在後端顯式帶上 last_activity 時才更新，
                        // 避免缺失欄位時把顯示重置成 0。
                        var patch = {
                            status: data.status,
                            status_message: data.status_message,
                            title: data.title
                        };
                        if (typeof data.last_activity === 'number') {
                            patch.last_activity = data.last_activity;
                        }
                        store.patchSession(data.session_id, patch);
                    }
                    break;

                case 'session_archived':
                case 'session_removed':
                    if (data.session_id) store.removeSession(data.session_id);
                    break;

                case 'session_expired':
                    if (data.session_id) {
                        // 過期本身不是使用者「操作」，沿用後端提供的 last_activity
                        // 若沒有就保持不變，避免視覺上突然變成 "0s"。
                        var expiredPatch = { status: data.status || 'expired' };
                        if (typeof data.last_activity === 'number') {
                            expiredPatch.last_activity = data.last_activity;
                        }
                        store.patchSession(data.session_id, expiredPatch);
                    }
                    break;

                case 'session_feedback_submitted':
                    if (data.session_id) {
                        // 提交回饋屬於真正的使用者操作。優先採用後端送來的
                        // last_activity（精確的提交時間），沒有就以 client now 兜底。
                        var submittedPatch = {
                            status: 'feedback_submitted',
                            feedback_completed: true
                        };
                        if (typeof data.last_activity === 'number') {
                            submittedPatch.last_activity = data.last_activity;
                        } else {
                            submittedPatch.last_activity = Date.now();
                        }
                        store.patchSession(data.session_id, submittedPatch);
                    }
                    break;

                case 'status_update':
                    if (data.status_info && data.status_info.session_id) {
                        var s = data.status_info;
                        // status_update 只是「狀態鏡像」，在 (re)connection 或
                        // get_status 主動拉取時都會重發，並不代表剛剛有操作。
                        // 不要把 last_activity 撥到 now。
                        var stPatch = {
                            status: s.status,
                            status_message: s.message || ''
                        };
                        if (typeof s.last_activity === 'number') {
                            stPatch.last_activity = s.last_activity;
                        }
                        store.patchSession(s.session_id, stPatch);
                    }
                    break;

                case 'notification':
                    if (data.session_id && store.getActiveSessionId() !== data.session_id) {
                        store.patchSession(data.session_id, {
                            has_pending_notification: true
                        });
                    }
                    break;
            }
        } catch (e) {
            console.warn('_updateStore 失敗:', e);
        }
    };

    /**
     * 處理訊息
     */
    WebSocketManager.prototype.processMessage = function(data) {
        console.log('收到 WebSocket 訊息:', data);

        this._updateStore(data);

        switch (data.type) {
            case 'connection_established':
                console.log('WebSocket 連接確認');
                this.connectionReady = true;
                this.handleConnectionReady();
                // 處理訊息代碼
                if (data.messageCode && window.i18nManager) {
                    const message = window.i18nManager.t(data.messageCode);
                    Utils.showMessage(message, Utils.CONSTANTS.MESSAGE_SUCCESS);
                }
                break;
            case 'heartbeat_response':
                this.handleHeartbeatResponse();
                // 記錄 pong 時間到監控器
                if (this.connectionMonitor) {
                    this.connectionMonitor.recordPong();
                }
                break;
            case 'ping':
                // 處理來自伺服器的 ping 消息（用於連接檢測）
                console.log('收到伺服器 ping，立即回應 pong');
                this.send({
                    type: 'pong',
                    timestamp: data.timestamp
                });
                break;
            case 'update_timeout_settings':
                // 處理超時設定更新
                if (data.settings) {
                    this.updateSessionTimeoutSettings(data.settings);
                }
                break;
            default:
                // 其他訊息類型由外部處理
                break;
        }
    };

    /**
     * 處理連接就緒
     */
    WebSocketManager.prototype.handleConnectionReady = function() {
        // 如果有待提交的內容，現在可以提交了
        if (this.pendingSubmission) {
            console.log('🔄 連接就緒，提交待處理的內容');
            const self = this;
            setTimeout(function() {
                if (self.pendingSubmission) {
                    self.send(self.pendingSubmission);
                    self.pendingSubmission = null;
                }
            }, 100);
        }
    };

    /**
     * 處理心跳回應
     */
    WebSocketManager.prototype.handleHeartbeatResponse = function() {
        if (this.tabManager) {
            this.tabManager.updateLastActivity();
        }
    };

    /**
     * 發送訊息
     */
    WebSocketManager.prototype.send = function(data) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            try {
                this.websocket.send(JSON.stringify(data));
                return true;
            } catch (error) {
                console.error('發送 WebSocket 訊息失敗:', error);
                return false;
            }
        } else {
            console.warn('WebSocket 未連接，無法發送訊息');
            return false;
        }
    };

    /**
     * 請求會話狀態
     */
    WebSocketManager.prototype.requestSessionStatus = function() {
        this.send({
            type: 'get_status'
        });
    };

    /**
     * Phase 3: 帶上指定 session_id 發送消息
     */
    WebSocketManager.prototype.sendTo = function(sessionId, data) {
        if (!data) return false;
        var payload = Object.assign({}, data);
        if (sessionId) payload.session_id = sessionId;
        return this.send(payload);
    };

    /**
     * Phase 3: 將消息發給當前 active session（從 Store 讀取）
     */
    WebSocketManager.prototype.sendToActive = function(data) {
        var store = window.MCPFeedback && window.MCPFeedback.sessionStore;
        var sid = store ? store.getActiveSessionId() : null;
        return this.sendTo(sid, data);
    };

    /**
     * Phase 3: 通過 WS 歸檔指定會話
     */
    WebSocketManager.prototype.archiveSession = function(sessionId) {
        return this.sendTo(sessionId, { type: 'archive_session' });
    };

    /**
     * Phase 3: 主動請求最新快照
     */
    WebSocketManager.prototype.requestSessionsSnapshot = function() {
        return this.send({ type: 'get_sessions_snapshot' });
    };

    /**
     * 開始心跳
     */
    WebSocketManager.prototype.startHeartbeat = function() {
        this.stopHeartbeat();

        const self = this;
        this.heartbeatInterval = setInterval(function() {
            if (self.websocket && self.websocket.readyState === WebSocket.OPEN) {
                // 記錄 ping 時間到監控器
                if (self.connectionMonitor) {
                    self.connectionMonitor.recordPing();
                }

                self.send({
                    type: 'heartbeat',
                    tabId: self.tabManager ? self.tabManager.getTabId() : null,
                    timestamp: Date.now()
                });
            }
        }, this.heartbeatFrequency);

        console.log('💓 WebSocket 心跳已啟動，頻率: ' + this.heartbeatFrequency + 'ms');
    };

    /**
     * 停止心跳
     */
    WebSocketManager.prototype.stopHeartbeat = function() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
            console.log('💔 WebSocket 心跳已停止');
        }
    };

    /**
     * 更新連接狀態
     */
    WebSocketManager.prototype.updateConnectionStatus = function(status, text) {
        if (this.onConnectionStatusChange) {
            this.onConnectionStatusChange(status, text);
        }
    };

    /**
     * 設置待處理的提交
     */
    WebSocketManager.prototype.setPendingSubmission = function(data) {
        this.pendingSubmission = data;
    };

    /**
     * 檢查是否已連接且就緒
     */
    WebSocketManager.prototype.isReady = function() {
        return this.isConnected && this.connectionReady;
    };

    /**
     * 設置網路狀態檢測
     */
    WebSocketManager.prototype.setupNetworkStatusDetection = function() {
        const self = this;

        // 監聽網路狀態變化
        window.addEventListener('online', function() {
            console.log('🌐 網路已恢復，嘗試重新連接...');
            self.networkOnline = true;

            // 如果 WebSocket 未連接且不在重連過程中，立即嘗試連接
            if (!self.isConnected && self.reconnectAttempts < self.maxReconnectAttempts) {
                // 重置重連計數器，因為網路問題已解決
                self.reconnectAttempts = 0;
                self.reconnectDelay = Utils.CONSTANTS.DEFAULT_RECONNECT_DELAY;

                setTimeout(function() {
                    self.connect();
                }, 1000); // 延遲 1 秒確保網路穩定
            }
        });

        window.addEventListener('offline', function() {
            console.log('🌐 網路已斷開');
            self.networkOnline = false;

            // 更新連接狀態
            const offlineMessage = window.i18nManager ?
                window.i18nManager.t('connectionMonitor.offline', '網路已斷開') :
                '網路已斷開';
            self.updateConnectionStatus('offline', offlineMessage);
        });
    };

    /**
     * 檢查是否應該嘗試重連
     */
    WebSocketManager.prototype.shouldAttemptReconnect = function(event) {
        // 如果網路離線，不嘗試重連
        if (!this.networkOnline) {
            console.log('🌐 網路離線，跳過重連');
            return false;
        }

        // 如果是正常關閉，不重連
        if (event.code === 1000) {
            return false;
        }

        // 如果達到最大重連次數，不重連
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            return false;
        }

        return true;
    };

    /**
     * 更新會話超時設定
     */
    WebSocketManager.prototype.updateSessionTimeoutSettings = function(settings) {
        this.sessionTimeoutSettings = settings;
        console.log('會話超時設定已更新:', settings);
        
        // 重新啟動計時器
        if (settings.enabled) {
            this.startSessionTimeout();
        } else {
            this.stopSessionTimeout();
        }
    };

    /**
     * 啟動會話超時計時器
     */
    WebSocketManager.prototype.startSessionTimeout = function() {
        // 先停止現有計時器
        this.stopSessionTimeout();
        
        if (!this.sessionTimeoutSettings.enabled) {
            return;
        }
        
        const timeoutSeconds = this.sessionTimeoutSettings.seconds;
        this.sessionTimeoutRemaining = timeoutSeconds;
        
        console.log('啟動會話超時計時器:', timeoutSeconds, '秒');
        
        // 顯示倒數計時器
        const displayElement = document.getElementById('sessionTimeoutDisplay');
        if (displayElement) {
            displayElement.style.display = '';
        }
        
        const self = this;
        
        // 更新倒數顯示
        function updateDisplay() {
            const minutes = Math.floor(self.sessionTimeoutRemaining / 60);
            const seconds = self.sessionTimeoutRemaining % 60;
            const displayText = minutes.toString().padStart(2, '0') + ':' + 
                               seconds.toString().padStart(2, '0');
            
            const timerElement = document.getElementById('sessionTimeoutTimer');
            if (timerElement) {
                timerElement.textContent = displayText;
            }
            
            // 當剩餘時間少於60秒時，改變顯示樣式
            if (self.sessionTimeoutRemaining < 60 && displayElement) {
                displayElement.classList.add('countdown-warning');
            }
        }
        
        // 立即更新一次顯示
        updateDisplay();
        
        // 每秒更新倒數
        this.sessionTimeoutInterval = setInterval(function() {
            self.sessionTimeoutRemaining--;
            updateDisplay();
            
            if (self.sessionTimeoutRemaining <= 0) {
                clearInterval(self.sessionTimeoutInterval);
                self.sessionTimeoutInterval = null;
                
                console.log('會話超時，準備關閉程序');
                
                // 發送超時通知給後端
                if (self.isConnected) {
                    self.send({
                        type: 'user_timeout',
                        timestamp: Date.now()
                    });
                }
                
                // 顯示超時訊息
                const timeoutMessage = window.i18nManager ?
                    window.i18nManager.t('sessionTimeout.triggered', '會話已超時，程序即將關閉') :
                    '會話已超時，程序即將關閉';
                Utils.showMessage(timeoutMessage, Utils.CONSTANTS.MESSAGE_WARNING);
                
                // 延遲關閉，讓用戶看到訊息
                setTimeout(function() {
                    window.close();
                }, 3000);
            }
        }, 1000);
    };

    /**
     * 停止會話超時計時器
     */
    WebSocketManager.prototype.stopSessionTimeout = function() {
        if (this.sessionTimeoutTimer) {
            clearTimeout(this.sessionTimeoutTimer);
            this.sessionTimeoutTimer = null;
        }
        
        if (this.sessionTimeoutInterval) {
            clearInterval(this.sessionTimeoutInterval);
            this.sessionTimeoutInterval = null;
        }
        
        // 隱藏倒數顯示
        const displayElement = document.getElementById('sessionTimeoutDisplay');
        if (displayElement) {
            displayElement.style.display = 'none';
            displayElement.classList.remove('countdown-warning');
        }
        
        console.log('會話超時計時器已停止');
    };

    /**
     * 重置會話超時計時器（用戶有活動時調用）
     */
    WebSocketManager.prototype.resetSessionTimeout = function() {
        if (this.sessionTimeoutSettings.enabled) {
            console.log('重置會話超時計時器');
            this.startSessionTimeout();
        }
    };

    /**
     * 關閉連接
     */
    WebSocketManager.prototype.close = function() {
        this.stopHeartbeat();
        this.stopSessionTimeout();
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        this.isConnected = false;
        this.connectionReady = false;
    };

    // 將 WebSocketManager 加入命名空間
    window.MCPFeedback.WebSocketManager = WebSocketManager;

    console.log('✅ WebSocketManager 模組載入完成');

})();
