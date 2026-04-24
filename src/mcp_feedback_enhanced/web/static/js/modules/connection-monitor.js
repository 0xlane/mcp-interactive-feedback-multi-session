/**
 * MCP Feedback Enhanced - 連線監控模組
 * ===================================
 * 
 * 處理 WebSocket 連線狀態監控、品質檢測和診斷功能
 */

(function() {
    'use strict';

    // 確保命名空間和依賴存在
    window.MCPFeedback = window.MCPFeedback || {};
    const Utils = window.MCPFeedback.Utils;

    /**
     * 連線監控器建構函數
     */
    function ConnectionMonitor(options) {
        options = options || {};
        
        // 監控狀態
        this.isMonitoring = false;
        this.connectionStartTime = null;
        this.lastPingTime = null;
        this.latencyHistory = [];
        this.maxLatencyHistory = 20;
        this.reconnectCount = 0;
        this.messageCount = 0;
        
        // 連線品質指標
        this.currentLatency = 0;
        this.averageLatency = 0;
        this.connectionQuality = 'unknown'; // excellent, good, fair, poor, unknown
        
        // UI 元素
        this.statusIcon = null;
        this.statusText = null;
        this.latencyDisplay = null;
        this.connectionTimeDisplay = null;
        this.reconnectCountDisplay = null;
        this.messageCountDisplay = null;
        this.signalBars = null;
        
        // 回調函數
        this.onStatusChange = options.onStatusChange || null;
        this.onQualityChange = options.onQualityChange || null;
        
        this.initializeUI();
        
        console.log('🔍 ConnectionMonitor 初始化完成');
    }

    /**
     * 初始化 UI 元素
     */
    ConnectionMonitor.prototype.initializeUI = function() {
        // 獲取 UI 元素引用
        this.statusIcon = Utils.safeQuerySelector('.status-icon');
        this.statusText = Utils.safeQuerySelector('.status-text');
        this.latencyDisplay = Utils.safeQuerySelector('.latency-indicator');
        this.connectionTimeDisplay = Utils.safeQuerySelector('.connection-time');
        this.reconnectCountDisplay = Utils.safeQuerySelector('.reconnect-count');
        this.messageCountDisplay = Utils.safeQuerySelector('#messageCount');
        this.latencyDisplayFooter = Utils.safeQuerySelector('#latencyDisplay');
        this.signalBars = document.querySelectorAll('.signal-bar');
        
        // 初始化顯示
        this.updateDisplay();
    };

    /**
     * 開始監控
     */
    ConnectionMonitor.prototype.startMonitoring = function() {
        if (this.isMonitoring) return;

        this.isMonitoring = true;
        this.connectionStartTime = Date.now();
        this.reconnectCount = 0;
        this.messageCount = 0;
        this.latencyHistory = [];

        // 連線時間 + 會話數/狀態這些值若只靠 pong/message 觸發 updateDisplay，
        // 在空閒或心跳頻率低（60s）時卡片就會長時間定格。這裡用 1s 輕量 tick
        // 保證 UI 會持續前進；回調只寫 DOM，不發網路請求。
        this._startDisplayTicker();

        console.log('🔍 開始連線監控');
        this.updateDisplay();
    };

    /**
     * 停止監控
     */
    ConnectionMonitor.prototype.stopMonitoring = function() {
        this.isMonitoring = false;
        this.connectionStartTime = null;
        this.lastPingTime = null;
        this._stopDisplayTicker();

        console.log('🔍 停止連線監控');
        this.updateDisplay();
    };

    ConnectionMonitor.prototype._startDisplayTicker = function() {
        if (this._displayTickerId) return;
        var self = this;
        this._displayTickerId = setInterval(function() {
            if (!self.isMonitoring) return;
            self.updateDisplay();
        }, 1000);
    };

    ConnectionMonitor.prototype._stopDisplayTicker = function() {
        if (this._displayTickerId) {
            clearInterval(this._displayTickerId);
            this._displayTickerId = null;
        }
    };

    /**
     * 更新連線狀態
     */
    ConnectionMonitor.prototype.updateConnectionStatus = function(status, message) {
        console.log('🔍 連線狀態更新:', status, message);

        // 更新狀態顯示
        if (this.statusText) {
            // 使用 i18n 翻譯或提供的訊息
            const displayText = message || (window.MCPFeedback && window.MCPFeedback.Utils && window.MCPFeedback.Utils.Status ?
                window.MCPFeedback.Utils.Status.getConnectionStatusText(status) : status);
            this.statusText.textContent = displayText;
        }

        // 更新狀態圖示
        if (this.statusIcon) {
            this.statusIcon.className = 'status-icon';

            switch (status) {
                case 'connecting':
                case 'reconnecting':
                    this.statusIcon.classList.add('pulse');
                    break;
                case 'connected':
                    this.statusIcon.classList.remove('pulse');
                    break;
                default:
                    this.statusIcon.classList.remove('pulse');
            }
        }

        // 更新連線指示器樣式
        const indicator = Utils.safeQuerySelector('.connection-indicator');
        if (indicator) {
            indicator.className = 'connection-indicator ' + status;
        }
        
        // 更新精簡的頂部狀態指示器（現在是緊湊版）
        const minimalIndicator = document.getElementById('connectionStatusMinimal');
        if (minimalIndicator) {
            minimalIndicator.className = 'connection-status-compact ' + status;
            const statusText = minimalIndicator.querySelector('.status-text');
            if (statusText) {
                let statusKey = '';
                switch (status) {
                    case 'connected':
                        statusKey = 'connectionMonitor.connected';
                        break;
                    case 'connecting':
                        statusKey = 'connectionMonitor.connecting';
                        break;
                    case 'disconnected':
                        statusKey = 'connectionMonitor.disconnected';
                        break;
                    case 'reconnecting':
                        statusKey = 'connectionMonitor.reconnecting';
                        break;
                    default:
                        statusKey = 'connectionMonitor.unknown';
                }
                // 重連狀態下 i18n 模板為 "重連中... (第{attempt}次)"，呼叫方（websocket-
                // manager）已經把 {attempt} 替換好並以 message 參數傳入，這裡若還沿用
                // data-i18n 讓 i18nManager 重新翻譯會把佔位符翻回來，導致 UI 出現字面
                // 的 "{attempt}"。所以只要能拿到 message 就直接寫入並移除 data-i18n，
                // 避免下一次語言切換時被覆蓋。
                if (status === 'reconnecting' && message) {
                    statusText.removeAttribute('data-i18n');
                    statusText.textContent = message;
                } else {
                    statusText.setAttribute('data-i18n', statusKey);
                    if (window.i18nManager) {
                        statusText.textContent = window.i18nManager.t(statusKey);
                    }
                }
            }
        }
        
        // 處理特殊狀態
        switch (status) {
            case 'connected':
                if (!this.isMonitoring) {
                    this.startMonitoring();
                }
                break;
            case 'disconnected':
            case 'error':
                this.stopMonitoring();
                break;
            case 'reconnecting':
                this.reconnectCount++;
                break;
        }
        
        this.updateDisplay();
        
        // 調用回調
        if (this.onStatusChange) {
            this.onStatusChange(status, message);
        }
    };

    /**
     * 記錄 ping 時間
     */
    ConnectionMonitor.prototype.recordPing = function() {
        this.lastPingTime = Date.now();
    };

    /**
     * 記錄 pong 時間並計算延遲
     */
    ConnectionMonitor.prototype.recordPong = function() {
        if (!this.lastPingTime) return;
        
        const now = Date.now();
        const latency = now - this.lastPingTime;
        
        this.currentLatency = latency;
        this.latencyHistory.push(latency);
        
        // 保持歷史記錄在限制範圍內
        if (this.latencyHistory.length > this.maxLatencyHistory) {
            this.latencyHistory.shift();
        }
        
        // 計算平均延遲
        this.averageLatency = this.latencyHistory.reduce((sum, lat) => sum + lat, 0) / this.latencyHistory.length;
        
        // 更新連線品質
        this.updateConnectionQuality();
        
        console.log('🔍 延遲測量:', latency + 'ms', '平均:', Math.round(this.averageLatency) + 'ms');
        
        this.updateDisplay();
    };

    /**
     * 記錄訊息
     */
    ConnectionMonitor.prototype.recordMessage = function() {
        this.messageCount++;
        this.updateDisplay();
    };

    /**
     * 更新連線品質
     */
    ConnectionMonitor.prototype.updateConnectionQuality = function() {
        const avgLatency = this.averageLatency;
        let quality;
        
        if (avgLatency < 50) {
            quality = 'excellent';
        } else if (avgLatency < 100) {
            quality = 'good';
        } else if (avgLatency < 200) {
            quality = 'fair';
        } else {
            quality = 'poor';
        }
        
        if (quality !== this.connectionQuality) {
            this.connectionQuality = quality;
            this.updateSignalStrength();
            
            if (this.onQualityChange) {
                this.onQualityChange(quality, avgLatency);
            }
        }
    };

    /**
     * 更新信號強度顯示
     */
    ConnectionMonitor.prototype.updateSignalStrength = function() {
        if (!this.signalBars || this.signalBars.length === 0) return;
        
        let activeBars = 0;
        
        switch (this.connectionQuality) {
            case 'excellent':
                activeBars = 3;
                break;
            case 'good':
                activeBars = 2;
                break;
            case 'fair':
                activeBars = 1;
                break;
            case 'poor':
            default:
                activeBars = 0;
                break;
        }
        
        this.signalBars.forEach(function(bar, index) {
            if (index < activeBars) {
                bar.classList.add('active');
            } else {
                bar.classList.remove('active');
            }
        });
    };

    /**
     * 更新顯示
     *
     * Phase 3 之後舊的底部「詳細統計面板」與相關舊版指標 DOM 已移除，
     * WebSocket 指標（延遲、重連、訊息數、連線時間、會話數）改以頂部
     * 連線點的 tooltip（`title` 屬性）呈現——懸停時一次性閱覽，平時不
     * 佔用版面，也不再與側欄底部會話歷史按鈕重疊。
     */
    ConnectionMonitor.prototype.updateDisplay = function() {
        const latencyStr = this.currentLatency > 0 ? this.currentLatency + 'ms' : '--ms';

        let connectionTimeStr = '--:--';
        if (this.connectionStartTime) {
            const duration = Math.floor((Date.now() - this.connectionStartTime) / 1000);
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            connectionTimeStr = String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
        }

        const sessionsCount = (function () {
            const store = window.MCPFeedback && window.MCPFeedback.sessionStore;
            if (store && typeof store.getSessions === 'function') {
                return store.getSessions().length;
            }
            return 0;
        })();

        this._updateMinimalIndicatorTooltip({
            latency: latencyStr,
            messages: this.messageCount,
            reconnects: this.reconnectCount,
            connectionTime: connectionTimeStr,
            sessions: sessionsCount
        });
    };

    /**
     * 將指標整合成一個單行 tooltip 寫入頂部連線指示器，讓使用者 hover 時
     * 能一次看到延遲 / 訊息數 / 重連次數 / 連線時間 / 會話數。
     *
     * 之所以每次都重建整串而非只更新變動欄位，是因為 `title` 屬性本身是
     * 字串、成本極低；而且這個方法由 1s 一次的 display ticker 呼叫，頻
     * 率穩定、可避免保存舊值造成語言切換時部分欄位殘留。
     */
    ConnectionMonitor.prototype._updateMinimalIndicatorTooltip = function(data) {
        const indicator = document.getElementById('connectionStatusMinimal');
        if (!indicator) return;

        const statusText = indicator.querySelector('.status-text');
        const statusLabel = statusText ? (statusText.textContent || '').trim() : '';

        const mgr = window.i18nManager;
        const t = function (key, fallback) {
            if (mgr && typeof mgr.t === 'function') {
                const v = mgr.t(key);
                if (v && v !== key) return v;
            }
            return fallback;
        };

        const sep = ' · ';
        const labels = {
            latency: t('connectionMonitor.latency', 'Latency'),
            messages: t('connectionMonitor.metrics.messages', 'Messages'),
            reconnects: t('connectionMonitor.reconnectCount', 'Reconnects'),
            connectionTime: t('connectionMonitor.connectionTime', 'Connection Time'),
            sessions: t('connectionMonitor.metrics.sessions', 'Sessions')
        };

        const parts = [];
        if (statusLabel) parts.push(statusLabel);
        parts.push(labels.latency + ' ' + data.latency);
        parts.push(labels.messages + ' ' + data.messages);
        parts.push(labels.reconnects + ' ' + data.reconnects);
        parts.push(labels.connectionTime + ' ' + data.connectionTime);
        parts.push(labels.sessions + ' ' + data.sessions);

        indicator.setAttribute('title', parts.join(sep));
    };

    /**
     * 獲取連線統計資訊
     */
    ConnectionMonitor.prototype.getConnectionStats = function() {
        return {
            isMonitoring: this.isMonitoring,
            connectionTime: this.connectionStartTime ? Date.now() - this.connectionStartTime : 0,
            currentLatency: this.currentLatency,
            averageLatency: Math.round(this.averageLatency),
            connectionQuality: this.connectionQuality,
            reconnectCount: this.reconnectCount,
            messageCount: this.messageCount,
            latencyHistory: this.latencyHistory.slice() // 複製陣列
        };
    };

    /**
     * 重置統計
     */
    ConnectionMonitor.prototype.resetStats = function() {
        this.reconnectCount = 0;
        this.messageCount = 0;
        this.latencyHistory = [];
        this.currentLatency = 0;
        this.averageLatency = 0;
        this.connectionQuality = 'unknown';
        
        this.updateDisplay();
        this.updateSignalStrength();
        
        console.log('🔍 連線統計已重置');
    };

    /**
     * 清理資源
     */
    ConnectionMonitor.prototype.cleanup = function() {
        this.stopMonitoring();
        
        // 清理 UI 引用
        this.statusIcon = null;
        this.statusText = null;
        this.latencyDisplay = null;
        this.connectionTimeDisplay = null;
        this.reconnectCountDisplay = null;
        this.messageCountDisplay = null;
        this.signalBars = null;
        
        console.log('🔍 ConnectionMonitor 清理完成');
    };

    // 將 ConnectionMonitor 加入命名空間
    window.MCPFeedback.ConnectionMonitor = ConnectionMonitor;

    console.log('✅ ConnectionMonitor 模組載入完成');

})();
