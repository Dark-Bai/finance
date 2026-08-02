// =========================== 【全局变量】 ===========================
let currentKlineData = [];           // 当前K线类型的完整原始数据 (字符串数组)
let currentKlineType = '101';        // 当前K线类型代码
let totalDays = 0;                   // 总天数
let earliestDate = '';
let latestDate = '';

// 滑块位置 (像素)
let leftSliderX = 30;
let rightSliderX = 940;
let draggingSlider = null;           // 'left' 或 'right'

// 当前显示的图表数据 (根据滑块范围筛选)
let currentChartData = [];           // 筛选后的原始数据
let currentDates = [];
let currentOpen = [];
let currentClose = [];
let currentHigh = [];
let currentLow = [];
let currentVolume = [];
let currentAmount = [];

// 完整历史数据 (用于计算指标)
let allDates = [];
let allOpen = [];
let allClose = [];
let allHigh = [];
let allLow = [];
let allVolume = [];
let allAmount = [];

// 技术指标 (完整历史)
let ma5 = [], ma10 = [], ma20 = [], ma60 = [];
let volumeMa5 = [], volumeMa10 = [];
let amountMa5 = [], amountMa10 = [];
let rsi6 = [], rsi12 = [], rsi24 = [];
let k = [], d = [], j = [];
let dif = [], dea = [], macd = [];

// 画布引用
let canvasKline, ctxKline;
let canvasIndicator, ctxIndicator;
let canvasTimeline, ctxTimeline;
let canvasSecondTimeline, ctxSecondTimeline;

// 鼠标交互变量
let verticalLineKline = null;
let verticalLineIndicator = null;
let horizontalLineKline = null;
let mouseInChartArea = false;
let maDisplayTextIds = []; // 存储均线文本的ID

// 信息面板元素
const infoPanel = document.getElementById('info-panel');
const securityInfoDiv = document.getElementById('security-info');
const hoverInfoDiv = document.getElementById('hover-info');

// =========================== 【工具函数】 ===========================
function formatValue(val) {
    return val !== undefined && val !== null ? val.toFixed(2) : 'None';
}

function xToDate(x) {
    // 将画布x坐标转换为日期字符串
    const totalPixels = 910; // 30到940
    const ratio = (x - 30) / totalPixels;
    let index = Math.floor(ratio * totalDays);
    if (index < 0) index = 0;
    if (index >= totalDays) index = totalDays - 1;
    return currentKlineData[index].split(',')[0];
}

// 将K线类型名称转换为代码
function klineNameToCode(name) {
    const map = {
        '日K': '101',
        '周K': '102',
        '月K': '103',
        '5分钟': '5',
        '15分钟': '15',
        '30分钟': '30',
        '60分钟': '60'
    };
    return map[name] || '101';
}

// =========================== 【指标计算函数】 ===========================
function calculateMA(prices, period) {
    const result = [];
    for (let i = 0; i < prices.length; i++) {
        if (i < period - 1) {
            result.push(null);
        } else {
            let sum = 0;
            for (let j = i - period + 1; j <= i; j++) sum += prices[j];
            result.push(sum / period);
        }
    }
    return result;
}

function calculateRSI(prices, period) {
    if (prices.length <= period) {
        return new Array(prices.length).fill(null);
    }

    const rsi = new Array(period).fill(null);

    // 计算价格变化
    const changes = [];
    for (let i = 1; i < prices.length; i++) {
        changes.push(prices[i] - prices[i-1]);
    }

    // 分离涨幅和跌幅
    const gains = changes.map(c => Math.max(c, 0));
    const losses = changes.map(c => Math.max(-c, 0));

    // 第一个平均值用简单平均
    let avgGain = gains.slice(0, period).reduce((a,b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a,b) => a + b, 0) / period;

    // 第一个RSI值
    let rsiVal;
    if (avgLoss === 0) {
        rsiVal = 100;
    } else {
        const rs = avgGain / avgLoss;
        rsiVal = 100 - (100 / (1 + rs));
    }
    rsi.push(rsiVal);

    // 后续使用Wilder平滑
    for (let i = period; i < changes.length; i++) {
        avgGain = (avgGain * (period - 1) + gains[i]) / period;
        avgLoss = (avgLoss * (period - 1) + losses[i]) / period;

        if (avgLoss === 0) {
            rsiVal = 100;
        } else {
            const rs = avgGain / avgLoss;
            rsiVal = 100 - (100 / (1 + rs));
        }
        rsi.push(rsiVal);
    }

    return rsi;
}

function calculateKDJ(highs, lows, closes) {
    const n = 9;
    const kArr = new Array(n).fill(50);
    const dArr = new Array(n).fill(50);
    const jArr = new Array(n).fill(50);
    if (closes.length <= n) return [kArr, dArr, jArr];
    for (let i = n; i < closes.length; i++) {
        const recentHigh = Math.max(...highs.slice(i-n+1, i+1));
        const recentLow = Math.min(...lows.slice(i-n+1, i+1));
        let rsv;
        if (recentHigh === recentLow) {
            rsv = 50;
        } else {
            rsv = (closes[i] - recentLow) / (recentHigh - recentLow) * 100;
        }
        const kVal = (2/3) * kArr[i-1] + (1/3) * rsv;
        const dVal = (2/3) * dArr[i-1] + (1/3) * kVal;
        const jVal = 3 * kVal - 2 * dVal;
        kArr.push(kVal);
        dArr.push(dVal);
        jArr.push(jVal);
    }
    return [kArr, dArr, jArr];
}

function calculateMACD(prices) {
    const ema12 = [prices[0]];
    const ema26 = [prices[0]];
    for (let i = 1; i < prices.length; i++) {
        ema12.push(ema12[i-1] * 11/13 + prices[i] * 2/13);
        ema26.push(ema26[i-1] * 25/27 + prices[i] * 2/27);
    }
    const difArr = ema12.map((v, i) => v - ema26[i]);
    const deaArr = [difArr[0]];
    for (let i = 1; i < difArr.length; i++) {
        deaArr.push(deaArr[i-1] * 8/10 + difArr[i] * 2/10);
    }
    const macdArr = difArr.map((v, i) => (v - deaArr[i]) * 2);
    return [difArr, deaArr, macdArr];
}

// =========================== 【数据加载与计算】 ===========================
async function loadKlineData(ktypeCode) {
    const params = new URLSearchParams({
        code: window.securityInfo.code,
        exchange: window.securityInfo.exchange,
        type: window.securityInfo.type,
        ktype: ktypeCode
    });
    const response = await fetch(`/api/kline?${params}`);
    const data = await response.json();
    if (data.error) {
        alert('获取数据失败：' + data.error);
        return;
    }
    currentKlineData = data.klines;
    totalDays = currentKlineData.length;
    if (totalDays === 0) return;

    // 解析全部数据
    allDates = [];
    allOpen = [];
    allClose = [];
    allHigh = [];
    allLow = [];
    allVolume = [];
    allAmount = [];
    currentKlineData.forEach(str => {
        const parts = str.split(',');
        if (parts.length >= 11) {
            allDates.push(parts[0]);
            allOpen.push(parseFloat(parts[1]));
            allClose.push(parseFloat(parts[2]));
            allHigh.push(parseFloat(parts[3]));
            allLow.push(parseFloat(parts[4]));
            allVolume.push(parseFloat(parts[5]));
            allAmount.push(parseFloat(parts[6]));
        }
    });

    earliestDate = allDates[0];
    latestDate = allDates[allDates.length - 1];

    // 计算完整技术指标
    ma5 = calculateMA(allClose, 5);
    ma10 = calculateMA(allClose, 10);
    ma20 = calculateMA(allClose, 20);
    ma60 = calculateMA(allClose, 60);
    volumeMa5 = calculateMA(allVolume, 5);
    volumeMa10 = calculateMA(allVolume, 10);
    amountMa5 = calculateMA(allAmount, 5);
    amountMa10 = calculateMA(allAmount, 10);
    rsi6 = calculateRSI(allClose, 6);
    rsi12 = calculateRSI(allClose, 12);
    rsi24 = calculateRSI(allClose, 24);
    const kdj = calculateKDJ(allHigh, allLow, allClose);
    k = kdj[0]; d = kdj[1]; j = kdj[2];
    const macdRes = calculateMACD(allClose);
    dif = macdRes[0]; dea = macdRes[1]; macd = macdRes[2];

    // 设置初始滑块位置
    if (totalDays <= 60) {
        leftSliderX = 30;
        rightSliderX = 940;
    } else {
        rightSliderX = 940;
        leftSliderX = 30 + 910 * (1 - 60 / totalDays);
    }

    // 绘制初始图表
    updateChartsFromSlider();
    drawTimeline();
    drawSecondTimeline();
}

// 根据滑块位置更新 currentChartData 并重新绘图
function updateChartsFromSlider() {
    const totalPixels = 910;
    const leftRatio = (leftSliderX - 30) / totalPixels;
    const rightRatio = (rightSliderX - 30) / totalPixels;
    let leftIdx = Math.floor(leftRatio * totalDays);
    let rightIdx = Math.floor(rightRatio * totalDays);
    leftIdx = Math.max(0, Math.min(totalDays - 1, leftIdx));
    rightIdx = Math.max(0, Math.min(totalDays - 1, rightIdx));
    if (leftIdx > rightIdx) leftIdx = rightIdx;

    const startDate = allDates[leftIdx];
    const endDate = allDates[rightIdx];

    // 筛选数据
    currentChartData = [];
    currentDates = [];
    currentOpen = [];
    currentClose = [];
    currentHigh = [];
    currentLow = [];
    currentVolume = [];
    currentAmount = [];

    for (let i = leftIdx; i <= rightIdx; i++) {
        currentChartData.push(currentKlineData[i]);
        currentDates.push(allDates[i]);
        currentOpen.push(allOpen[i]);
        currentClose.push(allClose[i]);
        currentHigh.push(allHigh[i]);
        currentLow.push(allLow[i]);
        currentVolume.push(allVolume[i]);
        currentAmount.push(allAmount[i]);
    }

    drawKline();
    drawIndicator();
    drawSecondTimeline(); // 更新第二时间轴刻度
}

// =========================== 【绘图函数】 ===========================
function drawKline() {
    if (!ctxKline) return;
    const w = 970, h = 300;
    ctxKline.clearRect(0, 0, w, h);
    if (currentOpen.length === 0) return;

    const n = currentOpen.length;
    const pad = {top: 20, bottom: 20, left: 30, right: 30};
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const gap = chartW / n;
    const candleW = Math.max(2, Math.min(10, gap * 0.6));
    const minPrice = Math.min(...currentLow);
    const maxPrice = Math.max(...currentHigh);
    const padding = (maxPrice - minPrice) * 0.08 || 1;
    const pMin = minPrice - padding;
    const pMax = maxPrice + padding;
    const priceRange = pMax - pMin;

    // 绘制网格（水平）
    ctxKline.strokeStyle = '#e5e7eb';
    ctxKline.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = pad.top + chartH * i / 4;
        ctxKline.beginPath();
        ctxKline.moveTo(pad.left, y);
        ctxKline.lineTo(w - pad.right, y);
        ctxKline.stroke();
    }

    // 右侧价格轴标签
    ctxKline.fillStyle = '#9ca3af';
    ctxKline.font = '10px sans-serif';
    ctxKline.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
        const y = pad.top + chartH * i / 4;
        const v = pMax - priceRange * i / 4;
        ctxKline.fillText(v.toFixed(2), w - pad.right + 2, y + 3);
    }

    // 绘制均线
    const maData = [ma5, ma10, ma20, ma60];
    const maColors = ['#3b82f6', '#f97316', '#8b5cf6', '#6b7280'];
    const maLabels = ['MA5', 'MA10', 'MA20', 'MA60'];
    for (let mi = 0; mi < 4; mi++) {
        const arr = maData[mi];
        ctxKline.beginPath();
        ctxKline.strokeStyle = maColors[mi];
        ctxKline.lineWidth = 1.2;
        let first = true;
        for (let i = 0; i < n; i++) {
            const fullIdx = allDates.indexOf(currentDates[i]);
            if (fullIdx === -1) continue;
            const val = arr[fullIdx];
            if (val === null || val === undefined) continue;
            const x = pad.left + i * gap + candleW / 2;
            const y = pad.top + (pMax - val) / priceRange * chartH;
            if (first) {
                ctxKline.moveTo(x, y);
                first = false;
            } else {
                ctxKline.lineTo(x, y);
            }
        }
        ctxKline.stroke();
    }

    // 均线图例（左上角）
    const legendY = pad.top + 2;
    maColors.forEach((color, mi) => {
        const idx = allDates.indexOf(currentDates[currentDates.length - 1]);
        const v = maData[mi][idx];
        if (v === null || v === undefined) return;
        const lx = pad.left + mi * 70;
        ctxKline.fillStyle = color;
        ctxKline.font = 'bold 11px sans-serif';
        ctxKline.textAlign = 'left';
        ctxKline.fillText(maLabels[mi] + ':' + v.toFixed(2), lx, legendY + 12);
    });

    // 绘制K线
    for (let i = 0; i < n; i++) {
        const xCenter = pad.left + i * gap + candleW / 2;
        const xLeft = xCenter - candleW / 2;
        const xRight = xCenter + candleW / 2;
        const open = currentOpen[i];
        const close = currentClose[i];
        const high = currentHigh[i];
        const low = currentLow[i];

        const highY = pad.top + (pMax - high) / priceRange * chartH;
        const lowY = pad.top + (pMax - low) / priceRange * chartH;
        const openY = pad.top + (pMax - open) / priceRange * chartH;
        const closeY = pad.top + (pMax - close) / priceRange * chartH;

        const isUp = close >= open;
        const color = isUp ? '#e63946' : '#2f9e6f';

        // 影线
        ctxKline.strokeStyle = color;
        ctxKline.lineWidth = 0.8;
        ctxKline.beginPath();
        ctxKline.moveTo(xCenter, highY);
        ctxKline.lineTo(xCenter, lowY);
        ctxKline.stroke();

        // 实体
        const top = Math.min(openY, closeY);
        const bot = Math.max(openY, closeY);
        ctxKline.fillStyle = color;
        const realW = Math.max(1, candleW * 0.8);
        if (bot - top < 1) {
            ctxKline.fillRect(xCenter - realW / 2, top, realW, 1);
        } else {
            ctxKline.fillRect(xCenter - realW / 2, top, realW, bot - top);
        }
    }
}

function drawIndicator() {
    if (!ctxIndicator) return;
    const w = 970, h = 120;
    ctxIndicator.clearRect(0, 0, w, h);
    const indicatorType = document.querySelector('input[name="indicator"]:checked').value;
    const n = currentOpen.length;
    if (n === 0) return;

    const pad = {top: 10, bottom: 15, left: 30, right: 30};
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const gap = chartW / n;
    const candleW = Math.max(2, Math.min(10, gap * 0.6));

    // 统一网格线
    ctxIndicator.strokeStyle = '#e5e7eb';
    ctxIndicator.lineWidth = 0.5;
    for (let i = 0; i <= 2; i++) {
        const y = pad.top + chartH * i / 2;
        ctxIndicator.beginPath();
        ctxIndicator.moveTo(pad.left, y);
        ctxIndicator.lineTo(w - pad.right, y);
        ctxIndicator.stroke();
    }

    if (indicatorType === '成交量') {
        const maxVol = Math.max(...currentVolume);
        for (let i = 0; i < n; i++) {
            const x = pad.left + i * gap;
            const barH = (currentVolume[i] / maxVol) * chartH;
            const y = pad.top + chartH - barH;
            ctxIndicator.fillStyle = currentClose[i] >= currentOpen[i] ? '#e63946' : '#2f9e6f';
            ctxIndicator.fillRect(x, y, Math.max(1, gap * 0.7), barH);
        }
        // 刻度
        ctxIndicator.fillStyle = '#9ca3af';
        ctxIndicator.font = '10px sans-serif';
        ctxIndicator.textAlign = 'right';
        ctxIndicator.fillText(maxVol.toLocaleString(), w - pad.right + 2, pad.top + 12);
        ctxIndicator.fillText('0', w - pad.right + 2, pad.top + chartH + 3);
    } else if (indicatorType === '成交额') {
        const maxAmt = Math.max(...currentAmount);
        for (let i = 0; i < n; i++) {
            const x = pad.left + i * gap;
            const barH = (currentAmount[i] / maxAmt) * chartH;
            const y = pad.top + chartH - barH;
            ctxIndicator.fillStyle = currentClose[i] >= currentOpen[i] ? '#e63946' : '#2f9e6f';
            ctxIndicator.fillRect(x, y, Math.max(1, gap * 0.7), barH);
        }
        ctxIndicator.fillStyle = '#9ca3af';
        ctxIndicator.font = '10px sans-serif';
        ctxIndicator.textAlign = 'right';
        ctxIndicator.fillText((maxAmt/10).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '(万元)', w - pad.right + 2, pad.top + 12);
        ctxIndicator.fillText('0', w - pad.right + 2, pad.top + chartH + 3);
    } else if (indicatorType === 'RSI') {
        const rsiData = [rsi6, rsi12, rsi24];
        const colors = ['#3b82f6', '#f97316', '#2f9e6f'];
        // 20/50/80参考线
        ctxIndicator.strokeStyle = '#d1d5db';
        ctxIndicator.lineWidth = 0.5;
        ctxIndicator.setLineDash([3, 3]);
        [20, 50, 80].forEach(v => {
            const y = pad.top + chartH - (v / 100 * chartH);
            ctxIndicator.beginPath();
            ctxIndicator.moveTo(pad.left, y);
            ctxIndicator.lineTo(w - pad.right, y);
            ctxIndicator.stroke();
        });
        ctxIndicator.setLineDash([]);
        ctxIndicator.fillStyle = '#9ca3af';
        ctxIndicator.font = '10px sans-serif';
        ctxIndicator.textAlign = 'right';
        ctxIndicator.fillText('80', w - pad.right + 2, pad.top + chartH * 0.2 + 3);
        ctxIndicator.fillText('50', w - pad.right + 2, pad.top + chartH * 0.5 + 3);
        ctxIndicator.fillText('20', w - pad.right + 2, pad.top + chartH * 0.8 + 3);
        for (let idx = 0; idx < 3; idx++) {
            ctxIndicator.beginPath();
            ctxIndicator.strokeStyle = colors[idx];
            ctxIndicator.lineWidth = 1.2;
            let first = true;
            for (let i = 0; i < n; i++) {
                const fullIdx = allDates.indexOf(currentDates[i]);
                if (fullIdx === -1) continue;
                const val = rsiData[idx][fullIdx];
                if (val === null) continue;
                const x = pad.left + i * gap;
                const y = pad.top + chartH - (val / 100 * chartH);
                if (first) {
                    ctxIndicator.moveTo(x, y);
                    first = false;
                } else {
                    ctxIndicator.lineTo(x, y);
                }
            }
            ctxIndicator.stroke();
        }
    } else if (indicatorType === 'KDJ') {
        const kdjData = [k, d, j];
        const colors = ['#3b82f6', '#f97316', '#8b5cf6'];
        // 20/50/80参考线
        ctxIndicator.strokeStyle = '#d1d5db';
        ctxIndicator.lineWidth = 0.5;
        ctxIndicator.setLineDash([3, 3]);
        [20, 50, 80].forEach(v => {
            const y = pad.top + chartH - (v / 100 * chartH);
            ctxIndicator.beginPath();
            ctxIndicator.moveTo(pad.left, y);
            ctxIndicator.lineTo(w - pad.right, y);
            ctxIndicator.stroke();
        });
        ctxIndicator.setLineDash([]);
        ctxIndicator.fillStyle = '#9ca3af';
        ctxIndicator.font = '10px sans-serif';
        ctxIndicator.textAlign = 'right';
        ctxIndicator.fillText('80', w - pad.right + 2, pad.top + chartH * 0.2 + 3);
        ctxIndicator.fillText('50', w - pad.right + 2, pad.top + chartH * 0.5 + 3);
        ctxIndicator.fillText('20', w - pad.right + 2, pad.top + chartH * 0.8 + 3);
        for (let idx = 0; idx < 3; idx++) {
            ctxIndicator.beginPath();
            ctxIndicator.strokeStyle = colors[idx];
            ctxIndicator.lineWidth = 1.2;
            let first = true;
            for (let i = 0; i < n; i++) {
                const fullIdx = allDates.indexOf(currentDates[i]);
                if (fullIdx === -1) continue;
                let val = kdjData[idx][fullIdx];
                if (val === null) continue;
                val = Math.min(100, Math.max(0, val));
                const x = pad.left + i * gap;
                const y = pad.top + chartH - (val / 100 * chartH);
                if (first) {
                    ctxIndicator.moveTo(x, y);
                    first = false;
                } else {
                    ctxIndicator.lineTo(x, y);
                }
            }
            ctxIndicator.stroke();
        }
    } else if (indicatorType === 'MACD') {
        const difVals = [], deaVals = [], macdVals = [];
        for (let i = 0; i < n; i++) {
            const fullIdx = allDates.indexOf(currentDates[i]);
            if (fullIdx !== -1) {
                difVals.push(dif[fullIdx]);
                deaVals.push(dea[fullIdx]);
                macdVals.push(macd[fullIdx]);
            }
        }
        const allVals = difVals.concat(deaVals).concat(macdVals).filter(v => v !== null);
        const macdMin = Math.min(...allVals);
        const macdMax = Math.max(...allVals);
        const macdRange = macdMax - macdMin || 1;

        // MACD柱
        for (let i = 0; i < n; i++) {
            const fullIdx = allDates.indexOf(currentDates[i]);
            if (fullIdx === -1) continue;
            const val = macd[fullIdx];
            if (val === null) continue;
            const x = pad.left + i * gap;
            const barH = Math.abs(val) / macdRange * chartH;
            const y = val >= 0 ? pad.top + chartH / 2 - barH : pad.top + chartH / 2;
            ctxIndicator.fillStyle = val >= 0 ? '#e63946' : '#2f9e6f';
            ctxIndicator.fillRect(x, y, Math.max(1, gap * 0.6), Math.max(1, barH));
        }

        // DIF线
        ctxIndicator.beginPath();
        ctxIndicator.strokeStyle = '#3b82f6';
        ctxIndicator.lineWidth = 1.2;
        let first = true;
        for (let i = 0; i < n; i++) {
            const fullIdx = allDates.indexOf(currentDates[i]);
            if (fullIdx === -1) continue;
            const val = dif[fullIdx];
            if (val === null) continue;
            const x = pad.left + i * gap;
            const y = pad.top + chartH / 2 - val / macdRange * chartH / 2;
            if (first) {
                ctxIndicator.moveTo(x, y);
                first = false;
            } else {
                ctxIndicator.lineTo(x, y);
            }
        }
        ctxIndicator.stroke();

        // DEA线
        ctxIndicator.beginPath();
        ctxIndicator.strokeStyle = '#f97316';
        ctxIndicator.lineWidth = 1.2;
        first = true;
        for (let i = 0; i < n; i++) {
            const fullIdx = allDates.indexOf(currentDates[i]);
            if (fullIdx === -1) continue;
            const val = dea[fullIdx];
            if (val === null) continue;
            const x = pad.left + i * gap;
            const y = pad.top + chartH / 2 - val / macdRange * chartH / 2;
            if (first) {
                ctxIndicator.moveTo(x, y);
                first = false;
            } else {
                ctxIndicator.lineTo(x, y);
            }
        }
        ctxIndicator.stroke();

        // 刻度
        ctxIndicator.fillStyle = '#9ca3af';
        ctxIndicator.font = '10px sans-serif';
        ctxIndicator.textAlign = 'right';
        ctxIndicator.fillText(macdMax.toFixed(2), w - pad.right + 2, pad.top + 12);
        ctxIndicator.fillText('0', w - pad.right + 2, pad.top + chartH / 2 + 3);
        ctxIndicator.fillText(macdMin.toFixed(2), w - pad.right + 2, pad.top + chartH + 3);
    }
}

function drawTimeline() {
    if (!ctxTimeline) return;
    const w = 970, h = 50;
    ctxTimeline.clearRect(0, 0, w, h);
    // 轨道
    ctxTimeline.fillStyle = '#e5e7eb';
    ctxTimeline.fillRect(30, h / 2 - 3, 910, 6);
    ctxTimeline.fillStyle = '#d1d5db';
    ctxTimeline.fillRect(30, h / 2 - 3, rightSliderX - 30, 6);
    // 左滑块
    ctxTimeline.fillStyle = '#6b7280';
    ctxTimeline.beginPath();
    ctxTimeline.arc(leftSliderX, h / 2, 7, 0, Math.PI * 2);
    ctxTimeline.fill();
    // 右滑块
    ctxTimeline.fillStyle = '#e63946';
    ctxTimeline.beginPath();
    ctxTimeline.arc(rightSliderX, h / 2, 7, 0, Math.PI * 2);
    ctxTimeline.fill();
    // 日期标签
    ctxTimeline.fillStyle = '#9ca3af';
    ctxTimeline.font = '9px sans-serif';
    ctxTimeline.textAlign = 'center';
    ctxTimeline.fillText(earliestDate || '', 40, h - 4);
    ctxTimeline.fillText(latestDate || '', w - 40, h - 4);
}

function drawSecondTimeline() {
    if (!ctxSecondTimeline) return;
    ctxSecondTimeline.clearRect(0, 0, 970, 40);
    // 绘制轴线
    ctxSecondTimeline.strokeStyle = '#e5e7eb';
    ctxSecondTimeline.lineWidth = 1;
    ctxSecondTimeline.beginPath();
    ctxSecondTimeline.moveTo(10, 10);
    ctxSecondTimeline.lineTo(960, 10);
    ctxSecondTimeline.stroke();

    if (currentDates.length === 0) return;
    const numSegments = 8;
    for (let i = 0; i <= numSegments; i++) {
        const x = 10 + i * 950 / numSegments;
        ctxSecondTimeline.strokeStyle = '#e5e7eb';
        ctxSecondTimeline.lineWidth = 1;
        ctxSecondTimeline.beginPath();
        ctxSecondTimeline.moveTo(x, 10);
        ctxSecondTimeline.lineTo(x, 15);
        ctxSecondTimeline.stroke();

        let idx = Math.floor(i / numSegments * (currentDates.length - 1));
        const rawDate = currentDates[idx];
        let displayDate = rawDate;
        let offsetX = x - 30;

        if (i === 0) {
            if (rawDate && rawDate.length === 8) {
                displayDate = rawDate.substring(4, 8);
            }
            offsetX = x - 8;
        } else if (i === numSegments) {
            if (rawDate && rawDate.length === 8) {
                displayDate = rawDate.substring(4, 8);
            }
            offsetX = x - 22;
        }

        ctxSecondTimeline.fillStyle = '#9ca3af';
        ctxSecondTimeline.font = '10px sans-serif';
        ctxSecondTimeline.fillText(displayDate, offsetX, 30);
    }
}

// =========================== 【鼠标交互】 ===========================
function handleMouseMove(e) {
    const rectK = canvasKline.getBoundingClientRect();
    const rectI = canvasIndicator.getBoundingClientRect();
    const mouseX = e.clientX;
    const mouseY = e.clientY;

    // 判断鼠标是否在K线图或指标图区域内
    const inKline = (mouseX >= rectK.left && mouseX <= rectK.right && mouseY >= rectK.top && mouseY <= rectK.bottom);
    const inIndicator = (mouseX >= rectI.left && mouseX <= rectI.right && mouseY >= rectI.top && mouseY <= rectI.bottom);

    if (!inKline && !inIndicator) {
        // 离开区域，清除线条，恢复基本信息
        if (verticalLineKline) {
            ctxKline.clearRect(0, 0, 970, 300);
            drawKline();
            verticalLineKline = null;
        }
        securityInfoDiv.style.display = 'block';
        hoverInfoDiv.style.display = 'none';
        return;
    }

    // 计算相对坐标
    let canvasX, canvasY;
    if (inKline) {
        canvasX = mouseX - rectK.left;
        canvasY = mouseY - rectK.top;
    } else {
        canvasX = mouseX - rectI.left;
        canvasY = mouseY - rectI.top;
    }

    const n = currentOpen.length;
    if (n === 0) return;

    const barWidth = 970 / n * 0.8;
    const barSpacing = 970 / n * 0.2;
    const dataIndex = Math.floor(canvasX / (barWidth + barSpacing));
    if (dataIndex < 0 || dataIndex >= n) return;

    const xCenter = dataIndex * (barWidth + barSpacing) + barWidth/2;

    // 绘制垂直线
    ctxKline.clearRect(0, 0, 970, 300);
    drawKline();
    ctxKline.beginPath();
    ctxKline.strokeStyle = '#6b7280';
    ctxKline.setLineDash([2, 2]);
    ctxKline.moveTo(xCenter, 0);
    ctxKline.lineTo(xCenter, 300);
    ctxKline.stroke();
    ctxKline.setLineDash([]);

    // 在指标图上绘制垂直线
    ctxIndicator.clearRect(0, 0, 970, 120);
    drawIndicator();
    ctxIndicator.beginPath();
    ctxIndicator.strokeStyle = '#6b7280';
    ctxIndicator.setLineDash([2, 2]);
    ctxIndicator.moveTo(xCenter, 0);
    ctxIndicator.lineTo(xCenter, 120);
    ctxIndicator.stroke();
    ctxIndicator.setLineDash([]);

    // 显示均线值在K线图顶部
    const fullIdx = allDates.indexOf(currentDates[dataIndex]);
    if (fullIdx !== -1) {
        const maVals = [ma5[fullIdx], ma10[fullIdx], ma20[fullIdx], ma60[fullIdx]];
        const colors = ['#3b82f6', '#f97316', '#8b5cf6', '#6b7280'];
        ctxKline.font = '11px sans-serif';
        const xPositions = [400, 490, 580, 670];
        maVals.forEach((val, idx) => {
            if (val !== null) {
                ctxKline.fillStyle = colors[idx];
                ctxKline.fillText(`MA${[5,10,20,60][idx]}:${val.toFixed(2)}`, xPositions[idx], 20);
            }
        });
    }

    // 更新信息面板：显示交易数据 + 技术指标值
    const dataStr = currentChartData[dataIndex];
    const parts = dataStr.split(',');
    if (parts.length >= 11) {
        securityInfoDiv.style.display = 'none';
        hoverInfoDiv.style.display = 'block';

        // 日期格式化：20240102 -> 2024年01月02日
        const rawDate__ = parts[0];
        let formattedDate__ = rawDate__;
        if (rawDate__.length === 8) {
            formattedDate__ = `${rawDate__.substring(0, 4)}年${rawDate__.substring(4, 6)}月${rawDate__.substring(6, 8)}日`;
        }

        // 成交额单位转换（千元 -> 万元，保留两位小数并加千分符）
        const amountInWan = (parseFloat(parts[6]) / 10).toFixed(2);
        const formattedAmount = amountInWan.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

        // 换手率保留两位小数
        const turnoverFormatted__ = parseFloat(parts[10]).toFixed(2);

        // 构建交易数据HTML
        let html = `
            <p>日期: ${formattedDate__}</p>
            <p>开盘价: ${parts[1]}</p>
            <p>收盘价: ${parts[2]}</p>
            <p>最高价: ${parts[3]}</p>
            <p>最低价: ${parts[4]}</p>
            <p>涨跌额: ${parts[9]}</p>
            <p>涨跌幅: ${parts[8]}%</p>
            <p>成交量: ${parseInt(parts[5]).toLocaleString()} (手)</p>
            <p>成交额: ${formattedAmount} (万元)</p>
            <p>振幅: ${parts[7]}%</p>
            <p>换手率: ${turnoverFormatted__}%</p>
            <hr>
        `;

        // 生成指标值文本
        const indicatorType = document.querySelector('input[name="indicator"]:checked').value;
        let indicatorText = '';
        if (fullIdx !== -1) {
            if (indicatorType === '成交量') {
                const vol = allVolume[fullIdx];
                const vma5 = volumeMa5[fullIdx];
                const vma10 = volumeMa10[fullIdx];
                indicatorText = `当前技术指标：成交量\nVOL: ${vol.toLocaleString()}`;
                if (vma5) indicatorText += `\nMA5: ${vma5.toLocaleString()}`;
                if (vma10) indicatorText += `\nMA10: ${vma10.toLocaleString()}`;
            } else if (indicatorType === '成交额') {
                const amt = allAmount[fullIdx] / 10;
                const ama5 = amountMa5[fullIdx] ? amountMa5[fullIdx]/10 : null;
                const ama10 = amountMa10[fullIdx] ? amountMa10[fullIdx]/10 : null;
                indicatorText = `当前技术指标：成交额\n成交额: ${amt.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}万元`;
                if (ama5) indicatorText += `\nMA5: ${ama5.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}万元`;
                if (ama10) indicatorText += `\nMA10: ${ama10.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}万元`;
            } else if (indicatorType === 'RSI') {
                indicatorText = `当前技术指标：RSI\nRSI6: ${rsi6[fullIdx]?.toFixed(2) || ''}\nRSI12: ${rsi12[fullIdx]?.toFixed(2) || ''}\nRSI24: ${rsi24[fullIdx]?.toFixed(2) || ''}`;
            } else if (indicatorType === 'KDJ') {
                indicatorText = `当前技术指标：KDJ\nK: ${k[fullIdx]?.toFixed(2) || ''}\nD: ${d[fullIdx]?.toFixed(2) || ''}\nJ: ${j[fullIdx]?.toFixed(2) || ''}`;
            } else if (indicatorType === 'MACD') {
                indicatorText = `当前技术指标：MACD\nDIF: ${dif[fullIdx]?.toFixed(3) || ''}\nDEA: ${dea[fullIdx]?.toFixed(3) || ''}\nMACD: ${macd[fullIdx]?.toFixed(3) || ''}`;
            }
        }

        // 将指标文本转换为HTML（换行转<br>）
        if (indicatorText) {
            html += '<pre style="margin:5px 0; font-family:inherit; font-size:13px;">' + indicatorText.replace(/\n/g, '<br>') + '</pre>';
        }

        hoverInfoDiv.innerHTML = html;
    }
}

function handleMouseLeave(e) {
    // 鼠标离开图表区域，清除线条并恢复基本信息
    if (verticalLineKline) {
        ctxKline.clearRect(0, 0, 970, 300);
        drawKline();
        verticalLineKline = null;
    }
    securityInfoDiv.style.display = 'block';
    hoverInfoDiv.style.display = 'none';
}

// =========================== 【滑块事件】 ===========================
function getTimelineX(clientX) {
    const rect = canvasTimeline.getBoundingClientRect();
    const scaleX = 970 / rect.width; // 处理 canvas 缩放
    return (clientX - rect.left) * scaleX;
}

function handleTimelineMouseDown(e) {
    const x = getTimelineX(e.clientX);
    const y = (e.clientY - canvasTimeline.getBoundingClientRect().top) * (50 / canvasTimeline.getBoundingClientRect().height);
    const hitRadius = 12; // 增大点击区域

    const distL = Math.abs(x - leftSliderX);
    const distR = Math.abs(x - rightSliderX);

    if (distL < hitRadius && y >= 5 && y <= 45) {
        draggingSlider = 'left';
    } else if (distR < hitRadius && y >= 5 && y <= 45) {
        draggingSlider = 'right';
    }
}

function handleTimelineMouseMove(e) {
    const x = getTimelineX(e.clientX);
    const y = (e.clientY - canvasTimeline.getBoundingClientRect().top) * (50 / canvasTimeline.getBoundingClientRect().height);
    const hitRadius = 12;

    // 悬停时改变光标样式
    const distL = Math.abs(x - leftSliderX);
    const distR = Math.abs(x - rightSliderX);
    if ((distL < hitRadius && y >= 5 && y <= 45) || (distR < hitRadius && y >= 5 && y <= 45)) {
        canvasTimeline.style.cursor = 'ew-resize';
    } else {
        canvasTimeline.style.cursor = 'default';
    }

    if (!draggingSlider) return;
    let nx = Math.max(30, Math.min(940, x));
    if (draggingSlider === 'left') {
        if (nx > rightSliderX) nx = rightSliderX;
        leftSliderX = nx;
    } else {
        if (nx < leftSliderX) nx = leftSliderX;
        rightSliderX = nx;
    }
    drawTimeline();
}

function handleTimelineMouseUp(e) {
    if (draggingSlider) {
        updateChartsFromSlider();
        drawTimeline();
        drawSecondTimeline();
        drawKline();
        drawIndicator();
        draggingSlider = null;
        canvasTimeline.style.cursor = 'default';
    }
}

// =========================== 【触摸事件（移动端）】 ===========================
function handleTimelineTouchStart(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const x = getTimelineX(touch.clientX);
    const y = (touch.clientY - canvasTimeline.getBoundingClientRect().top) * (50 / canvasTimeline.getBoundingClientRect().height);
    const hitRadius = 16; // 触摸区域更大

    const distL = Math.abs(x - leftSliderX);
    const distR = Math.abs(x - rightSliderX);

    if (distL < hitRadius && y >= 0 && y <= 50) {
        draggingSlider = 'left';
    } else if (distR < hitRadius && y >= 0 && y <= 50) {
        draggingSlider = 'right';
    }
}

function handleTimelineTouchMove(e) {
    e.preventDefault();
    if (!draggingSlider) return;
    const touch = e.touches[0];
    const x = getTimelineX(touch.clientX);
    let nx = Math.max(30, Math.min(940, x));
    if (draggingSlider === 'left') {
        if (nx > rightSliderX) nx = rightSliderX;
        leftSliderX = nx;
    } else {
        if (nx < leftSliderX) nx = leftSliderX;
        rightSliderX = nx;
    }
    drawTimeline();
}

function handleTimelineTouchEnd(e) {
    if (draggingSlider) {
        updateChartsFromSlider();
        drawTimeline();
        drawSecondTimeline();
        drawKline();
        drawIndicator();
        draggingSlider = null;
    }
}

// =========================== 【导出历史数据功能】 ===========================
function exportHistoryData__() {
    if (!currentChartData || currentChartData.length === 0) {
        alert('没有可导出的数据');
        return;
    }
    
    // 构建二维数组数据
    const dataArray__ = [];
    // 表头
    dataArray__.push(['日期', '开盘', '收盘', '最高', '最低', '成交量(手)', '成交额(万元)', '振幅(%)', '涨跌幅(%)', '涨跌额', '换手率(%)']);
    // 数据行
    currentChartData.forEach(item__ => {
        const parts__ = item__.split(',');
        if (parts__.length >= 11) {
            // 成交额转换为万元
            const amountInWan__ = (parseFloat(parts__[6]) / 10).toFixed(2);
            dataArray__.push([
                parts__[0],
                parseFloat(parts__[1]),
                parseFloat(parts__[2]),
                parseFloat(parts__[3]),
                parseFloat(parts__[4]),
                parseInt(parts__[5]),
                parseFloat(amountInWan__),
                parseFloat(parts__[7]),
                parseFloat(parts__[8]),
                parseFloat(parts__[9]),
                parseFloat(parts__[10])
            ]);
        }
    });
    
    // 使用 SheetJS 生成 xlsx 文件
    const wb__ = XLSX.utils.book_new();
    const ws__ = XLSX.utils.aoa_to_sheet(dataArray__);
    XLSX.utils.book_append_sheet(wb__, ws__, '历史数据');
    
    // 导出文件
    XLSX.writeFile(wb__, `历史数据表-${window.securityInfo.name}.xlsx`);
}

// =========================== 【初始化】 ===========================
window.onload = async function() {
    canvasKline = document.getElementById('canvas-kline');
    canvasIndicator = document.getElementById('canvas-indicator');
    canvasTimeline = document.getElementById('canvas-timeline');
    canvasSecondTimeline = document.getElementById('canvas-second-timeline');
    ctxKline = canvasKline.getContext('2d');
    ctxIndicator = canvasIndicator.getContext('2d');
    ctxTimeline = canvasTimeline.getContext('2d');
    ctxSecondTimeline = canvasSecondTimeline.getContext('2d');

    // 加载初始数据 (日K)
    await loadKlineData('101');

    // 绑定事件 - K线/指标悬停
    canvasKline.addEventListener('mousemove', handleMouseMove);
    canvasIndicator.addEventListener('mousemove', handleMouseMove);
    canvasKline.addEventListener('mouseleave', handleMouseLeave);
    canvasIndicator.addEventListener('mouseleave', handleMouseLeave);

    // 绑定事件 - 时间轴滑块
    canvasTimeline.addEventListener('mousedown', handleTimelineMouseDown);
    // 使用 document 级别的 mousemove/mouseup 确保拖动时不会丢失事件
    document.addEventListener('mousemove', handleTimelineMouseMove);
    document.addEventListener('mouseup', handleTimelineMouseUp);
    canvasTimeline.addEventListener('mouseleave', function(e) {
        // 鼠标离开画布时重置光标，但不中断拖拽
        if (!draggingSlider) {
            canvasTimeline.style.cursor = 'default';
        }
    });

    // 触摸事件支持（移动端）
    canvasTimeline.addEventListener('touchstart', handleTimelineTouchStart, {passive: false});
    document.addEventListener('touchmove', handleTimelineTouchMove, {passive: false});
    document.addEventListener('touchend', handleTimelineTouchEnd);

    // K线类型切换
    document.querySelectorAll('input[name="kline_type"]').forEach(radio => {
        radio.addEventListener('change', async function() {
            const code = klineNameToCode(this.value);
            currentKlineType = code;
            await loadKlineData(code);
        });
    });

    // 指标切换
    document.querySelectorAll('input[name="indicator"]').forEach(radio => {
        radio.addEventListener('change', function() {
            drawIndicator();
        });
    });

    // AI分析按钮跳转
    document.getElementById('btn-ai').addEventListener('click', function() {
        const url = `/ai?code=${encodeURIComponent(window.securityInfo.code)}&name=${encodeURIComponent(window.securityInfo.name)}&type=${encodeURIComponent(window.securityInfo.type)}&exchange=${encodeURIComponent(window.securityInfo.exchange)}`;
        window.open(url, '_blank');
    });

    // 导出历史数据按钮
    document.getElementById('btn-export-history').addEventListener('click', exportHistoryData__);

    // 基本面信息按钮
    document.getElementById('btn-fundamental').addEventListener('click', function() {
        const url = `/fundamental?code=${encodeURIComponent(window.securityInfo.code)}&name=${encodeURIComponent(window.securityInfo.name)}`;
        window.open(url, '_blank');
    });

    // 工具箱按钮
    document.getElementById('btn-toolbox').addEventListener('click', function() {
        const url = `/toolbox?code=${encodeURIComponent(window.securityInfo.code)}&name=${encodeURIComponent(window.securityInfo.name)}`;
        window.open(url, '_blank');
    });
};