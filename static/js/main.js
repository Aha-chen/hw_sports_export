const i18n = {
    zh: {
        title_huawei: '华为',
        title_to: '至',
        title_strava: 'Strava',
        subtitle: '将华为运动健康导出的压缩包无缝转换为包含完整心率、步频和海拔数据的 Strava 标准 TCX 文件。',
        upload_label: '上传运动数据',
        upload_prompt: '点击上传或将文件拖拽到这里',
        upload_hint: 'HUAWEI_HEALTH_xxxx.zip (最大 2GB)',
        pwd_label: '解压密码',
        pwd_hint: '华为导出时提供的密码',
        pwd_placeholder: '请输入解压密码',
        start_date: '开始日期',
        end_date: '截止日期',
        optional: '(可选)',
        btn_process: '解析并生成 TCX',
        btn_loading: '数据解析中...',
        error_title: '处理失败',
        no_activities: '没有找到可转换的 Activities。请确认 ZIP 文件来自华为运动健康，并检查解压密码是否正确。',
        date_range_error: '截止日期必须大于或等于开始日期。',
        invalid_date_error: '日期格式无效，请重新选择日期。',
        success_desc: '您的 TCX 文件已准备就绪！它们包含了精确的 GPS 坐标、心率曲线和步频数据，可以直接导入 Strava。',
        btn_download: '下载 ZIP 压缩包',
        btn_clear: '清除',
        results_title: '已解析的运动记录',
        results_total: '条记录',
        btn_process_another: '处理另一个文件',
        footer: '基于现代 Web 技术与精准的 TCX 生成引擎。所有数据仅在本地处理。',
        prev: '上一页',
        next: '下一页',
        detail_title: '运动详情',
        dist: '距离',
        time: '时长',
        avg_hr: '平均心率',
        avg_cad: '平均步频',
        cal: '卡路里',
        close: '关闭',
        track: '轨迹概览',
        strava_connect: '连接 Strava',
        strava_connected_as: '已连接：',
        strava_disconnect: '断开连接',
        strava_upload_btn: '上传至 Strava',
        strava_uploading: '正在上传',
        strava_status_success: '已上传',
        strava_status_duplicate: '活动已存在',
        strava_status_error: '上传失败',
        strava_status_processing: '处理中...',
        strava_expired: '会话已过期，请重新解析数据',
        strava_reconnect: '连接已断开，请重新连接 Strava',
        strava_rate_limit: '请求频率受限，请稍后再试'
    },
    en: {
        title_huawei: 'Huawei',
        title_to: 'to',
        title_strava: 'Strava',
        subtitle: 'Seamlessly convert Huawei Health exports into rich, Strava-ready TCX files with full heart rate and cadence support.',
        upload_label: 'Archive Upload',
        upload_prompt: 'Click to upload or drag and drop',
        upload_hint: 'HUAWEI_HEALTH_xxxx.zip (Max 2GB)',
        pwd_label: 'Extraction Password',
        pwd_hint: 'Required for Huawei Zip',
        pwd_placeholder: 'Enter decryption password',
        start_date: 'Start Date',
        end_date: 'End Date',
        optional: '(Optional)',
        btn_process: 'Process & Generate TCX',
        btn_loading: 'Extracting Data...',
        error_title: 'Processing Failed',
        no_activities: 'No convertible Activities were found. Check that the ZIP came from Huawei Health and that the extraction password is correct.',
        date_range_error: 'The end date must be on or after the start date.',
        invalid_date_error: 'Invalid date format. Please select the date again.',
        success_desc: 'Your TCX files are ready for Strava. They contain precise timestamps, GPS coordinates, heart rate, and cadence data.',
        btn_download: 'Download Export ZIP',
        btn_clear: 'Clear',
        results_title: 'Processed Activities',
        results_total: 'total',
        btn_process_another: 'Process another file',
        footer: 'Powered by modern web tech & precise TCX generation. Your data is processed locally.',
        prev: 'Prev',
        next: 'Next',
        detail_title: 'Activity Details',
        dist: 'Distance',
        time: 'Duration',
        avg_hr: 'Avg HR',
        avg_cad: 'Avg Cadence',
        cal: 'Calories',
        close: 'Close',
        track: 'Track Overview',
        strava_connect: 'Connect with Strava',
        strava_connected_as: 'Connected as ',
        strava_disconnect: 'Disconnect',
        strava_upload_btn: 'Upload to Strava',
        strava_uploading: 'Uploading',
        strava_status_success: 'Uploaded',
        strava_status_duplicate: 'Already on Strava',
        strava_status_error: 'Upload failed',
        strava_status_processing: 'Processing...',
        strava_expired: 'Session expired, please re-parse your data',
        strava_reconnect: 'Disconnected, please reconnect to Strava',
        strava_rate_limit: 'Rate limited, please try again later'
    }
};

document.addEventListener('alpine:init', () => {
    Alpine.data('datePickerData', (type) => ({
        isOpen: false,
        month: new Date().getMonth(),
        year: new Date().getFullYear(),
        monthNames: [],
        dayNames: [],

        init() {
            this.updateTranslations();
            this.$watch('lang', () => {
                this.updateTranslations();
            });
        },

        updateTranslations() {
            if (this.lang === 'zh') {
                this.monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
                this.dayNames = ['日', '一', '二', '三', '四', '五', '六'];
            } else {
                this.monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                this.dayNames = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
            }
        },

        get formattedDate() {
            return type === 'start' ? this.startDate : this.endDate;
        },

        get blankDays() {
            let days = [];
            let firstDay = new Date(this.year, this.month, 1).getDay();
            for (let i = 0; i < firstDay; i++) {
                days.push(i);
            }
            return days;
        },

        get daysInMonth() {
            let days = [];
            let daysInThisMonth = new Date(this.year, this.month + 1, 0).getDate();
            for (let i = 1; i <= daysInThisMonth; i++) {
                days.push(i);
            }
            return days;
        },

        togglePicker() {
            if (!this.isOpen) {
                let currentVal = type === 'start' ? this.startDate : this.endDate;
                if (currentVal) {
                    let d = new Date(currentVal);
                    if (!isNaN(d)) {
                        this.month = d.getMonth();
                        this.year = d.getFullYear();
                    }
                } else {
                    this.month = new Date().getMonth();
                    this.year = new Date().getFullYear();
                }
            }
            this.isOpen = !this.isOpen;
        },

        closePicker() {
            this.isOpen = false;
        },

        prevMonth() {
            if (this.month === 0) { this.month = 11; this.year--; }
            else { this.month--; }
        },

        nextMonth() {
            if (this.month === 11) { this.month = 0; this.year++; }
            else { this.month++; }
        },

        selectDate(date) {
            let selectedDate = new Date(this.year, this.month, date);
            let formatted = selectedDate.getFullYear() + '-' +
                            String(selectedDate.getMonth() + 1).padStart(2, '0') + '-' +
                            String(selectedDate.getDate()).padStart(2, '0');
            if (type === 'start') { this.startDate = formatted; }
            else { this.endDate = formatted; }
            this.isOpen = false;
        },

        clearDate() {
            if (type === 'start') { this.startDate = ''; }
            else { this.endDate = ''; }
            this.isOpen = false;
        },

        isSelected(date) {
            let currentVal = type === 'start' ? this.startDate : this.endDate;
            if (!currentVal) return false;
            let d = new Date(this.year, this.month, date);
            let formatted = d.getFullYear() + '-' +
                            String(d.getMonth() + 1).padStart(2, '0') + '-' +
                            String(d.getDate()).padStart(2, '0');
            return currentVal === formatted;
        },

        isToday(date) {
            const today = new Date();
            const d = new Date(this.year, this.month, date);
            return today.toDateString() === d.toDateString();
        }
    }));

    Alpine.data('appData', () => ({
        lang: 'zh',
        theme: 'dark',

        get t() {
            return i18n[this.lang];
        },

        init() {
            this.initTheme();
            this.checkStravaStatus();

            // Listen for OAuth popup callback
            window.addEventListener('message', (event) => {
                if (event.origin !== window.location.origin) return;
                if (event.data?.type === 'strava-connected') {
                    this.stravaConnected = true;
                    this.stravaAthlete = event.data.athlete || '';
                } else if (event.data?.type === 'strava-error') {
                    this.error = event.data.error || 'Strava authorization failed';
                }
            });
        },

        initTheme() {
            this.loadSelection();
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme) { this.setTheme(savedTheme); }
            else { this.autoTheme(); }
        },

        autoTheme() {
            // The dark workspace is the default product surface. Users can
            // still switch to light mode and the choice is persisted.
            this.setTheme('dark', false);
        },

        setTheme(themeName, save = true) {
            this.theme = themeName;
            if (themeName === 'dark') { document.documentElement.classList.add('dark'); }
            else { document.documentElement.classList.remove('dark'); }
            if (save) { localStorage.setItem('theme', themeName); }
        },

        toggleTheme() { this.setTheme(this.theme === 'dark' ? 'light' : 'dark'); },
        toggleLang() { this.lang = this.lang === 'zh' ? 'en' : 'zh'; },

        file: null,
        password: '',
        showPassword: false,
        startDate: '',
        endDate: '',
        dragActive: false,
        status: 'idle', // idle, loading, success
        error: null,
        results: [],
        resultMessage: '',
        downloadUrl: '',
        taskId: null,
        taskToken: null,
        parseProgress: { current: 0, total: 0, activity: '' },
        sportFilter: 'all',  // 运动类型筛选（必须在开头定义）
        currentPage: 1,      // 分页（必须在开头定义）
        itemsPerPage: 10,    // 分页（必须在开头定义）

        // Selection state
        selectedItems: [],

        get isAllSelected() {
            return this.filteredResults.length > 0 && this.selectedItems.length === this.filteredResults.length;
        },

        get isIndeterminate() {
            return this.selectedItems.length > 0 && this.selectedItems.length < this.filteredResults.length;
        },

        toggleSelectAll() {
            if (this.isAllSelected) { this.selectedItems = []; }
            else { this.selectedItems = this.filteredResults.map(r => r.filename); }
            this.saveSelection();
        },

        toggleSelection(filename) {
            const index = this.selectedItems.indexOf(filename);
            if (index > -1) { this.selectedItems.splice(index, 1); }
            else { this.selectedItems.push(filename); }
            this.saveSelection();
        },

        isSelected(filename) {
            return this.selectedItems.includes(filename);
        },

        saveSelection() {
            localStorage.setItem('selectedActivities', JSON.stringify(this.selectedItems));
        },

        loadSelection() {
            try {
                const saved = localStorage.getItem('selectedActivities');
                if (saved) { this.selectedItems = JSON.parse(saved); }
            } catch (e) { this.selectedItems = []; }
        },

        // Sidebar state
        selectedItem: null,
        isSidebarOpen: false,

        openDetails(item, event) {
            if (event) { event.stopPropagation(); }
            this.selectedItem = item;
            this.isSidebarOpen = true;
        },

        closeDetails() { this.isSidebarOpen = false; },

        formatDuration(seconds) {
            if (!seconds) return '00:00';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) { return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`; }
            return `${m}m ${s.toString().padStart(2, '0')}s`;
        },

        formatDistance(meters) {
            if (!meters) return '0.00 km';
            return (meters / 1000).toFixed(2) + ' km';
        },

        getSvgPath(pathData) {
            if (!pathData || pathData.length < 2) return '';
            const validPath = pathData.filter(pt => pt && pt.length >= 2 && Math.abs(pt[0]) > 0.1 && Math.abs(pt[1]) > 0.1);
            if (validPath.length < 2) return '';
            const sortedLats = [...validPath].map(p => p[0]).sort((a,b) => a-b);
            const sortedLons = [...validPath].map(p => p[1]).sort((a,b) => a-b);
            const medLat = sortedLats[Math.floor(sortedLats.length/2)];
            const medLon = sortedLons[Math.floor(sortedLons.length/2)];
            const cleanPath = validPath.filter(pt =>
                Math.abs(pt[0] - medLat) < 2.0 && Math.abs(pt[1] - medLon) < 2.0
            );
            if (cleanPath.length < 2) return '';
            let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
            cleanPath.forEach(pt => {
                if (pt[0] < minLat) minLat = pt[0]; if (pt[0] > maxLat) maxLat = pt[0];
                if (pt[1] < minLon) minLon = pt[1]; if (pt[1] > maxLon) maxLon = pt[1];
            });
            const midLat = (minLat + maxLat) / 2;
            const latScale = 1.0;
            const lonScale = Math.cos(midLat * Math.PI / 180);
            const latDiff = Math.max((maxLat - minLat) * latScale, 0.00001);
            const lonDiff = Math.max((maxLon - minLon) * lonScale, 0.00001);
            const maxDiff = Math.max(latDiff, lonDiff);
            const padLat = (maxDiff / latScale) * 0.1;
            const padLon = (maxDiff / lonScale) * 0.1;
            minLat -= padLat; maxLat += padLat; minLon -= padLon; maxLon += padLon;
            const finalLatDiff = (maxLat - minLat) * latScale;
            const finalLonDiff = (maxLon - minLon) * lonScale;
            const finalMaxDiff = Math.max(finalLatDiff, finalLonDiff);
            const pts = cleanPath.map(pt => {
                const xOffset = (finalMaxDiff - finalLonDiff) / 2;
                const yOffset = (finalMaxDiff - finalLatDiff) / 2;
                const x = (((pt[1] - minLon) * lonScale + xOffset) / finalMaxDiff) * 100;
                const y = 100 - ((((pt[0] - minLat) * latScale + yOffset) / finalMaxDiff) * 100);
                return `${x.toFixed(2)},${y.toFixed(2)}`;
            });
            return `M ${pts.join(' L ')}`;
        },

        // 心率/配速图表 SVG 路径生成（使用固定范围避免数据变化小时变成直线）
        getChartPath(series, type) {
            if (!series || series.length < 2) return '';

            // 使用固定范围，确保曲线有明显变化
            let minVal, maxVal, range;
            if (type === 'hr') {
                // 心率固定范围：60-200 bpm
                minVal = 60;
                maxVal = 200;
                range = 140;
            } else if (type === 'pace') {
                // 配速固定范围：3-12 分钟/公里（180-720 秒/公里）
                const values = series.map(pt => pt[type]);
                // 使用实际数据范围，但设置最小范围
                minVal = Math.min(...values);
                maxVal = Math.max(...values);
                range = Math.max(maxVal - minVal, 120); // 至少 2 分钟差距
            } else {
                const values = series.map(pt => pt[type]);
                minVal = Math.min(...values);
                maxVal = Math.max(...values);
                range = Math.max(maxVal - minVal, 1);
            }

            // 生成路径点
            const pts = series.map((pt, i) => {
                const x = (i / (series.length - 1)) * 100;
                // Y 轴反转（SVG y 从上到下增加），值越大 y 越小
                // 心率：值越大（心率越高），线越高（y 越小）
                // 配速：值越大（配速越慢），线越低（y 越大）- 需要反转
                let y;
                if (type === 'pace') {
                    // 配速反转：慢配速（大值）在上面还是下面？
                    // 通常配速曲线显示：快配速在上（跑得快），慢配速在下
                    y = ((pt[type] - minVal) / range) * 28 + 1;
                } else {
                    y = 30 - ((pt[type] - minVal) / range) * 28 - 1;
                }
                return `${x.toFixed(2)},${Math.max(1, Math.min(29, y)).toFixed(2)}`;
            });

            return `M ${pts.join(' L ')}`;
        },

        getChartAreaPath(series, type) {
            if (!series || series.length < 2) return '';

            // 使用固定范围
            let minVal, maxVal, range;
            if (type === 'hr') {
                minVal = 60;
                maxVal = 200;
                range = 140;
            } else if (type === 'pace') {
                const values = series.map(pt => pt[type]);
                minVal = Math.min(...values);
                maxVal = Math.max(...values);
                range = Math.max(maxVal - minVal, 120);
            } else {
                const values = series.map(pt => pt[type]);
                minVal = Math.min(...values);
                maxVal = Math.max(...values);
                range = Math.max(maxVal - minVal, 1);
            }

            const pts = series.map((pt, i) => {
                const x = (i / (series.length - 1)) * 100;
                let y;
                if (type === 'pace') {
                    y = ((pt[type] - minVal) / range) * 28 + 1;
                } else {
                    y = 30 - ((pt[type] - minVal) / range) * 28 - 1;
                }
                return `${x.toFixed(2)},${Math.max(1, Math.min(29, y)).toFixed(2)}`;
            });

            const linePath = `M ${pts.join(' L ')}`;
            return `${linePath} L 100,30 L 0,30 Z`;
        },

        // 根据筛选条件过滤结果（sportFilter/currentPage/itemsPerPage 已在顶部定义）
        get filteredResults() {
            if (this.sportFilter === 'all') {
                return this.results;
            }
            return this.results.filter(item => {
                const sport = item.sport || '';
                if (this.sportFilter === 'Run') {
                    return sport.includes('Run') || sport.includes('Indoor');
                }
                if (this.sportFilter === 'Cycl') {
                    return sport.includes('Cycl') || sport.includes('Spinning');
                }
                if (this.sportFilter === 'Walk') {
                    return sport.includes('Walk');
                }
                if (this.sportFilter === 'Swim') {
                    return sport.includes('Swim');
                }
                if (this.sportFilter === 'Other') {
                    return !sport.includes('Run') && !sport.includes('Indoor') &&
                           !sport.includes('Cycl') && !sport.includes('Spinning') &&
                           !sport.includes('Walk') && !sport.includes('Swim');
                }
                return true;
            });
        },

        get totalPages() { return Math.ceil(this.filteredResults.length / this.itemsPerPage) || 1; },
        get dateRangeInvalid() {
            return Boolean(this.startDate && this.endDate && this.endDate < this.startDate);
        },
        get paginatedResults() {
            const start = (this.currentPage - 1) * this.itemsPerPage;
            return this.filteredResults.slice(start, start + this.itemsPerPage);
        },
        nextPage() { if (this.currentPage < this.totalPages) this.currentPage++; },
        prevPage() { if (this.currentPage > 1) this.currentPage--; },

        // 筛选变化时重置分页
        setSportFilter(filter) {
            this.sportFilter = filter;
            this.currentPage = 1;
        },

        // --- Strava Integration ---
        stravaConfigured: false,
        stravaConnected: false,
        stravaAthlete: '',
        stravaUploading: false,
        stravaUploadResults: {},   // { filename: { status, error, activity_id } }
        stravaUploadCurrent: 0,
        stravaUploadTotal: 0,

        async checkStravaStatus() {
            try {
                const resp = await fetch('/api/strava/status');
                const data = await resp.json();
                this.stravaConfigured = data.configured || false;
                this.stravaConnected = data.connected || false;
                this.stravaAthlete = data.athlete_name || '';
            } catch (e) {
                this.stravaConfigured = false;
            }
        },

        connectStrava() {
            fetch('/api/strava/authorize').then(r => r.json()).then(data => {
                if (data.url) {
                    window.open(data.url, 'strava_auth', 'width=600,height=700');
                }
            });
        },

        async disconnectStrava() {
            await fetch('/api/strava/disconnect', { method: 'POST' });
            this.stravaConnected = false;
            this.stravaAthlete = '';
        },

        getUploadStatus(filename) {
            return this.stravaUploadResults[filename] || null;
        },

        async uploadToStrava() {
            if (!this.taskId || this.selectedItems.length === 0) return;

            this.stravaUploading = true;
            this.stravaUploadCurrent = 0;
            this.stravaUploadTotal = this.selectedItems.length;

            for (const filename of this.selectedItems) {
                this.stravaUploadCurrent++;
                this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'uploading' } };

                try {
                    const resp = await fetch('/api/strava/upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_id: this.taskId, task_token: this.taskToken, filename }),
                    });

                    if (resp.status === 401) {
                        this.stravaConnected = false;
                        this.error = this.t.strava_reconnect;
                        break;
                    }
                    if (resp.status === 404) {
                        this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: this.t.strava_expired } };
                        continue;
                    }
                    if (resp.status === 429) {
                        const data = await resp.json();
                        this.error = this.t.strava_rate_limit;
                        this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: 'Rate limited' } };
                        // Wait before continuing
                        await new Promise(r => setTimeout(r, (data.retry_after || 60) * 1000));
                        continue;
                    }

                    const data = await resp.json();
                    if (!data.upload_id) {
                        this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: data.error || 'Unknown error' } };
                        continue;
                    }

                    // Poll for upload status
                    this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'processing' } };
                    let resolved = false;
                    for (let i = 0; i < 30; i++) {
                        await new Promise(r => setTimeout(r, 2000));
                        try {
                            const statusResp = await fetch(`/api/strava/upload-status/${data.upload_id}`);
                            const statusData = await statusResp.json();

                            if (statusData.status === 'ready') {
                                this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'success', activity_id: statusData.activity_id } };
                                resolved = true;
                                break;
                            } else if (statusData.status === 'duplicate') {
                                this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'duplicate', error: statusData.error } };
                                resolved = true;
                                break;
                            } else if (statusData.status === 'error') {
                                this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: statusData.error } };
                                resolved = true;
                                break;
                            }
                        } catch (e) { /* continue polling */ }
                    }
                    if (!resolved) {
                        this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: 'Timeout' } };
                    }
                } catch (e) {
                    this.stravaUploadResults = { ...this.stravaUploadResults, [filename]: { status: 'error', error: e.message } };
                }
            }

            this.stravaUploading = false;
        },

        handleDrop(e) {
            this.dragActive = false;
            if (e.dataTransfer.files.length > 0) {
                const droppedFile = e.dataTransfer.files[0];
                if (droppedFile.name.endsWith('.zip')) {
                    this.file = droppedFile;
                    this.$refs.fileInput.files = e.dataTransfer.files;
                } else {
                    this.error = this.lang === 'zh' ? "请上传有效的 .zip 文件。" : "Please upload a valid .zip file.";
                }
            }
        },

        handleFileSelect(e) {
            if (e.target.files.length > 0) {
                this.file = e.target.files[0];
                this.error = null;
            }
        },

        async submitForm() {
            if (!this.file || !this.password) return;

            if (this.dateRangeInvalid) {
                this.error = this.t.date_range_error;
                return;
            }

            this.status = 'loading';
            this.error = null;
            this.currentPage = 1;
            this.stravaUploadResults = {};
            this.parseProgress = { current: 0, total: 0, activity: '' };

            const formData = new FormData();
            formData.append('file', this.file);
            formData.append('password', this.password);
            if (this.startDate) formData.append('start_date', this.startDate);
            if (this.endDate) formData.append('end_date', this.endDate);

            try {
                // Phase 1: Upload file, get task_id back immediately
                const uploadResp = await fetch('/api/parse', {
                    method: 'POST',
                    body: formData
                });
                const uploadData = await uploadResp.json();

                if (!uploadResp.ok || uploadData.status === 'error') {
                    this.error = uploadData.message || 'Upload failed';
                    this.status = 'idle';
                    return;
                }

                const taskId = uploadData.task_id;
                this.taskId = taskId;
                this.taskToken = uploadData.task_token;

                // Phase 2: Listen for progress via SSE
                const result = await new Promise((resolve, reject) => {
                    let es = null;
                    let reconnects = 0;
                    let settled = false;
                    const connect = () => {
                        es = new EventSource(`/api/parse/progress/${taskId}?token=${encodeURIComponent(uploadData.task_token)}`);
                        es.onopen = () => { reconnects = 0; };
                        es.onmessage = (event) => {
                            const data = JSON.parse(event.data);
                            this.parseProgress = {
                                current: data.current || 0,
                                total: data.total || 0,
                                activity: data.activity || ''
                            };
                            if (data.status === 'success') {
                                settled = true;
                                es.close();
                                if (!Array.isArray(data.results) || data.results.length === 0) {
                                    reject(new Error('NO_ACTIVITIES'));
                                } else {
                                    resolve(data);
                                }
                            } else if (data.status === 'error') {
                                settled = true;
                                es.close();
                                reject(new Error(data.error || 'Parse failed'));
                            }
                        };
                        es.onerror = () => {
                            es.close();
                            if (settled) return;
                            reconnects++;
                            if (reconnects <= 5) {
                                window.setTimeout(connect, Math.min(5000, reconnects * 1000));
                            } else {
                                settled = true;
                                reject(new Error('Connection lost'));
                            }
                        };
                    };
                    connect();
                });

                this.results = result.results;
                this.resultMessage = result.message;
                this.downloadUrl = result.download_url;
                this.selectedItems = [];
                localStorage.removeItem('selectedActivities');

                setTimeout(() => { this.status = 'success'; }, 300);
            } catch (err) {
                this.error = err.message === 'NO_ACTIVITIES'
                    ? this.t.no_activities
                    : (err.message || (this.lang === 'zh' ? "网络连接错误，请重试。" : "Connection error. Please try again."));
                this.status = 'idle';
            }
        },

        resetForm() {
            this.file = null;
            this.$refs.fileInput.value = '';
            this.status = 'idle';
            this.results = [];
            this.currentPage = 1;
            this.sportFilter = 'all';
            this.selectedItems = [];
            this.taskId = null;
            this.taskToken = null;
            this.stravaUploadResults = {};
            localStorage.removeItem('selectedActivities');
        }
    }));
});
