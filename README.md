# 行情选股 DSL 到高性能 Doris SQL 的自动化编译系统

![Python](https://img.shields.io/badge/python-3.10+-green)
![DuckDB](https://img.shields.io/badge/DuckDB-embedded-blue)
![Apache Doris](https://img.shields.io/badge/Doris-2.1.11-orange)
![Flask](https://img.shields.io/badge/Flask-2.x-red)
![Status](https://img.shields.io/badge/status-竞赛完成-success)

**面向 A 股市场的类 SQL 选股 DSL（领域特定语言）编译器**，自动翻译为高性能 SQL 在 Doris 数据仓库执行，支持历史时序分析、技术指标计算、风险筛选等多维选股策略。

---

## 核心特性

| 特性 | 说明 |
|---|---|
| **类 SQL DSL** | 无需编写 SQL，用接近自然语言的表达式描述选股条件 |
| **双后端支持** | 开发用 DuckDB（本地），生产用 Doris（分布式），代码零修改切换 |
| **条件下推** | 全部筛选逻辑编译为一条 SQL 在数据库端执行，性能优于 pandas 全量拉取方案 |
| **历史时序分析** | 内置 MA、区间涨幅、N 日最高/最低、连涨/连跌、创新高/低等 8 类历史函数 |
| **风险精准识别** | `ST`（含 ST 与 *ST）、`*ST`（纯 *ST）、`非风险警示股` 语义精确分离 |
| **可视化筛选** | Web 界面支持表单筛选 + DSL 面板双入口，结果实时渲染 |
| **K线图表** | Canvas 自绘日/周/月 K 线 + 均线 + MACD + KDJ + RSI |
| **基本面分析** | 财报数据、估值模型、股东信息、多因子估值综合评级 |

---

## 目录

- [快速开始](#快速开始)
- [DSL 语法速查](#dsl-语法速查)
- [系统架构](#系统架构)
- [数据库说明](#数据库说明)
- [开发命令](#开发命令)
- [项目结构](#项目结构)
- [已知限制](#已知限制)
- [技术亮点](#技术亮点)

---

## 快速开始

### 环境要求

- Python 3.10+
- (可选) Apache Doris 2.1.x — 生产模式

### 安装

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo/dsl-stock-screener

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 启动（DuckDB 模式）

```bash
cd dsl-stock-screener
python app.py
```

访问 http://127.0.0.1:5000

### 切换 Doris 模式

```bash
# 1. 启动 Doris（需要 sudo）
sudo bash -c 'export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64; /home/alan/doris/fe/bin/start_fe.sh --daemon'
sleep 8
sudo bash -c 'export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64; /home/alan/doris/be/bin/start_be.sh --daemon'
sleep 15

# 2. 切 Doris 模式启动
export STOCK_DB_TYPE=doris
python app.py
```

---

## DSL 语法速查

DSL 面板（首页右侧）可直接输入以下表达式：

```dsl
-- 基础筛选
行业 = "银行" AND 市盈率 < 8 AND 市净率 < 1
名称 包含 "科技"
行业 IN ("银行", "证券", "保险")
交易所 = "上证"

-- 风险筛选
ST                    -- 含 ST 与 *ST
*ST                   -- 仅 *ST
NOT ST                -- 排除所有风险股
ST AND NOT *ST        -- 仅纯 ST（不含 *ST）

-- 历史函数
MA(收盘价, 5) > MA(收盘价, 20)     -- 均线多头
区间涨幅(20) > 15                    -- 20 日涨幅超 15%
创新高(120)                          -- 创 120 日新高
N日最高(60) * 0.98 > 收盘价          -- 接近 60 日最高
连涨(3) AND 换手率 > 5               -- 连续上涨 + 放量

-- 组合
收盘价 >= N日最高(60) * 0.98 AND NOT ST AND 行业 IN ("银行","证券")
```

> 完整语法帮助点击 DSL 面板的 **"语法帮助"** 按钮，或查阅 [DSL语法帮助.md](./dsl-stock-screener/DSL语法帮助.md)

---

## 系统架构

```
前端（HTML + Canvas K线）
    ↓ HTTP
Flask 后端 (app.py)
    ↓ 调用
DSL 编译器 (dsl_engine.py)    ← 核心交付物
    ↓ 生成 SQL
DuckDB / Doris（环境变量切换）
    ↑ 写入
数据管道 (update_db.py)       ← Tushare API
```

**五阶段编译流水线**：词法分析（Lexer） → 语法分析（Parser） → 语义检查 → 代码生成（CodeGen） → 执行

- [系统架构详解](./系统架构详解.md)

---

## 数据库说明

### DuckDB（开发模式）

本地嵌入数据库 `instance/stock_data.duckdb`（约 1.5 GB）

| 表名 | 行数 | 说明 |
|---|---|---|
| 基本信息表 | 5,531 | 股票静态信息 |
| 当日信息表 | 5,526 | 最新交易日快照 |
| 日度信息表 | 18,030,339 | 全部历史日K |
| 周度信息表 | 3,812,243 | 周K 数据 |
| 月度信息表 | 907,112 | 月K 数据 |

### Doris（生产模式）

单节点 Apache Doris 2.1.11，数据通过迁移脚本同步：

```bash
python migrate_to_doris.py
```

| 表名 | 行数 |
|---|---|
| stock_basic | 5,531 |
| daily_basic | 5,526 |
| daily_kline | 18,030,339 |
| weekly_kline | 3,812,243 |
| monthly_kline | 907,112 |

---

## 开发命令

```bash
# ─── DuckDB 模式（默认） ───
cd dsl-stock-screener && python app.py

# ─── Doris 模式 ───
export STOCK_DB_TYPE=doris && cd dsl-stock-screener && python app.py

# ─── DSL 探针（无需数据库） ───
venv/bin/python3 -c "
import dsl_engine as de
print(de.translate('行业 = \"银行\" AND 市盈率 < 8')['where'])
"

# ─── 双后端对拍 ───
# 见 排查方案.md 附录探针脚本

# ─── 数据更新 ───
python update_db.py
```

---

## 项目结构

```
dsl-stock-screener/
├── app.py                       # Flask 后端 (~2863 行)
├── dsl_engine.py                # DSL→SQL 编译器 (~766 行，核心交付物)
├── update_db.py                 # 数据导入管道（~812 行，Tushare→DuckDB）
├── db.py                        # DuckDB / Doris 双后端连接（~95 行）
├── migrate_to_doris.py          # DuckDB→Doris 迁移脚本（~220 行）
├── doris_schema.sql             # Doris 建表 DDL（5 张英文表，重建时参考）
├── DSL语法帮助.md                # DSL 完整语法文档
├── 代码变更日志.md                # 代码变更按时间线归档
├── 系统架构详解.md                # 融合版架构文档（面向评委/队友）
├── Duckdb数据库结构.xlsx         # 数据库表结构配置
├── instance/stock_data.duckdb   # 本地数据库 (~1.5 GB, gitignored)
├── templates/                   # 5 个 HTML 页面
│   ├── index.html               # 证券筛选主页 + DSL 面板
│   ├── detail.html              # K线图 + 技术指标
│   ├── fundamental.html         # 基本面分析
│   ├── ai_chat.html             # AI 对话
│   └── toolbox.html             # 工具箱（占位）
├── static/
│   ├── css/style.css            # 主样式
│   ├── css/detail.css           # K线图样式
│   ├── css/fundamental.css      # 基本面样式
│   ├── css/ai_chat.css          # AI 对话样式
│   ├── js/script.js             # 主脚本 + DSL 前端
│   ├── js/detail.js             # Canvas K线绘制
│   ├── js/fundamental.js        # 基本面交互
│   └── js/ai_chat.js            # AI 对话
├── venv/                        # Python 虚拟环境 (gitignored)
└── temp_file__/                  # 临时文件（gitignored）
```

---

## 已知限制

- **概念板块**：数据库无概念成分表，前端下拉保留但静默忽略（记日志）
- **日K 数据截止**：数据源为 Tushare 免费接口，最新交易日取决于 Tushare 同步时间
- **AI 对话**：依赖阿里云百炼 API，需配置 `AI密钥.txt`

---

## 技术亮点

### DSL 编译器

自研纯 Python 递归下降解析器，零第三方依赖，精确字符级错误定位：

```
词法分析 → 语法分析 → 语义检查 → SQL 生成 → 数据库执行
```

### 双后端抽象层

`Dialect` 基类 + `DuckDBDialect` / `DorisDialect` 实现，切换只需环境变量：

| 维度 | DuckDB | Doris |
|---|---|---|
| 标识符引号 | `"列名"` | `` `列名` `` |
| 中文表名 | 原生支持 | 自动映射英文名 |
| 字符串拼接 | `a \|\| b` | `CONCAT(a, b)` |
| 占位符 | `?` | `%s` |

### 历史函数下推

`MA(收盘价, 20)` 等历史函数被编译为 CTE + 窗口函数（`ROW_NUMBER() OVER PARTITION BY`），全部在数据库端计算，不拉取原始日K 数据到 Python。

---

## 贡献

本项目为课程竞赛项目。如需改进或扩展功能，欢迎提 Issue 和 Pull Request。

---

## 许可

MIT License
