/**
 * 國際化（i18n）模組
 * =================
 * 
 * 處理多語言支援和界面文字翻譯
 * 從後端 /api/translations 載入翻譯數據
 */

class I18nManager {
    constructor() {
        this.currentLanguage = this.getDefaultLanguage();
        this.translations = {};
        this.loadingPromise = null;
    }
    
    getDefaultLanguage() {
        // 1. 先檢查本地儲存的設定
        const savedLanguage = localStorage.getItem('language');
        if (savedLanguage && ['zh-TW', 'zh-CN', 'en'].includes(savedLanguage)) {
            console.log('🌐 使用儲存的語言設定:', savedLanguage);
            return savedLanguage;
        }
        
        // 2. 檢查瀏覽器語言
        const browserLang = navigator.language || navigator.userLanguage;
        console.log('🌐 瀏覽器語言:', browserLang);
        
        if (browserLang.startsWith('zh-TW') || browserLang.includes('Hant')) {
            console.log('🌐 偵測到繁體中文環境');
            return 'zh-TW';
        }
        if (browserLang.startsWith('zh') || browserLang.includes('Hans')) {
            console.log('🌐 偵測到簡體中文環境');
            return 'zh-CN';
        }
        if (browserLang.startsWith('en')) {
            console.log('🌐 偵測到英文環境');
            return 'en';
        }
        
        // 3. 預設使用繁體中文
        console.log('🌐 使用預設語言: zh-TW');
        return 'zh-TW';
    }

    async init() {
        console.log(`i18nManager 使用預設語言: ${this.currentLanguage}`);

        // 載入翻譯數據
        await this.loadTranslations();

        // 應用翻譯
        this.applyTranslations();

        // 設置語言選擇器
        this.setupLanguageSelectors();

        // 延遲一點再更新動態內容，確保應用程式已初始化
        setTimeout(() => {
            this.updateDynamicContent();
        }, 100);
    }

    async loadTranslations() {
        if (this.loadingPromise) {
            return this.loadingPromise;
        }

        this.loadingPromise = fetch('/api/translations')
            .then(response => response.json())
            .then(data => {
                this.translations = data;
                console.log('翻譯數據載入完成:', Object.keys(this.translations));
                
                // 檢查當前語言是否有翻譯數據
                if (!this.translations[this.currentLanguage] || Object.keys(this.translations[this.currentLanguage]).length === 0) {
                    console.warn(`當前語言 ${this.currentLanguage} 沒有翻譯數據，回退到 zh-TW`);
                    this.currentLanguage = 'zh-TW';
                }
            })
            .catch(error => {
                console.error('載入翻譯數據失敗:', error);
                // 使用最小的回退翻譯
                this.translations = this.getMinimalFallbackTranslations();
            });

        return this.loadingPromise;
    }

    getMinimalFallbackTranslations() {
        // 最小的回退翻譯，只包含關鍵項目
        return {
            'zh-TW': {
                'app': {
                    'title': 'MCP Feedback Enhanced',
                    'projectDirectory': '專案目錄'
                },
                'tabs': {
                    'feedback': '💬 回饋',
                    'summary': '📋 AI 摘要',
                    'command': '⚡ 命令',
                    'settings': '⚙️ 設定'
                },
                'buttons': {
                    'cancel': '❌ 取消',
                    'submit': '✅ 提交回饋'
                },
                'settings': {
                    'language': '語言'
                }
            }
        };
    }

    // 支援巢狀鍵值的翻譯函數，支援參數替換
    t(key, params = {}) {
        const langData = this.translations[this.currentLanguage] || {};
        let translation = this.getNestedValue(langData, key);

        // 如果沒有找到翻譯，返回預設值或鍵名
        if (!translation) {
            return typeof params === 'string' ? params : key;
        }

        // 如果 params 是字串，當作預設值處理（向後相容）
        if (typeof params === 'string') {
            return translation;
        }

        // 參數替換：將 {key} 替換為對應的值
        if (typeof params === 'object' && params !== null) {
            Object.keys(params).forEach(paramKey => {
                const placeholder = `{${paramKey}}`;
                translation = translation.replace(new RegExp(placeholder, 'g'), params[paramKey]);
            });
        }

        return translation;
    }

    getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => {
            return current && current[key] !== undefined ? current[key] : null;
        }, obj);
    }

    setLanguage(language) {
        console.log(`🔄 i18nManager.setLanguage() 被調用: ${this.currentLanguage} -> ${language}`);
        if (this.translations[language]) {
            this.currentLanguage = language;
            this.applyTranslations();

            // 更新所有語言選擇器（包括現代化版本）
            this.setupLanguageSelectors();

            // 更新 HTML lang 屬性
            document.documentElement.lang = language;

            console.log(`✅ i18nManager 語言已切換到: ${language}`);
        } else {
            console.warn(`❌ i18nManager 不支援的語言: ${language}`);
        }
    }

    applyTranslations() {
        // 翻譯所有有 data-i18n 屬性的元素
        const elements = document.querySelectorAll('[data-i18n]');
        elements.forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);
            if (translation && translation !== key) {
                element.textContent = translation;
            }
        });

        // 翻譯有 data-i18n-placeholder 屬性的元素
        const placeholderElements = document.querySelectorAll('[data-i18n-placeholder]');
        placeholderElements.forEach(element => {
            const key = element.getAttribute('data-i18n-placeholder');
            const translation = this.t(key);
            if (translation && translation !== key) {
                element.placeholder = translation;
            }
        });

        // 翻譯有 data-i18n-title 屬性的元素
        const titleElements = document.querySelectorAll('[data-i18n-title]');
        titleElements.forEach(element => {
            const key = element.getAttribute('data-i18n-title');
            const translation = this.t(key);
            if (translation && translation !== key) {
                element.title = translation;
            }
        });

        // 翻譯有 data-i18n-aria-label 屬性的元素
        const ariaLabelElements = document.querySelectorAll('[data-i18n-aria-label]');
        ariaLabelElements.forEach(element => {
            const key = element.getAttribute('data-i18n-aria-label');
            const translation = this.t(key);
            if (translation && translation !== key) {
                element.setAttribute('aria-label', translation);
            }
        });

        // 更新動態內容
        this.updateDynamicContent();

        // 更新音效選擇器翻譯
        this.updateAudioSelectTranslations();

        console.log('翻譯已應用:', this.currentLanguage);
    }

    updateDynamicContent() {
        // 只更新終端歡迎信息，不要覆蓋 AI 摘要
        this.updateTerminalWelcome();

        // 更新會話管理相關的動態內容
        this.updateSessionManagementContent();

        // 更新連線監控相關的動態內容
        this.updateConnectionMonitorContent();

        // 更新提示詞按鈕文字
        this.updatePromptInputButtons();

        // 更新應用程式中的動態狀態文字（使用新的模組化架構）
        if (window.feedbackApp && window.feedbackApp.isInitialized) {
            // 更新 UI 狀態
            if (window.feedbackApp.uiManager && typeof window.feedbackApp.uiManager.updateUIState === 'function') {
                window.feedbackApp.uiManager.updateUIState();
            }

            if (window.feedbackApp.uiManager && typeof window.feedbackApp.uiManager.updateStatusIndicator === 'function') {
                window.feedbackApp.uiManager.updateStatusIndicator();
            }

            if (typeof window.feedbackApp.refreshI18nDynamicContent === 'function') {
                window.feedbackApp.refreshI18nDynamicContent();
            }

            // 會話側欄中動態產生的卡片文字（預設標題 / aria-label / 狀態標籤）
            // 在切換語言後需要強制重繪
            if (window.feedbackApp.sessionSidebar &&
                typeof window.feedbackApp.sessionSidebar.render === 'function') {
                window.feedbackApp.sessionSidebar.render();
            }
        }
    }

    updateTerminalWelcome() {
        const commandOutput = document.getElementById('commandOutput');
        if (commandOutput && window.feedbackApp && window.feedbackApp.isInitialized) {
            const welcomeTemplate = this.t('dynamic.terminalWelcome');
            if (welcomeTemplate && welcomeTemplate !== 'dynamic.terminalWelcome') {
                // 使用 currentSessionId 而不是 sessionId
                const sessionId = window.feedbackApp.currentSessionId || window.feedbackApp.sessionId || 'unknown';
                const welcomeMessage = welcomeTemplate.replace('{sessionId}', sessionId);
                commandOutput.textContent = welcomeMessage;
            }
        }
    }

    updateSessionManagementContent() {
        // 更新會話管理面板中的動態文字
        if (window.feedbackApp && window.feedbackApp.sessionManager) {
            // 觸發會話管理器重新渲染，這會使用最新的翻譯
            if (typeof window.feedbackApp.sessionManager.updateDisplay === 'function') {
                window.feedbackApp.sessionManager.updateDisplay();
            }

            // 重新渲染統計資訊以更新時間單位
            if (window.feedbackApp.sessionManager.dataManager &&
                window.feedbackApp.sessionManager.uiRenderer) {
                const renderer = window.feedbackApp.sessionManager.uiRenderer;

                // 語言切換時需要清除渲染快取，否則 renderSessionHistory / renderStats 會因
                // 「資料長度 / 內容未變」而跳過重繪，導致時間單位等 i18n 文本沒有更新
                if (renderer.lastRenderedData) {
                    renderer.lastRenderedData.stats = null;
                    renderer.lastRenderedData.historyLength = -1;
                    renderer.lastRenderedData.currentSessionId = null;
                }

                const stats = window.feedbackApp.sessionManager.dataManager.getStats();
                renderer.renderStats(stats);
                console.log('🌐 已更新統計資訊的語言顯示');

                // 重新渲染會話歷史以更新所有動態創建的元素
                const sessionHistory = window.feedbackApp.sessionManager.dataManager.getSessionHistory();
                renderer.renderSessionHistory(sessionHistory);
                console.log('🌐 已更新會話歷史的語言顯示');

                // 重新渲染當前會話卡片（時間單位 / 狀態徽章）
                const currentSession = window.feedbackApp.sessionManager.dataManager.getCurrentSession
                    ? window.feedbackApp.sessionManager.dataManager.getCurrentSession()
                    : null;
                if (currentSession && typeof renderer.renderCurrentSession === 'function') {
                    renderer.renderCurrentSession(currentSession);
                    console.log('🌐 已更新當前會話卡片的語言顯示');
                }
            }
        }

        // 更新狀態徽章文字
        const statusBadges = document.querySelectorAll('.status-badge');
        statusBadges.forEach(badge => {
            const statusClass = Array.from(badge.classList).find(cls =>
                ['waiting', 'active', 'completed', 'error', 'connecting', 'connected', 'disconnected'].includes(cls)
            );
            if (statusClass && window.MCPFeedback && window.MCPFeedback.Utils && window.MCPFeedback.Utils.Status) {
                badge.textContent = window.MCPFeedback.Utils.Status.getStatusText(statusClass);
            }
        });
    }

    updateConnectionMonitorContent() {
        // 更新連線監控器中的動態文字
        if (window.feedbackApp && window.feedbackApp.connectionMonitor) {
            // 觸發連線監控器重新更新顯示
            if (typeof window.feedbackApp.connectionMonitor.updateDisplay === 'function') {
                window.feedbackApp.connectionMonitor.updateDisplay();
            }
        }

        // 更新連線狀態文字
        const statusText = document.querySelector('.status-text');
        if (statusText && window.MCPFeedback && window.MCPFeedback.Utils && window.MCPFeedback.Utils.Status) {
            // 從元素的類名或數據屬性中獲取狀態
            const indicator = statusText.closest('.connection-indicator');
            if (indicator) {
                const statusClass = Array.from(indicator.classList).find(cls =>
                    ['connecting', 'connected', 'disconnected', 'reconnecting'].includes(cls)
                );
                if (statusClass) {
                    statusText.textContent = window.MCPFeedback.Utils.Status.getConnectionStatusText(statusClass);
                }
            }
        }
    }

    updatePromptInputButtons() {
        // 更新提示詞輸入按鈕的文字和狀態
        if (window.feedbackApp && window.feedbackApp.promptInputButtons) {
            // 觸發提示詞按鈕更新文字
            if (typeof window.feedbackApp.promptInputButtons.updateButtonTexts === 'function') {
                window.feedbackApp.promptInputButtons.updateButtonTexts();
            }
            // 觸發提示詞按鈕更新狀態（包括 tooltip）
            if (typeof window.feedbackApp.promptInputButtons.updateButtonStates === 'function') {
                window.feedbackApp.promptInputButtons.updateButtonStates();
            }
        }
    }

    setupLanguageSelectors() {
        // 設定頁籤的下拉選擇器
        const selector = document.getElementById('settingsLanguageSelect');
        if (selector) {
            // 只設置當前值，不綁定事件（讓 SettingsManager 統一處理）
            selector.value = this.currentLanguage;
            console.log(`🔧 setupLanguageSelectors: 設置 select.value = ${this.currentLanguage}`);
            
            // 不再綁定事件監聽器，避免與 SettingsManager 衝突
            // 事件處理完全交由 SettingsManager 負責
        }

        // 新版現代化語言選擇器
        const languageOptions = document.querySelectorAll('.language-option');
        if (languageOptions.length > 0) {
            // 只設置當前語言的活躍狀態，不綁定事件
            languageOptions.forEach(option => {
                const lang = option.getAttribute('data-lang');
                if (lang === this.currentLanguage) {
                    option.classList.add('active');
                } else {
                    option.classList.remove('active');
                }
            });
            // 事件監聽器由 SettingsManager 統一處理，避免重複綁定
        }
    }

    updateAudioSelectTranslations() {
        // 更新音效設定區域的所有翻譯
        if (window.feedbackApp && window.feedbackApp.audioSettingsUI) {
            if (typeof window.feedbackApp.audioSettingsUI.updateTranslations === 'function') {
                window.feedbackApp.audioSettingsUI.updateTranslations();
            }
        }
    }

    getCurrentLanguage() {
        return this.currentLanguage;
    }

    getAvailableLanguages() {
        return Object.keys(this.translations);
    }
}

// 創建全域實例
window.i18nManager = new I18nManager(); 