#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DuckDB -> Doris 数据迁移脚本
- 源: instance/stock_data.duckdb
- 目标: Doris 数据库 stock（daily_kline / stock_basic）
- 方式: DuckDB COPY TO parquet 落盘 -> curl Stream Load 导入 -> 校验
- 内存安全: 日度表按年分批，导完即删临时文件
"""

import os
import sys
import json
import time
import glob
import subprocess

import duckdb

# ---------- 配置 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'stock_data.duckdb')
TMP_DIR = os.path.join(BASE_DIR, 'temp_file__')

DORIS_HOST = '127.0.0.1'
DORIS_QUERY_PORT = 9030          # MySQL 协议（校验用）
DORIS_HTTP_PORT = 8030           # FE HTTP（Stream Load 用）
DORIS_USER = 'root'
DORIS_PWD = ''
DORIS_DB = 'stock'

# 中文表名 -> 英文表名 映射
TABLE_MAP = {
    '基本信息表': 'stock_basic',
    '日度信息表': 'daily_kline',
    '当日信息表': 'daily_basic',
    '周度信息表': 'weekly_kline',
    '月度信息表': 'monthly_kline',
}

os.makedirs(TMP_DIR, exist_ok=True)


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def mysql_query(sql):
    """通过 mysql 客户端执行查询，返回 stdout（tab 分隔，无表头用 -N）。"""
    cmd = ['mysql', '-h', DORIS_HOST, '-P', str(DORIS_QUERY_PORT),
           '-u', DORIS_USER, '-N', '-e', sql]
    if DORIS_PWD:
        cmd[7:7] = ['-p' + DORIS_PWD]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'mysql 查询失败: {r.stderr.strip()}')
    return r.stdout.strip()


def stream_load(parquet_path, table):
    """用 curl 把 parquet 文件 Stream Load 到 Doris 指定表。"""
    url = f'http://{DORIS_HOST}:{DORIS_HTTP_PORT}/api/{DORIS_DB}/{table}/_stream_load'
    cmd = [
        'curl', '--silent', '--location-trusted',
        '-u', f'{DORIS_USER}:{DORIS_PWD}',
        '-H', 'format:parquet',
        '-H', 'Expect:100-continue',
        '-T', parquet_path,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'curl 失败: {r.stderr.strip()}')
    try:
        resp = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f'Stream Load 返回非 JSON: {r.stdout[:500]}')
    if resp.get('Status') not in ('Success', 'Publish Timeout'):
        raise RuntimeError(f'Stream Load 失败: {json.dumps(resp, ensure_ascii=False)}')
    return resp


def export_parquet(con, sql, out_path):
    """DuckDB 流式导出查询结果到 parquet 文件。"""
    con.execute(f"COPY ({sql}) TO '{out_path}' (FORMAT parquet)")


def migrate_basic(con):
    """迁移 基本信息表 -> stock_basic（一次性）。"""
    src, dst = '基本信息表', TABLE_MAP['基本信息表']
    log(f'开始迁移 {src} -> {dst}')
    pq = os.path.join(TMP_DIR, 'stock_basic.parquet')
    # 显式列出列，确保顺序与 Doris 表一致
    cols = ('ts_code,symbol,name,type,exchange,sector,area,industry,fullname,'
            'enname,is_hs,chairman,manager,secretary,setup_date,list_date,'
            'employees,reg_capital,main_business,business_scope')
    export_parquet(con, f'SELECT {cols} FROM "{src}"', pq)
    resp = stream_load(pq, dst)
    log(f'  已导入 {resp.get("NumberLoadedRows")} 行, 耗时 {resp.get("LoadTimeMs")}ms')
    os.remove(pq)


def migrate_daily(con):
    """迁移 日度信息表 -> daily_kline（按年分批）。"""
    src, dst = '日度信息表', TABLE_MAP['日度信息表']
    log(f'开始迁移 {src} -> {dst}（按年分批）')
    yr_min, yr_max = con.execute(
        f'SELECT EXTRACT(year FROM MIN(trade_date)), '
        f'EXTRACT(year FROM MAX(trade_date)) FROM "{src}"').fetchone()
    yr_min, yr_max = int(yr_min), int(yr_max)
    cols = ('ts_code,trade_date,open,close,high,low,vol,amount,'
            'pre_close,amp,pct_chg,change')
    total = 0
    for yr in range(yr_min, yr_max + 1):
        pq = os.path.join(TMP_DIR, f'daily_{yr}.parquet')
        sql = (f'SELECT {cols} FROM "{src}" '
               f'WHERE trade_date >= DATE \'{yr}-01-01\' '
               f'AND trade_date < DATE \'{yr + 1}-01-01\'')
        export_parquet(con, sql, pq)
        # 空年份跳过
        n_src = con.execute(f'SELECT COUNT(*) FROM ({sql})').fetchone()[0]
        if n_src == 0:
            os.remove(pq)
            continue
        resp = stream_load(pq, dst)
        loaded = int(resp.get('NumberLoadedRows', 0))
        total += loaded
        log(f'  {yr}: 源 {n_src} 行 -> 导入 {loaded} 行 ({resp.get("LoadTimeMs")}ms)')
        os.remove(pq)
    log(f'  日度表累计导入 {total} 行')


def migrate_simple(con, src, cols):
    """通用：一次性迁移中小表（周/月 KLine 也走年份分批以控内存）。"""
    dst = TABLE_MAP[src]
    log(f'开始迁移 {src} -> {dst}')
    n_total = con.execute(f'SELECT COUNT(*) FROM "{src}"').fetchone()[0]
    # 大于 100 万行的按年分批，否则一次导
    if n_total > 1_000_000:
        yr_min, yr_max = con.execute(
            f'SELECT EXTRACT(year FROM MIN(trade_date)), '
            f'EXTRACT(year FROM MAX(trade_date)) FROM "{src}"').fetchone()
        total = 0
        for yr in range(int(yr_min), int(yr_max) + 1):
            pq = os.path.join(TMP_DIR, f'{dst}_{yr}.parquet')
            sql = (f'SELECT {cols} FROM "{src}" '
                   f'WHERE trade_date >= DATE \'{yr}-01-01\' '
                   f'AND trade_date < DATE \'{yr + 1}-01-01\'')
            n = con.execute(f'SELECT COUNT(*) FROM ({sql})').fetchone()[0]
            if n == 0:
                continue
            export_parquet(con, sql, pq)
            resp = stream_load(pq, dst)
            total += int(resp.get('NumberLoadedRows', 0))
            os.remove(pq)
        log(f'  {dst} 累计导入 {total} 行')
    else:
        pq = os.path.join(TMP_DIR, f'{dst}.parquet')
        export_parquet(con, f'SELECT {cols} FROM "{src}"', pq)
        resp = stream_load(pq, dst)
        log(f'  已导入 {resp.get("NumberLoadedRows")} 行, 耗时 {resp.get("LoadTimeMs")}ms')
        os.remove(pq)


def migrate_others(con):
    """迁移 当日信息表 / 周度信息表 / 月度信息表。"""
    migrate_simple(con, '当日信息表',
        'trade_date,ts_code,open,close,high,low,vol,amount,amp,pct_chg,change,'
        'turnover,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv,total_share,'
        'float_share,dv_ratio,dv_ttm,volume_ratio')
    migrate_simple(con, '周度信息表',
        'ts_code,trade_date,open_w,close_w,high_w,low_w,vol_w,amount_w,'
        'pre_close_w,amp_w,pct_chg_w,change_w')
    migrate_simple(con, '月度信息表',
        'ts_code,trade_date,open_m,close_m,high_m,low_m,vol_m,amount_m,'
        'pre_close_m,amp_m,pct_chg_m,change_m')


def verify(con):
    """校验：逐表比对行数 + 抽查一只股票。"""
    log('===== 校验 =====')
    ok = True
    for src, dst in TABLE_MAP.items():
        n_src = con.execute(f'SELECT COUNT(*) FROM "{src}"').fetchone()[0]
        n_dst = int(mysql_query(f'SELECT COUNT(*) FROM {DORIS_DB}.{dst}'))
        flag = '✅' if n_src == n_dst else '❌'
        if n_src != n_dst:
            ok = False
        log(f'  {src}({n_src}) vs {dst}({n_dst})  {flag}')
    # 抽查：平安银行 000001.SZ 最近一条日线
    sample = '000001.SZ'
    src_row = con.execute(
        f'SELECT close FROM "日度信息表" WHERE ts_code=? '
        f'ORDER BY trade_date DESC LIMIT 1', [sample]).fetchone()
    dst_row = mysql_query(
        f"SELECT close FROM {DORIS_DB}.daily_kline WHERE ts_code='{sample}' "
        f"ORDER BY trade_date DESC LIMIT 1")
    log(f'  抽查 {sample} 最新收盘价: 源={src_row[0]} 目标={dst_row}')
    log('校验通过 ✅' if ok else '校验发现行数不一致 ❌')
    return ok


def main():
    if not os.path.exists(DB_PATH):
        log(f'找不到 DuckDB: {DB_PATH}')
        sys.exit(1)
    con = duckdb.connect(DB_PATH, read_only=True)
    t0 = time.time()
    migrate_basic(con)
    migrate_daily(con)
    migrate_others(con)
    verify(con)
    # 清理残留临时文件
    for f in glob.glob(os.path.join(TMP_DIR, '*.parquet')):
        os.remove(f)
    log(f'全部完成，总耗时 {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()
