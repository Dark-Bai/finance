# -*- coding: utf-8 -*-
"""
数据库连接抽象层（DuckDB / Doris 双后端）

通过环境变量 STOCK_DB_TYPE 切换：
    export STOCK_DB_TYPE=doris   # 使用 Doris
    unset STOCK_DB_TYPE          # 回到默认 DuckDB

对外统一接口：
    db_connect()                 返回一个连接，用完 .close() 归还（Doris 走连接池）
    translate_table(sql)         中文表名 -> Doris 英文表名（仅 Doris 模式）
    translate_placeholder(sql)   ? -> %s（仅 Doris/pymysql 模式）
    fetchdf(cursor)              pymysql cursor 结果 -> pandas DataFrame
"""

import os
import re

import duckdb
import pandas as pd

# ---------- 配置 ----------
DB_TYPE = os.environ.get('STOCK_DB_TYPE', 'duckdb').lower()  # 'duckdb' | 'doris'
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'instance', 'stock_data.duckdb'
)

DORIS_HOST = '127.0.0.1'
DORIS_PORT = 9030
DORIS_USER = 'root'
DORIS_PWD = ''
DORIS_DB = 'stock'

# ---------- 表名映射 ----------
TABLE_MAP = {
    '基本信息表': 'stock_basic',
    '当日信息表': 'daily_basic',
    '日度信息表': 'daily_kline',
    '周度信息表': 'weekly_kline',
    '月度信息表': 'monthly_kline',
}

# ---------- Doris 连接池（懒初始化） ----------
_doris_pool = None


def _get_doris_pool():
    global _doris_pool
    if _doris_pool is None:
        from dbutils.pooled_db import PooledDB
        import pymysql
        _doris_pool = PooledDB(
            creator=pymysql,
            host=DORIS_HOST, port=DORIS_PORT,
            user=DORIS_USER, password=DORIS_PWD, database=DORIS_DB,
            maxconnections=8, mincached=2, maxcached=5,
            blocking=True,
            charset='utf8mb4',
        )
    return _doris_pool


def db_connect():
    """返回一个数据库连接。Doris 模式下来自连接池，调用方用完应 .close() 归还。"""
    if DB_TYPE == 'doris':
        return _get_doris_pool().connection()
    return duckdb.connect(DB_PATH)


# ---------- SQL 工具函数 ----------
def translate_table(sql):
    """将 SQL 中被引号包裹的中文表名替换为 Doris 英文表名（仅 Doris 模式生效）。"""
    if DB_TYPE != 'doris':
        return sql
    for cn, en in TABLE_MAP.items():
        # 仅匹配被双引号或单引号包裹的完整表名，避免误伤字符串字面量里的中文
        sql = re.sub(
            r'["\']' + re.escape(cn) + r'["\']',
            f'`{en}`',
            sql,
        )
    return sql


def translate_placeholder(sql):
    """将 ? 占位符替换为 %s（pymysql 使用 %s）。仅 Doris 模式生效。"""
    if DB_TYPE != 'doris':
        return sql
    return sql.replace('?', '%s')


def fetchdf(cursor):
    """将 pymysql cursor 的查询结果转为 pandas DataFrame。"""
    cols = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=cols)