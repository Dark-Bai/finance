// =========================== 【全局变量】 ===========================
let conversationId = null;
let securityInfo = window.securityInfo || {};

// DOM 元素
const outputText = document.getElementById('output-text');
const inputText = document.getElementById('input-text');
const btnSend = document.getElementById('btn-send');
const btnClear = document.getElementById('btn-clear');
const btnReport = document.getElementById('btn-report');
const btnExportData = document.getElementById('btn-export-data');
const btnClose = document.getElementById('btn-close');
const presetBtns = document.querySelectorAll('.preset-btn');

// =========================== 【初始化】 ===========================
async function initChat() {
    // 显示加载信息
    appendOutput(`AI证券分析助手启动中...\n`);
    appendOutput(`证券: ${securityInfo.name} (${securityInfo.code})\n`);
    appendOutput(`类型: ${securityInfo.type} | 板块: ${securityInfo.exchange}\n`);
    appendOutput(`正在加载数据...\n`);

    try {
        const response = await fetch('/ai/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(securityInfo)
        });
        const data = await response.json();
        if (data.error) {
            appendOutput(`初始化失败: ${data.error}\n`);
            return;
        }
        conversationId = data.conversation_id;
        appendOutput(`数据加载完成，包含完整的历史交易数据和技术指标数据。\n`);
        appendOutput(`您可以开始提问，或使用右侧的预设问题快速开始分析。\n`);
        appendOutput(`------------------------------------------------\n\n`);
    } catch (err) {
        appendOutput(`网络错误: ${err}\n`);
    }
}

// =========================== 【工具函数】 ===========================
function appendOutput(text) {
    outputText.value += text;
    outputText.scrollTop = outputText.scrollHeight; // 滚动到底部
}

function clearOutput() {
    outputText.value = '';
}

// =========================== 【发送消息】 ===========================
async function sendMessage(message) {
    if (!message.trim()) return;
    if (!conversationId) {
        appendOutput('错误：会话未初始化\n');
        return;
    }

    // 显示用户消息
    appendOutput(`用户: ${message}\n`);
    appendOutput(`------------------------------\n`);

    // 清空输入框
    inputText.value = '';

    // 显示等待
    appendOutput(`AI分析中...\n`);

    try {
        const response = await fetch('/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                message: message
            })
        });
        const data = await response.json();
        // 移除“AI分析中...”行（最后两行？简单方式：重新刷新输出，但这里我们删除最后一行）
        let lines = outputText.value.split('\n');
        if (lines[lines.length-2] === 'AI分析中...') {
            lines.splice(lines.length-2, 1);
            outputText.value = lines.join('\n');
        } else {
            // 如果格式不符，直接覆盖最后一行
            outputText.value = outputText.value.substring(0, outputText.value.lastIndexOf('AI分析中...'));
        }

        if (data.error) {
            appendOutput(`错误: ${data.error}\n`);
        } else {
            appendOutput(`AI分析师: ${data.response}\n`);
        }
        appendOutput(`==================================================\n\n`);
    } catch (err) {
        appendOutput(`网络错误: ${err}\n`);
    }
}

// =========================== 【清空对话】 ===========================
async function clearConversation() {
    if (!conversationId) return;
    try {
        const response = await fetch('/ai/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: conversationId })
        });
        const data = await response.json();
        if (data.success) {
            clearOutput();
            appendOutput(`对话已清空，重新开始...\n`);
            appendOutput(`证券: ${securityInfo.name} (${securityInfo.code})\n`);
            appendOutput(`------------------------------------------------\n\n`);
        } else {
            appendOutput(`清空失败: ${data.error}\n`);
        }
    } catch (err) {
        appendOutput(`网络错误: ${err}\n`);
    }
}

// =========================== 【生成报告】 ===========================
async function generateReport() {
    if (!conversationId) return;
    appendOutput(`正在生成专业分析报告...\n`);
    try {
        const response = await fetch('/ai/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: conversationId })
        });
        const data = await response.json();
        if (data.report) {
            // 移除最后一行“正在生成...”
            let lines = outputText.value.split('\n');
            if (lines[lines.length-2] === '正在生成专业分析报告...') {
                lines.splice(lines.length-2, 1);
                outputText.value = lines.join('\n');
            }
            appendOutput(`专业分析报告：\n${data.report}\n`);
            appendOutput(`==================================================\n\n`);
            // 可选：提供下载
            const blob = new Blob([data.report], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${securityInfo.code}_${securityInfo.name}_分析报告.txt`;
            a.click();
            URL.revokeObjectURL(url);
        } else {
            appendOutput(`生成报告失败: ${data.error}\n`);
        }
    } catch (err) {
        appendOutput(`网络错误: ${err}\n`);
    }
}

// =========================== 【导出数据】 ===========================
async function exportData() {
    if (!conversationId) return;
    try {
        const response = await fetch('/ai/export_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: conversationId })
        });
        if (!response.ok) {
            const err = await response.json();
            appendOutput(`导出失败: ${err.error}\n`);
            return;
        }
        // 处理文件下载
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${securityInfo.code}_${securityInfo.name}_完整证券数据.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        appendOutput(`证券数据导出成功\n`);
    } catch (err) {
        appendOutput(`网络错误: ${err}\n`);
    }
}

// =========================== 【事件绑定】 ===========================
btnSend.addEventListener('click', () => {
    sendMessage(inputText.value);
});

inputText.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(inputText.value);
    }
});

btnClear.addEventListener('click', clearConversation);

btnReport.addEventListener('click', generateReport);

btnExportData.addEventListener('click', exportData);

btnClose.addEventListener('click', () => {
    window.close(); // 可能被浏览器阻止，备选跳转首页
    window.location.href = '/';
});

presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const question = btn.getAttribute('data-question');
        inputText.value = question;
        sendMessage(question);
    });
});

// =========================== 【启动】 ===========================
initChat();