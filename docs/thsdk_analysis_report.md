# THSDK 接口分析报告、集成方案及测试结果

> **生成日期**: 2026-08-02  
> **项目名称**: 证券筛选系统  
> **目标包**: thsdk-main (v1.0)

---

## 目录

1. [thsdk-main 包概述](#1-thsdk-main-包概述)
2. [接口功能全景分析](#2-接口功能全景分析)
3. [实用接口筛选与详细说明](#3-实用接口筛选与详细说明)
4. [接口集成方案](#4-接口集成方案)
5. [错误处理与日志机制](#5-错误处理与日志机制)
6. [单元测试结果](#6-单元测试结果)
7. [附录](#7-附录)

---

## 1. thsdk-main 包概述

### 1.1 包定位

thsdk-main 是一个基于 C 动态链接库（`hq.dll`/`hq.so`/`hq.dylib`）的金融数据接入 SDK，通过 `ctypes` 调用同花顺行情服务器接口，提供沪深 A 股、港股、美股、期货、外汇、债券、基金等全市场金融数据查询能力。

### 1.2 包结构

```
thsdk-main/src/thsdk/
├── __init__.py          # 包入口，导出 THS, Response
├── base.py              # 核心基类：连接管理、DLL加载、通用调用
├── thsdk.py             # THS 主类（多继承组合）
├── catalog.py           # 目录/列表类接口（板块、市场列表）
├── domestic.py          # 国内业务接口（K线、分时、逐笔、深度）
├── market_queries.py    # 市场行情查询接口（多市场实时行情）
├── misc_api.py          # 杂项接口（问财、新闻、IPO、代码补齐）
├── response.py          # 响应封装（Response + Payload 数据类）
├── query_configs.py     # 行情查询配置（字段ID映射表）
├── validators.py        # 参数校验器
├── _constants.py        # 常量（市场代码、字段名映射、游客账户）
├── libs/                # 平台原生库
│   ├── windows/hq.dll
│   ├── linux/amd64/hq.so
│   └── darwin/arm64/hq.dylib
└── examples/            # 示例代码
    ├── kline.py, search_symbols.py, news.py, ...
    └── test_thsdk.py    # 内置测试框架
```

### 1.3 核心架构

```
┌─────────────────────────────────────────────────┐
│   THS 类（多继承 Mixin）                          │
│   ├── DomesticAPIMixin    — 国内业务              │
│   ├── CatalogAPIMixin     — 目录/列表              │
│   ├── MarketQueryAPIMixin — 市场行情              │
│   └── MiscAPIMixin        — 杂项                  │
├─────────────────────────────────────────────────┤
│   THSBase（基类）                                 │
│   ├── connect() / disconnect() — 连接管理         │
│   ├── call() — 通用方法调用                       │
│   ├── lib_call() — 底层 DLL 调用                  │
│   └── query_data() — 行情数据查询                  │
├─────────────────────────────────────────────────┤
│   Response 数据封装                               │
│   ├── success / error — 状态                      │
│   ├── data — 数据内容（list/dict）                │
│   ├── df — Pandas DataFrame 属性                  │
│   └── extra — 额外元数据                          │
└─────────────────────────────────────────────────┘
```

### 1.4 连接方式

```python
from thsdk import THS

# 方式1：上下文管理器（推荐）
with THS() as ths:
    response = ths.klines("USZA300033", count=100)

# 方式2：手动管理
ths = THS()
ths.connect()
response = ths.klines("USZA300033", count=100)
ths.disconnect()
```

---

## 2. 接口功能全景分析

### 2.1 接口分类总表

| 分类 | 接口数 | 说明 |
|------|--------|------|
| **目录/列表** | 18 | 获取板块/市场/品种列表 |
| **国内业务** | 9 | K线、分时、逐笔、深度、大单等 |
| **市场行情** | 10 | 多市场实时行情查询 |
| **杂项** | 10 | 问财、新闻、IPO、代码补齐等 |
| **合计** | **47** |  |

### 2.2 完整接口清单

#### 2.2.1 目录/列表接口 (CatalogAPIMixin)

| 方法名 | 参数 | 返回值 | 功能描述 |
|--------|------|--------|----------|
| `block(block_id)` | `block_id: int` | `Response` | 按板块ID获取板块数据 |
| `market_block(market)` | `market: str` | `Response` | 按市场代码获取市场列表 |
| `block_constituents(link_code)` | `link_code: str` | `Response` | 获取板块成分股 |
| `ths_industry()` | 无 | `Response` | 获取同花顺行业分类（block_id=0xCE5F） |
| `ths_concept()` | 无 | `Response` | 获取同花顺概念分类（block_id=0xCE5E） |
| `forex_list()` | 无 | `Response` | 获取外汇列表 |
| `index_list()` | 无 | `Response` | 获取指数列表 |
| `stock_cn_lists()` | 无 | `Response` | 获取A股全量列表 |
| `stock_us_lists()` | 无 | `Response` | 获取美股列表 |
| `stock_hk_lists()` | 无 | `Response` | 获取港股列表 |
| `stock_bj_lists()` | 无 | `Response` | 获取北交所列表 |
| `stock_uk_lists()` | 无 | `Response` | 获取英股列表 |
| `stock_b_lists()` | 无 | `Response` | 获取B股列表 |
| `futures_lists()` | 无 | `Response` | 获取期货列表 |
| `nasdaq_lists()` | 无 | `Response` | 获取纳斯达克列表 |
| `bond_lists()` | 无 | `Response` | 获取债券列表 |
| `fund_etf_lists()` | 无 | `Response` | 获取ETF基金列表 |
| `fund_etf_t0_lists()` | 无 | `Response` | 获取T0 ETF列表 |

#### 2.2.2 国内业务接口 (DomesticAPIMixin)

| 方法名 | 参数 | 返回值 | 功能描述 |
|--------|------|--------|----------|
| `intraday_data(ths_code)` | `ths_code: str` | `Response` | 获取日内分时数据 |
| `tick_level1(ths_code)` | `ths_code: str` | `Response` | Level1逐笔成交 |
| `tick_super_level1(ths_code, date, buffer_size)` | `ths_code, date, buffer_size` | `Response` | 超级Level1逐笔 |
| `min_snapshot(ths_code, date, buffer_size)` | `ths_code, date, buffer_size` | `Response` | 分钟快照 |
| `depth(ths_code)` | `ths_code: str/list` | `Response` | 五档买卖盘口 |
| `call_auction(ths_code)` | `ths_code: str` | `Response` | 集合竞价数据 |
| `big_order_flow(ths_code)` | `ths_code: str` | `Response` | 大单资金流向 |
| `corporate_action(ths_code)` | `ths_code: str` | `Response` | 权息资料（分红送转） |
| `klines(ths_code, start_time, end_time, adjust, interval, count)` | 见下方 | `Response` | K线数据（核心接口） |

**klines 参数详解：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ths_code` | str | 必填 | THS格式证券代码 |
| `start_time` | datetime | None | 起始时间 |
| `end_time` | datetime | None | 结束时间 |
| `adjust` | str | `""` | 复权：`forward`/`backward`/`""` |
| `interval` | str | `"day"` | 周期：`1m/5m/15m/30m/60m/120m/day/week/month/quarter/year` |
| `count` | int | -1 | 条数（与start_time/end_time二选一） |

#### 2.2.3 市场行情接口 (MarketQueryAPIMixin)

| 方法名 | 参数 | 返回值 | 功能描述 |
|--------|------|--------|----------|
| `market_data_block(block_code, query_key)` | `block_code, query_key` | `Response` | 板块行情数据 |
| `market_data_cn(ths_code, query_key)` | `ths_code, query_key` | `Response` | A股实时行情 |
| `market_data_us(ths_code, query_key)` | `ths_code, query_key` | `Response` | 美股实时行情 |
| `market_data_hk(ths_code, query_key)` | `ths_code, query_key` | `Response` | 港股实时行情 |
| `market_data_uk(ths_code, query_key)` | `ths_code, query_key` | `Response` | 英股实时行情 |
| `market_data_bond(ths_code, query_key)` | `ths_code, query_key` | `Response` | 债券实时行情 |
| `market_data_fund(ths_code, query_key)` | `ths_code, query_key` | `Response` | 基金实时行情 |
| `market_data_future(ths_code, query_key)` | `ths_code, query_key` | `Response` | 期货实时行情 |
| `market_data_forex(ths_code, query_key)` | `ths_code, query_key` | `Response` | 外汇实时行情 |
| `market_data_index(ths_code, query_key)` | `ths_code, query_key` | `Response` | 指数实时行情 |

**market_data_cn 查询键（query_key）：**

| 查询键 | 包含字段 |
|--------|----------|
| `基础数据` | 代码, 名称, 价格, 涨幅, 涨跌, 成交量, 总金额, 开盘价, 最高价, 最低价, 昨收价, 换手率... |
| `基础数据2` | 精简版基础数据 |
| `基础数据3` | 最简版（代码, 名称, 价格, 成交量） |
| `扩展1` | 市盈率TTM, 市净率, 总市值, 流通市值, 量比... |
| `扩展2` | 扩展数据（含更多财务指标） |
| `汇总` | 综合数据（含几乎所有可用字段） |

#### 2.2.4 杂项接口 (MiscAPIMixin)

| 方法名 | 参数 | 返回值 | 功能描述 |
|--------|------|--------|----------|
| `call_auction_anomaly(market)` | `market: str` | `Response` | 集合竞价异动 |
| `wencai_base(condition)` | `condition: str` | `Response` | 问财基础查询 |
| `wencai_nlp(condition)` | `condition: str` | `Response` | 问财NLP自然语言查询 |
| `order_book_ask(ths_code)` | `ths_code: str` | `Response` | 卖委托队列 |
| `order_book_bid(ths_code)` | `ths_code: str` | `Response` | 买委托队列 |
| `search_symbols(pattern, needmarket)` | `pattern, needmarket` | `Response` | 模糊搜索证券 |
| `news(text_id, code, market)` | `text_id, code, market` | `Response` | 新闻资讯 |
| `ipo_today()` | 无 | `Response` | 今日IPO |
| `ipo_wait()` | 无 | `Response` | 待发行IPO |
| `complete_ths_code(ths_code)` | `ths_code: str/list` | `Response` | 补齐THS格式代码 |
| `help(req)` | `req: str` | `str` | SDK帮助信息 |

---

## 3. 实用接口筛选与详细说明

### 3.1 筛选标准

根据本项目（证券筛选系统）的实际需求，筛选出以下高价值接口：

1. **可直接替换现有Tushare调用的接口** — 降低依赖
2. **能增强现有功能的接口** — 提供新数据维度
3. **接口稳定、文档完整** — 生产可用

### 3.2 高价值接口详细说明

#### 3.2.1 ★★★ `klines()` — K线数据（核心）

**用途**: 替代现有 Tushare K线数据获取，为 detail.js 提供K线数据

**参数**:
```python
def klines(
    ths_code: str,                    # THS格式代码，如 "USZA300033"
    start_time: Optional[datetime],   # 起始时间
    end_time: Optional[datetime],     # 结束时间
    adjust: str = "",                 # 复权: forward/backward
    interval: str = "day",            # 周期: 1m/5m/15m/30m/60m/day/week/month
    count: int = -1,                  # 条数（与起止时间二选一）
) -> Response
```

**返回值示例**:
```python
# response.data 为列表，每项包含:
[
    {
        "时间": datetime(2024, 1, 2),      # 日期
        "开盘": 100.0,                      # 开盘价
        "收盘": 101.5,                      # 收盘价
        "最高": 102.0,                      # 最高价
        "最低": 99.5,                       # 最低价
        "成交量": 1000000,                  # 成交量
        "总金额": 50000000,                 # 成交金额
        "涨幅": 1.5,                        # 涨幅(%)
        "涨跌": 1.5,                        # 涨跌额
        "换手率": 0.5,                      # 换手率(%)
        # ... 更多字段
    },
    ...
]
```

**使用示例**:
```python
from thsdk import THS
from datetime import datetime

with THS() as ths:
    # 获取最近100条日K线
    resp = ths.klines("USZA300033", count=100)
    df = resp.df  # 转为 Pandas DataFrame
    print(df.head())

    # 获取指定时间范围的K线
    resp = ths.klines(
        "USZA300033",
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 12, 31),
    )

    # 获取前复权K线
    resp = ths.klines("USZA300033", count=100, adjust="forward")
```

#### 3.2.2 ★★★ `market_data_cn()` — A股实时行情

**用途**: 替代 Tushare 的日线行情数据，获取实时行情 + 财务指标

**参数**:
```python
def market_data_cn(
    ths_code: str,                    # THS格式代码
    query_key: str = "基础数据",       # 查询键
) -> Response
```

**返回值示例**（基础数据）:
```python
{
    "代码": "300033",
    "名称": "同花顺",
    "价格": 150.00,
    "涨幅": 2.5,           # %
    "涨跌": 3.75,
    "成交量": 5000000,
    "总金额": 750000000,
    "开盘价": 148.00,
    "最高价": 152.00,
    "最低价": 147.50,
    "昨收价": 146.25,
    "换手率": 1.85,
    "量比": 1.20,
    "振幅": 3.08,
    "市盈率": 35.6,
    "市净率": 6.2,
    "总市值": 80000000000,
    "流通市值": 60000000000,
    # ...
}
```

#### 3.2.3 ★★★ `search_symbols()` — 证券模糊搜索

**用途**: 按名称或代码搜索证券，支持多市场

**参数**:
```python
def search_symbols(
    pattern: str,          # 搜索关键词
    needmarket: str = "",  # 市场限制，如 "SH,SZ" 或 "NQ"
) -> Response
```

**使用示例**:
```python
# 全市场搜索
resp = ths.search_symbols("同花顺")

# 限制市场
resp = ths.search_symbols("同花顺", "SH,SZ")  # 仅沪深
resp = ths.search_symbols("特斯拉", "NQ")      # 仅纳斯达克
resp = ths.search_symbols("600000")            # 按代码搜索
```

#### 3.2.4 ★★★ `complete_ths_code()` — 代码补齐

**用途**: 将普通6位代码补齐为THS格式（10位），支持批量

**参数**:
```python
def complete_ths_code(
    ths_code: Union[str, list],   # 单个代码或代码列表
) -> Response
```

**使用示例**:
```python
# 单个补齐
resp = ths.complete_ths_code("300033")
# 结果: [{"代码": "300033", "市场": "USZA", "THSCODE": "USZA300033", "名称": "同花顺"}]

# 批量补齐
resp = ths.complete_ths_code(["300033", "600519", "TSLA"])
```

#### 3.2.5 ★★★ `block_constituents()` — 板块成分股

**用途**: 获取行业/概念板块成分股，替代 Tushare 的成分股查询

**参数**:
```python
def block_constituents(
    link_code: str,   # 板块链接代码，如 "URFI886037"
) -> Response
```

#### 3.2.6 ★★★ `ths_industry()` / `ths_concept()` — 行业/概念列表

**用途**: 获取同花顺行业分类和概念分类列表

**使用示例**:
```python
industry = ths.ths_industry()  # 行业列表
concept = ths.ths_concept()    # 概念列表
```

#### 3.2.7 ★★☆ `stock_cn_lists()` — A股全量列表

**用途**: 获取所有A股股票的基本信息（代码、名称、市场等）

#### 3.2.8 ★★☆ `depth()` — 五档行情

**用途**: 获取买卖盘口五档数据

**使用示例**:
```python
# 单只
resp = ths.depth("USZA300033")
# 多只
resp = ths.depth(["USZA300033", "USZA300750"])
```

#### 3.2.9 ★★☆ `big_order_flow()` — 大单资金流向

**用途**: 获取个股的大单资金流向数据，用于资金面分析

**使用示例**:
```python
resp = ths.big_order_flow("USZA300033")
# 包含: 主动买入/卖出特大单、大单、中单、小单的数量和金额
```

#### 3.2.10 ★★☆ `wencai_nlp()` — 问财自然语言查询

**用途**: 使用自然语言进行选股查询

**使用示例**:
```python
resp = ths.wencai_nlp("龙头行业;国资委;所属行业")
```

#### 3.2.11 ★★☆ `news()` — 新闻资讯

**用途**: 获取7×24快讯、个股公告、研报等

**参数**:
```python
def news(
    text_id: int = 0x3814,   # 文本ID
    code: str = "1A0001",    # 证券代码
    market: str = "USHI",    # 市场代码
) -> Response
```

**text_id 说明**:
| text_id | 内容 |
|---------|------|
| 0x3814  | 7×24快讯（最新） |
| 0x2001  | 7×24快讯（重要） |
| 0x3805  | 个股公告 |
| 0x3806  | 个股研报 |
| 0x3808  | 个股社区 |

#### 3.2.12 ★★☆ `ipo_today()` / `ipo_wait()` — IPO信息

**用途**: 获取当日IPO和待发行IPO列表

#### 3.2.13 ★☆☆ `intraday_data()` — 日内分时

**用途**: 获取个股当日分时成交数据

#### 3.2.14 ★☆☆ `call_auction()` — 集合竞价

**用途**: 获取集合竞价数据

#### 3.2.15 ★☆☆ `call_auction_anomaly()` — 竞价异动

**用途**: 获取集合竞价期间的异动信息（试盘、撤单、抢筹等）

#### 3.2.16 ★☆☆ `corporate_action()` — 权息资料

**用途**: 获取分红、送转股等权息资料

#### 3.2.17 ★☆☆ `market_data_index()` — 指数行情

**用途**: 获取指数实时行情

#### 3.2.18 ★☆☆ `tick_level1()` / `min_snapshot()` — 逐笔/分钟快照

**用途**: 获取Level1逐笔成交和分钟级快照数据

---

## 4. 接口集成方案

### 4.1 集成架构

```
┌───────────────────────────────────────────────────────────────┐
│                         Flask App (app.py)                     │
│                                                               │
│  ┌──────────────────┐    ┌──────────────────────────────┐     │
│  │   现有路由         │    │   THSDK 路由 (thsdk_routes.py)│     │
│  │   /api/filter     │    │   /api/thsdk/klines          │     │
│  │   /api/kline      │    │   /api/thsdk/market_data     │     │
│  │   /api/dsl_filter │    │   /api/thsdk/search          │     │
│  │   ...             │    │   /api/thsdk/health          │     │
│  └──────────────────┘    │   ... (16个端点)              │     │
│                          └──────────────┬───────────────┘     │
│                                         │                      │
│                          ┌──────────────▼───────────────┐     │
│                          │   thsdk_service.py            │     │
│                          │   - 连接管理 (connect/disconnect)│     │
│                          │   - 缓存装饰器 (@cached)       │     │
│                          │   - 重试机制 (@retry_on_failure)│     │
│                          │   - 结果封装 (THSDKResult)     │     │
│                          │   - 工具函数 (代码转换)         │     │
│                          └──────────────┬───────────────┘     │
│                                         │                      │
│                          ┌──────────────▼───────────────┐     │
│                          │   THSDK Core (thsdk-main)     │     │
│                          │   - C DLL 调用                 │     │
│                          │   - 行情服务器连接              │     │
│                          └──────────────────────────────┘     │
└───────────────────────────────────────────────────────────────┘
```

### 4.2 新增文件清单

| 文件 | 说明 |
|------|------|
| `thsdk_service.py` | 服务封装层：连接管理、缓存、重试、日志、工具函数 |
| `thsdk_routes.py` | Flask蓝图：16个REST API端点 |
| `tests/test_thsdk_integration.py` | 单元测试：45个测试用例 |
| `docs/thsdk_analysis_report.md` | 本文档 |

### 4.3 集成步骤

#### 步骤1：安装依赖

```bash
# 确保已有 ctypes（Python内置）
# 可选：安装 pandas 用于 DataFrame 支持
pip install pandas

# 可选：安装 orjson 提升 JSON 解析性能
pip install orjson
```

#### 步骤2：配置环境变量（可选，默认使用游客账户）

```bash
set THS_USERNAME=your_username
set THS_PASSWORD=your_password
set THS_MAC=your_mac_address
```

#### 步骤3：导入模块

已在 `app.py` 末尾自动注册：
```python
from thsdk_routes import register_thsdk_routes
register_thsdk_routes(app)
```

#### 步骤4：启动验证

```bash
python app.py
# 访问 http://localhost:5000/api/thsdk/health
# 返回: {"success": true, "status": "connected", "message": "THSDK 服务正常"}
```

### 4.4 API 端点清单

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/thsdk/health` | GET | 无 | 健康检查 |
| `/api/thsdk/klines` | GET | code, count, interval, adjust | K线数据 |
| `/api/thsdk/market_data` | GET | code, query_key | A股实时行情 |
| `/api/thsdk/search` | GET | pattern, market | 证券搜索 |
| `/api/thsdk/complete_code` | GET/POST | code | 代码补齐 |
| `/api/thsdk/industry` | GET | 无 | 行业列表 |
| `/api/thsdk/concept` | GET | 无 | 概念列表 |
| `/api/thsdk/block_constituents` | GET | link_code | 板块成分股 |
| `/api/thsdk/news` | GET | text_id, code, market | 新闻资讯 |
| `/api/thsdk/ipo` | GET | type (today/wait) | IPO信息 |
| `/api/thsdk/depth` | GET | code | 五档行情 |
| `/api/thsdk/big_order_flow` | GET | code | 大单资金流向 |
| `/api/thsdk/wencai` | POST | condition | 问财查询 |
| `/api/thsdk/batch_market_data` | POST | codes (数组) | 批量行情 |

### 4.5 代码转换规则

```python
# 6位代码 -> THS格式（10位）
def convert_to_ths_code(code, market="USZA"):
    "300033" -> "USZA300033"   # 深市
    "600519" -> "USHA600519"   # 沪市
    "688001" -> "USHA688001"   # 科创板

# 自动识别规则（在 klines 端点中实现）
if code.startswith(("60", "68")):  market = "USHA"  # 沪市
if code.startswith(("00", "30")):  market = "USZA"  # 深市
if code.startswith(("8", "4")):    market = "USTM"  # 北交所
```

---

## 5. 错误处理与日志机制

### 5.1 多层错误处理架构

```
┌─────────────────────────────────────────────────────────────────┐
│  第一层: Flask 路由层 (thsdk_routes.py)                         │
│  - 参数校验（必填参数检查）                                     │
│  - 异常捕获（try/except 包装）                                  │
│  - 统一 JSON 响应格式                                           │
├─────────────────────────────────────────────────────────────────┤
│  第二层: 服务封装层 (thsdk_service.py)                          │
│  - 重试机制 (@retry_on_failure)                                 │
│  - 缓存机制 (@cached)                                           │
│  - 结果封装 (THSDKResult)                                       │
│  - 自定义异常 (THSDKServiceError / THSDKConnectionError)        │
├─────────────────────────────────────────────────────────────────┤
│  第三层: THSDK 核心层 (thsdk-main)                              │
│  - Response.success/error 状态                                  │
│  - 错误码映射 (get_err_info_by_code)                            │
│  - 缓冲区自动扩展 (query_data)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 错误处理策略

#### 5.2.1 重试机制

```python
@retry_on_failure(max_retries=3, delay=1.0)
def connect(self):
    """连接失败时自动重试，指数退避"""
    # 第1次重试: 等待 1秒
    # 第2次重试: 等待 2秒
    # 第3次重试: 等待 3秒
```

#### 5.2.2 缓存机制

```python
@cached(ttl=30)  # 30秒缓存
def klines(self, ...):
    """K线数据缓存30秒"""

@cached(ttl=3600)  # 1小时缓存
def ths_industry(self):
    """行业列表缓存1小时（不频繁变化）"""
```

#### 5.2.3 统一错误返回

```python
# 成功响应
{
    "success": true,
    "data": [...],
    "count": 100
}

# 失败响应
{
    "success": false,
    "error": "错误描述信息"
}
```

### 5.3 日志记录

日志文件位于 `logs/thsdk_service.log`，格式：

```
[2026-08-02 22:25:05] [thsdk_service/INFO] ✅ TCP成功连接到服务器 account:thsguest_xxx mac:xx:xx:xx:xx:xx:xx
[2026-08-02 22:25:05] [thsdk_service/WARNING] 第 1/3 次调用 connect 失败: 连接超时
[2026-08-02 22:25:06] [thsdk_service/ERROR] 调用 klines 异常: 连接失败
[2026-08-02 22:25:06] [thsdk_service/DEBUG] 缓存命中: klines:USZA300033:count=100
```

日志级别：
- **DEBUG**: 缓存命中/写入详情
- **INFO**: 连接成功/断开、路由注册
- **WARNING**: 重试、游客账户提醒
- **ERROR**: 调用失败、异常

---

## 6. 单元测试结果

### 6.1 测试概况

| 测试类 | 测试数 | 通过 | 跳过 | 通过率 |
|--------|--------|------|------|--------|
| `TestConvertFunctions` | 5 | 5 | 0 | 100% |
| `TestTHSDKResult` | 3 | 3 | 0 | 100% |
| `TestCacheDecorator` | 2 | 2 | 0 | 100% |
| `TestRetryDecorator` | 2 | 2 | 0 | 100% |
| `TestTHSDKServiceMocked` | 4 | 4 | 0 | 100% |
| `TestFlaskRoutes` | 16 | 16 | 0 | 100% |
| `TestTHSDKIntegration` (跳过) | 13 | 0 | 13 | — |
| **合计** | **45** | **32** | **13** | **100%** |

### 6.2 测试覆盖的功能点

#### 单元测试（Mock模式）
- [x] 代码转换函数（普通→THS格式、THS→普通格式）
- [x] 无效代码异常处理
- [x] THSDKResult 成功/失败状态
- [x] 布尔值转换
- [x] 缓存命中/过期
- [x] 重试成功（首次失败后重试成功）
- [x] 重试耗尽（持续失败）
- [x] K线方法参数传递验证
- [x] 搜索方法调用验证
- [x] 连接失败场景
- [x] 方法不存在场景

#### Flask 路由测试
- [x] 健康检查端点
- [x] 缺少参数验证（400）
- [x] K线端点（带参数）
- [x] 搜索端点
- [x] IPO端点
- [x] 新闻端点
- [x] 行业/概念列表端点
- [x] 代码补齐端点
- [x] 行情数据端点
- [x] 五档行情端点
- [x] 大单资金流向端点
- [x] 批量行情端点
- [x] 问财端点
- [x] 板块成分股端点

### 6.3 运行测试

```bash
# 运行全部测试（跳过需要实际连接的）
python -m unittest tests.test_thsdk_integration -v

# 仅运行单元测试
python -m unittest tests.test_thsdk_integration.TestConvertFunctions -v
python -m unittest tests.test_thsdk_integration.TestTHSDKServiceMocked -v
python -m unittest tests.test_thsdk_integration.TestFlaskRoutes -v

# 运行集成测试（需要 hq.dll 可用）
set SKIP_INTEGRATION_TESTS=0
python -m unittest tests.test_thsdk_integration.TestTHSDKIntegration -v

# 使用 pytest（如果已安装）
python -m pytest tests/test_thsdk_integration.py -v -k "not integration"
```

---

## 7. 附录

### 7.1 THS格式代码对照表

| 市场 | 代码 | THS格式 | 说明 |
|------|------|---------|------|
| 上海A股 | 600519 | USHA600519 | 沪市主板 |
| 上海科创板 | 688001 | USHA688001 | 科创板 |
| 深圳A股 | 300033 | USZA300033 | 深市创业板 |
| 深圳主板 | 000001 | USZA000001 | 深市主板 |
| 北交所 | 830799 | USTM830799 | 北交所 |
| 上海指数 | 1A0001 | USHI1A0001 | 上证指数 |
| 深圳指数 | 399001 | USZI399001 | 深证成指 |

### 7.2 市场代码速查

| 市场代码 | 说明 |
|----------|------|
| USHA | 上海A股 |
| USZA | 深圳A股 |
| USTM | 北交所 |
| USHI | 上海指数 |
| USZI | 深圳指数 |
| UHKG | 港股 |
| UNQQ | 美股纳斯达克 |
| UFXB | 外汇 |
| UEUA | 英国 |

### 7.3 常见问题

**Q: THSDK 连接失败？**
A: 确保 `hq.dll` 存在于 `thsdk-main/src/thsdk/libs/windows/` 目录。如缺少，需重新安装或编译 SDK。

**Q: 游客账户的限制？**
A: 游客账户（`thsguest_*`）仅供测试，可能随时失效。生产环境请使用正式账户，通过环境变量 `THS_USERNAME` / `THS_PASSWORD` / `THS_MAC` 配置。

**Q: 如何提升性能？**
A: 服务层已内置缓存（`@cached` 装饰器），高频数据（K线）缓存30秒，低频数据（行业列表）缓存1小时。批量查询使用 `batch_market_data` 方法。

**Q: K线数据与现有系统的兼容性？**
A: 返回的 `Response.data` 为字典列表，字段名已映射为中文（如"时间"、"开盘"、"收盘"），与现有前端 `detail.js` 期望的数据格式兼容，可直接替换 Tushare 数据源。