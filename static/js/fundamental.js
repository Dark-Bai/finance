// =========================== 【全局变量】 ===========================
let Dict_company_info__ = null;           // 公司基本信息
let Dict_valuation_data__ = null;         // 估值数据
let Dict_financial_data__ = null;         // 财务数据
let Dict_shareholder_data__ = null;       // 股东信息
let Dict_news_data__ = null;              // 公告数据

// =========================== 【工具函数】 ===========================
function Tool_function_format_number__(value__, unit__ = '', decimal__ = 2) {
    if (value__ === null || value__ === undefined || value__ === '') {
        return '—';
    }
    const num__ = parseFloat(value__);
    if (isNaN(num__)) return '—';
    
    let result__;
    if (unit__ === '亿') {
        result__ = num__ / 100000000;  // 万元 -> 亿元
    } else if (unit__ === '万') {
        result__ = num__ / 10000;       // 元 -> 万元
    } else if (unit__ === '原值') {
        result__ = num__;               // 保持原值（注册资本已是万元）
    } else if (unit__ === '百分比') {
        return num__.toFixed(decimal__) + '%';
    } else {
        return num__.toLocaleString(undefined, { minimumFractionDigits: decimal__, maximumFractionDigits: decimal__ });
    }
    
    return result__.toLocaleString(undefined, { minimumFractionDigits: decimal__, maximumFractionDigits: decimal__ });
}

function Tool_function_format_date__(date_str__) {
    if (!date_str__ || date_str__.length !== 8) return date_str__ || '—';
    return `${date_str__.substring(0, 4)}-${date_str__.substring(4, 6)}-${date_str__.substring(6, 8)}`;
}

function Tool_function_build_ts_code__(code__, exchange__) {
    // 根据代码前缀和交易所字段双重判断
    const prefix = code__.substring(0, 2);
    // 如果 exchange 字段明确包含 "上证"、"科创板" 或代码以 60/68 开头，返回 .SH
    if (exchange__ && (exchange__.includes('上证') || exchange__.includes('科创板'))) {
        return `${code__}.SH`;
    }
    // 如果 exchange 字段明确包含 "深证"、"创业板" 或代码以 00/30 开头，返回 .SZ
    if (exchange__ && (exchange__.includes('深证') || exchange__.includes('创业板'))) {
        return `${code__}.SZ`;
    }
    // 北交所
    if (exchange__ && exchange__.includes('北交所')) {
        return `${code__}.BJ`;
    }
    // 通过代码前缀判断（备用）
    if (prefix === '60' || prefix === '68') {
        return `${code__}.SH`;
    } else if (prefix === '00' || prefix === '30') {
        return `${code__}.SZ`;
    } else if (prefix === '92') {
        return `${code__}.BJ`;
    }
    // 默认返回 .SH（可根据需要调整）
    return `${code__}.SH`;
}

function Tool_function_show_error__(message__) {
    document.getElementById('loading-container').style.display = 'none';
    document.getElementById('content-container').style.display = 'none';
    document.getElementById('error-container').style.display = 'block';
    document.getElementById('error-message').textContent = message__;
}

function Tool_function_hide_loading__() {
    document.getElementById('loading-container').style.display = 'none';
    document.getElementById('content-container').style.display = 'block';
}

// =========================== 【数据加载函数】 ===========================
async function Main_function_load_fundamental_data__() {
    const code__ = window.securityInfo.code;
    const exchange__ = window.securityInfo.exchange;
    const ts_code__ = Tool_function_build_ts_code__(code__, exchange__);
    
    try {
        const response__ = await fetch('/api/fundamental_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code__,
                exchange: exchange__,
                ts_code: ts_code__,
                name: window.securityInfo.name
            })
        });
        
        if (!response__.ok) {
            throw new Error(`HTTP error! status: ${response__.status}`);
        }
        
        const data__ = await response__.json();
        
        if (!data__.success) {
            Tool_function_show_error__(data__.error || '加载数据失败');
            return;
        }
        
        // 存储数据（无权限字段）
        Dict_company_info__ = data__.data.company;
        Dict_valuation_data__ = data__.data.valuation;
        Dict_financial_data__ = data__.data.financial;
        Dict_shareholder_data__ = data__.data.shareholder;
        Dict_news_data__ = data__.data.news;

        // 存储扩展的估值数据（新增）
        if (data__.data.valuation_extended) {
            window.Dict_valuation_extended__ = data__.data.valuation_extended;
        }

        // 渲染页面
        Level_1_render_company_info__();
        Level_1_render_valuation_info__();
        Level_1_render_financial_info__();
        Level_1_render_shareholder_info__();
        Level_1_render_news_info__();
        
        Tool_function_hide_loading__();
        
    } catch (error__) {
        console.error('加载基本面数据失败:', error__);
        Tool_function_show_error__('网络请求失败：' + error__.message);
    }
}

// =========================== 【渲染函数】 ===========================
function Level_1_render_company_info__() {
    const tag__ = document.getElementById('company-permission-tag');
    const body__ = document.getElementById('company-info-body');
    
    if (!Dict_company_info__) {
        tag__.textContent = '暂无数据';
        tag__.className = 'permission-tag denied';
        body__.innerHTML = `<div class="permission-denied-message"><p>暂无公司基本信息数据</p></div>`;
        return;
    }
    
    tag__.textContent = '已获取';
    tag__.className = 'permission-tag';
    
    const info__ = Dict_company_info__;

    const renderItem__ = (label__, key__, formatter__ = null) => {
        let value__ = info__[key__];
        let formatted__ = '—';
        if (value__ !== null && value__ !== undefined && value__ !== '') {
            if (formatter__) {
                formatted__ = formatter__(value__);
            } else if (key__.includes('date') && String(value__).length === 8) {
                formatted__ = Tool_function_format_date__(String(value__));
            } else if (key__ === 'reg_capital') {
                formatted__ = Tool_function_format_number__(value__, '原值', 2) + ' 万元';
            } else if (key__ === 'is_hs') {
                if (value__ === 'H') formatted__ = '沪股通';
                else if (value__ === 'S') formatted__ = '深股通';
                else if (value__ === 'N') formatted__ = '否';
                else formatted__ = value__;
            } else {
                formatted__ = String(value__);
            }
        }
        return `<div class="info-item"><span class="info-label">${label__}：</span><span class="info-value">${formatted__}</span></div>`;
    };

    let html__ = '';

    html__ += '<div class="company-info-row">';
    html__ += renderItem__('证券名称', 'name');
    html__ += renderItem__('公司全称', 'fullname');
    html__ += renderItem__('英文名称', 'enname');
    html__ += '</div>';

    html__ += '<div class="company-info-row">';
    html__ += renderItem__('所属地域', 'area');
    html__ += renderItem__('所属行业', 'industry');
    html__ += renderItem__('沪深港通', 'is_hs');
    html__ += '</div>';

    html__ += '<div class="company-info-row">';
    html__ += renderItem__('董事长', 'chairman');
    html__ += renderItem__('总经理', 'manager');
    html__ += renderItem__('董事会秘书', 'secretary');
    html__ += '</div>';

    html__ += '<div class="company-info-row">';
    html__ += renderItem__('成立日期', 'setup_date');
    html__ += renderItem__('上市日期', 'list_date');
    html__ += '<div class="info-item"></div>';
    html__ += '</div>';

    html__ += '<div class="company-info-row">';
    html__ += renderItem__('员工人数', 'employees', (v) => v ? v.toLocaleString() + ' 人' : '—');
    html__ += renderItem__('注册资本', 'reg_capital', (v) => Tool_function_format_number__(v, '原值', 2) + ' 万元');
    html__ += '<div class="info-item"></div>';
    html__ += '</div>';
    
    if (info__.main_business) {
        html__ += `<div class="info-item" style="margin-top:10px;flex-wrap:wrap;"><span class="info-label">主营业务：</span><span class="info-value" style="flex:1;line-height:1.6;text-align:left;">${info__.main_business}</span></div>`;
    }
    if (info__.business_scope) {
        html__ += `<div class="info-item" style="margin-top:10px;flex-wrap:wrap;"><span class="info-label">经营范围：</span><span class="info-value" style="flex:1;line-height:1.6;text-align:left;">${info__.business_scope}</span></div>`;
    }
    
    body__.innerHTML = html__;
}

function Level_1_render_valuation_info__() {
    const tag__ = document.getElementById('valuation-permission-tag');
    const body__ = document.getElementById('valuation-info-body');
    
    if (!Dict_valuation_data__) {
        tag__.textContent = '暂无数据';
        tag__.className = 'permission-tag denied';
        body__.innerHTML = `<div class="permission-denied-message"><p>暂无估值指标数据</p></div>`;
        return;
    }
    
    tag__.textContent = '已获取';
    tag__.className = 'permission-tag';
    
    const data__ = Dict_valuation_data__;
    const extended__ = window.Dict_valuation_extended__ || {};
    const theoretical__ = extended__.theoretical_valuation || {};
    const industry__ = extended__.industry || {};
    const metrics__ = extended__.financial_metrics || {};

    let html__ = '';

    // 数据日期提示
    if (extended__.data_date) {
        const formattedDate__ = Tool_function_format_date__(extended__.data_date);
        html__ += `<p style="font-size:12px;color:#999;margin-bottom:15px;">📅 数据截止：${formattedDate__}</p>`;
    }

    // ========== 第一部分：关键基础指标（表格风格） ==========
    html__ += '<div style="margin-bottom:20px;">';
    html__ += '<div style="font-weight:bold;font-size:14px;margin-bottom:10px;border-bottom:1px solid #e0e0e0;padding-bottom:5px;">📈 关键基础指标</div>';
    html__ += '<div class="info-grid">';

    // 第一行：收盘价、市净率、流通市值
    html__ += `<div class="info-item"><span class="info-label">收盘价（元）：</span><span class="info-value">${data__.close?.toFixed(2) || '—'}</span></div>`;
    html__ += `<div class="info-item"><span class="info-label">流通市值：</span><span class="info-value">${data__.circ_mv ? (data__.circ_mv / 10000).toFixed(2) + ' 亿元' : '—'}</span></div>`;
    html__ += `<div class="info-item"><span class="info-label">总市值：</span><span class="info-value">${data__.total_mv ? (data__.total_mv / 10000).toFixed(2) + ' 亿元' : '—'}</span></div>`;

    // 第二行：市盈率(PE)、市销率(PS)、总市值（补充）
    html__ += `<div class="info-item"><span class="info-label">市盈率(PE)：</span><span class="info-value">${data__.pe?.toFixed(2) || '—'}</span></div>`;
    html__ += `<div class="info-item"><span class="info-label">市净率(PB)：</span><span class="info-value">${data__.pb?.toFixed(2) || '—'}</span></div>`;
    html__ += `<div class="info-item"><span class="info-label">市销率(PS)：</span><span class="info-value">${data__.ps?.toFixed(2) || '—'}</span></div>`;

    // 第三行：市盈率(TTM)、股息率、每股股息(DPS)
    html__ += `<div class="info-item"><span class="info-label">市盈率(TTM)：</span><span class="info-value">${data__.pe_ttm?.toFixed(2) || '—'}</span></div>`;

    // 处理股息率：确保是数字类型后再调用 toFixed
    const dvRatioValue = parseFloat(data__.dv_ratio);
    const dvRatioDisplay = !isNaN(dvRatioValue) ? dvRatioValue.toFixed(2) + '%' : '—';
    html__ += `<div class="info-item"><span class="info-label">股息率：</span><span class="info-value">${dvRatioDisplay}</span></div>`;

    // 处理每股股息：确保是数字类型后再调用 toFixed
    const dpsValue = parseFloat(metrics__.dps);
    const dpsDisplay = !isNaN(dpsValue) ? dpsValue.toFixed(3) + ' 元' : '—';
    html__ += `<div class="info-item"><span class="info-label">每股股息(DPS)：</span><span class="info-value">${dpsDisplay}</span></div>`;

    html__ += '</div></div>';

    // ========== 第二部分：行业估值对比（表格风格） ==========
    if (industry__.name) {
        html__ += '<div style="margin-bottom:20px;">';
        html__ += '<div style="font-weight:bold;font-size:14px;margin-bottom:10px;border-bottom:1px solid #e0e0e0;padding-bottom:5px;">🏭 行业估值对比</div>';
        html__ += '<div class="info-grid">';

        // 第一行：所属行业、样本数量、空
        html__ += `<div class="info-item"><span class="info-label">所属行业：</span><span class="info-value">${industry__.name || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">样本数量：</span><span class="info-value">${industry__.sample_count || '—'}</span></div>`;
        html__ += `<div class="info-item"></div>`;

        // 第二行：行业平均PE、标的PE、差异度
        const pe = data__.pe;
        const peAvg = industry__.pe_avg;
        let peDiff = '—';
        if (pe && peAvg) {
            const diff = (pe / peAvg - 1) * 100;
            peDiff = (diff > 0 ? '+' : '') + diff.toFixed(2) + '%';
        }
        html__ += `<div class="info-item"><span class="info-label">行业平均PE：</span><span class="info-value">${peAvg?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">标的个股PE：</span><span class="info-value">${pe?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">差异度：</span><span class="info-value">${peDiff}</span></div>`;

        // 第三行：行业平均PB、标的PB、差异度
        const pb = data__.pb;
        const pbAvg = industry__.pb_avg;
        let pbDiff = '—';
        if (pb && pbAvg) {
            const diff = (pb / pbAvg - 1) * 100;
            pbDiff = (diff > 0 ? '+' : '') + diff.toFixed(2) + '%';
        }
        html__ += `<div class="info-item"><span class="info-label">行业平均PB：</span><span class="info-value">${pbAvg?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">标的个股PB：</span><span class="info-value">${pb?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">差异度：</span><span class="info-value">${pbDiff}</span></div>`;

        // 第四行：行业平均PS、标的PS、差异度
        const ps = data__.ps;
        const psAvg = industry__.ps_avg;
        let psDiff = '—';
        if (ps && psAvg) {
            const diff = (ps / psAvg - 1) * 100;
            psDiff = (diff > 0 ? '+' : '') + diff.toFixed(2) + '%';
        }
        html__ += `<div class="info-item"><span class="info-label">行业平均PS：</span><span class="info-value">${psAvg?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">标的个股PS：</span><span class="info-value">${ps?.toFixed(2) || '—'}</span></div>`;
        html__ += `<div class="info-item"><span class="info-label">差异度：</span><span class="info-value">${psDiff}</span></div>`;

        html__ += '</div></div>';
    }

    // ========== 第三部分：多模型理论估值 ==========
    html__ += '<div style="margin-bottom:15px;">';
    html__ += '<div style="font-weight:bold;font-size:14px;margin-bottom:10px;border-bottom:1px solid #e0e0e0;padding-bottom:5px;">🔬 多模型理论估值</div>';

    // 固定五种模型配置
    const modelConfigs = [
        { name: '股息贴现模型（零增长）', formula: '每股股息 ÷ 无风险利率' },
        { name: 'PE估值法', formula: '行业PE × 每股收益(EPS)' },
        { name: 'PB估值法', formula: '行业PB × 每股净资产(BPS)' },
        { name: 'PS估值法', formula: '行业PS × 每股营收(SPS)' },
        { name: 'PEG估值法', formula: '个股PE / 企业盈利增长率（G）' }
    ];

    const modelsMap = {};
    if (theoretical__ && theoretical__.models) {
        theoretical__.models.forEach(m => { modelsMap[m.name] = m; });
    }

    if (Object.keys(modelsMap).length > 0 || true) { // 始终显示表格框架
        html__ += '<table style="width:100%;font-size:13px;border-collapse:collapse;margin-bottom:15px;table-layout:fixed;">';
        html__ += '<thead><tr style="background:#f5f5f5;">';
        html__ += '<th style="padding:8px;text-align:left;width:20%;">估值方法</th>';
        html__ += '<th style="padding:8px;text-align:left;width:30%;">计算公式</th>';
        html__ += '<th style="padding:8px;text-align:right;width:15%;">理论价格</th>';
        html__ += '<th style="padding:8px;text-align:right;width:15%;">差异度</th>';
        html__ += '<th style="padding:8px;text-align:center;width:20%;">估值评价</th>';
        html__ += '</tr></thead><tbody>';

        modelConfigs.forEach(cfg => {
            const model = modelsMap[cfg.name];
            let theoPrice = '—', diffPercent = '—', signal = '—', signalColor = '#6c757d';
            if (model) {
                theoPrice = model.theoretical_price;
                diffPercent = (model.diff_percent > 0 ? '+' : '') + model.diff_percent + '%';
                signal = model.signal;
                signalColor = model.signal === '低估' ? '#28a745' : '#dc3545';
            }
            const diffColor = model && model.diff_percent > 0 ? '#dc3545' : '#28a745';
            html__ += `<tr style="border-bottom:1px solid #eee;">`;
            html__ += `<td style="padding:8px;"><strong>${cfg.name}</strong></td>`;
            html__ += `<td style="padding:8px;text-align:left;color:#666;">${cfg.formula}</td>`;
            html__ += `<td style="padding:8px;text-align:right;font-weight:bold;">${theoPrice}</td>`;
            html__ += `<td style="padding:8px;text-align:right;color:${model ? diffColor : '#6c757d'};">${diffPercent}</td>`;
            html__ += `<td style="padding:8px;text-align:center;"><span style="background:${signalColor};color:white;padding:2px 8px;border-radius:12px;font-size:12px;">${signal}</span></td>`;
            html__ += `</tr>`;
        });

        html__ += '</tbody></table>';

        // 汇总信息行
        const closePrice = theoretical__?.close_price?.toFixed(2) || data__?.close?.toFixed(2) || '—';
        let avgTheoPrice = '—', avgDiff = '—', avgDiffColor = '#6c757d';
        if (theoretical__ && theoretical__.avg_theoretical_price != null) {
            avgTheoPrice = theoretical__.avg_theoretical_price.toFixed(2);
            const diffVal = theoretical__.avg_diff_percent;
            avgDiff = (diffVal > 0 ? '+' : '') + diffVal.toFixed(2) + '%';
            avgDiffColor = diffVal > 0 ? '#dc3545' : '#28a745';
        }
        const riskFree = extended__.risk_free_rate ? (extended__.risk_free_rate * 100).toFixed(2) + '%' : '—';


        html__ += '<div style="background:#f8f9fa;padding:12px;border-radius:8px;margin-top:10px;">';
        html__ += '<div style="display:flex;flex-wrap:wrap;gap:20px;align-items:center;">';
        html__ += `<span><span style="color:#666;">最近收盘价：</span><strong>${closePrice}</strong></span>`;
        html__ += `<span><span style="color:#666;">综合平均理论价格：</span><strong style="color:#007bff;">${avgTheoPrice}</strong></span>`;
        html__ += `<span><span style="color:#666;">平均差异度：</span><strong style="color:${avgDiffColor};">${avgDiff}</strong></span>`;
        html__ += `<span><span style="color:#666;">无风险利率参考值：</span><strong>${riskFree}</strong></span>`;
        html__ += '</div>';
        html__ += '</div>';
    } else {
        html__ += '<p style="color:#999;text-align:center;padding:20px;">财务数据不足，无法进行多模型估值计算。<br>可能原因：每股收益(EPS)或每股净资产(BPS)数据缺失。</p>';
    }

    html__ += '</div>'; // 关闭第三部分容器

    body__.innerHTML = html__;
}

// =========================== 【财务信息渲染函数】 ===========================
function Level_1_render_financial_info__() {
    const tag__ = document.getElementById('financial-permission-tag');
    const container__ = document.querySelector('.financial-card .card-body');

    const balanceTable__ = document.getElementById('balance-table');
    const incomeTable__ = document.getElementById('income-table');
    const cashflowTable__ = document.getElementById('cashflow-table');
    const perShareTable__ = document.getElementById('per_share-table');
    const profitTable__ = document.getElementById('profit-table');
    const growthTable__ = document.getElementById('growth-table');
    const solvencyTable__ = document.getElementById('solvency-table');
    const operationTable__ = document.getElementById('operation-table');

    [balanceTable__, incomeTable__, cashflowTable__, perShareTable__, profitTable__, growthTable__, solvencyTable__, operationTable__].forEach(t => {
        if (t) t.innerHTML = '';
    });

    if (!Dict_financial_data__) {
        tag__.textContent = '暂无数据';
        tag__.className = 'permission-tag denied';
        container__.innerHTML = `<div class="financial-permission-denied">📊 暂无财务数据</div>`;
        return;
    }

    tag__.textContent = '已获取';
    tag__.className = 'permission-tag';

    const financialData__ = Dict_financial_data__;
    const periods__ = financialData__.periods || [];
    const displayPeriods__ = [...periods__].reverse();

    const formatPeriod__ = (periodStr__) => {
        if (periodStr__.length === 8) {
            const year__ = periodStr__.substring(0, 4);
            const md__ = periodStr__.substring(4);
            if (md__ === '1231') return `${year__}年报`;
            if (md__ === '0930') return `${year__}三季报`;
            if (md__ === '0630') return `${year__}中报`;
            if (md__ === '0331') return `${year__}一季报`;
        }
        return periodStr__;
    };

    // 完整中文映射表（与后端一致）
    const cnMap__ = {
        'total_revenue': '营业总收入',
        'revenue': '营业收入',
        'int_income': '利息收入',
        'prem_earned': '已赚保费',
        'comm_income': '手续费及佣金收入',
        'n_commis_income': '手续费及佣金净收入',
        'n_oth_income': '其他经营净收益',
        'n_oth_b_income': '其他业务净收益',
        'prem_income': '保险业务收入',
        'out_prem': '分出保费',
        'une_prem_reser': '提取未到期责任准备金',
        'reins_income': '分保费收入',
        'n_sec_tb_income': '代理买卖证券业务净收入',
        'n_sec_uw_income': '证券承销业务净收入',
        'n_asset_mg_income': '受托客户资产管理业务净收入',
        'oth_b_income': '其他业务收入',
        'fv_value_chg_gain': '公允价值变动净收益',
        'invest_income': '投资净收益',
        'ass_invest_income': '对联营企业和合营企业的投资收益',
        'forex_gain': '汇兑净收益',
        'total_cogs': '营业总成本',
        'oper_cost': '营业成本',
        'int_exp': '利息支出',
        'comm_exp': '手续费及佣金支出',
        'biz_tax_surchg': '税金及附加',
        'sell_exp': '销售费用',
        'admin_exp': '管理费用',
        'fin_exp': '财务费用',
        'assets_impair_loss': '资产减值损失',
        'credit_impa_loss': '信用减值损失',
        'rd_exp': '研发费用',
        'prem_refund': '退保金',
        'compens_payout': '赔付总支出',
        'reser_insur_liab': '提取保险责任准备金',
        'div_payt': '保户红利支出',
        'reins_exp': '分保费用',
        'oper_exp': '营业支出',
        'compens_payout_refu': '摊回赔付支出',
        'insur_reser_refu': '摊回保险责任准备金',
        'reins_cost_refund': '摊回分保费用',
        'other_bus_cost': '其他业务成本',
        'operate_profit': '营业利润',
        'non_oper_income': '营业外收入',
        'non_oper_exp': '营业外支出',
        'nca_disploss': '非流动资产处置损失',
        'total_profit': '利润总额',
        'income_tax': '所得税费用',
        'n_income': '净利润',
        'n_income_attr_p': '归属于母公司股东的净利润',
        'minority_gain': '少数股东损益',
        'oth_compr_income': '其他综合收益的税后净额',
        't_compr_income': '综合收益总额',
        'compr_inc_attr_p': '归属于母公司股东的综合收益总额',
        'compr_inc_attr_m_s': '归属于少数股东的综合收益总额',
        'ebit': '息税前利润',
        'ebitda': '息税折旧摊销前利润',
        'fin_exp_int_exp': '利息费用',
        'fin_exp_int_inc': '利息收入',
        'basic_eps': '基本每股收益',
        'diluted_eps': '稀释每股收益',
        'continued_net_profit': '持续经营净利润',
        'money_cap': '货币资金',
        'trad_asset': '交易性金融资产',
        'deriv_assets': '衍生金融资产',
        'notes_receiv': '应收票据',
        'accounts_receiv': '应收账款',
        'accounts_receiv_bill': '应收票据及应收账款',
        'prepayment': '预付款项',
        'oth_receiv': '其他应收款',
        'oth_rcv_total': '其他应收款合计',
        'div_receiv': '应收股利',
        'int_receiv': '应收利息',
        'inventories': '存货',
        'contract_assets': '合同资产',
        'nca_within_1y': '一年内到期的非流动资产',
        'oth_cur_assets': '其他流动资产',
        'total_cur_assets': '流动资产合计',
        'fa_avail_for_sale': '可供出售金融资产',
        'htm_invest': '持有至到期投资',
        'debt_invest': '债权投资',
        'oth_debt_invest': '其他债权投资',
        'oth_eqt_tools': '其他权益工具投资',
        'lt_eqt_invest': '长期股权投资',
        'invest_real_estate': '投资性房地产',
        'fix_assets': '固定资产',
        'fixed_assets_disp': '固定资产清理',
        'fix_assets_total': '固定资产合计',
        'cip': '在建工程',
        'const_materials': '工程物资',
        'cip_total': '在建工程合计',
        'produc_bio_assets': '生产性生物资产',
        'oil_and_gas_assets': '油气资产',
        'use_right_asset_dep': '使用权资产折旧',
        'intan_assets': '无形资产',
        'r_and_d': '开发支出',
        'goodwill': '商誉',
        'lt_amor_exp': '长期待摊费用',
        'defer_tax_assets': '递延所得税资产',
        'oth_nca': '其他非流动资产',
        'total_nca': '非流动资产合计',
        'total_assets': '资产总计',
        'st_borr': '短期借款',
        'cb_borr': '向中央银行借款',
        'loan_oth_bank': '拆入资金',
        'trading_fl': '交易性金融负债',
        'deriv_liab': '衍生金融负债',
        'notes_payable': '应付票据',
        'acct_payable': '应付账款',
        'accounts_pay': '应付票据及应付账款',
        'adv_receipts': '预收款项',
        'contract_liab': '合同负债',
        'payroll_payable': '应付职工薪酬',
        'taxes_payable': '应交税费',
        'int_payable': '应付利息',
        'div_payable': '应付股利',
        'oth_payable': '其他应付款',
        'oth_pay_total': '其他应付款合计',
        'non_cur_liab_due_1y': '一年内到期的非流动负债',
        'oth_cur_liab': '其他流动负债',
        'total_cur_liab': '流动负债合计',
        'lt_borr': '长期借款',
        'bond_payable': '应付债券',
        'lt_payable': '长期应付款',
        'long_pay_total': '长期应付款合计',
        'specific_payables': '专项应付款',
        'estimated_liab': '预计负债',
        'defer_tax_liab': '递延所得税负债',
        'defer_inc_non_cur_liab': '递延收益-非流动负债',
        'oth_ncl': '其他非流动负债',
        'total_ncl': '非流动负债合计',
        'total_liab': '负债合计',
        'total_share': '实收资本（或股本）',
        'oth_eqt_tools_p_shr': '其他权益工具（优先股）',
        'cap_rese': '资本公积',
        'treasury_share': '库存股',
        'surplus_rese': '盈余公积',
        'ordin_risk_reser': '一般风险准备',
        'undistr_porfit': '未分配利润',
        'total_hldr_eqy_exc_min_int': '归属于母公司股东权益合计',
        'minority_int': '少数股东权益',
        'total_hldr_eqy_inc_min_int': '股东权益合计',
        'total_liab_hldr_eqy': '负债及股东权益总计',
        'c_fr_sale_sg': '销售商品、提供劳务收到的现金',
        'recp_tax_rends': '收到的税费返还',
        'c_fr_oth_operate_a': '收到其他与经营活动有关的现金',
        'c_inf_fr_operate_a': '经营活动现金流入小计',
        'c_paid_goods_s': '购买商品、接受劳务支付的现金',
        'c_paid_to_for_empl': '支付给职工以及为职工支付的现金',
        'c_paid_for_taxes': '支付的各项税费',
        'oth_cash_pay_oper_act': '支付其他与经营活动有关的现金',
        'st_cash_out_act': '经营活动现金流出小计',
        'n_cashflow_act': '经营活动产生的现金流量净额',
        'c_disp_withdrwl_invest': '收回投资收到的现金',
        'c_recp_return_invest': '取得投资收益收到的现金',
        'n_recp_disp_fiolta': '处置固定资产、无形资产和其他长期资产收回的现金净额',
        'n_recp_disp_sobu': '处置子公司及其他营业单位收到的现金净额',
        'oth_recp_ral_inv_act': '收到其他与投资活动有关的现金',
        'stot_inflows_inv_act': '投资活动现金流入小计',
        'c_pay_acq_const_fiolta': '购建固定资产、无形资产和其他长期资产支付的现金',
        'c_paid_invest': '投资支付的现金',
        'n_disp_subs_oth_biz': '取得子公司及其他营业单位支付的现金净额',
        'oth_pay_ral_inv_act': '支付其他与投资活动有关的现金',
        'stot_out_inv_act': '投资活动现金流出小计',
        'n_cashflow_inv_act': '投资活动产生的现金流量净额',
        'c_recp_borrow': '取得借款收到的现金',
        'c_recp_cap_contrib': '吸收投资收到的现金',
        'proc_issue_bonds': '发行债券收到的现金',
        'oth_cash_recp_ral_fnc_act': '收到其他与筹资活动有关的现金',
        'stot_cash_in_fnc_act': '筹资活动现金流入小计',
        'c_prepay_amt_borr': '偿还债务支付的现金',
        'c_pay_dist_dpcp_int_exp': '分配股利、利润或偿付利息支付的现金',
        'oth_cashpay_ral_fnc_act': '支付其他与筹资活动有关的现金',
        'stot_cashout_fnc_act': '筹资活动现金流出小计',
        'n_cash_flows_fnc_act': '筹资活动产生的现金流量净额',
        'eff_fx_flu_cash': '汇率变动对现金及现金等价物的影响',
        'n_incr_cash_cash_equ': '现金及现金等价物净增加额',
        'c_cash_equ_beg_period': '期初现金及现金等价物余额',
        'c_cash_equ_end_period': '期末现金及现金等价物余额',
        'net_profit': '净利润',
        'finan_exp': '财务费用',
        'invest_loss': '投资损失',
        'loss_disp_fiolta': '处置固定资产、无形资产和其他长期资产的损失',
        'loss_fv_chg': '公允价值变动损失',
        'loss_scr_fa': '固定资产报废损失',
        'im_net_cashflow_oper_act': '经营活动产生的现金流量净额(间接法)',
        'im_n_incr_cash_equ': '现金及现金等价物净增加额(间接法)',
        'free_cashflow': '自由现金流',
        'incr_def_inc_tax_liab': '递延所得税负债增加',
        'incr_oper_payable': '经营性应付项目的增加',
        'lt_amort_deferred_exp': '长期待摊费用摊销',
    };

    const balanceOrder__ = [
        '===== 资产 =====',
        'money_cap', 'trad_asset', 'deriv_assets', 'notes_receiv', 'accounts_receiv_bill',
        'accounts_receiv', 'prepayment', 'oth_receiv', 'oth_rcv_total', 'div_receiv', 'int_receiv',
        'inventories', 'contract_assets', 'nca_within_1y', 'oth_cur_assets', 'total_cur_assets',
        '===== 非流动资产 =====',
        'fa_avail_for_sale', 'htm_invest', 'debt_invest', 'oth_debt_invest', 'oth_eqt_tools',
        'lt_eqt_invest', 'invest_real_estate', 'fix_assets_total', 'fix_assets', 'fixed_assets_disp',
        'cip_total', 'cip', 'const_materials', 'produc_bio_assets', 'oil_and_gas_assets',
        'use_right_asset_dep', 'intan_assets', 'r_and_d', 'goodwill', 'lt_amor_exp',
        'defer_tax_assets', 'oth_nca', 'total_nca', 'total_assets',
        '===== 负债 =====',
        'st_borr', 'cb_borr', 'loan_oth_bank', 'trading_fl', 'deriv_liab',
        'notes_payable', 'accounts_pay', 'acct_payable', 'adv_receipts', 'contract_liab',
        'payroll_payable', 'taxes_payable', 'int_payable', 'div_payable', 'oth_pay_total', 'oth_payable',
        'non_cur_liab_due_1y', 'oth_cur_liab', 'total_cur_liab',
        '===== 非流动负债 =====',
        'lt_borr', 'bond_payable', 'long_pay_total', 'lt_payable', 'specific_payables',
        'estimated_liab', 'defer_tax_liab', 'defer_inc_non_cur_liab', 'oth_ncl', 'total_ncl', 'total_liab',
        '===== 所有者权益 =====',
        'total_share', 'oth_eqt_tools_p_shr', 'cap_rese', 'treasury_share', 'surplus_rese',
        'ordin_risk_reser', 'undistr_porfit', 'total_hldr_eqy_exc_min_int', 'minority_int',
        'total_hldr_eqy_inc_min_int', 'total_liab_hldr_eqy'
    ];

    const incomeOrder__ = [
        '===== 一、营业收入 =====',
        'total_revenue', 'revenue', 'int_income', 'prem_earned', 'comm_income', 'oth_b_income',
        '===== 二、营业总成本 =====',
        'total_cogs', 'oper_cost', 'int_exp', 'comm_exp', 'biz_tax_surchg', 'sell_exp',
        'admin_exp', 'fin_exp', 'rd_exp', 'assets_impair_loss', 'credit_impa_loss',
        '===== 三、其他经营损益 =====',
        'fv_value_chg_gain', 'invest_income', 'ass_invest_income', 'forex_gain',
        'n_oth_income', 'n_oth_b_income',
        '===== 四、营业利润 =====',
        'operate_profit', 'non_oper_income', 'non_oper_exp',
        '===== 五、利润总额 =====',
        'total_profit', 'income_tax',
        '===== 六、净利润 =====',
        'n_income', 'n_income_attr_p', 'minority_gain',
        '===== 七、其他综合收益 =====',
        'oth_compr_income', 't_compr_income', 'compr_inc_attr_p', 'compr_inc_attr_m_s',
        '===== 八、每股收益 =====',
        'basic_eps', 'diluted_eps',
        '===== 九、补充信息 =====',
        'ebit', 'ebitda', 'fin_exp_int_exp', 'fin_exp_int_inc', 'continued_net_profit'
    ];

    const cashflowOrder__ = [
        '===== 一、经营活动产生的现金流量 =====',
        'c_fr_sale_sg', 'recp_tax_rends', 'c_fr_oth_operate_a', 'c_inf_fr_operate_a',
        'c_paid_goods_s', 'c_paid_to_for_empl', 'c_paid_for_taxes', 'oth_cash_pay_oper_act',
        'st_cash_out_act', 'n_cashflow_act',
        '===== 二、投资活动产生的现金流量 =====',
        'c_disp_withdrwl_invest', 'c_recp_return_invest', 'n_recp_disp_fiolta', 'n_recp_disp_sobu',
        'oth_recp_ral_inv_act', 'stot_inflows_inv_act', 'c_pay_acq_const_fiolta', 'c_paid_invest',
        'n_disp_subs_oth_biz', 'oth_pay_ral_inv_act', 'stot_out_inv_act', 'n_cashflow_inv_act',
        '===== 三、筹资活动产生的现金流量 =====',
        'c_recp_borrow', 'c_recp_cap_contrib', 'proc_issue_bonds', 'oth_cash_recp_ral_fnc_act',
        'stot_cash_in_fnc_act', 'c_prepay_amt_borr', 'c_pay_dist_dpcp_int_exp', 'oth_cashpay_ral_fnc_act',
        'stot_cashout_fnc_act', 'n_cash_flows_fnc_act',
        '===== 四、汇率变动对现金的影响 =====',
        'eff_fx_flu_cash',
        '===== 五、现金及现金等价物净增加额 =====',
        'n_incr_cash_cash_equ', 'c_cash_equ_beg_period', 'c_cash_equ_end_period',
        '===== 六、补充资料 =====',
        'net_profit', 'finan_exp', 'invest_loss', 'loss_disp_fiolta', 'loss_fv_chg',
        'loss_scr_fa', 'im_net_cashflow_oper_act', 'im_n_incr_cash_equ', 'free_cashflow',
        'incr_def_inc_tax_liab', 'incr_oper_payable', 'lt_amort_deferred_exp'
    ];

    const formatNumber__ = (val, isPercent = false, decimalDigits = 2) => {
        if (val === null || val === undefined || isNaN(val)) return '—';
        if (isPercent) return val.toFixed(2) + '%';
        return val.toLocaleString(undefined, { minimumFractionDigits: decimalDigits, maximumFractionDigits: decimalDigits });
    };

    const buildHeader__ = (unit = '') => {
        let html = '<tr><th>报表项目</th>';
        displayPeriods__.forEach(p => html += `<th>${formatPeriod__(p)}${unit ? ' (' + unit + ')' : ''}</th>`);
        html += '</tr>';
        return html;
    };

    const renderTableByOrder__ = (tableElement, dataArray, fieldOrder, unit = '元') => {
        if (!tableElement) return;
        if (!dataArray || dataArray.length === 0) {
            tableElement.innerHTML = `<tr><td colspan="${displayPeriods__.length + 1}" style="text-align:center;padding:20px;">暂无数据</td></tr>`;
            return;
        }
        const periodMap__ = {};
        dataArray.forEach(row => { periodMap__[row.end_date] = row; });

        const excludeFields__ = [
            'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type', 'update_flag',
            'cb_borr', 'loan_oth_bank', 'n_depos_incr_fi', 'n_incr_loans_cb', 'n_inc_borr_oth_fi',
            'prem_fr_orig_contr', 'n_incr_insured_dep', 'n_reinsur_prem', 'n_incr_disp_tfa',
            'ifc_cash_incr', 'n_incr_disp_faas', 'n_incr_loans_oth_bank', 'n_cap_incr_repur',
            'c_pay_claims_orig_inco', 'pay_handling_chrg', 'pay_comm_insur_plcy', 'n_incr_clt_loan_adv',
            'n_incr_dep_cbob', 'sett_rsrv', 'loanto_oth_bank_fi', 'premium_receiv', 'reinsur_receiv',
            'reinsur_res_receiv', 'pur_resale_fa', 'cash_reser_cb', 'depos_in_oth_bfi', 'prec_metals',
            'rr_reins_une_prem', 'rr_reins_outstd_cla', 'rr_reins_lins_liab', 'rr_reins_lthins_liab',
            'refund_depos', 'ph_pledge_loans', 'refund_cap_depos', 'indep_acct_assets',
            'client_depos', 'client_prov', 'transac_seat_fee', 'invest_as_receiv', 'depos_ib_deposits',
            'sold_for_repur_fa', 'comm_payable', 'payable_to_reinsurer', 'rsrv_insur_cont',
            'acting_trading_sec', 'acting_uw_sec', 'depos_oth_bfi', 'depos', 'agency_bus_liab',
            'oth_liab', 'prem_receiv_adva', 'depos_received', 'ph_invest', 'reser_une_prem',
            'reser_outstd_claims', 'reser_lins_liab', 'reser_lthins_liab', 'indept_acc_liab',
            'pledge_borr', 'indem_payable', 'policy_div_payable', 'amor_exp', 'acc_exp',
            'deferred_inc', 'st_bonds_payable', 'lt_payroll_payable', 'oth_comp_income',
            'invest_loss_unconf', 'decr_in_disbur', 'time_deposits', 'oth_assets', 'lt_rec',
            'insurance_exp', 'undist_profit', 'distable_profit', 'transfer_surplus_rese',
            'transfer_housing_imprest', 'transfer_oth', 'adj_lossgain', 'withdra_legal_surplus',
            'withdra_legal_pubfund', 'withdra_biz_devfund', 'withdra_rese_fund', 'withdra_oth_ersu',
            'workers_welfare', 'distr_profit_shrhder', 'prfshare_payable_dvd', 'comshare_payable_dvd',
            'capit_comstock_div', 'uncon_invest_loss', 'prov_depr_assets', 'depr_fa_coga_dpba',
            'amort_intang_assets', 'decr_deferred_exp', 'incr_acc_exp', 'decr_def_inc_tax_assets',
            'decr_inventories', 'decr_oper_payable', 'others', 'conv_debt_into_cap',
            'conv_copbonds_due_within_1y', 'fa_fnc_leases', 'net_dism_capital_add', 'net_cash_rece_sec',
            'oth_loss_asset', 'end_bal_cash', 'beg_bal_cash', 'end_bal_cash_equ', 'beg_bal_cash_equ',
            'incl_dvd_profit_paid_sc_ms', 'incl_cash_rec_saims', 'n_incr_pledge_loan'
        ];

        let html = buildHeader__(unit);
        for (const field of fieldOrder) {
            if (field.startsWith('=====')) {
                const sectionName = field.replace(/=/g, '').trim();
                html += `<tr class="section-row"><td colspan="${displayPeriods__.length + 1}"><strong>${sectionName}</strong></td></tr>`;
                continue;
            }

            if (excludeFields__.includes(field)) continue;

            const hasData = displayPeriods__.some(p => {
                const row = periodMap__[p];
                if (!row) return false;
                const val = row[field];
                return val !== null && val !== undefined && !isNaN(val) && val !== 0;
            });
            if (!hasData) continue;

            const cnName = cnMap__[field] || field;
            html += '<tr><td>' + cnName + '</td>';
            displayPeriods__.forEach(p => {
                const row = periodMap__[p];
                let val = row ? row[field] : null;
                let display = '—';
                if (val !== null && val !== undefined && !isNaN(val)) {
                    display = val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
                html += `<td>${display}</td>`;
            });
            html += '</tr>';
        }
        tableElement.innerHTML = html;
    };

    renderTableByOrder__(balanceTable__, financialData__.balancesheet, balanceOrder__, '元');
    renderTableByOrder__(incomeTable__, financialData__.income, incomeOrder__, '元');
    renderTableByOrder__(cashflowTable__, financialData__.cashflow, cashflowOrder__, '元');

    const finaIndicatorData__ = financialData__.fina_indicator;
    const incomeData__ = financialData__.income;
    const balanceData__ = financialData__.balancesheet;

    if (finaIndicatorData__ && finaIndicatorData__.length > 0) {
        const periodMap__ = {};
        finaIndicatorData__.forEach(row => { periodMap__[row.end_date] = row; });

        const incomePeriodMap__ = {};
        if (incomeData__) incomeData__.forEach(row => { incomePeriodMap__[row.end_date] = row; });
        const balancePeriodMap__ = {};
        if (balanceData__) balanceData__.forEach(row => { balancePeriodMap__[row.end_date] = row; });

        const getPrevPeriod__ = (periodStr__) => {
            if (!periodStr__ || periodStr__.length !== 8) return null;
            const year = parseInt(periodStr__.substring(0, 4));
            const md = periodStr__.substring(4);
            return `${year - 1}${md}`;
        };

        const calcAverage__ = (currentVal, prevVal) => {
            if (currentVal == null || prevVal == null || isNaN(currentVal) || isNaN(prevVal)) return null;
            return (currentVal + prevVal) / 2;
        };

        const renderIndicatorTable__ = (tableElement, fields, decimalDigits = 2) => {
            if (!tableElement) return;
            let html = buildHeader__('');
            fields.forEach(item => {
                const field = item.field;
                const name = item.name;
                const isPercent = item.isPercent || false;
                const customRender = item.customRender;
                html += '<tr><td>' + name + '</td>';
                displayPeriods__.forEach(p => {
                    const row = periodMap__[p];
                    let val = row ? row[field] : null;

                    if (customRender) {
                        val = customRender(p, row, incomePeriodMap__, balancePeriodMap__);
                    }

                    let display = '—';
                    if (val !== null && val !== undefined && !isNaN(val) && isFinite(val)) {
                        if (field === 'debt_to_eqt' || field === 'current_ratio' || field === 'quick_ratio') {
                            val = val * 100;
                        }
                        if (isPercent) {
                            display = val.toFixed(2) + '%';
                        } else {
                            display = val.toLocaleString(undefined, { minimumFractionDigits: decimalDigits, maximumFractionDigits: decimalDigits });
                        }
                    }
                    html += `<td>${display}</td>`;
                });
                html += '</tr>';
            });
            tableElement.innerHTML = html;
        };

        const perShareFields__ = [
            { field: 'eps', name: '基本每股收益(EPS)' },
            { field: 'bps', name: '每股净资产(BPS)' },
            { field: 'capital_rese_ps', name: '每股资本公积' },
            { field: 'undist_profit_ps', name: '每股未分配利润' },
            { field: 'ocfps', name: '每股经营现金流' }
        ];
        renderIndicatorTable__(perShareTable__, perShareFields__, 3);

        const profitFields__ = [
            { field: 'grossprofit_margin', name: '销售毛利率', isPercent: true },
            { field: 'netprofit_margin', name: '销售净利率', isPercent: true },
            { field: 'roe', name: '净资产收益率(ROE)', isPercent: true },
            { field: 'roa', name: '总资产报酬率(ROA)', isPercent: true }
        ];
        renderIndicatorTable__(profitTable__, profitFields__, 2);

        const growthFields__ = [
            { field: 'or_yoy', name: '营业收入同比增长率', isPercent: true },
            {
                field: 'operate_profit_yoy',
                name: '营业利润同比增长率',
                isPercent: true,
                customRender: (p, row, incomeMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const prevIncome = incomeMap[prevP];
                    if (!currIncome || !prevIncome) return null;
                    const currVal = currIncome['operate_profit'];
                    const prevVal = prevIncome['operate_profit'];
                    if (currVal == null || prevVal == null || prevVal === 0) return null;
                    return (currVal / Math.abs(prevVal) - 1) * 100;
                }
            },
            {
                field: 'net_profit_yoy',
                name: '净利润同比增长率',
                isPercent: true,
                customRender: (p, row, incomeMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const prevIncome = incomeMap[prevP];
                    if (!currIncome || !prevIncome) return null;
                    const currVal = currIncome['n_income'];
                    const prevVal = prevIncome['n_income'];
                    if (currVal == null || prevVal == null || prevVal === 0) return null;
                    return (currVal / Math.abs(prevVal) - 1) * 100;
                }
            },
            {
                field: 'eps_yoy_calculated',
                name: '每股收益同比增长率',
                isPercent: true,
                customRender: (p, row) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currRow = row;
                    const prevRow = periodMap__[prevP];
                    if (!currRow || !prevRow) return null;
                    const currVal = currRow['eps'];
                    const prevVal = prevRow['eps'];
                    if (currVal == null || prevVal == null || prevVal === 0) return null;
                    return (currVal / Math.abs(prevVal) - 1) * 100;
                }
            },
            { field: 'assets_yoy', name: '总资产同比增长率', isPercent: true }
        ];
        renderIndicatorTable__(growthTable__, growthFields__, 2);

        const operationFields__ = [
            {
                field: 'ar_turnover',
                name: '应收账款周转率',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const revenue = currIncome['revenue'];
                    const arCurr = currBalance['accounts_receiv'];
                    const arPrev = prevBalance['accounts_receiv'];
                    const avgAr = calcAverage__(arCurr, arPrev);
                    if (!revenue || !avgAr || avgAr === 0) return null;
                    return revenue / avgAr;
                }
            },
            {
                field: 'ar_turnover_days',
                name: '应收账款周转天数',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const revenue = currIncome['revenue'];
                    const arCurr = currBalance['accounts_receiv'];
                    const arPrev = prevBalance['accounts_receiv'];
                    const avgAr = calcAverage__(arCurr, arPrev);
                    if (!revenue || !avgAr || avgAr === 0) return null;
                    const turnover = revenue / avgAr;
                    if (!turnover || turnover === 0) return null;
                    return 365 / turnover;
                }
            },
            {
                field: 'inv_turnover',
                name: '存货周转率',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const cost = currIncome['total_cogs'] || currIncome['oper_cost'];
                    const invCurr = currBalance['inventories'];
                    const invPrev = prevBalance['inventories'];
                    const avgInv = calcAverage__(invCurr, invPrev);
                    if (!cost || !avgInv || avgInv === 0) return null;
                    return cost / avgInv;
                }
            },
            {
                field: 'inv_turnover_days',
                name: '存货周转天数',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const cost = currIncome['total_cogs'] || currIncome['oper_cost'];
                    const invCurr = currBalance['inventories'];
                    const invPrev = prevBalance['inventories'];
                    const avgInv = calcAverage__(invCurr, invPrev);
                    if (!cost || !avgInv || avgInv === 0) return null;
                    const turnover = cost / avgInv;
                    if (!turnover || turnover === 0) return null;
                    return 365 / turnover;
                }
            },
            {
                field: 'total_asset_turnover',
                name: '总资产周转率',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const revenue = currIncome['revenue'];
                    const assetCurr = currBalance['total_assets'];
                    const assetPrev = prevBalance['total_assets'];
                    const avgAsset = calcAverage__(assetCurr, assetPrev);
                    if (!revenue || !avgAsset || avgAsset === 0) return null;
                    return revenue / avgAsset;
                }
            },
            {
                field: 'total_asset_turnover_days',
                name: '总资产周转天数',
                customRender: (p, row, incomeMap, balanceMap) => {
                    const prevP = getPrevPeriod__(p);
                    if (!prevP) return null;
                    const currIncome = incomeMap[p];
                    const currBalance = balanceMap[p];
                    const prevBalance = balanceMap[prevP];
                    if (!currIncome || !currBalance || !prevBalance) return null;
                    const revenue = currIncome['revenue'];
                    const assetCurr = currBalance['total_assets'];
                    const assetPrev = prevBalance['total_assets'];
                    const avgAsset = calcAverage__(assetCurr, assetPrev);
                    if (!revenue || !avgAsset || avgAsset === 0) return null;
                    const turnover = revenue / avgAsset;
                    if (!turnover || turnover === 0) return null;
                    return 365 / turnover;
                }
            }
        ];
        renderIndicatorTable__(operationTable__, operationFields__, 2);

        const solvencyFields__ = [
            { field: 'current_ratio', name: '流动比率', isPercent: true },
            { field: 'quick_ratio', name: '速动比率', isPercent: true },
            { field: 'debt_to_eqt', name: '产权比率', isPercent: true },
            { field: 'debt_to_assets', name: '资产负债率', isPercent: true }
        ];
        renderIndicatorTable__(solvencyTable__, solvencyFields__, 2);
    } else {
        [perShareTable__, profitTable__, growthTable__, solvencyTable__, operationTable__].forEach(t => {
            if (t) t.innerHTML = '<tr><td colspan="' + (displayPeriods__.length + 1) + '" style="text-align:center;padding:20px;">暂无财务指标数据</td></tr>';
        });
    }

    setupTabSwitching__();
}

function setupTabSwitching__() {
    const statementTabs = document.querySelectorAll('#statement-tabs .tab-btn');
    statementTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetId = this.getAttribute('data-tab');
            statementTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            document.querySelectorAll('#tab-balance, #tab-income, #tab-cashflow').forEach(c => c.classList.remove('active'));
            document.getElementById('tab-' + targetId).classList.add('active');
        });
    });

    const indicatorTabs = document.querySelectorAll('#indicator-tabs .tab-btn');
    indicatorTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetId = this.getAttribute('data-tab');
            indicatorTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            document.querySelectorAll('#tab-per_share, #tab-profit, #tab-growth, #tab-operation, #tab-solvency').forEach(c => c.classList.remove('active'));
            document.getElementById('tab-' + targetId).classList.add('active');
        });
    });
}

function Level_1_render_shareholder_info__() {
    const tag__ = document.getElementById('shareholder-permission-tag');
    const body__ = document.getElementById('shareholder-info-body');
    
    if (!Dict_shareholder_data__) {
        tag__.textContent = '暂无数据';
        tag__.className = 'permission-tag denied';
        body__.innerHTML = '<p style="color:#999;text-align:center;padding:20px;">暂无股东数据</p>';
        return;
    }
    
    tag__.textContent = '已获取';
    tag__.className = 'permission-tag';
    
    const data__ = Dict_shareholder_data__;
    
    let html__ = '';
    
    if (data__.holder_num && data__.holder_num.length > 0) {
        html__ += '<div class="section-title">📈 股东户数趋势</div>';
        html__ += '<div class="scrollable-table-container">';
        html__ += '<table class="data-table">';
        html__ += '<thead><tr><th>截止日期</th><th style="text-align:right;">股东户数</th><th style="text-align:right;">较上期变动</th><th style="text-align:right;">户均持股</th></tr></thead><tbody>';
        
        const sorted__ = [...data__.holder_num].sort((a, b) => (b.end_date || '').localeCompare(a.end_date || ''));
        
        sorted__.forEach((item__, index__) => {
            const currentNum__ = item__.holder_num || 0;
            let changePercent__ = '—';
            if (index__ < sorted__.length - 1) {
                const prevNum__ = sorted__[index__ + 1].holder_num || 0;
                if (prevNum__ !== 0) {
                    const change__ = ((currentNum__ - prevNum__) / prevNum__ * 100);
                    changePercent__ = change__.toFixed(2) + '%';
                    if (change__ > 0) changePercent__ = '+' + changePercent__;
                }
            }
            const avgShare__ = item__.avg_share ? item__.avg_share.toFixed(0) : '—';
            html__ += `<tr>
                <td>${Tool_function_format_date__(item__.end_date)}</td>
                <td style="text-align:right;">${currentNum__.toLocaleString()}</td>
                <td style="text-align:right;">${changePercent__}</td>
                <td style="text-align:right;">${avgShare__}</td>
            </tr>`;
        });
        
        html__ += '</tbody></table></div>';
    }
    
    if (data__.top_holders && data__.top_holders.length > 0) {
        html__ += '<div class="section-title" style="margin-top:15px;">🏆 前十大股东</div>';
        html__ += '<div class="scrollable-table-container" style="max-height:250px;">';
        html__ += '<table class="data-table">';
        html__ += '<thead><tr><th>股东名称</th><th style="text-align:right;">持股数量（股）</th><th style="text-align:right;">持股比例</th><th style="text-align:right;">股东性质</th></tr></thead><tbody>';
        
        data__.top_holders.forEach(item__ => {
            html__ += `<tr>
                <td>${item__.holder_name || '—'}</td>
                <td style="text-align:right;">${(item__.hold_amount || 0).toLocaleString()}</td>
                <td style="text-align:right;">${(item__.hold_ratio || 0).toFixed(2)}%</td>
                <td style="text-align:right;">${item__.holder_type || '—'}</td>
            </tr>`;
        });
        
        html__ += '</tbody></table></div>';
    }
    
    if ((!data__.holder_num || data__.holder_num.length === 0) && (!data__.top_holders || data__.top_holders.length === 0)) {
        html__ = '<p style="color:#999;text-align:center;padding:20px;">暂无股东数据</p>';
    }
    
    body__.innerHTML = html__;
}

function Level_1_render_news_info__() {
    const tag__ = document.getElementById('news-permission-tag');
    const body__ = document.getElementById('news-info-body');
    
    if (!Dict_news_data__) {
        tag__.textContent = '暂无数据';
        tag__.className = 'permission-tag denied';
        body__.innerHTML = '<p style="color:#999;text-align:center;padding:20px;">暂无公告数据</p>';
        return;
    }
    
    tag__.textContent = '已获取';
    tag__.className = 'permission-tag';
    
    const news_list__ = Dict_news_data__ || [];
    
    if (news_list__.length === 0) {
        body__.innerHTML = '<p style="color:#999;text-align:center;padding:20px;">暂无公告数据</p>';
        return;
    }
    
    let html__ = '<ul class="news-list">';
    news_list__.forEach(item__ => {
        html__ += `<li class="news-item">`;
        html__ += `<span class="news-date">${Tool_function_format_date__(item__.ann_date)}</span>`;
        html__ += `<span class="news-title">${item__.title || '—'}</span>`;
        html__ += `<span class="news-type">${item__.type || '公告'}</span>`;
        html__ += `</li>`;
    });
    html__ += '</ul>';
    
    body__.innerHTML = html__;
}

// =========================== 【页面初始化】 ===========================
window.onload = function() {
    Main_function_load_fundamental_data__();
    
    document.getElementById('btn-retry').addEventListener('click', function() {
        document.getElementById('error-container').style.display = 'none';
        document.getElementById('loading-container').style.display = 'flex';
        Main_function_load_fundamental_data__();
    });
};