/**
 * MCP Feedback Enhanced - 會話詳情彈窗模組
 * =======================================
 * 
 * 負責會話詳情彈窗的創建、顯示和管理
 */

(function() {
    'use strict';

    // 確保命名空間存在
    window.MCPFeedback = window.MCPFeedback || {};
    window.MCPFeedback.Session = window.MCPFeedback.Session || {};

    const DOMUtils = window.MCPFeedback.Utils.DOM;
    const TimeUtils = window.MCPFeedback.Utils.Time;
    const StatusUtils = window.MCPFeedback.Utils.Status;

    /**
     * 會話詳情彈窗管理器
     */
    function SessionDetailsModal(options) {
        options = options || {};

        // 彈窗選項
        this.enableEscapeClose = options.enableEscapeClose !== false;
        this.enableBackdropClose = options.enableBackdropClose !== false;
        this.showFullSessionId = options.showFullSessionId || false;

        // 當前彈窗引用
        this.currentModal = null;
        this.keydownHandler = null;

        // console.log('🔍 SessionDetailsModal 初始化完成');
    }

    /**
     * 顯示會話詳情
     */
    SessionDetailsModal.prototype.showSessionDetails = function(sessionData) {
        if (!sessionData) {
            this.showError('沒有可顯示的會話數據');
            return;
        }

        // console.log('🔍 顯示會話詳情:', sessionData.session_id);

        // 存储当前会话数据，供复制功能使用
        this.currentSessionData = sessionData;

        // 關閉現有彈窗
        this.closeModal();

        // 格式化會話詳情
        const details = this.formatSessionDetails(sessionData);

        // 創建並顯示彈窗
        this.createAndShowModal(details);
    };

    /**
     * 格式化會話詳情
     */
    SessionDetailsModal.prototype.formatSessionDetails = function(sessionData) {
        // console.log('🔍 格式化會話詳情:', sessionData);

        const unknownText = window.i18nManager
            ? window.i18nManager.t('sessionManagement.sessionDetails.unknown')
            : '未知';
        const inProgressText = window.i18nManager
            ? window.i18nManager.t('sessionManagement.sessionDetails.inProgress')
            : '進行中';
        const inProgressSuffixText = window.i18nManager
            ? window.i18nManager.t('sessionManagement.sessionDetails.inProgressSuffix')
            : '(進行中)';

        const sessionId = sessionData.session_id || unknownText;

        const createdTime = sessionData.created_at ?
            TimeUtils.formatTimestamp(sessionData.created_at) :
            unknownText;

        let duration = inProgressText;
        if (sessionData.duration && sessionData.duration > 0) {
            duration = TimeUtils.formatDuration(sessionData.duration);
        } else if (sessionData.created_at && sessionData.completed_at) {
            const durationSeconds = sessionData.completed_at - sessionData.created_at;
            duration = TimeUtils.formatDuration(durationSeconds);
        } else if (sessionData.created_at && sessionData.last_activity) {
            var terminalStatuses = ['completed', 'timeout', 'error', 'expired', 'closed'];
            var isTerminal = terminalStatuses.indexOf(sessionData.status) !== -1;
            if (isTerminal) {
                var normalize = function(ts) { return ts > 1e12 ? ts / 1000 : ts; };
                var created = normalize(sessionData.created_at);
                var lastAct = normalize(sessionData.last_activity);
                var diff = lastAct - created;
                if (diff > 0) {
                    duration = TimeUtils.formatDuration(diff);
                }
            } else {
                var elapsed = TimeUtils.calculateElapsedTime(sessionData.created_at);
                if (elapsed > 0) {
                    duration = TimeUtils.formatDuration(elapsed) + ' ' + inProgressSuffixText;
                }
            }
        } else if (sessionData.created_at) {
            const elapsed = TimeUtils.calculateElapsedTime(sessionData.created_at);
            if (elapsed > 0) {
                duration = TimeUtils.formatDuration(elapsed) + ' ' + inProgressSuffixText;
            }
        }

        // 處理狀態
        const status = sessionData.status || 'waiting';
        const statusText = StatusUtils.getStatusText(status);
        const statusColor = StatusUtils.getStatusColor(status);

        // 處理用戶訊息記錄
        const userMessages = sessionData.user_messages || [];
        const userMessageCount = userMessages.length;

        const aiSummaries = sessionData.ai_summaries || [];

        return {
            sessionId: sessionId,
            status: statusText,
            statusColor: statusColor,
            createdTime: createdTime,
            duration: duration,
            projectDirectory: sessionData.project_directory || (window.i18nManager ? window.i18nManager.t('sessionManagement.sessionDetails.unknown') : '未知'),
            summary: sessionData.summary || (window.i18nManager ? window.i18nManager.t('sessionManagement.sessionDetails.noSummary') : '暫無摘要'),
            aiSummaries: aiSummaries,
            userMessages: userMessages,
            userMessageCount: userMessageCount
        };
    };

    /**
     * 創建並顯示彈窗
     */
    SessionDetailsModal.prototype.createAndShowModal = function(details) {
        // 創建彈窗 HTML
        const modalHtml = this.createModalHTML(details);

        // 插入到頁面中
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // 獲取彈窗元素
        this.currentModal = document.getElementById('sessionDetailsModal');

        // 設置事件監聽器
        this.setupEventListeners();

        // 添加顯示動畫
        this.showModal();
    };

    /**
     * 創建彈窗 HTML
     */
    SessionDetailsModal.prototype.createModalHTML = function(details) {
        const i18n = window.i18nManager;
        const title = i18n ? i18n.t('sessionManagement.sessionDetails.title') : '會話詳細資訊';
        const closeLabel = i18n ? i18n.t('sessionManagement.sessionDetails.close') : '關閉';
        const sessionIdLabel = i18n ? i18n.t('sessionManagement.sessionId') : '會話 ID';
        const statusLabel = i18n ? i18n.t('sessionManagement.status') : '狀態';

        return `
            <div class="session-details-modal" id="sessionDetailsModal">
                <div class="modal-backdrop"></div>
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>${title}</h3>
                        <button class="modal-close" id="closeSessionDetails" aria-label="${closeLabel}">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="detail-row">
                            <span class="detail-label">${sessionIdLabel}:</span>
                            <span class="detail-value session-id" title="${details.sessionId}">${details.sessionId}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">${statusLabel}:</span>
                            <span class="detail-value" style="color: ${details.statusColor};">${details.status}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">${i18n ? i18n.t('sessionManagement.createdTime') : '建立時間'}:</span>
                            <span class="detail-value">${details.createdTime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">${i18n ? i18n.t('sessionManagement.sessionDetails.duration') : '持續時間'}:</span>
                            <span class="detail-value">${details.duration}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">${i18n ? i18n.t('sessionManagement.sessionDetails.projectDirectory') : '專案目錄'}:</span>
                            <span class="detail-value project-path" title="${details.projectDirectory}">${details.projectDirectory}</span>
                        </div>
                        ${this.createConversationTimeline(details)}
                    </div>
                    <div class="modal-footer">
                        <button class="btn-secondary" id="closeSessionDetailsBtn">${closeLabel}</button>
                    </div>
                </div>
            </div>
        `;
    };

    /**
     * 創建對話時間線（AI 摘要 + 用戶訊息按時間排序合併）
     */
    SessionDetailsModal.prototype.createConversationTimeline = function(details) {
        const i18n = window.i18nManager;
        const aiSummaries = details.aiSummaries || [];
        const userMessages = details.userMessages || [];

        if (aiSummaries.length <= 1 && userMessages.length === 0) {
            const sectionLabel = i18n ? i18n.t('sessionManagement.aiSummary') : 'AI 摘要';
            return `
                <div class="detail-row">
                    <span class="detail-label">${sectionLabel}:</span>
                    <div class="detail-value summary">
                        <div class="summary-actions">
                            <button class="btn-copy-summary" title="複製摘要" aria-label="複製摘要">📋</button>
                        </div>
                        <div class="summary-content">${this.renderMarkdownSafely(details.summary)}</div>
                    </div>
                </div>
            `;
        }

        var timeline = [];

        aiSummaries.forEach(function(item) {
            timeline.push({
                type: 'ai',
                timestamp: (item.timestamp || 0) * 1000,
                content: item.summary || ''
            });
        });

        userMessages.forEach(function(msg) {
            timeline.push({
                type: 'user',
                timestamp: msg.timestamp || 0,
                content: msg.content,
                contentLength: msg.content_length,
                imageCount: msg.image_count || (msg.images ? msg.images.length : 0),
                images: msg.images,
                submissionMethod: msg.submission_method,
                privacyNote: msg.privacy_note
            });
        });

        timeline.sort(function(a, b) { return a.timestamp - b.timestamp; });

        const self = this;
        let timelineHtml = '';
        timeline.forEach(function(entry, index) {
            const ts = entry.timestamp ? TimeUtils.formatTimestamp(entry.timestamp) : '';
            if (entry.type === 'ai') {
                const roleLabel = 'AI';
                timelineHtml += `
                    <div class="timeline-item timeline-ai" data-index="${index}">
                        <div class="message-header">
                            <span class="timeline-role timeline-role-ai">${roleLabel}</span>
                            <span class="message-time">${ts}</span>
                            <button class="btn-copy-message" title="複製" aria-label="複製" data-message-content="${self.escapeHtml(entry.content)}">📋</button>
                        </div>
                        <div class="summary-content">${self.renderMarkdownSafely(entry.content)}</div>
                    </div>
                `;
            } else {
                const roleLabel = i18n ? i18n.t('sessionManagement.userLabel') : '用户';
                const methodLabel = entry.submissionMethod === 'auto'
                    ? (i18n ? i18n.t('sessionHistory.userMessages.auto') : '自動提交')
                    : (i18n ? i18n.t('sessionHistory.userMessages.manual') : '手動提交');

                let contentHtml = '';
                if (entry.content !== undefined && entry.content !== null) {
                    contentHtml = `<div class="message-content">${self.escapeHtml(entry.content)}</div>`;
                    if (entry.imageCount > 0) {
                        contentHtml += `<div class="message-images"><em>${entry.imageCount} 張圖片</em></div>`;
                    }
                } else if (entry.contentLength !== undefined) {
                    contentHtml = `<div class="message-stats">${entry.contentLength} 字元${entry.imageCount ? '，' + entry.imageCount + ' 張圖片' : ''}</div>`;
                } else if (entry.privacyNote) {
                    contentHtml = `<div class="message-privacy"><em style="color: var(--text-secondary);">內容記錄已停用（隱私設定）</em></div>`;
                }

                timelineHtml += `
                    <div class="timeline-item timeline-user" data-index="${index}">
                        <div class="message-header">
                            <span class="timeline-role timeline-role-user">${roleLabel}</span>
                            <span class="message-time">${ts}</span>
                            <span class="message-method">${methodLabel}</span>
                            ${entry.content !== undefined && entry.content !== null ? '<button class="btn-copy-message" title="複製" aria-label="複製" data-message-content="' + self.escapeHtml(entry.content) + '">📋</button>' : ''}
                        </div>
                        ${contentHtml}
                    </div>
                `;
            }
        });

        const sectionTitle = i18n ? i18n.t('sessionManagement.conversationTimeline') : '反馈记录';
        const totalCount = timeline.length;

        return `
            <div class="detail-row conversation-timeline-section">
                <span class="detail-label">${sectionTitle}:</span>
                <div class="detail-value">
                    <div class="summary-actions">
                        <button class="btn-copy-summary" title="${i18n ? i18n.t('sessionManagement.sessionDetails.copyAll') || '复制全部' : '复制全部'}" aria-label="复制全部">📋 ${i18n ? i18n.t('sessionManagement.sessionDetails.copyAll') || '复制全部' : '复制全部'}</button>
                    </div>
                    <div class="user-messages-summary">
                        <strong>${i18n ? i18n.t('sessionManagement.timelineSummary', { total: totalCount, ai: aiSummaries.length, user: userMessages.length }) : '共 ' + totalCount + ' 条记录（AI ' + aiSummaries.length + ' / 用户 ' + userMessages.length + '）'}</strong>
                    </div>
                    <div class="conversation-timeline">
                        ${timelineHtml}
                    </div>
                </div>
            </div>
        `;
    };

    /**
     * 設置事件監聽器
     */
    SessionDetailsModal.prototype.setupEventListeners = function() {
        if (!this.currentModal) return;

        const self = this;

        // 關閉按鈕
        const closeBtn = this.currentModal.querySelector('#closeSessionDetails');
        const closeFooterBtn = this.currentModal.querySelector('#closeSessionDetailsBtn');

        if (closeBtn) {
            DOMUtils.addEventListener(closeBtn, 'click', function() {
                self.closeModal();
            });
        }

        if (closeFooterBtn) {
            DOMUtils.addEventListener(closeFooterBtn, 'click', function() {
                self.closeModal();
            });
        }

        // 背景點擊關閉
        if (this.enableBackdropClose) {
            const backdrop = this.currentModal.querySelector('.modal-backdrop');
            if (backdrop) {
                DOMUtils.addEventListener(backdrop, 'click', function() {
                    self.closeModal();
                });
            }
        }

        // ESC 鍵關閉
        if (this.enableEscapeClose) {
            this.keydownHandler = function(e) {
                if (e.key === 'Escape') {
                    self.closeModal();
                }
            };
            document.addEventListener('keydown', this.keydownHandler);
        }

        // 复制摘要按钮
        const copyBtn = this.currentModal.querySelector('.btn-copy-summary');
        if (copyBtn) {
            DOMUtils.addEventListener(copyBtn, 'click', function() {
                self.copySummaryToClipboard();
            });
        }

        // 复制用户消息按钮
        const copyMessageBtns = this.currentModal.querySelectorAll('.btn-copy-message');
        copyMessageBtns.forEach(function(btn) {
            DOMUtils.addEventListener(btn, 'click', function(e) {
                e.stopPropagation(); // 防止事件冒泡
                const messageContent = btn.getAttribute('data-message-content');
                self.copyMessageToClipboard(messageContent);
            });
        });
    };

    /**
     * 顯示彈窗動畫
     */
    SessionDetailsModal.prototype.showModal = function() {
        if (!this.currentModal) return;

        // 彈窗已經通過 CSS 動畫自動顯示，無需額外處理
        // console.log('🔍 會話詳情彈窗已顯示');
    };

    /**
     * 關閉彈窗
     */
    SessionDetailsModal.prototype.closeModal = function() {
        if (!this.currentModal) return;

        // 移除鍵盤事件監聽器
        if (this.keydownHandler) {
            document.removeEventListener('keydown', this.keydownHandler);
            this.keydownHandler = null;
        }

        // 立即移除元素，無延遲
        DOMUtils.safeRemoveElement(this.currentModal);
        this.currentModal = null;
    };

    /**
     * 顯示錯誤訊息
     */
    SessionDetailsModal.prototype.showError = function(message) {
        if (window.MCPFeedback && window.MCPFeedback.Utils && window.MCPFeedback.Utils.showMessage) {
            window.MCPFeedback.Utils.showMessage(message, 'error');
        } else {
            alert(message);
        }
    };

    /**
     * HTML 轉義
     */
    SessionDetailsModal.prototype.escapeHtml = function(text) {
        if (!text) return '';

        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    /**
     * 安全地渲染 Markdown 內容
     */
    SessionDetailsModal.prototype.renderMarkdownSafely = function(content) {
        if (!content) return '';

        try {
            // 檢查 marked 和 DOMPurify 是否可用
            if (typeof window.marked === 'undefined' || typeof window.DOMPurify === 'undefined') {
                console.warn('⚠️ Markdown 庫未載入，使用純文字顯示');
                return this.escapeHtml(content);
            }

            // 使用 marked 解析 Markdown
            const htmlContent = window.marked.parse(content);

            // 使用 DOMPurify 清理 HTML
            const cleanHtml = window.DOMPurify.sanitize(htmlContent, {
                ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote', 'a', 'hr', 'del', 's', 'table', 'thead', 'tbody', 'tr', 'td', 'th'],
                ALLOWED_ATTR: ['href', 'title', 'class', 'align', 'style'],
                ALLOW_DATA_ATTR: false
            });

            return cleanHtml;
        } catch (error) {
            console.error('❌ Markdown 渲染失敗:', error);
            return this.escapeHtml(content);
        }
    };

    /**
     * 傳統複製文字到剪貼板的方法
     */
    SessionDetailsModal.prototype.fallbackCopyTextToClipboard = function(text, successMessage) {
        const self = this;
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        try {
            const successful = document.execCommand('copy');
            if (successful) {
                // console.log('✅ 內容已複製到剪貼板（傳統方法）');
                self.showToast(successMessage, 'success');
            } else {
                console.error('❌ 複製失敗（傳統方法）');
                self.showToast('❌ 複製失敗，請手動複製', 'error');
            }
        } catch (err) {
            console.error('❌ 複製失敗:', err);
            self.showToast('❌ 複製失敗，請手動複製', 'error');
        } finally {
            document.body.removeChild(textArea);
        }
    };

    /**
     * 複製摘要內容到剪貼板
     */
    SessionDetailsModal.prototype.copySummaryToClipboard = function() {
        const self = this;

        try {
            const sd = this.currentSessionData;
            if (!sd) {
                console.warn('⚠️ 沒有會話數據可複製');
                return;
            }

            const aiSummaries = sd.ai_summaries || [];
            const userMessages = sd.user_messages || [];
            let summaryContent = '';

            if (aiSummaries.length > 1 || userMessages.length > 0) {
                var timeline = [];
                aiSummaries.forEach(function(item) {
                    timeline.push({ type: 'ai', timestamp: (item.timestamp || 0) * 1000, content: item.summary || '' });
                });
                userMessages.forEach(function(msg) {
                    timeline.push({ type: 'user', timestamp: msg.timestamp || 0, content: msg.content || '' });
                });
                timeline.sort(function(a, b) { return a.timestamp - b.timestamp; });

                var i18n = window.i18nManager;
                var userLabel = i18n ? i18n.t('sessionManagement.userLabel') : '用户';
                summaryContent = timeline.map(function(entry) {
                    const ts = entry.timestamp ? TimeUtils.formatTimestamp(entry.timestamp) : '';
                    const role = entry.type === 'ai' ? 'AI' : userLabel;
                    return '### ' + role + (ts ? ' (' + ts + ')' : '') + '\n\n' + entry.content;
                }).join('\n\n---\n\n');
            } else {
                summaryContent = sd.summary || '';
            }

            if (!summaryContent) {
                console.warn('⚠️ 沒有內容可複製');
                return;
            }

            // 使用現代 Clipboard API
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(summaryContent).then(function() {
                    // console.log('✅ 摘要內容已複製到剪貼板');
                    self.showToast('✅ 摘要已複製到剪貼板', 'success');
                }).catch(function(err) {
                    console.error('❌ 複製失敗:', err);
                    // 降級到傳統方法
                    self.fallbackCopyTextToClipboard(summaryContent, '✅ 摘要已複製到剪貼板');
                });
            } else {
                // 降級到傳統方法
                this.fallbackCopyTextToClipboard(summaryContent, '✅ 摘要已複製到剪貼板');
            }
        } catch (error) {
            console.error('❌ 複製摘要時發生錯誤:', error);
            this.showToast('❌ 複製失敗，請手動複製', 'error');
        }
    };

    /**
     * 複製用戶消息內容到剪貼板
     */
    SessionDetailsModal.prototype.copyMessageToClipboard = function(messageContent) {
        if (!messageContent) {
            console.warn('⚠️ 沒有消息內容可複製');
            return;
        }

        const self = this;

        try {
            // 使用現代 Clipboard API
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(messageContent).then(function() {
                    // console.log('✅ 用戶消息已複製到剪貼板');
                    self.showToast('✅ 消息已複製到剪貼板', 'success');
                }).catch(function(err) {
                    console.error('❌ 複製失敗:', err);
                    // 降級到傳統方法
                    self.fallbackCopyTextToClipboard(messageContent, '✅ 消息已複製到剪貼板');
                });
            } else {
                // 降級到傳統方法
                this.fallbackCopyTextToClipboard(messageContent, '✅ 消息已複製到剪貼板');
            }
        } catch (error) {
            console.error('❌ 複製用戶消息時發生錯誤:', error);
            this.showToast('❌ 複製失敗，請手動複製', 'error');
        }
    };



    /**
     * 顯示提示消息
     */
    SessionDetailsModal.prototype.showToast = function(message, type) {
        // 創建提示元素
        const toast = document.createElement('div');
        toast.className = 'copy-toast copy-toast-' + type;
        toast.textContent = message;

        // 添加到彈窗中
        if (this.currentModal) {
            this.currentModal.appendChild(toast);

            // 顯示動畫
            setTimeout(function() {
                toast.classList.add('show');
            }, 10);

            // 自動隱藏
            setTimeout(function() {
                toast.classList.remove('show');
                setTimeout(function() {
                    if (toast.parentNode) {
                        toast.parentNode.removeChild(toast);
                    }
                }, 300);
            }, 2000);
        }
    };

    /**
     * 檢查是否有彈窗開啟
     */
    SessionDetailsModal.prototype.isModalOpen = function() {
        return this.currentModal !== null;
    };

    /**
     * 強制關閉所有彈窗
     */
    SessionDetailsModal.prototype.forceCloseAll = function() {
        // 關閉當前彈窗
        this.closeModal();

        // 清理可能遺留的彈窗元素
        const existingModals = document.querySelectorAll('.session-details-modal');
        existingModals.forEach(modal => {
            DOMUtils.safeRemoveElement(modal);
        });

        // 清理事件監聽器
        if (this.keydownHandler) {
            document.removeEventListener('keydown', this.keydownHandler);
            this.keydownHandler = null;
        }

        this.currentModal = null;
    };

    /**
     * 清理資源
     */
    SessionDetailsModal.prototype.cleanup = function() {
        this.forceCloseAll();
        // console.log('🔍 SessionDetailsModal 清理完成');
    };

    // 將 SessionDetailsModal 加入命名空間
    window.MCPFeedback.Session.DetailsModal = SessionDetailsModal;

    // console.log('✅ SessionDetailsModal 模組載入完成');

})();
