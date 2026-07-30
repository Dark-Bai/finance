-- Doris 建表 DDL（dsl-stock-screener：DuckDB → Doris 迁移）
-- Doris 2.1.x 表名限英文，故中文表名映射为英文：
--   日度信息表 -> daily_kline
--   基本信息表 -> stock_basic
-- 单 BE 环境：replication_num = 1

CREATE DATABASE IF NOT EXISTS stock;

-- ============ daily_kline（日度信息表，事实表，约 1800 万行）============
CREATE TABLE IF NOT EXISTS stock.daily_kline (
  ts_code     VARCHAR(12) NOT NULL COMMENT '股票代码',
  trade_date  DATE        NOT NULL COMMENT '交易日期',
  `open`      DOUBLE COMMENT '开盘价',
  `close`     DOUBLE COMMENT '收盘价',
  high        DOUBLE COMMENT '最高价',
  low         DOUBLE COMMENT '最低价',
  vol         DOUBLE COMMENT '成交量',
  amount      DOUBLE COMMENT '成交额',
  pre_close   DOUBLE COMMENT '前收盘价',
  amp         DOUBLE COMMENT '振幅',
  pct_chg     DOUBLE COMMENT '涨跌幅',
  `change`    DOUBLE COMMENT '涨跌额'
)
ENGINE=OLAP
DUPLICATE KEY(ts_code, trade_date)
PARTITION BY RANGE(trade_date) (
  FROM ("1990-01-01") TO ("2028-01-01") INTERVAL 1 YEAR
)
DISTRIBUTED BY HASH(ts_code) BUCKETS 4
PROPERTIES ("replication_num" = "1");

-- ============ stock_basic（基本信息表，维度表，约 5500 行）============
CREATE TABLE IF NOT EXISTS stock.stock_basic (
  ts_code        VARCHAR(12) NOT NULL COMMENT '股票代码',
  symbol         VARCHAR(16)  COMMENT '股票symbol',
  name           VARCHAR(64)  COMMENT '股票名称',
  type           VARCHAR(16)  COMMENT '类型',
  exchange       VARCHAR(16)  COMMENT '交易所',
  sector         VARCHAR(16)  COMMENT '板块',
  area           VARCHAR(16)  COMMENT '地域',
  industry       VARCHAR(32)  COMMENT '行业',
  fullname       VARCHAR(128) COMMENT '全称',
  enname         STRING       COMMENT '英文名',
  is_hs          VARCHAR(8)   COMMENT '是否沪深港通',
  chairman       VARCHAR(128) COMMENT '董事长',
  manager        VARCHAR(192) COMMENT '总经理',
  secretary      VARCHAR(128) COMMENT '董秘',
  setup_date     DATE         COMMENT '成立日期',
  list_date      DATE         COMMENT '上市日期',
  employees      INT          COMMENT '员工人数',
  reg_capital    DOUBLE       COMMENT '注册资本',
  main_business  STRING       COMMENT '主营业务',
  business_scope STRING       COMMENT '经营范围'
)
ENGINE=OLAP
UNIQUE KEY(ts_code)
DISTRIBUTED BY HASH(ts_code) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- ============ daily_basic（当日信息表，含 PE/PB/市值等估值指标）============
CREATE TABLE IF NOT EXISTS stock.daily_basic (
  trade_date   DATE        NOT NULL COMMENT '交易日期',
  ts_code      VARCHAR(12) NOT NULL COMMENT '股票代码',
  `open`       DOUBLE COMMENT '开盘价',
  `close`      DOUBLE COMMENT '收盘价',
  high         DOUBLE COMMENT '最高价',
  low          DOUBLE COMMENT '最低价',
  vol          DOUBLE COMMENT '成交量',
  amount       DOUBLE COMMENT '成交额',
  amp          DOUBLE COMMENT '振幅',
  pct_chg      DOUBLE COMMENT '涨跌幅',
  `change`     DOUBLE COMMENT '涨跌额',
  turnover     DOUBLE COMMENT '换手率',
  pe           DOUBLE COMMENT '市盈率',
  pe_ttm       DOUBLE COMMENT '市盈率TTM',
  pb           DOUBLE COMMENT '市净率',
  ps           DOUBLE COMMENT '市销率',
  ps_ttm       DOUBLE COMMENT '市销率TTM',
  total_mv     DOUBLE COMMENT '总市值（万元）',
  circ_mv      DOUBLE COMMENT '流通市值（万元）',
  total_share  DOUBLE COMMENT '总股本',
  float_share  DOUBLE COMMENT '流通股本',
  dv_ratio     DOUBLE COMMENT '股息率',
  dv_ttm       DOUBLE COMMENT '股息率TTM',
  volume_ratio DOUBLE COMMENT '量比'
)
ENGINE=OLAP
UNIQUE KEY(trade_date, ts_code)
DISTRIBUTED BY HASH(ts_code) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- ============ weekly_kline（周度信息表，约 381 万行）============
CREATE TABLE IF NOT EXISTS stock.weekly_kline (
  ts_code     VARCHAR(12) NOT NULL COMMENT '股票代码',
  trade_date  DATE        NOT NULL COMMENT '周末交易日',
  open_w      DOUBLE COMMENT '周开盘',
  close_w     DOUBLE COMMENT '周收盘',
  high_w      DOUBLE COMMENT '周最高',
  low_w       DOUBLE COMMENT '周最低',
  vol_w       DOUBLE COMMENT '周成交量',
  amount_w    DOUBLE COMMENT '周成交额',
  pre_close_w DOUBLE COMMENT '上周收盘',
  amp_w       DOUBLE COMMENT '振幅',
  pct_chg_w   DOUBLE COMMENT '涨跌幅',
  change_w    DOUBLE COMMENT '涨跌额'
)
ENGINE=OLAP
DUPLICATE KEY(ts_code, trade_date)
PARTITION BY RANGE(trade_date) (
  FROM ("1990-01-01") TO ("2028-01-01") INTERVAL 1 YEAR
)
DISTRIBUTED BY HASH(ts_code) BUCKETS 2
PROPERTIES ("replication_num" = "1");

-- ============ monthly_kline（月度信息表，约 90 万行）============
CREATE TABLE IF NOT EXISTS stock.monthly_kline (
  ts_code     VARCHAR(12) NOT NULL COMMENT '股票代码',
  trade_date  DATE        NOT NULL COMMENT '月末交易日',
  open_m      DOUBLE COMMENT '月开盘',
  close_m     DOUBLE COMMENT '月收盘',
  high_m      DOUBLE COMMENT '月最高',
  low_m       DOUBLE COMMENT '月最低',
  vol_m       DOUBLE COMMENT '月成交量',
  amount_m    DOUBLE COMMENT '月成交额',
  pre_close_m DOUBLE COMMENT '上月收盘',
  amp_m       DOUBLE COMMENT '振幅',
  pct_chg_m   DOUBLE COMMENT '涨跌幅',
  change_m    DOUBLE COMMENT '涨跌额'
)
ENGINE=OLAP
DUPLICATE KEY(ts_code, trade_date)
PARTITION BY RANGE(trade_date) (
  FROM ("1990-01-01") TO ("2028-01-01") INTERVAL 1 YEAR
)
DISTRIBUTED BY HASH(ts_code) BUCKETS 2
PROPERTIES ("replication_num" = "1");
