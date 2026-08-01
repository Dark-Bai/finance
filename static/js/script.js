// =========================== 【全局变量】 ===========================
let currentSecuritiesData = [];
let currentSecuritiesType = '股票';
let currentSortColumn = null;       // 当前排序列的索引（0为序号列，不排序）
let currentSortDirection = 'asc';   // 'asc' 或 'desc'

// =========================== 【页面加载】 ===========================
document.addEventListener('DOMContentLoaded', function() {
    // 初始化：加载概念/行业/地域列表
    loadSectorList('概念列表', 'stock_concept');
    loadSectorList('行业列表', 'stock_industry');
    loadSectorList('地域列表', 'stock_region');

    // 绑定证券类型切换事件
    const typeRadios = document.querySelectorAll('input[name="security_type"]');
    typeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            switchConditions(this.value);
        });
    });

    // 为所有多选select绑定互斥逻辑（选中“全部”时取消其他）
    setupMutualExclusive();

    // 初始化股票分层选股步骤切换
    initStockStepSelector();

    // 绑定筛选按钮
    document.getElementById('btn-filter').addEventListener('click', executeFilter);

    // 绑定导出按钮
    document.getElementById('btn-export').addEventListener('click', exportExcel);

    // 绑定更新数据库按钮
    document.getElementById('btn-update-db').addEventListener('click', function() {
        const btn = this;
        if (!confirm('此操作将从Tushare重新获取全市场数据，耗时较长，确定继续吗？')) {
            return;
        }
        btn.disabled = true;
        btn.textContent = '更新中...';
        appendLog('开始更新数据库，请耐心等待...');

        // 显示进度弹窗
        const modal = document.getElementById('update-modal');
        modal.style.display = 'block';

        fetch('/api/update_db', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.error || '请求失败'); });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                appendLog('✅ ' + data.message);
                alert('✅ ' + data.message);   // 更新完成弹窗
            } else {
                const errMsg = data.error || '未知错误';
                appendLog('❌ 更新失败: ' + errMsg);
                alert('❌ 更新失败：' + errMsg);
            }
        })
        .catch(err => {
            appendLog('❌ 请求出错: ' + err);
            alert('❌ 请求出错：' + err);
        })
        .finally(() => {
            // 隐藏进度弹窗
            modal.style.display = 'none';
            btn.disabled = false;
            btn.textContent = '更新数据库数据';
        });
    });
});

// =========================== 【证券类型切换】 ===========================
function switchConditions(type) {
    const allConditions = document.querySelectorAll('.conditions');
    allConditions.forEach(el => el.classList.remove('active'));

    let targetId = '';
    switch (type) {
        case '股票': targetId = 'stock-conditions'; break;
        case '指数': targetId = 'index-conditions'; break;
        case 'ETF': targetId = 'etf-conditions'; break;
        case 'LOF': targetId = 'lof-conditions'; break;
        case '国债': targetId = 'national-debt-conditions'; break;
        case '企债': targetId = 'corporate-bond-conditions'; break;
        case '可转债': targetId = 'convertible-bond-conditions'; break;
    }
    if (targetId) {
        document.getElementById(targetId).classList.add('active');
    }
}

// =========================== 【加载概念/行业/地域列表】 ===========================
function loadSectorList(type, selectId) {
    fetch('/api/sector_list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: type })
    })
    .then(response => response.json())
    .then(data => {
        if (data.list) {
            const select = document.getElementById(selectId);
            select.innerHTML = '<option value="全部" selected>全部</option>';
            data.list.forEach(item => {
                if (item !== '全部') {
                    const option = document.createElement('option');
                    option.value = item;
                    option.textContent = item;
                    select.appendChild(option);
                }
            });
        } else if (data.error) {
            appendLog(`加载${type}失败: ${data.error}`);
        }
    })
    .catch(err => {
        appendLog(`加载${type}出错: ${err}`);
    });
}

// =========================== 【互斥逻辑】 ===========================
function setupMutualExclusive() {
    const selectIds = [
        'stock_exchange', 'stock_concept', 'stock_industry', 'stock_region', 'stock_risk',
        'index_series', 'debt_exchange', 'corporate_exchange', 'convertible_exchange'
    ];
    selectIds.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.addEventListener('change', function() {
                const options = this.options;
                const allSelected = Array.from(options).some(opt => opt.value === '全部' && opt.selected);
                if (allSelected) {
                    for (let opt of options) {
                        if (opt.value !== '全部') opt.selected = false;
                    }
                }
            });
        }
    });
}

// =========================== 【股票分层选股步骤切换】 ===========================
function initStockStepSelector() {
    const tabs = document.querySelectorAll('.unified-selector .step-tab');
    const panels = document.querySelectorAll('.unified-selector .step-panel');
    const prevBtn = document.getElementById('stock-step-prev');
    const nextBtn = document.getElementById('stock-step-next');
    const stepIndicator = document.getElementById('stock-current-step');
    if (!tabs.length || !panels.length || !prevBtn || !nextBtn || !stepIndicator) return;

    let currentStep = 1;
    const totalSteps = tabs.length;

    function switchStep(step) {
        if (step < 1 || step > totalSteps) return;
        currentStep = step;

        tabs.forEach(tab => {
            const isActive = parseInt(tab.dataset.step) === step;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        panels.forEach(panel => {
            const isActive = parseInt(panel.dataset.step) === step;
            panel.classList.toggle('active', isActive);
            panel.hidden = !isActive;
        });

        stepIndicator.textContent = step;
        prevBtn.disabled = step === 1;
        nextBtn.textContent = step === totalSteps ? '完成' : '下一步';
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchStep(parseInt(tab.dataset.step)));
    });

    prevBtn.addEventListener('click', () => switchStep(currentStep - 1));
    nextBtn.addEventListener('click', () => {
        if (currentStep < totalSteps) {
            switchStep(currentStep + 1);
        }
    });

    switchStep(1);
}

// =========================== 【收集参数】 ===========================
function collectParams() {
    const secType = document.querySelector('input[name="security_type"]:checked').value;
    let params = {
        security_type: secType,
        metric_conditions: {}
    };

    // 指标条件
    const metrics = [
        { idMin: 'price_min', idMax: 'price_max', name: '最近收盘价' },
        { idMin: 'pe_min', idMax: 'pe_max', name: '动态市盈率' },
        { idMin: 'pb_min', idMax: 'pb_max', name: '市净率' },
        { idMin: 'marketcap_min', idMax: 'marketcap_max', name: '总市值（亿元）' },
        { idMin: 'circ_mv_min', idMax: 'circ_mv_max', name: '流通市值（亿元）' }
    ];
    metrics.forEach(m => {
        const minVal = document.getElementById(m.idMin).value.trim();
        const maxVal = document.getElementById(m.idMax).value.trim();
        params.metric_conditions[m.name] = {
            '下限': minVal === '' ? null : parseFloat(minVal),
            '上限': maxVal === '' ? null : parseFloat(maxVal)
        };
    });

    // 根据类型收集板块条件
    if (secType === '股票') {
        params.exchange = getSelectedValues('stock_exchange');
        params.concept = getSelectedValues('stock_concept');
        params.industry = getSelectedValues('stock_industry');
        params.region = getSelectedValues('stock_region');
        params.risk = getSelectedValues('stock_risk');
        params.name_keywords = document.getElementById('stock_name').value;
    } else if (secType === '指数') {
        params.index_series = getSelectedValues('index_series');
        params.name_keywords = document.getElementById('index_name').value;
    } else if (secType === 'ETF') {
        params.name_keywords = document.getElementById('etf_name').value;
    } else if (secType === 'LOF') {
        params.name_keywords = document.getElementById('lof_name').value;
    } else if (secType === '国债') {
        params.exchange = getSelectedValues('debt_exchange');
        params.name_keywords = document.getElementById('debt_name').value;
    } else if (secType === '企债') {
        params.exchange = getSelectedValues('corporate_exchange');
        params.name_keywords = document.getElementById('corporate_name').value;
    } else if (secType === '可转债') {
        params.exchange = getSelectedValues('convertible_exchange');
        params.name_keywords = document.getElementById('convertible_name').value;
    }

    return params;
}

function getSelectedValues(selectId) {
    const select = document.getElementById(selectId);
    return Array.from(select.selectedOptions).map(opt => opt.value);
}

// =========================== 【执行筛选】 ===========================
function executeFilter() {
    const params = collectParams();
    appendLog('正在提交筛选请求...');

    fetch('/api/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentSecuritiesData = data.data;
            currentSecuritiesType = data.type;
            if (data.log) data.log.forEach(msg => appendLog(msg));
            renderTable(data.data, data.type);
        } else {
            appendLog('筛选失败: ' + data.error);
            if (data.log) data.log.forEach(msg => appendLog(msg));
        }
    })
    .catch(err => {
        appendLog('请求出错: ' + err);
    });
}

// =========================== 【排序函数】 ===========================
function sortData(data, columnIndex, direction, type, metricHeaders) {
    // columnIndex: 表格列索引（0开始），0为序号列，不参与排序
    if (columnIndex === 0) return data;

    const headerRow = document.getElementById('table-header');
    const headers = Array.from(headerRow.children);
    const columnName = headers[columnIndex]?.textContent;

    // 确定该列的数据类型
    const baseHeaders = ['证券种类', '证券名称', '证券代码', '交易板块'];
    if (baseHeaders.includes(columnName)) {
        if (columnName === '证券代码') {
            // 按数字排序
            return [...data].sort((a, b) => {
                const valA = parseInt(a['证券代码']) || 0;
                const valB = parseInt(b['证券代码']) || 0;
                return direction === 'asc' ? valA - valB : valB - valA;
            });
        } else {
            // 按拼音排序
            return [...data].sort((a, b) => {
                const valA = a[columnName] || '';
                const valB = b[columnName] || '';
                if (direction === 'asc') {
                    return valA.localeCompare(valB, 'zh-CN');
                } else {
                    return valB.localeCompare(valA, 'zh-CN');
                }
            });
        }
    } else {
        // 指标列，按数值排序
        return [...data].sort((a, b) => {
            const valA = parseFloat(a[columnName]) || 0;
            const valB = parseFloat(b[columnName]) || 0;
            return direction === 'asc' ? valA - valB : valB - valA;
        });
    }
}

// =========================== 【渲染表格】 ===========================
function renderTable(data, type) {
    const headerRow = document.getElementById('table-header');
    const tbody = document.getElementById('table-body');
    headerRow.innerHTML = '';
    tbody.innerHTML = '';

    if (!data || data.length === 0) {
        document.getElementById('result-info').innerText = '共 0 个证券';
        headerRow.innerHTML = '<th>无数据</th>';
        return;
    }

    // 表头定义：增加序号列
    const baseHeaders = ['序号', '证券种类', '证券名称', '证券代码', '交易板块'];
    const metricMap = {
        '股票': ['最近收盘价', '动态市盈率', '市净率', '总市值（亿元）', '流通市值（亿元）'],
        '指数': ['最近收盘价', '涨跌幅', '量比', '成交量（万手）', '成交额（万元）'],
        'ETF': ['最近收盘价', '涨跌幅', '涨跌额', '成交量（万手）', '成交额（万元）'],
        'LOF': ['最近收盘价', '涨跌幅', '涨跌额', '成交量（万手）', '成交额（万元）'],
        '国债': ['最近收盘价', '涨跌幅', '涨跌额', '成交量（万手）', '成交额（万元）'],
        '企债': ['最近收盘价', '涨跌幅', '涨跌额', '成交量（万手）', '成交额（万元）'],
        '可转债': ['最近收盘价', '涨跌幅', '涨跌额', '成交量（万手）', '成交额（万元）']
    };
    const metricHeaders = metricMap[type] || [];
    const fullHeaders = baseHeaders.concat(metricHeaders);

    // 创建 colgroup 设置列宽
    const table = document.getElementById('result-table');
    const oldColgroup = table.querySelector('colgroup');
    if (oldColgroup) oldColgroup.remove();
    const colgroup = document.createElement('colgroup');
    const colCount = fullHeaders.length;
    for (let i = 0; i < colCount; i++) {
        const col = document.createElement('col');
        if (i === 0) {
            col.style.width = '5%'; // 序号列
        } else {
            col.style.width = (95 / (colCount - 1)) + '%'; // 剩余列等宽
        }
        colgroup.appendChild(col);
    }
    table.prepend(colgroup);

    // 生成表头
    fullHeaders.forEach((h, idx) => {
        const th = document.createElement('th');
        th.textContent = h;
        th.setAttribute('data-col-index', idx);
        // 添加点击排序事件（除了序号列）
        if (idx !== 0) {
            th.style.cursor = 'pointer';
            th.addEventListener('click', function() {
                const colIndex = parseInt(this.getAttribute('data-col-index'));
                if (currentSortColumn === colIndex) {
                    currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    currentSortColumn = colIndex;
                    currentSortDirection = 'asc';
                }
                const sortedData = sortData(data, colIndex, currentSortDirection, type, metricHeaders);
                renderTable(sortedData, type);
            });
        }
        headerRow.appendChild(th);
    });

    // 生成数据行（带序号）
    data.forEach((item, index) => {
        const tr = document.createElement('tr');
        const rowData = [
            (index + 1).toString(),
            item['证券种类'] || '',
            item['证券名称'] || '',
            item['证券代码'] || '',
            item['交易板块'] || ''
        ];
        metricHeaders.forEach(h => {
            let val = item[h];
            if (val === 'None' || val === null || val === undefined) val = '';
            rowData.push(val);
        });
        rowData.forEach(cell => {
            const td = document.createElement('td');
            td.textContent = cell;
            tr.appendChild(td);
        });

        // 双击跳转详情页（在新标签页打开）
        tr.addEventListener('dblclick', function() {
            const code = item['证券代码'];
            const name = item['证券名称'];
            const secType = item['证券种类'];
            const exchange = item['交易板块'];
            const url = `/detail?code=${encodeURIComponent(code)}&name=${encodeURIComponent(name)}&type=${encodeURIComponent(secType)}&exchange=${encodeURIComponent(exchange)}`;
            window.open(url, '_blank');
        });

        tbody.appendChild(tr);
    });

    document.getElementById('result-info').innerText = `共 ${data.length} 个证券 | 双击查看证券详情`;
}

// =========================== 【日志追加】 ===========================
function appendLog(msg) {
    const logDiv = document.getElementById('process-logs');
    logDiv.innerHTML += msg + '\n';
    logDiv.scrollTop = logDiv.scrollHeight;
}

// =========================== 【导出Excel】 ===========================
function exportExcel() {
    if (currentSecuritiesData.length === 0) {
        alert('没有可导出的数据，请先执行筛选');
        return;
    }

    fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            data: currentSecuritiesData,
            type: currentSecuritiesType
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error); });
        }
        return response.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '证券筛选表.xlsx';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        appendLog('导出成功');
    })
    .catch(err => {
        appendLog('导出失败: ' + err.message);
    });
}

// =========================== 【DSL 选股指令（任务4/任务5）】 ===========================
document.addEventListener('DOMContentLoaded', function () {
    const btnDslRun = document.getElementById('btn-dsl-run');
    const btnDslHelp = document.getElementById('btn-dsl-help');
    const codeInput = document.getElementById('code-input');
    if (btnDslRun) btnDslRun.addEventListener('click', executeDsl);
    if (btnDslHelp) btnDslHelp.addEventListener('click', toggleDslHelp);
    if (codeInput) {
        codeInput.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                executeDsl();
            }
        });
    }
});

function executeDsl() {
    const codeInput = document.getElementById('code-input');
    const dsl = codeInput.value.trim();
    hideDslError();
    if (!dsl) {
        showDslError('请输入选股条件，例如：市盈率 < 20 AND 行业 = "银行"', null);
        return;
    }
    appendLog('正在翻译并执行 DSL 指令...');
    fetch('/api/dsl_filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dsl: dsl, dialect: 'duckdb' })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.log) data.log.forEach(function (m) { appendLog(m); });
        if (data.success) {
            currentSecuritiesData = data.data;
            currentSecuritiesType = data.type;
            currentSortColumn = null;
            renderTable(data.data, data.type);
            showDslSql(data.sql, data.dialect);
        } else {
            showDslError(data.error || '未知错误', data.error_pos);
        }
    })
    .catch(function (err) {
        appendLog('DSL 请求出错: ' + err);
        showDslError('请求出错: ' + err, null);
    });
}

function showDslSql(sql, dialect) {
    document.getElementById('dsl-sql').textContent = sql;
    document.getElementById('dsl-dialect-name').textContent =
        dialect === 'doris' ? 'Doris' : 'DuckDB';
    document.getElementById('dsl-sql-panel').style.display = 'block';
}

function showDslError(msg, pos) {
    const box = document.getElementById('dsl-error');
    let html = '<div class="dsl-error-msg">❌ ' + escapeHtml(msg) + '</div>';
    if (pos !== null && pos !== undefined && pos >= 0) {
        const src = document.getElementById('code-input').value;
        const lines = src.split('\n');
        let start = 0, lineNo = 0, lineStart = 0;
        for (let i = 0; i < lines.length; i++) {
            if (start + lines[i].length >= pos) { lineNo = i; lineStart = start; break; }
            start += lines[i].length + 1;
        }
        const caretPos = Math.max(0, pos - lineStart);
        html += '<pre class="dsl-error-caret">' + escapeHtml(lines[lineNo]) + '\n' +
                ' '.repeat(caretPos) + '^</pre>';
    }
    box.innerHTML = html;
    box.style.display = 'block';
}

function hideDslError() {
    const box = document.getElementById('dsl-error');
    if (box) box.style.display = 'none';
}

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let dslHelpLoaded = false;
function toggleDslHelp() {
    const panel = document.getElementById('dsl-help-panel');
    if (panel.style.display === 'block') {
        panel.style.display = 'none';
        return;
    }
    if (dslHelpLoaded) {
        panel.style.display = 'block';
        return;
    }
    fetch('/api/dsl_help', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(function (r) { return r.json(); })
    .then(function (h) {
        panel.innerHTML = renderDslHelp(h);
        dslHelpLoaded = true;
        panel.style.display = 'block';
        panel.querySelectorAll('.dsl-example').forEach(function (el) {
            el.addEventListener('click', function () {
                document.getElementById('code-input').value = this.getAttribute('data-dsl');
                hideDslError();
            });
        });
    })
    .catch(function (err) { appendLog('加载语法帮助失败: ' + err); });
}

function renderDslHelp(h) {
    let html = '<h4>DSL 语法帮助</h4><p class="dsl-help-intro">' + escapeHtml(h.intro) + '</p>';
    html += '<details open><summary>数值字段（括号内为单位）</summary><div class="dsl-tags">';
    h.numeric_fields.forEach(function (f) {
        html += '<span class="dsl-tag">' + escapeHtml(f.name) +
                (f.unit ? '<em>' + escapeHtml(f.unit) + '</em>' : '') + '</span>';
    });
    html += '</div></details>';
    html += '<details><summary>文本字段</summary><ul>';
    h.string_fields.forEach(function (f) {
        html += '<li><b>' + escapeHtml(f.name) + '</b>：' + escapeHtml(f.note) + '</li>';
    });
    html += '</ul></details>';
    html += '<details><summary>布尔字段</summary><ul>';
    h.bool_fields.forEach(function (f) {
        html += '<li><b>' + escapeHtml(f.name) + '</b>：' + escapeHtml(f.note) + '</li>';
    });
    html += '</ul></details>';
    html += '<details open><summary>历史函数（基于日K线计算）</summary><ul>';
    h.functions.forEach(function (f) {
        html += '<li><b>' + escapeHtml(f.sig) + '</b>：' + escapeHtml(f.desc) +
                '<br><code>' + escapeHtml(f.example) + '</code></li>';
    });
    html += '</ul></details>';
    html += '<details><summary>运算符</summary><ul>';
    h.operators.forEach(function (f) {
        html += '<li><b>' + escapeHtml(f.sig) + '</b>：' + escapeHtml(f.desc) + '</li>';
    });
    html += '</ul></details>';
    html += '<details open><summary>示例（点击填入输入框）</summary><ul class="dsl-examples">';
    h.examples.forEach(function (f) {
        html += '<li class="dsl-example" data-dsl="' + escapeHtml(f.dsl) + '"><b>' +
                escapeHtml(f.title) + '</b>：<code>' + escapeHtml(f.dsl) + '</code></li>';
    });
    html += '</ul></details>';
    html += '<p class="dsl-help-notes">' + h.notes.map(function (n) { return escapeHtml(n); }).join('<br>') + '</p>';
    return html;
}
