# =========================== 【↓导入第三方库↓】 ===========================
from flask import Flask, render_template, request, jsonify, send_file, session
import pypinyin
from datetime import datetime, timedelta
import re
import os
import random
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from openpyxl import Workbook
import io
import time
import traceback
import uuid
from openai import OpenAI
import tushare as ts
import pandas as pd
import math
from collections import Counter

import duckdb

import threading
from update_db import incremental_update, full_update
from dsl_engine import execute_dsl, get_dsl_help, DSLError

# =========================== 【↑导入第三方库↑】 ===========================





# =========================== 【↓定义全局变量↓】 ===========================
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # 用于session，实际生产需修改

# Tushare初始化
TUSHARE_TOKENS_2000__ = ['2288acdb7397a302d5b7160a2d5878eebf95db0c774d5c3e042918cc'] 
TUSHARE_TOKENS__ = [
    '2288acdb7397a302d5b7160a2d5878eebf95db0c774d5c3e042918cc',
    'e8bc8974b028e1e7a54fb844320ec248c93025fd1d2bd5eee79c5232',
    '285e90f673a28841080220492009989b613dce0a622edc22f28f9871',
    'b5f46fa9591ab477b028f70c218fb12be223d580cb53afd449dfc216',
    'e9bac38172fdb42c76a46b58e25ffefa747cfb53dffed5ef74e93240'
    # 后续新增Token直接追加到此列表即可
]
# 设置第一个Token为默认
ts.set_token(TUSHARE_TOKENS__[0])
pro__ = ts.pro_api()

# 板块数据缓存（减少API调用）
Dict_cached_concept_list__ = None
Dict_cached_industry_list__ = None
Dict_cached_area_list__ = None
Dict_cached_stock_basic__ = None
Dict_cached_concept_member__ = {}
Dict_cached_industry_member__ = {}
Dict_cached_area_member__ = {}
Dict_cached_concept_code_map__ = None  # 概念名称 -> 概念代码映射
Dict_cached_daily_basic__ = {}  # 缓存每日指标数据，供股票筛选使用
Dict_cached_float_share__ = {}
Dict_cached_industry_avg__ = None  # 格式: {f"{industry_name}_{trade_date}": {...}}

# 临时文件夹路径
Path_current_dir__ = os.path.dirname(os.path.abspath(__file__))
Path_temfile_dir__ = os.path.join(Path_current_dir__, "temp_file__")
os.makedirs(Path_temfile_dir__, exist_ok=True)

# AI对话存储
Dict_ai_conversations__ = {}

# 日K数据缓存 { ts_code: pd.DataFrame }
Dict_cached_daily_kline__ = {}

# 数据库路径（与 update_db.py 保持一致）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'stock_data.duckdb')

# =========================== 【↑定义全局变量↑】 ===========================





# =========================== 【↓定义工具函数↓】 ===========================
def Tool_function_string_sort__(parameter_list__):
    def Lever_1_sunfun_Get_sort_key__(parameter_string__):
        def Lever_2_subfun_char_key__(parameter_char__):
            if parameter_char__.isdigit():
                return (0, int(parameter_char__))
            pinyin = pypinyin.pinyin(parameter_char__, style=pypinyin.NORMAL)
            if pinyin:
                return (1, pinyin[0][0])
            return (2, parameter_char__)
        return [Lever_2_subfun_char_key__(parameter_char__) for parameter_char__ in parameter_string__]
    return sorted(parameter_list__, key=Lever_1_sunfun_Get_sort_key__)

def Tool_function_replace__(parameter_replace_str__, parameter_replace_list__):
    if parameter_replace_list__ == 1:
        parameter_replace_list__ == [("年", "-"), ("月", "-"), ("日", "")]
    elif parameter_replace_list__ == 2:
        parameter_replace_list__ == [("时", ":"), ("分", ":"), ("秒", "")]
    try:
        for loop_tuple_replace__ in parameter_replace_list__:
            parameter_replace_str__ = str(parameter_replace_str__).replace(loop_tuple_replace__[0], loop_tuple_replace__[1])
    except:
        parameter_replace_str__ = str(parameter_replace_str__)
    str_replace__ = parameter_replace_str__
    return str_replace__

def Tool_function_random_delay__(min_seconds__=0.5, max_seconds__=1.5):
    time.sleep(random.uniform(min_seconds__, max_seconds__))

def Tool_function_read_ai_key__():
    """读取AI密钥文件"""
    ai_key_file__ = os.path.join(Path_current_dir__, "AI密钥.txt")
    ai_key_info__ = {}
    try:
        with open(ai_key_file__, 'r', encoding='utf-8') as file__:
            for line__ in file__:
                line__ = line__.strip()
                if '：' in line__:
                    key__, value__ = line__.split('：', 1)
                    ai_key_info__[key__.strip()] = value__.strip()
                elif ':' in line__:
                    key__, value__ = line__.split(':', 1)
                    ai_key_info__[key__.strip()] = value__.strip()
    except Exception as e__:
        print(f"读取AI密钥文件失败: {e__}")
        return None
    return ai_key_info__

def Tool_function_convert_daily_to_weekly_improved__(df_daily__):
    """
    将日K线DataFrame转换为周K线（改进版）
    要求：开盘=本周第一个交易日开盘，收盘=本周最后一个交易日收盘（未结束则用最新收盘），
         最高=周内最高，最低=周内最低，日期=本周最后一个交易日（未结束则当日）
    """
    if df_daily__ is None or df_daily__.empty:
        return pd.DataFrame()
    df__ = df_daily__.copy()
    df__['trade_date'] = pd.to_datetime(df__['trade_date'])
    # 按周分组
    df__['week'] = df__['trade_date'].dt.to_period('W')
    # 按周分组聚合
    weekly_list__ = []
    for week__, group__ in df__.groupby('week'):
        # 按日期排序
        group__ = group__.sort_values('trade_date')
        open_price__ = group__.iloc[0]['open']
        close_price__ = group__.iloc[-1]['close']
        high_price__ = group__['high'].max()
        low_price__ = group__['low'].min()
        vol_sum__ = group__['vol'].sum()
        amount_sum__ = group__['amount'].sum()
        # 日期取该周最后一个交易日
        last_date__ = group__.iloc[-1]['trade_date']
        # 判断该周是否已结束（通过是否包含最新交易日）
        latest_trade_date__ = df__['trade_date'].max()
        if last_date__.date() < latest_trade_date__.date():
            # 已结束的周，日期不变
            pass
        else:
            # 本周尚未结束，收盘价使用最新收盘价，日期使用最新交易日
            last_date__ = latest_trade_date__
            close_price__ = df__[df__['trade_date'] == latest_trade_date__].iloc[0]['close']
        weekly_list__.append({
            'trade_date': last_date__.strftime('%Y%m%d'),
            'open': open_price__,
            'high': high_price__,
            'low': low_price__,
            'close': close_price__,
            'vol': vol_sum__,
            'amount': amount_sum__
        })
    weekly_df__ = pd.DataFrame(weekly_list__)
    # 按日期排序
    weekly_df__ = weekly_df__.sort_values('trade_date').reset_index(drop=True)
    return weekly_df__

def Tool_function_convert_daily_to_monthly_improved__(df_daily__):
    """
    将日K线DataFrame转换为月K线（改进版）
    要求：开盘=本月第一个交易日开盘，收盘=本月最后一个交易日收盘（未结束则用最新收盘），
         最高=月内最高，最低=月内最低，日期=本月最后一个交易日（未结束则当日）
    """
    if df_daily__ is None or df_daily__.empty:
        return pd.DataFrame()
    df__ = df_daily__.copy()
    df__['trade_date'] = pd.to_datetime(df__['trade_date'])
    # 按月分组
    df__['month'] = df__['trade_date'].dt.to_period('M')
    monthly_list__ = []
    for month__, group__ in df__.groupby('month'):
        group__ = group__.sort_values('trade_date')
        open_price__ = group__.iloc[0]['open']
        close_price__ = group__.iloc[-1]['close']
        high_price__ = group__['high'].max()
        low_price__ = group__['low'].min()
        vol_sum__ = group__['vol'].sum()
        amount_sum__ = group__['amount'].sum()
        last_date__ = group__.iloc[-1]['trade_date']
        latest_trade_date__ = df__['trade_date'].max()
        if last_date__.date() < latest_trade_date__.date():
            pass
        else:
            last_date__ = latest_trade_date__
            close_price__ = df__[df__['trade_date'] == latest_trade_date__].iloc[0]['close']
        monthly_list__.append({
            'trade_date': last_date__.strftime('%Y%m%d'),
            'open': open_price__,
            'high': high_price__,
            'low': low_price__,
            'close': close_price__,
            'vol': vol_sum__,
            'amount': amount_sum__
        })
    monthly_df__ = pd.DataFrame(monthly_list__)
    monthly_df__ = monthly_df__.sort_values('trade_date').reset_index(drop=True)
    return monthly_df__

def Tool_function_get_latest_trade_date__(parameter_pro__):
    """
    获取最近一个交易日日期
    """
    str_today__ = datetime.now().strftime('%Y%m%d')
    str_start__ = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
    
    try:
        df_cal__ = parameter_pro__.trade_cal(
            exchange='SSE', 
            start_date=str_start__, 
            end_date=str_today__, 
            is_open='1'
        )
        if df_cal__ is not None and not df_cal__.empty:
            df_cal__ = df_cal__.sort_values('cal_date', ascending=False)
            str_latest_date__ = df_cal__.iloc[0]['cal_date']
            return str_latest_date__
    except:
        pass
    return (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

# =========================== 【↑定义工具函数↑】 ===========================





# =========================== 【↓指标计算函数↓】 ===========================
def Tool_function_calculate_ma__(prices__, period__):
    result__ = []
    for i__ in range(len(prices__)):
        if i__ < period__ - 1:
            result__.append(None)
        else:
            sum__ = sum(prices__[i__-period__+1:i__+1])
            result__.append(sum__ / period__)
    return result__

def Tool_function_calculate_rsi__(prices__, period__):
    """计算RSI指标，采用Wilder平滑方式（与主流平台一致）"""
    if len(prices__) <= period__:
        return [None] * len(prices__)
    
    rsi_values__ = [None] * period__
    
    # 计算价格变化序列
    changes__ = []
    for i__ in range(1, len(prices__)):
        changes__.append(prices__[i__] - prices__[i__-1])
    
    # 分离涨幅和跌幅
    gains__ = [max(change__, 0) for change__ in changes__]
    losses__ = [max(-change__, 0) for change__ in changes__]
    
    # 第一个平均值使用简单算术平均
    avg_gain__ = sum(gains__[:period__]) / period__
    avg_loss__ = sum(losses__[:period__]) / period__
    
    # 计算第一个RSI值
    if avg_loss__ == 0:
        rsi__ = 100
    else:
        rs__ = avg_gain__ / avg_loss__
        rsi__ = 100 - (100 / (1 + rs__))
    rsi_values__.append(rsi__)
    
    # 后续值使用Wilder平滑（指数移动平均）
    for i__ in range(period__, len(changes__)):
        avg_gain__ = (avg_gain__ * (period__ - 1) + gains__[i__]) / period__
        avg_loss__ = (avg_loss__ * (period__ - 1) + losses__[i__]) / period__
        
        if avg_loss__ == 0:
            rsi__ = 100
        else:
            rs__ = avg_gain__ / avg_loss__
            rsi__ = 100 - (100 / (1 + rs__))
        rsi_values__.append(rsi__)
    
    return rsi_values__

def Tool_function_calculate_kdj__(highs__, lows__, closes__):
    n__ = 9
    k_arr__ = [50] * n__
    d_arr__ = [50] * n__
    j_arr__ = [50] * n__
    if len(closes__) <= n__:
        return k_arr__, d_arr__, j_arr__
    for i__ in range(n__, len(closes__)):
        recent_high__ = max(highs__[i__-n__+1:i__+1])
        recent_low__ = min(lows__[i__-n__+1:i__+1])
        if recent_high__ == recent_low__:
            rsv__ = 50
        else:
            rsv__ = (closes__[i__] - recent_low__) / (recent_high__ - recent_low__) * 100
        k_val__ = (2/3) * k_arr__[-1] + (1/3) * rsv__
        d_val__ = (2/3) * d_arr__[-1] + (1/3) * k_val__
        j_val__ = 3 * k_val__ - 2 * d_val__
        k_arr__.append(k_val__)
        d_arr__.append(d_val__)
        j_arr__.append(j_val__)
    return k_arr__, d_arr__, j_arr__

def Tool_function_calculate_macd__(prices__):
    if not prices__:
        return [], [], []
    ema12__ = [prices__[0]]
    ema26__ = [prices__[0]]
    for i__ in range(1, len(prices__)):
        ema12__.append(ema12__[i__-1] * 11/13 + prices__[i__] * 2/13)
        ema26__.append(ema26__[i__-1] * 25/27 + prices__[i__] * 2/27)
    dif_arr__ = [ema12__[i__] - ema26__[i__] for i__ in range(len(prices__))]
    dea_arr__ = [dif_arr__[0]]
    for i__ in range(1, len(dif_arr__)):
        dea_arr__.append(dea_arr__[i__-1] * 8/10 + dif_arr__[i__] * 2/10)
    macd_arr__ = [(dif_arr__[i__] - dea_arr__[i__]) * 2 for i__ in range(len(prices__))]
    return dif_arr__, dea_arr__, macd_arr__
# =========================== 【↑指标计算函数↑】 ===========================





# =========================== 【↓获取列表数据↓】 ===========================
def Main_function_Get_securities_sector_name_list__(parameter_securities_type__, _=None):
    """
    获取板块列表（概念、行业、地域）
    使用Tushare免费接口替换原爬虫逻辑
    """
    global Dict_cached_concept_list__, Dict_cached_industry_list__, Dict_cached_area_list__
    global Dict_cached_concept_code_map__
    
    def Level_1_subfun_fetch_concept_list__():
        """获取概念列表及代码映射"""
        global Dict_cached_concept_code_map__
        try:
            df__ = pro__.concept()
            if df__ is not None and not df__.empty:
                concept_list__ = df__['name'].unique().tolist()
                # 构建名称到代码的映射
                Dict_cached_concept_code_map__ = dict(zip(df__['name'], df__['code']))
                return concept_list__
            return []
        except Exception as e__:
            print(f"获取概念列表失败: {e__}")
            return []
    
    def Level_1_subfun_fetch_industry_and_area_lists__():
        """从 stock_basic 中获取行业和地域列表"""
        global Dict_cached_stock_basic__
        try:
            if Dict_cached_stock_basic__ is None:
                # 获取全量股票基础信息（仅上市状态）
                df__ = pro__.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
                Dict_cached_stock_basic__ = df__
            
            df__ = Dict_cached_stock_basic__
            industry_list__ = df__['industry'].dropna().unique().tolist()
            area_list__ = df__['area'].dropna().unique().tolist()
            return industry_list__, area_list__
        except Exception as e__:
            print(f"获取行业和地域列表失败: {e__}")
            return [], []

    if parameter_securities_type__ == '概念列表':
        if Dict_cached_concept_list__ is None:
            Dict_cached_concept_list__ = Level_1_subfun_fetch_concept_list__()
        return Dict_cached_concept_list__
    elif parameter_securities_type__ == '行业列表':
        if Dict_cached_industry_list__ is None:
            Dict_cached_industry_list__, _ = Level_1_subfun_fetch_industry_and_area_lists__()
        return Dict_cached_industry_list__
    elif parameter_securities_type__ == '地域列表':
        if Dict_cached_area_list__ is None:
            _, Dict_cached_area_list__ = Level_1_subfun_fetch_industry_and_area_lists__()
        return Dict_cached_area_list__
    else:
        return []
# =========================== 【↑获取列表数据↑】 ===========================





# =========================== 【↓核心筛选函数↓】 ===========================
def Tool_function_get_industry_members_tushare__(industry_name__):
    """获取指定行业板块的成分股（全局可调用）"""
    global Dict_cached_industry_member__
    if industry_name__ not in Dict_cached_industry_member__:
        try:
            df_all__ = pro__.stock_basic(exchange='', list_status='L', fields='ts_code,industry')
            if df_all__ is not None and not df_all__.empty:
                members__ = df_all__[df_all__['industry'] == industry_name__]['ts_code'].tolist()
                Dict_cached_industry_member__[industry_name__] = members__
            else:
                Dict_cached_industry_member__[industry_name__] = []
        except Exception as e__:
            print(f"获取行业成分股失败 ({industry_name__}): {e__}")
            Dict_cached_industry_member__[industry_name__] = []
    return Dict_cached_industry_member__[industry_name__]

def Tool_function_get_industry_members__(industry_name__):
    """获取指定行业板块的成分股（从数据库读取）"""
    global Dict_cached_industry_member__
    if industry_name__ not in Dict_cached_industry_member__:
        try:
            conn = duckdb.connect(DB_PATH)
            # 从基本信息表查询该行业的所有 ts_code
            result = conn.execute(
                'SELECT ts_code FROM "基本信息表" WHERE industry = ?',
                [industry_name__]
            ).fetchall()
            members = [row[0] for row in result]
            conn.close()
            Dict_cached_industry_member__[industry_name__] = members
        except Exception as e__:
            print(f"获取行业成分股失败 ({industry_name__}): {e__}")
            Dict_cached_industry_member__[industry_name__] = []
    return Dict_cached_industry_member__[industry_name__]

def Main_Func_Get_securities_identification_data__(Parameter_dict__, log_messages__):
    """
    从 DuckDB 数据库获取证券筛选数据，返回字典列表
    """
    def log__(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_messages__.append(f"[{timestamp}] {msg}")

    # 定义指标字段映射（用于后续转换）
    Dict_market_indicator_securities_type__ = {
        '股票': [('最近收盘价', 'close'), ('动态市盈率', 'pe'), ('市净率', 'pb'),
                 ('总市值（亿元）', 'total_mv'), ('流通市值（亿元）', 'circ_mv')],
        # 其他类型暂不支持，返回空
    }

    # 转换函数：将数据库行转为前端所需字典格式
    def process_securities(df, sec_type):
        """df 需包含：symbol, name, ts_code, exchange, sector, close, pe, pb, total_mv, circ_mv"""
        processed = []
        for _, row in df.iterrows():
            info = {}
            info['证券种类'] = sec_type
            info['证券名称'] = row.get('name', '')
            info['证券代码'] = row.get('symbol', '')
            info['交易所码'] = row.get('exchange', '')
            # 判断交易板块（若数据库已有 sector 则直接用，否则回退）
            info['交易板块'] = row.get('sector', '')
            # 填充指标（单位转换：总市值、流通市值从万元转为亿元）
            for field_name, db_col in Dict_market_indicator_securities_type__[sec_type]:
                raw = row.get(db_col)
                if raw is None or pd.isna(raw):
                    info[field_name] = 'None'
                else:
                    val = float(raw)
                    if db_col in ['total_mv', 'circ_mv']:
                        val = val / 10000  # 万元 -> 亿元
                    elif db_col in ['vol']:
                        val = val / 10000  # 手 -> 万手（若需要）
                    elif db_col in ['amount']:
                        val = val / 1000   # 千元 -> 万元（若需要）
                    info[field_name] = round(val, 2)
            processed.append(info)
        return processed

    # 获取证券类型（仅支持股票）
    sec_type = '股票'
    if not Parameter_dict__['股票']['选择']:
        log__("当前仅支持股票类型筛选，其他类型暂未实现")
        return [], sec_type

    # ---------- 1. 从数据库读取基础信息 ----------
    try:
        conn = duckdb.connect(DB_PATH)
        # 获取所有上市股票的基础信息（仅上市状态）
        df_basic = conn.execute('''
            SELECT ts_code, symbol, name, area, industry, exchange, sector, list_date
            FROM "基本信息表"
        ''').fetchdf()
        if df_basic.empty:
            log__("基本信息表无数据，请先更新数据库")
            conn.close()
            return [], sec_type
        log__(f"从数据库获取到 {len(df_basic)} 只股票基础信息")

        # ---------- 2. 获取最新交易日（从当日信息表取最大日期） ----------
        latest_date = conn.execute('SELECT MAX(trade_date) FROM "当日信息表"').fetchone()[0]
        if latest_date is None:
            log__("当日信息表无数据，请先更新数据库")
            conn.close()
            return [], sec_type
        log__(f"最新交易日: {latest_date}")

        # ---------- 3. 获取该日的每日指标 ----------
        df_daily = conn.execute('''
            SELECT ts_code, close, pe, pb, total_mv, circ_mv
            FROM "当日信息表"
            WHERE trade_date = ?
        ''', [latest_date]).fetchdf()
        if df_daily.empty:
            log__("当日信息表无该交易日数据")
            conn.close()
            return [], sec_type
        log__(f"获取到 {len(df_daily)} 条当日指标数据")

        # ---------- 4. 合并基本信息与指标 ----------
        df = df_basic.merge(df_daily, on='ts_code', how='inner')
        if df.empty:
            log__("合并后无数据（可能当日信息表缺少对应股票）")
            conn.close()
            return [], sec_type
        log__(f"合并后共 {len(df)} 只股票")

        conn.close()
    except Exception as e:
        log__(f"数据库查询失败: {e}")
        return [], sec_type

    # ---------- 5. 应用筛选条件 ----------
    # 5.1 交易所板块筛选
    exchange_list = Parameter_dict__['股票']['交易所板块']
    if exchange_list and '全部' not in exchange_list:
        exchange_set = set()
        sector_set = set()
        for board in exchange_list:
            if board == '上证A股':
                exchange_set.add('SSE')
            elif board == '深证A股':
                exchange_set.add('SZSE')
            elif board == '北证A股':
                exchange_set.add('BSE')
            elif board == '上证主板':
                sector_set.add('上证主板')
            elif board == '科创板':
                sector_set.add('科创板')
            elif board == '深证主板':
                sector_set.add('深证主板')
            elif board == '创业板':
                sector_set.add('创业板')
        # 构建筛选掩码
        mask = pd.Series(False, index=df.index)
        if exchange_set:
            mask |= df['exchange'].isin(exchange_set)
        if sector_set:
            mask |= df['sector'].isin(sector_set)
        if mask.any():
            df = df[mask]
            log__(f"交易所板块筛选后剩余 {len(df)} 只股票")
        else:
            log__("交易所板块条件未匹配到任何股票，已跳过")
    else:
        log__("未进行交易所板块筛选（全部）")
        
    # 5.2 概念筛选（数据库暂无 concept 字段，忽略）
    concept_list = Parameter_dict__['股票']['概念']
    if concept_list and '全部' not in concept_list:
        log__("概念筛选功能暂未支持（数据库无 concept 字段），将忽略此条件")

    # 5.3 行业筛选
    industry_list = Parameter_dict__['股票']['行业']
    if industry_list and '全部' not in industry_list and not df.empty:
        df = df[df['industry'].isin(industry_list)]
        log__(f"行业筛选后剩余 {len(df)} 只股票")

    # 5.4 地域筛选
    area_list = Parameter_dict__['股票']['地域']
    if area_list and '全部' not in area_list and not df.empty:
        df = df[df['area'].isin(area_list)]
        log__(f"地域筛选后剩余 {len(df)} 只股票")

    # 5.5 风险警示筛选
    risk_list = Parameter_dict__['股票']['风险警示']
    if risk_list and '全部' not in risk_list and not df.empty:
        if '非风险警示股' in risk_list and 'ST股' not in risk_list and '*ST股' not in risk_list:
            df = df[~df['name'].str.contains('ST', na=False)]
        elif 'ST股' in risk_list and '非风险警示股' not in risk_list and '*ST股' not in risk_list:
            df = df[df['name'].str.contains('ST', na=False) & ~df['name'].str.contains('\\*ST', na=False, regex=False)]
        elif '*ST股' in risk_list and '非风险警示股' not in risk_list and 'ST股' not in risk_list:
            df = df[df['name'].str.contains('\\*ST', na=False, regex=False)]
        elif set(risk_list) == {'非风险警示股', 'ST股'}:
            df = df[~df['name'].str.contains('\\*ST', na=False, regex=False)]
        elif set(risk_list) == {'非风险警示股', '*ST股'}:
            df = df[~df['name'].str.contains('ST', na=False) | df['name'].str.contains('\\*ST', na=False, regex=False)]
        elif set(risk_list) == {'ST股', '*ST股'}:
            df = df[df['name'].str.contains('ST', na=False)]
        log__(f"风险警示筛选后剩余 {len(df)} 只股票")

    # 5.6 名称关键字筛选
    name_keywords = Parameter_dict__['股票']['名称（关键字）']
    if name_keywords and None not in name_keywords and not df.empty:
        mask = pd.Series([False] * len(df), index=df.index)
        for kw in name_keywords:
            if kw:
                mask |= df['name'].str.contains(kw, na=False)
        df = df[mask]
        log__(f"名称关键字筛选后剩余 {len(df)} 只股票")

    # ---------- 6. 指标筛选（数值范围） ----------
    metric_conditions = Parameter_dict__.get('metric_conditions', {})
    if metric_conditions and not df.empty:
        # 筛选条件，注意字段名与数据库列名映射
        metric_map = {
            '最近收盘价': 'close',
            '动态市盈率': 'pe',
            '市净率': 'pb',
            '总市值（亿元）': 'total_mv',
            '流通市值（亿元）': 'circ_mv'
        }
        for metric_name, bounds in metric_conditions.items():
            if metric_name not in metric_map:
                continue
            col = metric_map[metric_name]
            min_val = bounds.get('下限')
            max_val = bounds.get('上限')
            if min_val is not None or max_val is not None:
                # 注意：总市值和流通市值在 df 中是万元，需除以10000转为亿元以匹配用户输入
                if col in ['total_mv', 'circ_mv']:
                    # 但我们已在上面的转换中未直接使用df中的原值，但这里用的是合并后的df，字段是原始值（万元）
                    # 所以比较时需要转换
                    col_series = df[col] / 10000  # 转为亿元
                else:
                    col_series = df[col]
                if min_val is not None:
                    df = df[col_series >= min_val]
                if max_val is not None:
                    df = df[col_series <= max_val]
                log__(f"指标 '{metric_name}' 筛选后剩余 {len(df)} 只股票")
                if df.empty:
                    break

    # ---------- 7. 转换为输出格式 ----------
    result_list = process_securities(df, sec_type)
    log__(f"最终筛选出 {len(result_list)} 个证券")
    return result_list, sec_type


def Main_function_apply_metric_filter__(para_securities_list__, metric_conditions__):
    filtered_list__ = []
    for security__ in para_securities_list__:
        match__ = True
        for metric_name__, conditions__ in metric_conditions__.items():
            min_value__ = conditions__['下限']
            max_value__ = conditions__['上限']
            if min_value__ is None and max_value__ is None:
                continue
            security_value__ = security__.get(metric_name__)
            if security_value__ == 'None' or security_value__ is None:
                match__ = False
                break
            try:
                security_value_float__ = float(security_value__)
            except (ValueError, TypeError):
                match__ = False
                break
            if min_value__ is not None and security_value_float__ < min_value__:
                match__ = False
                break
            if max_value__ is not None and security_value_float__ > max_value__:
                match__ = False
                break
        if match__:
            filtered_list__.append(security__)
    return filtered_list__

# =========================== 【↑核心筛选函数↑】 ===========================





# =========================== 【↓导出筛选列表↓】 ===========================
def Main_function_write_securities_to_excel__(parameter_securities_type__, List_securities_data__):
    Dict_market_indicator_securities_type__ = {
        '股票': [('最近收盘价', 'f2'), ('动态市盈率', 'f9'), ('市净率', 'f23'), ('总市值（亿元）', 'f20'), ('流通市值（亿元）', 'f21')],
        '指数': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('量比', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')],
        'ETF': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('涨跌额', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')],
        'LOF': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('涨跌额', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')],
        '国债': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('涨跌额', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')],
        '企债': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('涨跌额', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')],
        '可转债': [('最近收盘价', 'f2'), ('涨跌幅', 'f3'), ('涨跌额', 'f4'), ('成交量（万手）', 'f5'), ('成交额（万元）', 'f6')]
    }

    List_tuple_para__ = Dict_market_indicator_securities_type__[parameter_securities_type__]
    workbook__ = Workbook()
    worksheet__ = workbook__.active
    worksheet__.title = "证券筛选表"
    List_headers__ = ["证券种类", "证券名称", "证券代码", "交易板块"]
    for loop_field_name__, _ in List_tuple_para__:
        List_headers__.append(loop_field_name__)
    worksheet__.append(List_headers__)

    for loop_security_info__ in List_securities_data__:
        List_row_data__ = [
            loop_security_info__.get("证券种类", ""),
            loop_security_info__.get("证券名称", ""),
            loop_security_info__.get("证券代码", ""),
            loop_security_info__.get("交易板块", "")
        ]
        for loop_field_name__, _ in List_tuple_para__:
            value__ = loop_security_info__.get(loop_field_name__, "")
            if value__ == 'None' or value__ is None:
                List_row_data__.append("")
            else:
                List_row_data__.append(value__)
        worksheet__.append(List_row_data__)

    for loop_column__ in worksheet__.columns:
        max_length__ = 0
        column_letter__ = loop_column__[0].column_letter
        for loop_cell__ in loop_column__:
            try:
                if len(str(loop_cell__.value)) > max_length__:
                    max_length__ = len(str(loop_cell__.value))
            except:
                pass
        adjusted_width__ = min(max_length__ + 2, 30)
        worksheet__.column_dimensions[column_letter__].width = adjusted_width__

    return workbook__
# =========================== 【↑导出Excel函数↑】 ===========================





# =========================== 【↓获取历史数据↓】 ===========================

def Main_function_Get_security_histinfo_json__(Parameter_info_tuple__, Parameter_K_line_type__, Parameter_dir_path__):
    """
    从 DuckDB 数据库获取指定证券的历史K线数据（日/周/月）
    Parameter_info_tuple__: (证券种类, 证券名称, 证券代码, 交易板块)
    Parameter_K_line_type__: "101"(日K), "102"(周K), "103"(月K)
    """
    # 构建 ts_code
    code__ = Parameter_info_tuple__[2]
    exchange__ = Parameter_info_tuple__[3]
    ts_code__ = Tool_function_build_ts_code__(code__, exchange__)

    try:
        conn = duckdb.connect(DB_PATH)

        # ---------- 1. 获取日K换手率（从 Tushare daily_basic，使用高级 Token） ----------
        df_turnover = pd.DataFrame()
        if TUSHARE_TOKENS_2000__:
            try:
                ts.set_token(TUSHARE_TOKENS_2000__[0])
                pro_adv = ts.pro_api()
                df_turnover = pro_adv.daily_basic(ts_code=ts_code__, fields='trade_date,turnover_rate')
                if df_turnover is not None and not df_turnover.empty:
                    df_turnover['trade_date'] = df_turnover['trade_date'].astype(str)
                    df_turnover = df_turnover.drop_duplicates(subset='trade_date')
                else:
                    df_turnover = pd.DataFrame()
            except Exception as e:
                print(f"获取换手率失败: {e}")
                df_turnover = pd.DataFrame()
        else:
            print("警告：未配置高级Token，换手率将设为0")

        # ---------- 2. 从数据库读取日K数据 ----------
        df_daily_db = conn.execute('''
            SELECT ts_code, trade_date, open, close, high, low, vol, amount, 
                   pre_close, amp, pct_chg, change
            FROM "日度信息表"
            WHERE ts_code = ?
            ORDER BY trade_date
        ''', [ts_code__]).fetchdf()

        if df_daily_db.empty:
            conn.close()
            return {'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '', 'data': None}

        # 将日K的 trade_date 转为字符串 YYYYMMDD，以便与 df_turnover 合并
        df_daily_db['trade_date'] = pd.to_datetime(df_daily_db['trade_date']).dt.strftime('%Y%m%d')

        # 合并换手率（如果有）
        if not df_turnover.empty:
            df_daily_db = df_daily_db.merge(df_turnover, on='trade_date', how='left')
            df_daily_db['turnover_rate'] = df_daily_db['turnover_rate'].fillna(0)
        else:
            df_daily_db['turnover_rate'] = 0

        # 推算流通股本（用于周/月换手率）：取最近一个 turnover_rate>0 且 vol>0 的交易日
        float_share_est = None
        df_valid = df_daily_db[(df_daily_db['turnover_rate'] > 0) & (df_daily_db['vol'] > 0)]
        if not df_valid.empty:
            last_valid = df_valid.iloc[-1]
            float_share_est = last_valid['vol'] / last_valid['turnover_rate']

        # ---------- 3. 根据K线类型返回数据 ----------
        if Parameter_K_line_type__ == '101':  # 日K
            klines = []
            for _, row in df_daily_db.iterrows():
                kline_str = (f"{row['trade_date']},{row['open']:.2f},{row['close']:.2f},"
                             f"{row['high']:.2f},{row['low']:.2f},{row['vol']:.0f},"
                             f"{row['amount']:.2f},{row['amp']:.2f},{row['pct_chg']:.2f},"
                             f"{row['change']:.2f},{row['turnover_rate']:.2f}")
                klines.append(kline_str)
            conn.close()
            return {
                'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '',
                'data': {'klines': klines}
            }

        elif Parameter_K_line_type__ == '102':  # 周K
            df_weekly = conn.execute('''
                SELECT trade_date, open_w, close_w, high_w, low_w, vol_w, amount_w,
                       pre_close_w, amp_w, pct_chg_w, change_w
                FROM "周度信息表"
                WHERE ts_code = ?
                ORDER BY trade_date
            ''', [ts_code__]).fetchdf()
            if df_weekly.empty:
                conn.close()
                return {'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '', 'data': None}
            # 将日期转为字符串 YYYYMMDD
            df_weekly['trade_date'] = pd.to_datetime(df_weekly['trade_date']).dt.strftime('%Y%m%d')
            klines = []
            for _, row in df_weekly.iterrows():
                turnover = 0
                if float_share_est and float_share_est > 0 and row['vol_w'] > 0:
                    turnover = row['vol_w'] / float_share_est
                kline_str = (f"{row['trade_date']},{row['open_w']:.2f},{row['close_w']:.2f},"
                             f"{row['high_w']:.2f},{row['low_w']:.2f},{row['vol_w']:.0f},"
                             f"{row['amount_w']:.2f},{row['amp_w']:.2f},{row['pct_chg_w']:.2f},"
                             f"{row['change_w']:.2f},{turnover:.2f}")
                klines.append(kline_str)
            conn.close()
            return {
                'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '',
                'data': {'klines': klines}
            }

        elif Parameter_K_line_type__ == '103':  # 月K
            df_monthly = conn.execute('''
                SELECT trade_date, open_m, close_m, high_m, low_m, vol_m, amount_m,
                       pre_close_m, amp_m, pct_chg_m, change_m
                FROM "月度信息表"
                WHERE ts_code = ?
                ORDER BY trade_date
            ''', [ts_code__]).fetchdf()
            if df_monthly.empty:
                conn.close()
                return {'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '', 'data': None}
            df_monthly['trade_date'] = pd.to_datetime(df_monthly['trade_date']).dt.strftime('%Y%m%d')
            klines = []
            for _, row in df_monthly.iterrows():
                turnover = 0
                if float_share_est and float_share_est > 0 and row['vol_m'] > 0:
                    turnover = row['vol_m'] / float_share_est
                kline_str = (f"{row['trade_date']},{row['open_m']:.2f},{row['close_m']:.2f},"
                             f"{row['high_m']:.2f},{row['low_m']:.2f},{row['vol_m']:.0f},"
                             f"{row['amount_m']:.2f},{row['amp_m']:.2f},{row['pct_chg_m']:.2f},"
                             f"{row['change_m']:.2f},{turnover:.2f}")
                klines.append(kline_str)
            conn.close()
            return {
                'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '',
                'data': {'klines': klines}
            }

        else:
            conn.close()
            return {'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '', 'data': None}

    except Exception as e:
        print(f"获取历史数据失败: {e}")
        traceback.print_exc()
        return {'rc': 0, 'rt': 0, 'svr': 0, 'lt': 0, 'full': 0, 'dlmkts': '', 'data': None}
# =========================== 【↑获取历史数据↑】 ===========================





# =========================== 【↓获取财务报表↓】 ===========================
def Tool_function_build_ts_code__(code__, exchange__):
    """
    根据证券代码判断正确的Tushare ts_code后缀
    规则：
    - 60xxxx -> .SH (上证主板/科创板)
    - 688xxx -> .SH (科创板)
    - 00xxxx, 30xxxx -> .SZ (深证主板/创业板)
    - 83xxxx, 87xxxx, 43xxxx, 92xxxx -> .BJ (北交所)
    如果无法判断，则根据传入的exchange参数辅助判断。
    """
    code_str = str(code__).strip()
    
    # 根据代码开头数字判断
    if code_str.startswith('60'):
        return f"{code_str}.SH"
    elif code_str.startswith('68'):
        return f"{code_str}.SH"
    elif code_str.startswith('00') or code_str.startswith('30'):
        return f"{code_str}.SZ"
    elif code_str.startswith(('83', '87', '43', '92')):
        return f"{code_str}.BJ"
    
    # 根据传入的exchange参数辅助判断
    if exchange__ in ['上证主板', '科创板', '上证A股']:
        return f"{code_str}.SH"
    elif exchange__ in ['深证主板', '创业板', '深证A股']:
        return f"{code_str}.SZ"
    elif exchange__ in ['北交所', '北证A股']:
        return f"{code_str}.BJ"
    
    # 默认返回 .SH (但这种情况不应发生)
    return f"{code_str}.SH"

def Tool_function_get_actual_latest_periods__(parameter_ts_code__, parameter_pro__):
    """获取三年一期报告期列表（允许重复）"""
    try:
        df_income_all__ = parameter_pro__.income(
            ts_code=parameter_ts_code__,
            fields='end_date,report_type'
        )
        if df_income_all__ is None or df_income_all__.empty:
            return Tool_function_get_fallback_periods__()
        
        df_merged__ = df_income_all__[df_income_all__['report_type'] == '1'].drop_duplicates(subset=['end_date'])
        df_merged__ = df_merged__.sort_values('end_date', ascending=False)
        
        List_all_periods__ = df_merged__['end_date'].tolist()
        if not List_all_periods__:
            return Tool_function_get_fallback_periods__()
        
        str_latest__ = List_all_periods__[0]
        List_annual_periods__ = []
        int_latest_year__ = int(str_latest__[:4])
        for year__ in range(int_latest_year__, int_latest_year__ - 5, -1):
            str_annual__ = f"{year__}1231"
            if str_annual__ <= str_latest__ and str_annual__ in List_all_periods__:
                List_annual_periods__.append(str_annual__)
            if len(List_annual_periods__) >= 3:
                break
        
        List_final__ = [str_latest__] + List_annual_periods__
        List_final__.sort()
        return List_final__
        
    except Exception as e__:
        print(f"动态获取期间失败，使用回退方案: {e__}")
        return Tool_function_get_fallback_periods__()

def Tool_function_get_fallback_periods__():
    int_current_year__ = datetime.now().year
    List_annuals__ = [f"{int_current_year__ - i__}1231" for i__ in range(3)]
    List_final__ = [f"{int_current_year__}1231"] + List_annuals__
    List_final__.sort()
    return List_final__

def Tool_function_dedupe_dataframe__(parameter_df__, parameter_key__='end_date'):
    if parameter_df__ is None or parameter_df__.empty:
        return parameter_df__
    df__ = parameter_df__.copy()
    if 'report_type' in df__.columns:
        df__['_priority'] = df__['report_type'].apply(lambda x: 0 if x == '1' else 1)
        df__ = df__.sort_values('_priority').drop_duplicates(subset=[parameter_key__], keep='first')
        df__ = df__.drop(columns=['_priority'])
    else:
        df__ = df__.drop_duplicates(subset=[parameter_key__], keep='first')
    return df__

def Tool_function_calculate_missing_metrics_enhanced__(
        parameter_df_fina__, 
        parameter_df_income__, 
        parameter_df_balance__,
        parameter_target_periods__
    ):
    if parameter_df_fina__ is None or parameter_df_fina__.empty:
        return None

    dict_income__ = {}
    if parameter_df_income__ is not None and not parameter_df_income__.empty:
        for _, row__ in parameter_df_income__.iterrows():
            dict_income__[row__['end_date']] = row__

    dict_balance__ = {}
    if parameter_df_balance__ is not None and not parameter_df_balance__.empty:
        for _, row__ in parameter_df_balance__.iterrows():
            dict_balance__[row__['end_date']] = row__

    df_target__ = parameter_df_fina__[parameter_df_fina__['end_date'].isin(parameter_target_periods__)].copy()
    df_target__ = df_target__.sort_values('end_date').reset_index(drop=True)

    for idx__, row__ in df_target__.iterrows():
        period__ = row__['end_date']
        int_year__ = int(period__[:4])
        str_prev_year_period__ = f"{int_year__-1}{period__[4:]}"

        income_curr__ = dict_income__.get(period__)
        income_prev__ = dict_income__.get(str_prev_year_period__)

        if income_curr__ is not None and income_prev__ is not None:
            curr_op__ = Tool_function_get_field_value__(income_curr__, 'operate_profit')
            prev_op__ = Tool_function_get_field_value__(income_prev__, 'operate_profit')
            yoy_op__ = Tool_function_calculate_yoy__(curr_op__, prev_op__)
            df_target__.loc[idx__, 'profit_yoy_calc'] = yoy_op__

            curr_net__ = Tool_function_get_field_value__(income_curr__, 'n_income')
            prev_net__ = Tool_function_get_field_value__(income_prev__, 'n_income')
            yoy_net__ = Tool_function_calculate_yoy__(curr_net__, prev_net__)
            df_target__.loc[idx__, 'q_profit_yoy_calc'] = yoy_net__

        curr_eps__ = Tool_function_get_field_value__(row__, 'eps')
        prev_fina__ = parameter_df_fina__[parameter_df_fina__['end_date'] == str_prev_year_period__]
        if not prev_fina__.empty:
            prev_eps__ = Tool_function_get_field_value__(prev_fina__.iloc[0], 'eps')
            yoy_eps__ = Tool_function_calculate_yoy__(curr_eps__, prev_eps__)
            df_target__.loc[idx__, 'eps_yoy_calc'] = yoy_eps__

        balance_curr__ = dict_balance__.get(period__)
        balance_prev__ = dict_balance__.get(str_prev_year_period__)

        if income_curr__ is not None and balance_curr__ is not None and balance_prev__ is not None:
            revenue__ = Tool_function_get_field_value__(income_curr__, 'revenue')
            cost__ = Tool_function_get_field_value__(income_curr__, 'total_cogs')

            inv_curr__ = Tool_function_get_field_value__(balance_curr__, 'inventories')
            inv_prev__ = Tool_function_get_field_value__(balance_prev__, 'inventories')
            avg_inv__ = (inv_curr__ + inv_prev__) / 2 if inv_curr__ and inv_prev__ else None
            inv_turn__ = Tool_function_safe_divide__(cost__, avg_inv__)
            df_target__.loc[idx__, 'inv_turn_calc'] = inv_turn__

            ar_curr__ = Tool_function_get_field_value__(balance_curr__, 'accounts_receiv')
            ar_prev__ = Tool_function_get_field_value__(balance_prev__, 'accounts_receiv')
            avg_ar__ = (ar_curr__ + ar_prev__) / 2 if ar_curr__ and ar_prev__ else None
            ar_turn__ = Tool_function_safe_divide__(revenue__, avg_ar__)
            df_target__.loc[idx__, 'ar_turn_calc'] = ar_turn__

            asset_curr__ = Tool_function_get_field_value__(balance_curr__, 'total_assets')
            asset_prev__ = Tool_function_get_field_value__(balance_prev__, 'total_assets')
            avg_asset__ = (asset_curr__ + asset_prev__) / 2 if asset_curr__ and asset_prev__ else None
            asset_turn__ = Tool_function_safe_divide__(revenue__, avg_asset__)
            df_target__.loc[idx__, 'assets_turn_calc'] = asset_turn__

            if inv_turn__ and inv_turn__ > 0:
                df_target__.loc[idx__, 'invturn_days_calc'] = 365 / inv_turn__
            if ar_turn__ and ar_turn__ > 0:
                df_target__.loc[idx__, 'arturn_days_calc'] = 365 / ar_turn__

    return df_target__

def Tool_function_format_value__(parameter_value__, parameter_decimals__=2):
    if parameter_value__ is None or pd.isna(parameter_value__):
        return None
    try:
        if parameter_decimals__ == 0:
            return int(parameter_value__)
        return round(float(parameter_value__), parameter_decimals__)
    except:
        return None

def Tool_function_safe_divide__(parameter_numerator__, parameter_denominator__):
    if parameter_numerator__ is None or parameter_denominator__ is None or parameter_denominator__ == 0:
        return None
    return parameter_numerator__ / parameter_denominator__

def Tool_function_calculate_yoy__(parameter_current__, parameter_previous__):
    if parameter_current__ is None or parameter_previous__ is None or parameter_previous__ == 0:
        return None
    return (parameter_current__ / parameter_previous__ - 1) * 100

def Tool_function_get_field_value__(parameter_row__, parameter_field__, parameter_default__=None):
    if parameter_field__ in parameter_row__.index:
        val__ = parameter_row__[parameter_field__]
        if pd.isna(val__):
            return parameter_default__
        return val__
    return parameter_default__

def clean_nan(obj):
    """递归清理对象中的 NaN/Infinity，替换为 None"""
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    else:
        return obj

def Main_function_format_period_display__(parameter_period__, parameter_suffix__=''):
    if pd.isna(parameter_period__):
        return str(parameter_period__)
    str_period__ = str(parameter_period__)
    if len(str_period__) == 8:
        year__ = str_period__[:4]
        month_day__ = str_period__[4:]
        if month_day__ == '1231':
            base__ = f"{year__}年报"
        elif month_day__ == '0930':
            base__ = f"{year__}三季报"
        elif month_day__ == '0630':
            base__ = f"{year__}中报"
        elif month_day__ == '0331':
            base__ = f"{year__}一季报"
        else:
            base__ = str_period__
        return base__ + parameter_suffix__
    return str_period__

def Main_function_get_financial_report_data__(parameter_ts_code__):
    """获取三年一期财务报表和指标数据，返回字典供前端渲染"""
    try:
        List_target_periods__ = Tool_function_get_actual_latest_periods__(parameter_ts_code__, pro__)
        # 处理重复期（若最近一期为年报则重复）
        counter__ = Counter(List_target_periods__)
        List_display_periods__ = []
        seen__ = {}
        for p__ in List_target_periods__:
            if counter__[p__] > 1:
                seen__[p__] = seen__.get(p__, 0) + 1
                suffix__ = " (最新)" if seen__[p__] == 2 else f" ({seen__[p__]})"
            else:
                suffix__ = ""
            List_display_periods__.append({
                'code': p__,
                'name': Main_function_format_period_display__(p__, suffix__)
            })
        
        # 实际请求范围（需要包括上一年同期以计算同比）
        List_request_periods__ = set(List_target_periods__)
        for p__ in List_target_periods__:
            if len(p__) == 8 and p__[4:] == '1231':
                List_request_periods__.add(f"{int(p__[:4])-1}1231")
        List_request_periods__ = sorted(List_request_periods__)
        
        # 获取数据
        def fetch_interface__(interface_name__, fetch_func__, period_list__):
            frames__ = []
            for period__ in period_list__:
                try:
                    df_tmp__ = fetch_func__(ts_code=parameter_ts_code__, period=period__)
                    if df_tmp__ is not None and not df_tmp__.empty:
                        frames__.append(df_tmp__)
                    time.sleep(0.3)
                except:
                    pass
            if frames__:
                df__ = pd.concat(frames__, ignore_index=True)
                df__ = Tool_function_dedupe_dataframe__(df__)
                return df__.sort_values('end_date')
            return None
        
        df_fina__ = fetch_interface__('fina_indicator', pro__.fina_indicator, List_request_periods__)
        df_income__ = fetch_interface__('income', pro__.income, List_request_periods__)
        df_balance__ = fetch_interface__('balancesheet', pro__.balancesheet, List_request_periods__)
        df_cashflow__ = fetch_interface__('cashflow', pro__.cashflow, List_request_periods__)
        
        # 计算增强指标
        df_fina_enhanced__ = Tool_function_calculate_missing_metrics_enhanced__(
            df_fina__, df_income__, df_balance__, List_target_periods__
        )
        
        # 对齐展示期
        def align_df__(df__):
            if df__ is None or df__.empty:
                return None
            df_a__ = df__[df__['end_date'].isin(List_target_periods__)].copy()
            df_a__ = df_a__.set_index('end_date').reindex(List_target_periods__).reset_index()
            return df_a__
        
        df_income_show__ = align_df__(df_income__)
        df_balance_show__ = align_df__(df_balance__)
        df_cashflow_show__ = align_df__(df_cashflow__)
        df_fina_show__ = align_df__(df_fina_enhanced__)
        
        # 准备返回数据
        # 报表项目映射（中文）
        Dict_cn_mapping__ = {
            # 利润表
            'basic_eps': '基本每股收益',
            'diluted_eps': '稀释每股收益',
            'total_revenue': '营业总收入',
            'revenue': '营业收入',
            'int_income': '利息收入',
            'prem_earned': '已赚保费',
            'comm_income': '手续费及佣金收入',
            'n_commis_income': '手续费及佣金净收入',
            'n_oth_income': '其他经营净收益',
            'n_oth_b_income': '其他业务净收入',
            'prem_income': '保费收入',
            'out_prem': '分出保费',
            'une_prem_reser': '未到期责任准备金',
            'reins_income': '分保收入',
            'n_sec_tb_income': '代理买卖证券业务净收入',
            'n_sec_uw_income': '证券承销业务净收入',
            'n_asset_mg_income': '受托客户资产管理业务净收入',
            'oth_b_income': '其他业务收入',
            'fv_value_chg_gain': '公允价值变动收益',
            'invest_income': '投资收益',
            'ass_invest_income': '对联营企业和合营企业的投资收益',
            'forex_gain': '汇兑收益',
            'total_cogs': '营业总成本',
            'oper_cost': '营业成本',
            'int_exp': '利息支出',
            'comm_exp': '手续费及佣金支出',
            'biz_tax_surchg': '税金及附加',
            'sell_exp': '销售费用',
            'admin_exp': '管理费用',
            'fin_exp': '财务费用',
            'assets_impair_loss': '资产减值损失',
            'prem_refund': '退保金',
            'compens_payout': '赔付支出',
            'reser_insur_liab': '提取保险责任准备金',
            'div_payt': '保单红利支出',
            'reins_exp': '分保费用',
            'oper_exp': '业务及管理费',
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
            'insurance_exp': '保险业务支出',
            'undist_profit': '未分配利润',
            'distable_profit': '可供分配的利润',
            'rd_exp': '研发费用',
            'fin_exp_int_exp': '利息费用',
            'fin_exp_int_inc': '利息收入',
            'transfer_surplus_rese': '盈余公积转入',
            'transfer_housing_imprest': '住房周转金转入',
            'transfer_oth': '其他转入',
            'adj_lossgain': '调整以前年度损益',
            'withdra_legal_surplus': '提取法定盈余公积',
            'withdra_legal_pubfund': '提取法定公益金',
            'withdra_biz_devfund': '提取企业发展基金',
            'withdra_rese_fund': '提取储备基金',
            'withdra_oth_ersu': '提取其他盈余公积',
            'workers_welfare': '职工奖励及福利基金',
            'distr_profit_shrhder': '应付股东股利',
            'prfshare_payable_dvd': '应付优先股股利',
            'comshare_payable_dvd': '应付普通股股利',
            'capit_comstock_div': '转作股本的普通股股利',
            'continued_net_profit': '持续经营净利润',

            # 资产负债表
            'total_share': '实收资本(或股本)',
            'cap_rese': '资本公积',
            'undistr_porfit': '未分配利润',
            'surplus_rese': '盈余公积',
            'special_rese': '专项储备',
            'money_cap': '货币资金',
            'trad_asset': '交易性金融资产',
            'notes_receiv': '应收票据',
            'accounts_receiv': '应收账款',
            'oth_receiv': '其他应收款',
            'prepayment': '预付款项',
            'div_receiv': '应收股利',
            'int_receiv': '应收利息',
            'inventories': '存货',
            'amor_exp': '待摊费用',
            'nca_within_1y': '一年内到期的非流动资产',
            'sett_rsrv': '结算备付金',
            'loanto_oth_bank_fi': '拆出资金',
            'premium_receiv': '应收保费',
            'reinsur_receiv': '应收分保账款',
            'reinsur_res_receiv': '应收分保合同准备金',
            'pur_resale_fa': '买入返售金融资产',
            'oth_cur_assets': '其他流动资产',
            'total_cur_assets': '流动资产合计',
            'fa_avail_for_sale': '可供出售金融资产',
            'htm_invest': '持有至到期投资',
            'lt_eqt_invest': '长期股权投资',
            'invest_real_estate': '投资性房地产',
            'time_deposits': '定期存款',
            'oth_assets': '其他资产',
            'lt_rec': '长期应收款',
            'fix_assets': '固定资产',
            'cip': '在建工程',
            'const_materials': '工程物资',
            'fixed_assets_disp': '固定资产清理',
            'produc_bio_assets': '生产性生物资产',
            'oil_and_gas_assets': '油气资产',
            'intan_assets': '无形资产',
            'r_and_d': '开发支出',
            'goodwill': '商誉',
            'lt_amor_exp': '长期待摊费用',
            'defer_tax_assets': '递延所得税资产',
            'decr_in_disbur': '待处理财产损溢',
            'oth_nca': '其他非流动资产',
            'total_nca': '非流动资产合计',
            'cash_reser_cb': '存放中央银行款项',
            'depos_in_oth_bfi': '存放同业款项',
            'prec_metals': '贵金属',
            'deriv_assets': '衍生金融资产',
            'rr_reins_une_prem': '应收分保未到期责任准备金',
            'rr_reins_outstd_cla': '应收分保未决赔款准备金',
            'rr_reins_lins_liab': '应收分保寿险责任准备金',
            'rr_reins_lthins_liab': '应收分保长期健康险责任准备金',
            'refund_depos': '存出保证金',
            'ph_pledge_loans': '保户质押贷款',
            'refund_cap_depos': '存出资本保证金',
            'indep_acct_assets': '独立账户资产',
            'client_depos': '客户资金存款',
            'client_prov': '客户备付金',
            'transac_seat_fee': '交易席位费',
            'invest_as_receiv': '应收款项类投资',
            'total_assets': '资产总计',
            'lt_borr': '长期借款',
            'st_borr': '短期借款',
            'cb_borr': '向中央银行借款',
            'depos_ib_deposits': '吸收存款及同业存放',
            'loan_oth_bank': '拆入资金',
            'trading_fl': '交易性金融负债',
            'notes_payable': '应付票据',
            'acct_payable': '应付账款',
            'adv_receipts': '预收款项',
            'sold_for_repur_fa': '卖出回购金融资产款',
            'comm_payable': '应付手续费及佣金',
            'payroll_payable': '应付职工薪酬',
            'taxes_payable': '应交税费',
            'int_payable': '应付利息',
            'div_payable': '应付股利',
            'oth_payable': '其他应付款',
            'acc_exp': '预提费用',
            'deferred_inc': '递延收益',
            'st_bonds_payable': '应付短期债券',
            'payable_to_reinsurer': '应付分保账款',
            'rsrv_insur_cont': '保险合同准备金',
            'acting_trading_sec': '代理买卖证券款',
            'acting_uw_sec': '代理承销证券款',
            'non_cur_liab_due_1y': '一年内到期的非流动负债',
            'oth_cur_liab': '其他流动负债',
            'total_cur_liab': '流动负债合计',
            'bond_payable': '应付债券',
            'lt_payable': '长期应付款',
            'specific_payables': '专项应付款',
            'estimated_liab': '预计负债',
            'defer_tax_liab': '递延所得税负债',
            'defer_inc_non_cur_liab': '递延收益-非流动负债',
            'oth_ncl': '其他非流动负债',
            'total_ncl': '非流动负债合计',
            'depos_oth_bfi': '同业及其他金融机构存放款项',
            'deriv_liab': '衍生金融负债',
            'depos': '吸收存款',
            'agency_bus_liab': '代理业务负债',
            'oth_liab': '其他负债',
            'prem_receiv_adva': '预收保费',
            'depos_received': '存入保证金',
            'ph_invest': '保户储金及投资款',
            'reser_une_prem': '未到期责任准备金',
            'reser_outstd_claims': '未决赔款准备金',
            'reser_lins_liab': '寿险责任准备金',
            'reser_lthins_liab': '长期健康险责任准备金',
            'indept_acc_liab': '独立账户负债',
            'pledge_borr': '质押借款',
            'indem_payable': '应付赔付款',
            'policy_div_payable': '应付保单红利',
            'total_liab': '负债合计',
            'treasury_share': '库存股',
            'ordin_risk_reser': '一般风险准备',
            'forex_differ': '外币报表折算差额',
            'invest_loss_unconf': '未确认的投资损失',
            'minority_int': '少数股东权益',
            'total_hldr_eqy_exc_min_int': '归属于母公司股东权益合计',
            'total_hldr_eqy_inc_min_int': '股东权益合计',
            'total_liab_hldr_eqy': '负债及股东权益总计',
            'lt_payroll_payable': '长期应付职工薪酬',
            'oth_comp_income': '其他综合收益',
            'oth_eqt_tools': '其他权益工具',
            'oth_eqt_tools_p_shr': '其他权益工具(优先股)',
            'lending_funds': '拆出资金',
            'acc_receivable': '应收款项',
            'st_fin_payable': '短期融资券',
            'payables': '应付款项',
            'hfs_assets': '持有待售资产',
            'hfs_sales': '持有待售负债',
            'cost_fin_assets': '以摊余成本计量的金融资产',
            'fair_value_fin_assets': '以公允价值计量且其变动计入其他综合收益的金融资产',
            'contract_assets': '合同资产',
            'contract_liab': '合同负债',
            'accounts_receiv_bill': '应收票据及应收账款',
            'accounts_pay': '应付票据及应付账款',
            'oth_rcv_total': '其他应收款合计',
            'fix_assets_total': '固定资产合计',
            'cip_total': '在建工程合计',
            'oth_pay_total': '其他应付款合计',
            'long_pay_total': '长期应付款合计',
            'debt_invest': '债权投资',
            'oth_debt_invest': '其他债权投资',

            # 现金流量表
            'net_profit': '净利润',
            'finan_exp': '财务费用',
            'c_fr_sale_sg': '销售商品、提供劳务收到的现金',
            'recp_tax_rends': '收到的税费返还',
            'n_depos_incr_fi': '客户存款和同业存放款项净增加额',
            'n_incr_loans_cb': '向中央银行借款净增加额',
            'n_inc_borr_oth_fi': '向其他金融机构拆入资金净增加额',
            'prem_fr_orig_contr': '收到原保险合同保费取得的现金',
            'n_incr_insured_dep': '保户储金及投资款净增加额',
            'n_reinsur_prem': '收到再保险业务现金净额',
            'n_incr_disp_tfa': '处置交易性金融资产净增加额',
            'ifc_cash_incr': '收取利息、手续费及佣金的现金',
            'n_incr_disp_faas': '拆入资金净增加额',
            'n_incr_loans_oth_bank': '回购业务资金净增加额',
            'n_cap_incr_repur': '客户贷款及垫款净增加额',
            'c_fr_oth_operate_a': '收到其他与经营活动有关的现金',
            'c_inf_fr_operate_a': '经营活动现金流入小计',
            'c_paid_goods_s': '购买商品、接受劳务支付的现金',
            'c_paid_to_for_empl': '支付给职工以及为职工支付的现金',
            'c_paid_for_taxes': '支付的各项税费',
            'n_incr_clt_loan_adv': '客户贷款及垫款净增加额',
            'n_incr_dep_cbob': '存放中央银行和同业款项净增加额',
            'c_pay_claims_orig_inco': '支付原保险合同赔付款项的现金',
            'pay_handling_chrg': '支付手续费的现金',
            'pay_comm_insur_plcy': '支付保单红利的现金',
            'oth_cash_pay_oper_act': '支付其他与经营活动有关的现金',
            'st_cash_out_act': '经营活动现金流出小计',
            'n_cashflow_act': '经营活动产生的现金流量净额',
            'oth_recp_ral_inv_act': '收到其他与投资活动有关的现金',
            'c_disp_withdrwl_invest': '收回投资收到的现金',
            'c_recp_return_invest': '取得投资收益收到的现金',
            'n_recp_disp_fiolta': '处置固定资产、无形资产和其他长期资产收回的现金净额',
            'n_recp_disp_sobu': '处置子公司及其他营业单位收到的现金净额',
            'stot_inflows_inv_act': '投资活动现金流入小计',
            'c_pay_acq_const_fiolta': '购建固定资产、无形资产和其他长期资产支付的现金',
            'c_paid_invest': '投资支付的现金',
            'n_disp_subs_oth_biz': '取得子公司及其他营业单位支付的现金净额',
            'oth_pay_ral_inv_act': '支付其他与投资活动有关的现金',
            'n_incr_pledge_loan': '质押贷款净增加额',
            'stot_out_inv_act': '投资活动现金流出小计',
            'n_cashflow_inv_act': '投资活动产生的现金流量净额',
            'c_recp_borrow': '取得借款收到的现金',
            'proc_issue_bonds': '发行债券收到的现金',
            'oth_cash_recp_ral_fnc_act': '收到其他与筹资活动有关的现金',
            'stot_cash_in_fnc_act': '筹资活动现金流入小计',
            'free_cashflow': '自由现金流',
            'c_prepay_amt_borr': '偿还债务支付的现金',
            'c_pay_dist_dpcp_int_exp': '分配股利、利润或偿付利息支付的现金',
            'incl_dvd_profit_paid_sc_ms': '子公司支付给少数股东的股利、利润',
            'oth_cashpay_ral_fnc_act': '支付其他与筹资活动有关的现金',
            'stot_cashout_fnc_act': '筹资活动现金流出小计',
            'n_cash_flows_fnc_act': '筹资活动产生的现金流量净额',
            'eff_fx_flu_cash': '汇率变动对现金及现金等价物的影响',
            'n_incr_cash_cash_equ': '现金及现金等价物净增加额',
            'c_cash_equ_beg_period': '期初现金及现金等价物余额',
            'c_cash_equ_end_period': '期末现金及现金等价物余额',
            'c_recp_cap_contrib': '吸收投资收到的现金',
            'incl_cash_rec_saims': '其中：子公司吸收少数股东投资收到的现金',
            'uncon_invest_loss': '未确认的投资损失',
            'prov_depr_assets': '资产减值准备',
            'depr_fa_coga_dpba': '固定资产折旧、油气资产折耗、生产性生物资产折旧',
            'amort_intang_assets': '无形资产摊销',
            'lt_amort_deferred_exp': '长期待摊费用摊销',
            'decr_deferred_exp': '待摊费用减少',
            'incr_acc_exp': '预提费用增加',
            'loss_disp_fiolta': '处置固定资产、无形资产和其他长期资产的损失',
            'loss_scr_fa': '固定资产报废损失',
            'loss_fv_chg': '公允价值变动损失',
            'invest_loss': '投资损失',
            'decr_def_inc_tax_assets': '递延所得税资产减少',
            'incr_def_inc_tax_liab': '递延所得税负债增加',
            'decr_inventories': '存货的减少',
            'decr_oper_payable': '经营性应收项目的减少',
            'incr_oper_payable': '经营性应付项目的增加',
            'others': '其他',
            'im_net_cashflow_oper_act': '经营活动产生的现金流量净额(间接法)',
            'conv_debt_into_cap': '债务转为资本',
            'conv_copbonds_due_within_1y': '一年内到期的可转换公司债券',
            'fa_fnc_leases': '融资租入固定资产',
            'im_n_incr_cash_equ': '现金及现金等价物净增加额(间接法)',
            'net_dism_capital_add': '处置子公司及其他收到的现金',
            'net_cash_rece_sec': '收到的其他与投资活动有关的现金',
            'credit_impa_loss': '信用减值损失',
            'use_right_asset_dep': '使用权资产折旧',
            'oth_loss_asset': '其他资产损失',
            'end_bal_cash': '现金的期末余额',
            'beg_bal_cash': '现金的期初余额',
            'end_bal_cash_equ': '现金等价物的期末余额',
            'beg_bal_cash_equ': '现金等价物的期初余额',
        }
        
        def extract_table_data__(df_show__, exclude_cols__):
            if df_show__ is None or df_show__.empty:
                return []
            exclude_cols__ = exclude_cols__ or ['ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type', 'update_flag']
            all_cols__ = df_show__.columns.tolist()
            project_cols__ = [c for c in all_cols__ if c not in exclude_cols__]
            
            rows__ = []
            for col__ in project_cols__:
                cn_name__ = Dict_cn_mapping__.get(col__, col__)
                values__ = []
                has_data__ = False
                for _, row__ in df_show__.iterrows():
                    val__ = Tool_function_get_field_value__(row__, col__)
                    if val__ is not None and not pd.isna(val__):
                        has_data__ = True
                        # 金额保留整数
                        try:
                            val__ = int(val__)
                        except:
                            pass
                    else:
                        val__ = None
                    values__.append(val__)
                if has_data__:  # 至少有一期有数据才展示
                    rows__.append({
                        'name': cn_name__,
                        'values': values__
                    })
            return rows__
        
        # 指标分组
        def extract_indicator_group__(df__, fields__, group_name__):
            if df__ is None or df__.empty:
                return []
            rows__ = []
            for field__, name__ in fields__:
                values__ = []
                has_data__ = False
                for _, row__ in df__.iterrows():
                    val__ = Tool_function_get_field_value__(row__, field__)
                    if val__ is not None and not pd.isna(val__):
                        has_data__ = True
                        # 百分比保留两位小数，比率保留两位小数
                        if 'yoy' in field__ or 'margin' in field__ or 'roe' in field__ or 'roa' in field__ or 'debt' in field__:
                            val__ = round(float(val__), 2)
                        else:
                            val__ = round(float(val__), 2)
                    else:
                        val__ = None
                    values__.append(val__)
                if has_data__:
                    rows__.append({
                        'name': name__,
                        'values': values__,
                        'unit': '%' if ('yoy' in field__ or 'margin' in field__ or 'roe' in field__ or 'roa' in field__ or 'debt' in field__) else ''
                    })
            return rows__
        
        # 盈利能力指标
        profit_fields__ = [
            ('roe', '净资产收益率(ROE)'),
            ('roa', '总资产报酬率(ROA)'),
            ('grossprofit_margin', '销售毛利率'),
            ('netprofit_margin', '销售净利率'),
            ('eps', '基本每股收益(EPS)'),
            ('bps', '每股净资产(BPS)'),
        ]
        # 成长能力
        growth_fields__ = [
            ('or_yoy', '营业收入同比增长率'),
            ('profit_yoy_calc', '营业利润同比增长率*'),
            ('q_profit_yoy_calc', '净利润同比增长率*'),
            ('eps_yoy_calc', '每股收益同比增长率*'),
            ('assets_yoy', '总资产同比增长率'),
        ]
        # 偿债能力
        solvency_fields__ = [
            ('current_ratio', '流动比率'),
            ('quick_ratio', '速动比率'),
            ('debt_to_assets', '资产负债率'),
            ('debt_to_eqt', '产权比率'),
        ]
        # 营运能力
        operation_fields__ = [
            ('ar_turn', '应收账款周转率'),
            ('ar_turn_calc', '应收账款周转率*'),
            ('inv_turn_calc', '存货周转率*'),
            ('assets_turn', '总资产周转率'),
            ('assets_turn_calc', '总资产周转率*'),
            ('arturn_days_calc', '应收账款周转天数*'),
            ('invturn_days_calc', '存货周转天数*'),
        ]
        
        result__ = {
            'periods': List_display_periods__,
            'balance': extract_table_data__(df_balance_show__, ['ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type', 'update_flag']),
            'income': extract_table_data__(df_income_show__, ['ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type', 'update_flag']),
            'cashflow': extract_table_data__(df_cashflow_show__, ['ts_code', 'ann_date', 'f_ann_date', 'end_date', 'report_type', 'comp_type', 'end_type', 'update_flag']),
            'indicators': {
                'profit': extract_indicator_group__(df_fina_show__, profit_fields__, 'profit'),
                'growth': extract_indicator_group__(df_fina_show__, growth_fields__, 'growth'),
                'solvency': extract_indicator_group__(df_fina_show__, solvency_fields__, 'solvency'),
                'operation': extract_indicator_group__(df_fina_show__, operation_fields__, 'operation')
            }
        }
        return result__
    except Exception as e__:
        print(f"获取财务报告数据失败: {e__}")
        return None

def Main_function_get_financial_data_optimized__(parameter_ts_code__):
    Dict_result__ = {
        'ts_code': parameter_ts_code__,
        'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fina_indicator': None,
        'income': None,
        'balancesheet': None,
        'cashflow': None,
        'errors': []
    }

    List_target_periods__ = Tool_function_get_actual_latest_periods__(parameter_ts_code__, pro__)
    List_request_periods__ = set(List_target_periods__)
    for p__ in List_target_periods__:
        if len(p__) == 8 and p__[4:] == '1231':
            List_request_periods__.add(f"{int(p__[:4])-1}1231")
    List_request_periods__ = sorted(List_request_periods__)

    def fetch_interface__(interface_name__, fetch_func__, period_list__):
        frames__ = []
        for period__ in period_list__:
            try:
                df_tmp__ = fetch_func__(ts_code=parameter_ts_code__, period=period__)
                if df_tmp__ is not None and not df_tmp__.empty:
                    frames__.append(df_tmp__)
                time.sleep(0.3)
            except Exception as e__:
                Dict_result__['errors'].append(f"{interface_name__} {period__}: {str(e__)}")
        if frames__:
            df__ = pd.concat(frames__, ignore_index=True)
            df__ = Tool_function_dedupe_dataframe__(df__)
            df__ = df__.sort_values('end_date')
            return df__
        else:
            return None

    Dict_result__['fina_indicator'] = fetch_interface__('fina_indicator', pro__.fina_indicator, List_request_periods__)
    Dict_result__['income'] = fetch_interface__('income', pro__.income, List_request_periods__)
    Dict_result__['balancesheet'] = fetch_interface__('balancesheet', pro__.balancesheet, List_request_periods__)
    Dict_result__['cashflow'] = fetch_interface__('cashflow', pro__.cashflow, List_request_periods__)

    return Dict_result__

def Main_function_calculate_missing_metrics_enhanced__(
        parameter_df_fina__, 
        parameter_df_income__, 
        parameter_df_balance__,
        parameter_target_periods__
    ):
    if parameter_df_fina__ is None or parameter_df_fina__.empty:
        return None

    dict_income__ = {}
    if parameter_df_income__ is not None and not parameter_df_income__.empty:
        for _, row__ in parameter_df_income__.iterrows():
            dict_income__[row__['end_date']] = row__

    dict_balance__ = {}
    if parameter_df_balance__ is not None and not parameter_df_balance__.empty:
        for _, row__ in parameter_df_balance__.iterrows():
            dict_balance__[row__['end_date']] = row__

    df_target__ = parameter_df_fina__[parameter_df_fina__['end_date'].isin(parameter_target_periods__)].copy()
    df_target__ = df_target__.sort_values('end_date').reset_index(drop=True)

    for idx__, row__ in df_target__.iterrows():
        period__ = row__['end_date']
        int_year__ = int(period__[:4])
        str_prev_year_period__ = f"{int_year__-1}{period__[4:]}"

        income_curr__ = dict_income__.get(period__)
        income_prev__ = dict_income__.get(str_prev_year_period__)

        if income_curr__ is not None and income_prev__ is not None:
            curr_op__ = Tool_function_get_field_value__(income_curr__, 'operate_profit')
            prev_op__ = Tool_function_get_field_value__(income_prev__, 'operate_profit')
            yoy_op__ = Tool_function_calculate_yoy__(curr_op__, prev_op__)
            df_target__.loc[idx__, 'profit_yoy_calc'] = yoy_op__

            curr_net__ = Tool_function_get_field_value__(income_curr__, 'n_income')
            prev_net__ = Tool_function_get_field_value__(income_prev__, 'n_income')
            yoy_net__ = Tool_function_calculate_yoy__(curr_net__, prev_net__)
            df_target__.loc[idx__, 'q_profit_yoy_calc'] = yoy_net__

        curr_eps__ = Tool_function_get_field_value__(row__, 'eps')
        prev_fina__ = parameter_df_fina__[parameter_df_fina__['end_date'] == str_prev_year_period__]
        if not prev_fina__.empty:
            prev_eps__ = Tool_function_get_field_value__(prev_fina__.iloc[0], 'eps')
            yoy_eps__ = Tool_function_calculate_yoy__(curr_eps__, prev_eps__)
            df_target__.loc[idx__, 'eps_yoy_calc'] = yoy_eps__

        balance_curr__ = dict_balance__.get(period__)
        balance_prev__ = dict_balance__.get(str_prev_year_period__)

        if income_curr__ is not None and balance_curr__ is not None and balance_prev__ is not None:
            revenue__ = Tool_function_get_field_value__(income_curr__, 'revenue')
            cost__ = Tool_function_get_field_value__(income_curr__, 'total_cogs')

            inv_curr__ = Tool_function_get_field_value__(balance_curr__, 'inventories')
            inv_prev__ = Tool_function_get_field_value__(balance_prev__, 'inventories')
            avg_inv__ = (inv_curr__ + inv_prev__) / 2 if inv_curr__ and inv_prev__ else None
            inv_turn__ = Tool_function_safe_divide__(cost__, avg_inv__)
            df_target__.loc[idx__, 'inv_turn_calc'] = inv_turn__

            ar_curr__ = Tool_function_get_field_value__(balance_curr__, 'accounts_receiv')
            ar_prev__ = Tool_function_get_field_value__(balance_prev__, 'accounts_receiv')
            avg_ar__ = (ar_curr__ + ar_prev__) / 2 if ar_curr__ and ar_prev__ else None
            ar_turn__ = Tool_function_safe_divide__(revenue__, avg_ar__)
            df_target__.loc[idx__, 'ar_turn_calc'] = ar_turn__

            asset_curr__ = Tool_function_get_field_value__(balance_curr__, 'total_assets')
            asset_prev__ = Tool_function_get_field_value__(balance_prev__, 'total_assets')
            avg_asset__ = (asset_curr__ + asset_prev__) / 2 if asset_curr__ and asset_prev__ else None
            asset_turn__ = Tool_function_safe_divide__(revenue__, avg_asset__)
            df_target__.loc[idx__, 'assets_turn_calc'] = asset_turn__

            if inv_turn__ and inv_turn__ > 0:
                df_target__.loc[idx__, 'invturn_days_calc'] = 365 / inv_turn__
            if ar_turn__ and ar_turn__ > 0:
                df_target__.loc[idx__, 'arturn_days_calc'] = 365 / ar_turn__

    return df_target__
# =========================== 【↑获取财务报表↑】 ===========================





# =========================== 【↓获取估值信息↓】 ===========================
def Tool_function_get_industry_avg_valuation__(industry_name__, trade_date__):
    """
    获取指定行业的平均PE、PB、PS
    参数：
        industry_name__: 行业名称
        trade_date__: 交易日期（YYYYMMDD）
    返回：
        {'pe_avg': float, 'pb_avg': float, 'sample_count': int}
    """
    global Dict_cached_industry_avg__
    if Dict_cached_industry_avg__ is None:
        Dict_cached_industry_avg__ = {}

    cache_key__ = f"{industry_name__}_{trade_date__}"
    if cache_key__ in Dict_cached_industry_avg__:
        print(f"[行业估值] 使用缓存: {industry_name__} {trade_date__}")
        return Dict_cached_industry_avg__[cache_key__]

    try:
        # 获取该行业所有股票的ts_code
        industry_codes__ = Tool_function_get_industry_members__(industry_name__)
        if not industry_codes__:
            print(f"[行业估值] 行业'{industry_name__}'无成分股数据")
            result__ = {'pe_avg': None, 'pb_avg': None, 'sample_count': 0}
            Dict_cached_industry_avg__[cache_key__] = result__
            return result__
        
        # 获取daily_basic数据（全市场）
        df_daily__ = pro__.daily_basic(
            trade_date=trade_date__,
            fields='ts_code,pe,pe_ttm,pb,ps,total_mv'   # 新增 ps
        )
        if df_daily__ is None or df_daily__.empty:
            result__ = {'pe_avg': None, 'pb_avg': None, 'sample_count': 0}
            Dict_cached_industry_avg__[cache_key__] = result__
            return result__
        
        # 筛选该行业的股票
        df_industry__ = df_daily__[df_daily__['ts_code'].isin(industry_codes__)].copy()

        # 计算 PE 平均值
        df_valid_pe__ = df_industry__[(df_industry__['pe'] > 0) & (df_industry__['pe'].notna())]
        pe_avg__ = df_valid_pe__['pe'].mean() if not df_valid_pe__.empty else None

        # 计算 PB 平均值
        df_valid_pb__ = df_industry__[(df_industry__['pb'] > 0) & (df_industry__['pb'] < 50) & (df_industry__['pb'].notna())]
        pb_avg__ = df_valid_pb__['pb'].mean() if not df_valid_pb__.empty else None

        # 计算 PS 平均值（新增）
        df_valid_ps__ = df_industry__[(df_industry__['ps'] > 0) & (df_industry__['ps'].notna())]
        ps_avg__ = df_valid_ps__['ps'].mean() if not df_valid_ps__.empty else None

        result__ = {
            'pe_avg': round(pe_avg__, 2) if pe_avg__ is not None else None,
            'pb_avg': round(pb_avg__, 2) if pb_avg__ is not None else None,
            'ps_avg': round(ps_avg__, 2) if ps_avg__ is not None else None,
            'sample_count': len(df_industry__)
        }
        Dict_cached_industry_avg__[cache_key__] = result__
        return result__
        
    except Exception as e__:
        print(f"[行业估值] 计算失败: {e__}")
        result__ = {'pe_avg': None, 'pb_avg': None, 'sample_count': 0}
        Dict_cached_industry_avg__[cache_key__] = result__
        return result__

def Tool_function_calculate_theoretical_valuation__(
        close_price__, eps__, bps__, sps__, dps__, profit_growth__,
        industry_pe__, industry_pb__, industry_ps__, risk_free_rate__=0.01
    ):
    """
    计算多种方法下的理论估值
    
    参数：
        close_price__: 当前收盘价
        eps__: 每股收益
        bps__: 每股净资产
        dps__: 每股股息
        sps__: 每股营收（营业收入/总股本）
        profit_growth__: 净利润同比增长率（%）
        industry_pe__: 行业平均PE
        industry_pb__: 行业平均PB
        industry_ps__: 行业平均PS
        risk_free_rate__: 无风险利率（默认1%）
    
    返回：
        字典包含各模型的理论价格和差异度
    """
    models__ = []
    
    models__ = []
    
    # PE估值法
    if eps__ and eps__ > 0 and industry_pe__ and industry_pe__ > 0:
        theo_price_pe__ = industry_pe__ * eps__
        diff_pe__ = (theo_price_pe__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        models__.append({
            'name': 'PE估值法',
            'formula': '行业PE × 每股收益(EPS)',
            'theoretical_price': round(theo_price_pe__, 2),
            'diff_percent': round(diff_pe__, 2),
            'signal': '低估' if diff_pe__ > 0 else '高估'
        })
    
    # PB估值法
    if bps__ and bps__ > 0 and industry_pb__ and industry_pb__ > 0:
        theo_price_pb__ = industry_pb__ * bps__
        diff_pb__ = (theo_price_pb__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        models__.append({
            'name': 'PB估值法',
            'formula': '行业PB × 每股净资产(BPS)',
            'theoretical_price': round(theo_price_pb__, 2),
            'diff_percent': round(diff_pb__, 2),
            'signal': '低估' if diff_pb__ > 0 else '高估'
        })
    
    # PS估值法
    if sps__ and sps__ > 0 and industry_ps__ and industry_ps__ > 0:
        theo_price_ps__ = industry_ps__ * sps__
        diff_ps__ = (theo_price_ps__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        models__.append({
            'name': 'PS估值法',
            'formula': '行业PS × 每股营收(SPS)',
            'theoretical_price': round(theo_price_ps__, 2),
            'diff_percent': round(diff_ps__, 2),
            'signal': '低估' if diff_ps__ > 0 else '高估'
        })
    
    # PEG估值法
    if eps__ and eps__ > 0 and profit_growth__ and profit_growth__ > 0:
        reasonable_pe__ = profit_growth__
        theo_price_peg__ = reasonable_pe__ * eps__
        diff_peg__ = (theo_price_peg__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        models__.append({
            'name': 'PEG估值法',
            'formula': '净利润增长率 × EPS',
            'theoretical_price': round(theo_price_peg__, 2),
            'diff_percent': round(diff_peg__, 2),
            'signal': '低估' if diff_peg__ > 0 else '高估'
        })
    
    # 股息贴现模型
    if dps__ and dps__ > 0:
        theo_price_ddm__ = dps__ / risk_free_rate__
        diff_ddm__ = (theo_price_ddm__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        models__.append({
            'name': '股息贴现模型（零增长）',
            'formula': '每股股息 ÷ 无风险利率',
            'theoretical_price': round(theo_price_ddm__, 2),
            'diff_percent': round(diff_ddm__, 2),
            'signal': '低估' if diff_ddm__ > 0 else '高估'
        })
        
    # 综合计算
    if models__:
        avg_theo_price__ = sum(m['theoretical_price'] for m in models__) / len(models__)
        avg_diff__ = (avg_theo_price__ / close_price__ - 1) * 100 if close_price__ > 0 else 0
        
        if avg_diff__ > 20: rating__, color__ = '显著低估', 'green'
        elif avg_diff__ > 10: rating__, color__ = '低估', 'green'
        elif avg_diff__ > -10: rating__, color__ = '合理估值', 'orange'
        elif avg_diff__ > -20: rating__, color__ = '高估', 'red'
        else: rating__, color__ = '显著高估', 'red'
    else:
        avg_theo_price__, avg_diff__, rating__, color__ = None, None, '数据不足', 'gray'
    
    return {
        'models': models__,
        'avg_theoretical_price': round(avg_theo_price__, 2) if avg_theo_price__ else None,
        'avg_diff_percent': round(avg_diff__, 2) if avg_diff__ else None,
        'rating': rating__,
        'rating_color': color__,
        'close_price': close_price__
    }

def Tool_function_get_shibor_rate__():
    """获取1年期Shibor利率"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        df_shibor = pro__.shibor(date=today)
        if df_shibor is not None and not df_shibor.empty:
            rate = df_shibor.iloc[0].get('1y')
            if rate is not None:
                return rate / 100
    except Exception as e:
        print(f"[Shibor] 获取失败: {e}")
    return 0.01  # 默认1%


# =========================== 【↑获取估值信息↑】 ===========================




# =========================== 【↓ AI分析函数 ↓】 ===========================
def Tool_function_prepare_data_for_ai__(security_info__, kline_data__):
    """
    根据证券信息和K线原始数据构建AI摘要
    security_info__: (证券种类, 证券名称, 证券代码, 交易板块)
    kline_data__: 从接口获取的klines列表（字符串"日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率"）
    """
    if not kline_data__:
        return None

    # 解析K线数据
    dates__ = []
    opens__ = []
    closes__ = []
    highs__ = []
    lows__ = []
    volumes__ = []
    amounts__ = []
    for item__ in kline_data__:
        parts__ = item__.split(',')
        if len(parts__) >= 11:
            dates__.append(parts__[0])
            opens__.append(float(parts__[1]))
            closes__.append(float(parts__[2]))
            highs__.append(float(parts__[3]))
            lows__.append(float(parts__[4]))
            volumes__.append(float(parts__[5]))
            amounts__.append(float(parts__[6]))

    if not dates__:
        return None

    # 计算技术指标
    ma5__ = Tool_function_calculate_ma__(closes__, 5)
    ma10__ = Tool_function_calculate_ma__(closes__, 10)
    ma20__ = Tool_function_calculate_ma__(closes__, 20)
    ma60__ = Tool_function_calculate_ma__(closes__, 60)
    rsi6__ = Tool_function_calculate_rsi__(closes__, 6)
    rsi12__ = Tool_function_calculate_rsi__(closes__, 12)
    rsi24__ = Tool_function_calculate_rsi__(closes__, 24)
    k__, d__, j__ = Tool_function_calculate_kdj__(highs__, lows__, closes__)
    dif__, dea__, macd__ = Tool_function_calculate_macd__(closes__)

    # 构建摘要字典
    summary_dict__ = {
        "证券基本信息": {
            "证券名称": security_info__[1],
            "证券代码": security_info__[2],
            "证券种类": security_info__[0],
            "交易板块": security_info__[3]
        },
        "数据统计": {
            "数据周期数": len(dates__),
            "时间范围": f"{dates__[0]} 至 {dates__[-1]}",
            "最新收盘价": closes__[-1] if closes__ else 'N/A',
            "价格均值": sum(closes__) / len(closes__) if closes__ else 0,
            "成交量均值": sum(volumes__) / len(volumes__) if volumes__ else 0
        },
        "近期交易数据摘要": {},
        "关键技术指标摘要": {}
    }

    # 近期交易数据（最近5天）
    recent_count__ = min(5, len(dates__))
    summary_dict__["近期交易数据摘要"]["日期"] = dates__[-recent_count__:]
    for key__, data__ in [("开盘价", opens__), ("收盘价", closes__), ("最高价", highs__), ("最低价", lows__), ("成交量", volumes__)]:
        summary_dict__["近期交易数据摘要"][key__] = data__[-recent_count__:]

    # 关键技术指标最新值
    summary_dict__["关键技术指标摘要"]["MA5"] = {"最新值": ma5__[-1] if ma5__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MA10"] = {"最新值": ma10__[-1] if ma10__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MA20"] = {"最新值": ma20__[-1] if ma20__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MA60"] = {"最新值": ma60__[-1] if ma60__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["RSI6"] = {"最新值": rsi6__[-1] if rsi6__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["RSI12"] = {"最新值": rsi12__[-1] if rsi12__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["RSI24"] = {"最新值": rsi24__[-1] if rsi24__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["KDJ_K"] = {"最新值": k__[-1] if k__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["KDJ_D"] = {"最新值": d__[-1] if d__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["KDJ_J"] = {"最新值": j__[-1] if j__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MACD_DIF"] = {"最新值": dif__[-1] if dif__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MACD_DEA"] = {"最新值": dea__[-1] if dea__[-1] is not None else 'N/A'}
    summary_dict__["关键技术指标摘要"]["MACD"] = {"最新值": macd__[-1] if macd__[-1] is not None else 'N/A'}

    return summary_dict__

def Tool_function_build_initial_prompt__(summary_dict__):
    """构建初始用户消息"""
    prompt__ = f"""请分析以下证券数据：

证券基本信息：
证券名称: {summary_dict__['证券基本信息']['证券名称']}
证券代码: {summary_dict__['证券基本信息']['证券代码']}
证券种类: {summary_dict__['证券基本信息']['证券种类']}
交易板块: {summary_dict__['证券基本信息']['交易板块']}

数据统计：
数据周期数: {summary_dict__['数据统计']['数据周期数']}个交易日
时间范围: {summary_dict__['数据统计']['时间范围']}
最新收盘价: {summary_dict__['数据统计']['最新收盘价']}
价格均值: {summary_dict__['数据统计']['价格均值']:.2f}
成交量均值: {summary_dict__['数据统计']['成交量均值']:,.0f}

近期交易数据摘要（最近5个交易日）：
"""
    # 添加近期交易数据
    if "近期交易数据摘要" in summary_dict__:
        for i__, date__ in enumerate(summary_dict__["近期交易数据摘要"].get("日期", [])):
            prompt__ += f"\n交易日 {i__+1} ({date__}): "
            data_parts__ = []
            for key__ in ['开盘价', '收盘价', '最高价', '最低价', '成交量']:
                if key__ in summary_dict__["近期交易数据摘要"] and i__ < len(summary_dict__["近期交易数据摘要"][key__]):
                    val__ = summary_dict__["近期交易数据摘要"][key__][i__]
                    if key__ == '成交量':
                        data_parts__.append(f"{key__}: {val__:,.0f}")
                    else:
                        data_parts__.append(f"{key__}: {val__:.2f}")
            prompt__ += "; ".join(data_parts__)

    prompt__ += "\n\n关键技术指标摘要："
    for key__, value__ in summary_dict__.get("关键技术指标摘要", {}).items():
        prompt__ += f"\n{key__}: 最新值 {value__.get('最新值', 'N/A')}"

    prompt__ += """

请基于这些完整数据进行分析。您可以随时提出具体问题，我会为您提供详细的分析。
"""
    return prompt__

def Tool_function_create_ai_client__():
    ai_key_info__ = Tool_function_read_ai_key__()
    if not ai_key_info__ or "API Key" not in ai_key_info__:
        return None
    api_key__ = ai_key_info__["API Key"]
    try:
        client__ = OpenAI(
            api_key=api_key__,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        return client__
    except Exception as e__:
        print(f"创建AI客户端失败: {e__}")
        return None

def Tool_function_send_message_to_ai__(conversation_history__):
    client__ = Tool_function_create_ai_client__()
    if not client__:
        return "AI服务初始化失败，请检查API密钥。"
    try:
        completion__ = client__.chat.completions.create(
            model="qwen-plus",
            messages=conversation_history__,
            temperature=0.7
        )
        return completion__.choices[0].message.content
    except Exception as e__:
        return f"AI调用失败: {str(e__)}"
# =========================== 【↑ AI分析函数 ↑】 ===========================






# =========================== 【↓ Flask 路由 ↓】 ===========================
# =========================== 【基本功能路由】 ===========================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sector_list', methods=['POST'])
def api_sector_list():
    """获取概念、行业、地域列表"""
    data = request.get_json()
    sector_type = data.get('type')  # 例如 '概念列表'
    try:
        sector_list = Main_function_Get_securities_sector_name_list__(sector_type)
        sector_list = ['全部'] + Tool_function_string_sort__(sector_list)
        return jsonify({'list': sector_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filter', methods=['POST'])
def api_filter():
    """执行证券筛选，返回结果和日志"""
    data = request.get_json()
    # 构建参数字典
    Parameter_dict__ = {
        '股票': {'选择': False, '交易所板块': [], '概念': [], '行业': [], '地域': [], '风险警示': [], '名称（关键字）': []},
        '指数': {'选择': False, '指数系列': [], '名称（关键字）': []},
        'ETF': {'选择': False, '名称（关键字）': []},
        'LOF': {'选择': False, '名称（关键字）': []},
        '国债': {'选择': False, '交易所': [], '名称（关键字）': []},
        '企债': {'选择': False, '交易所': [], '名称（关键字）': []},
        '可转债': {'选择': False, '交易所': [], '名称（关键字）': []}
    }
    sec_type = data.get('security_type', '股票')
    Parameter_dict__[sec_type]['选择'] = True

    # 填充板块筛选
    if sec_type == '股票':
        Parameter_dict__['股票']['交易所板块'] = data.get('exchange', [])
        Parameter_dict__['股票']['概念'] = data.get('concept', [])
        Parameter_dict__['股票']['行业'] = data.get('industry', [])
        Parameter_dict__['股票']['地域'] = data.get('region', [])
        Parameter_dict__['股票']['风险警示'] = data.get('risk', [])
        name_keywords = data.get('name_keywords', '')
        if name_keywords.strip():
            Re_split_pattern__ = r'[,，、。\s]+'
            Parameter_dict__['股票']['名称（关键字）'] = [k for k in re.split(Re_split_pattern__, name_keywords.strip()) if k]
        else:
            Parameter_dict__['股票']['名称（关键字）'] = [None]
    elif sec_type == '指数':
        Parameter_dict__['指数']['指数系列'] = data.get('index_series', [])
        name_keywords = data.get('name_keywords', '')
        if name_keywords.strip():
            Re_split_pattern__ = r'[,，、。\s]+'
            Parameter_dict__['指数']['名称（关键字）'] = [k for k in re.split(Re_split_pattern__, name_keywords.strip()) if k]
        else:
            Parameter_dict__['指数']['名称（关键字）'] = [None]
    elif sec_type in ['ETF', 'LOF']:
        name_keywords = data.get('name_keywords', '')
        if name_keywords.strip():
            Re_split_pattern__ = r'[,，、。\s]+'
            Parameter_dict__[sec_type]['名称（关键字）'] = [k for k in re.split(Re_split_pattern__, name_keywords.strip()) if k]
        else:
            Parameter_dict__[sec_type]['名称（关键字）'] = [None]
    elif sec_type in ['国债', '企债', '可转债']:
        Parameter_dict__[sec_type]['交易所'] = data.get('exchange', [])
        name_keywords = data.get('name_keywords', '')
        if name_keywords.strip():
            Re_split_pattern__ = r'[,，、。\s]+'
            Parameter_dict__[sec_type]['名称（关键字）'] = [k for k in re.split(Re_split_pattern__, name_keywords.strip()) if k]
        else:
            Parameter_dict__[sec_type]['名称（关键字）'] = [None]

    # 指标筛选条件
    metric_conditions = data.get('metric_conditions', {})
    # 转换空字符串为None
    for metric, bounds in metric_conditions.items():
        if '下限' in bounds and bounds['下限'] == '':
            bounds['下限'] = None
        if '上限' in bounds and bounds['上限'] == '':
            bounds['上限'] = None

    log_messages = []
    log_messages.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行证券筛选")
    log_messages.append(f"用户所选证券类型：{sec_type}")
    try:
        # 执行筛选
        List_filter_result__, Str_current_type__ = Main_Func_Get_securities_identification_data__(Parameter_dict__, log_messages)
        log_messages.append(f"板块筛选共选出 {len(List_filter_result__)} 个证券")
        # 应用指标筛选
        if metric_conditions:
            List_filter_result__ = Main_function_apply_metric_filter__(List_filter_result__, metric_conditions)
            log_messages.append(f"指标筛选后剩余 {len(List_filter_result__)} 个证券")
        log_messages.append("证券筛选执行完毕")
        return jsonify({
            'success': True,
            'data': List_filter_result__,
            'type': Str_current_type__,
            'log': log_messages
        })
    except Exception as e:
        log_messages.append(f"【筛选错误】{str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'log': log_messages
        }), 500

@app.route('/api/export', methods=['POST'])
def api_export():
    """导出Excel文件"""
    data = request.get_json()
    securities_data = data.get('data', [])
    sec_type = data.get('type', '股票')
    if not securities_data:
        return jsonify({'error': '无数据可导出'}), 400
    try:
        workbook__ = Main_function_write_securities_to_excel__(sec_type, securities_data)
        output = io.BytesIO()
        workbook__.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name="证券筛选表.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dsl_filter', methods=['POST'])
def api_dsl_filter():
    """DSL 选股指令：翻译引擎（任务4）+ 执行（任务5 后端）"""
    data = request.get_json() or {}
    dsl_text = (data.get('dsl') or '').strip()
    dialect = data.get('dialect', 'duckdb')
    log_messages = [f"[{datetime.now().strftime('%H:%M:%S')}] 收到 DSL 指令：{dsl_text}"]
    if not dsl_text:
        return jsonify({'success': False, 'error': '指令为空，请输入选股条件', 'log': log_messages})
    try:
        result = execute_dsl(dsl_text, DB_PATH, dialect=dialect)
        log_messages.append(f"翻译成功（{result['dialect']} 方言），生成 SQL 已返回前端展示")
        if result['used_functions']:
            log_messages.append('调用的历史函数：' + '、'.join(result['used_functions']))
        log_messages.append(f"DSL 筛选完成，共选出 {result['count']} 只股票")
        return jsonify({
            'success': True,
            'data': result['rows'],
            'type': '股票',
            'sql': result['sql'],
            'dialect': result['dialect'],
            'log': log_messages
        })
    except DSLError as e:
        log_messages.append(f"【DSL 错误】{e}")
        return jsonify({'success': False, 'error': e.message, 'error_pos': e.pos, 'log': log_messages})
    except Exception as e:
        log_messages.append(f"【执行错误】{str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'执行失败：{str(e)}', 'log': log_messages}), 500


@app.route('/api/dsl_help', methods=['POST'])
def api_dsl_help():
    """返回 DSL 词库与语法帮助"""
    return jsonify(get_dsl_help())


@app.route('/detail')
def detail():
    """详情页"""
    code = request.args.get('code', '')
    name = request.args.get('name', '')
    sec_type = request.args.get('type', '股票')
    exchange = request.args.get('exchange', '')
    return render_template('detail.html', code=code, name=name, sec_type=sec_type, exchange=exchange)

@app.route('/results')
def results():
    """独立结果页面"""
    return render_template('results.html')

@app.route('/api/kline', methods=['GET'])
def api_kline():
    """获取指定证券的K线数据"""
    code = request.args.get('code')
    exchange = request.args.get('exchange')
    sec_type = request.args.get('type', '股票')
    ktype = request.args.get('ktype', '101')  # 默认日K

    if not code or not exchange:
        return jsonify({'error': '缺少参数'}), 400

    info_tuple = (sec_type, '', code, exchange)

    # 获取数据
    result = Main_function_Get_security_histinfo_json__(info_tuple, ktype, Path_temfile_dir__)

    if result.get('data') is None:
        return jsonify({'error': '获取数据失败'}), 500

    klines = result['data'].get('klines', [])

    return jsonify({
        'code': code,
        'exchange': exchange,
        'ktype': ktype,
        'klines': klines
    })



# =========================== 【导入数据库路由】 ===========================
@app.route('/api/update_db', methods=['POST'])
def api_update_db():
    """同步执行数据库更新，等待完成后返回结果"""
    excel_path = os.path.join(Path_current_dir__, 'Duckdb数据库结构.xlsx')
    if not os.path.exists(excel_path):
        return jsonify({
            'success': False,
            'error': '缺少数据库结构文件，请确保 "Duckdb数据库结构.xlsx" 存在于程序目录'
        }), 400

    try:
        from update_db import incremental_update
        # 同步调用，等待完成
        incremental_update()
        return jsonify({'success': True, 'message': '数据库更新已完成！'})
    except Exception as e:
        app.logger.error(f"更新任务异常: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================== 【基本面信息路由】 ===========================
@app.route('/fundamental')
def fundamental():
    """基本面信息页面"""
    code = request.args.get('code', '')
    name = request.args.get('name', '')
    sec_type = request.args.get('type', '股票')
    exchange = request.args.get('exchange', '')
    return render_template('fundamental.html', code=code, name=name, sec_type=sec_type, exchange=exchange)

# =========================== 【↓ 基本面信息数据API ↓】 ===========================
@app.route('/api/fundamental_data', methods=['POST'])
def api_fundamental_data():
    """获取股票基本面信息（无权限判断版本，增强日志）"""
    data__ = request.get_json()
    code__ = data__.get('code')
    exchange__ = data__.get('exchange')
    ts_code__ = data__.get('ts_code')
    name__ = data__.get('name', '')
    
    print(f"\n{'='*50}")
    print(f"[基本面API] 请求股票: {ts_code__} ({name__})")
    
    if not code__ or not ts_code__:
        return jsonify({'success': False, 'error': '缺少证券信息'}), 400
    
    List_result__ = {
        'company': None,
        'valuation': None,
        'financial': None,
        'shareholder': None,
        'news': None
    }
    
    # ========== 1. 公司基本信息 ==========
    print("[公司信息] 开始获取...")
    Dict_company_combined__ = {}
    company_basic_ok = False
    company_detail_ok = False
    
    try:
        df_basic__ = pro__.stock_basic(ts_code=ts_code__, 
                                       fields='ts_code,symbol,name,area,industry,fullname,enname,list_date,exchange,is_hs')
        if df_basic__ is not None and not df_basic__.empty:
            basic_dict__ = df_basic__.iloc[0].to_dict()
            for k, v in basic_dict__.items():
                Dict_company_combined__[k] = None if pd.isna(v) else v
            company_basic_ok = True
            print(f"[公司信息] stock_basic 获取成功，字段数: {len(basic_dict__)}")
        else:
            print("[公司信息] stock_basic 返回空数据")
    except Exception as e__:
        print(f"[公司信息] stock_basic 异常: {e__}")

    try:
        df_company__ = pro__.stock_company(ts_code=ts_code__)
        if df_company__ is not None and not df_company__.empty:
            company_dict__ = df_company__.iloc[0].to_dict()
            for k, v in company_dict__.items():
                Dict_company_combined__[k] = None if pd.isna(v) else v
            company_detail_ok = True
            print(f"[公司信息] stock_company 获取成功，字段数: {len(company_dict__)}")
        else:
            print("[公司信息] stock_company 返回空数据")
    except Exception as e__:
        print(f"[公司信息] stock_company 异常: {e__}")

    if company_basic_ok or company_detail_ok:
        List_result__['company'] = Dict_company_combined__
        print(f"[公司信息] 最终合并字段数: {len(Dict_company_combined__)}")
    else:
        List_result__['company'] = None
        print("[公司信息] 所有接口均失败，返回 None")

    # ========== 2. 财务数据 ==========
    print("[财务数据] 开始获取...")
    try:
        Dict_financial_full__ = Main_function_get_financial_data_optimized__(ts_code__)
        List_target_periods__ = Tool_function_get_actual_latest_periods__(ts_code__, pro__)
        print(f"[财务数据] 目标期间: {List_target_periods__}")
        
        df_fina_enhanced__ = Main_function_calculate_missing_metrics_enhanced__(
            Dict_financial_full__.get('fina_indicator'),
            Dict_financial_full__.get('income'),
            Dict_financial_full__.get('balancesheet'),
            List_target_periods__
        )
        
        Dict_financial_result__ = {
            'periods': List_target_periods__,
            'fina_indicator': None,
            'income': None,
            'balancesheet': None,
            'cashflow': None,
            'errors': Dict_financial_full__.get('errors', [])
        }
        
        def align_df_to_target_periods__(df__, target_periods__):
            if df__ is None or df__.empty:
                return None
            if not target_periods__:
                return df__.to_dict('records')
            extra_periods = set()
            earliest = min(target_periods__)
            if len(earliest) == 8:
                prev_year = int(earliest[:4]) - 1
                prev_period = f"{prev_year}{earliest[4:]}"
                extra_periods.add(prev_period)
            all_periods = set(target_periods__) | extra_periods
            df_a__ = df__[df__['end_date'].isin(all_periods)].copy()
            if df_a__.empty:
                # 回退：返回最近4期数据
                df_sorted = df__.sort_values('end_date', ascending=False)
                df_a__ = df_sorted.head(4).copy()
                print(f"[财务数据] 警告：未找到匹配期间，使用最近4期数据")
            df_a__ = df_a__.sort_values('end_date')
            return df_a__.to_dict('records')
        
        Dict_financial_result__['fina_indicator'] = df_fina_enhanced__.to_dict('records') if df_fina_enhanced__ is not None else None
        Dict_financial_result__['income'] = align_df_to_target_periods__(Dict_financial_full__.get('income'), List_target_periods__)
        Dict_financial_result__['balancesheet'] = align_df_to_target_periods__(Dict_financial_full__.get('balancesheet'), List_target_periods__)
        Dict_financial_result__['cashflow'] = align_df_to_target_periods__(Dict_financial_full__.get('cashflow'), List_target_periods__)
        
        List_result__['financial'] = Dict_financial_result__
        print(f"[财务数据] 获取成功，收入表记录数: {len(Dict_financial_result__['income']) if Dict_financial_result__['income'] else 0}")
    except Exception as e__:
        print(f"[财务数据] 异常: {e__}")
        traceback.print_exc()
        List_result__['financial'] = None

    # ========== 3. 估值指标 ==========
    print("[估值指标] 开始获取...")
    valuation_data__ = None
    data_date__ = None

    try:
        # 先尝试获取最新交易日数据
        latest_date__ = Tool_function_get_latest_trade_date__(pro__)
        df_valuation__ = None
        for offset__ in range(3):
            try_date__ = (datetime.strptime(latest_date__, '%Y%m%d') - timedelta(days=offset__)).strftime('%Y%m%d')
            df_valuation__ = pro__.daily_basic(
                ts_code=ts_code__,
                trade_date=try_date__,
                fields='ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv,total_share,float_share,turnover_rate,dv_ratio,dv_ttm,volume_ratio'
            )
            if df_valuation__ is not None and not df_valuation__.empty:
                data_date__ = try_date__
                print(f"[估值指标] 成功获取 {try_date__} 的数据")
                break
            else:
                print(f"[估值指标] {try_date__} 无数据")
        
        if df_valuation__ is not None and not df_valuation__.empty:
            val_dict__ = df_valuation__.iloc[0].to_dict()
            for k__, v__ in val_dict__.items():
                if pd.isna(v__):
                    val_dict__[k__] = None
            valuation_data__ = val_dict__
            List_result__['valuation'] = valuation_data__
        else:
            List_result__['valuation'] = None
    except Exception as e__:
        print(f"[估值指标] 异常: {e__}")
        List_result__['valuation'] = None

    # ========== 3.5 获取财务指标用于估值计算 ==========
    print("[估值计算] 开始获取财务指标...")
    eps__ = bps__ = sps__ = profit_growth__ = None

    # 提取营业收入（最新一期）
    revenue__ = None
    if List_result__['financial'] and List_result__['financial'].get('income'):
        income_list = List_result__['financial']['income']
        if income_list:
            latest_income = sorted(income_list, key=lambda x: x.get('end_date', ''), reverse=True)[0]
            revenue__ = latest_income.get('revenue')  # 单位：元

    # 提取总股本（来自估值数据或资产负债表）
    total_share__ = None
    if valuation_data__:
        total_share__ = valuation_data__.get('total_share')  # 单位：万股

    # 计算 SPS（元）
    if revenue__ and total_share__ and total_share__ > 0:
        # revenue 单位元，total_share 单位万股（即10,000股）
        sps__ = revenue__ / (total_share__ * 10000)
        print(f"[估值计算] 计算 SPS: 营业收入={revenue__}, 总股本={total_share__}万股 → SPS={sps__:.2f}")

    try:
        fina_list = List_result__['financial'].get('fina_indicator') if List_result__['financial'] else None
        if fina_list and isinstance(fina_list, list) and len(fina_list) > 0:
            # 按 end_date 降序排序，取最新一期
            sorted_fina = sorted(fina_list, key=lambda x: x.get('end_date', ''), reverse=True)
            latest_fina = sorted_fina[0]
            eps__ = latest_fina.get('eps')
            bps__ = latest_fina.get('bps')
            profit_growth__ = latest_fina.get('q_profit_yoy') or latest_fina.get('profit_yoy') or latest_fina.get('or_yoy')
            print(f"[估值计算] 从fina_indicator获取: EPS={eps__}, BPS={bps__}, SPS={sps__}, 增长率={profit_growth__}%")
    except Exception as e__:
        print(f"[估值计算] 从财务数据提取指标失败: {e__}")
        
    # ========== 3.6 获取股息数据 ==========
    dps__ = None
    try:
        df_dividend__ = pro__.dividend(ts_code=ts_code__, limit=5)
        if df_dividend__ is not None and not df_dividend__.empty:
            latest_dividend__ = df_dividend__.iloc[0]
            dps__ = latest_dividend__.get('cash_div')
            if dps__ is not None and dps__ > 0:
                print(f"[估值计算] 从dividend获取: 每股股息={dps__}元")
    except Exception as e__:
        print(f"[估值计算] 获取股息数据失败: {e__}")

    # 如果dividend没有有效数据，尝试从fina_indicator获取
    if dps__ is None or dps__ == 0:
        try:
            if List_result__['financial'] and List_result__['financial'].get('fina_indicator'):
                fina_data__ = List_result__['financial']['fina_indicator']
                if fina_data__:
                    sorted_fina__ = sorted(fina_data__, key=lambda x: x.get('end_date', ''), reverse=True)
                    latest_fina__ = sorted_fina__[0] if sorted_fina__ else {}
                    dps__ = latest_fina__.get('dps')
                    if dps__ is not None and dps__ > 0:
                        print(f"[估值计算] 从fina_indicator获取: 每股股息={dps__}元")
        except Exception as e__:
            print(f"[估值计算] 从fina_indicator提取股息失败: {e__}")

    # 如果还没有数据，则使用股息率反推 DPS
    if dps__ is None or dps__ == 0:
        try:
            if valuation_data__:
                close_price__ = valuation_data__.get('close')
                dv_ratio__ = valuation_data__.get('dv_ratio')
                if close_price__ and dv_ratio__ and dv_ratio__ > 0:
                    dps__ = close_price__ * dv_ratio__ / 100  # 股息率是百分比
                    print(f"[估值计算] 从股息率反推 DPS: {dps__:.3f}元 (股息率={dv_ratio__:.2f}%)")

        except Exception as e__:
            print(f"[估值计算] 获取股息数据失败: {e__}")
    
    # ========== 3.7 获取行业平均估值 ==========
    industry_pe__ = None
    industry_pb__ = None
    industry_sample_count__ = 0

    try:
        # 从公司信息中获取行业
        industry_name__ = Dict_company_combined__.get('industry') if Dict_company_combined__ else None
        if industry_name__ and valuation_data__:
            # 使用估值数据对应的交易日期
            trade_date_for_industry__ = data_date__ or valuation_data__.get('trade_date')
            if trade_date_for_industry__:
                industry_result__ = Tool_function_get_industry_avg_valuation__(industry_name__, trade_date_for_industry__)
                industry_pe__ = industry_result__.get('pe_avg')
                industry_pb__ = industry_result__.get('pb_avg')
                industry_ps__ = industry_result__.get('ps_avg')
                industry_sample_count__ = industry_result__.get('sample_count', 0)
                print(f"[估值计算] 行业'{industry_name__}'平均: PE={industry_pe__}, PB={industry_pb__}, 样本数={industry_sample_count__}")
    except Exception as e__:
        print(f"[估值计算] 获取行业平均估值失败: {e__}")

    # ========== 3.8 执行多模型估值计算 ==========
    theoretical_valuation__ = None
    if valuation_data__:
        close_price__ = valuation_data__.get('close')
        if close_price__ is not None and close_price__ > 0:
            # 获取无风险利率
            risk_free_rate__ = Tool_function_get_shibor_rate__()
            
            theoretical_valuation__ = Tool_function_calculate_theoretical_valuation__(
                close_price__=close_price__,
                eps__=eps__,
                bps__=bps__,
                sps__=sps__,
                dps__=dps__,
                profit_growth__=profit_growth__,
                industry_pe__=industry_pe__,
                industry_pb__=industry_pb__,
                industry_ps__=industry_ps__,
                risk_free_rate__=risk_free_rate__
            )

            print(f"[估值计算] 多模型估值完成，综合评级: {theoretical_valuation__.get('rating')}")
        else:
            print("[估值计算] 收盘价无效，跳过估值计算")

    # 将估值计算相关数据存入结果
    List_result__['valuation_extended'] = {
        'data_date': data_date__,
        'industry': {
            'name': Dict_company_combined__.get('industry') if Dict_company_combined__ else None,
            'pe_avg': industry_pe__,
            'pb_avg': industry_pb__,
            'ps_avg': industry_ps__,
            'sample_count': industry_sample_count__
        },
        'financial_metrics': {
            'eps': float(eps__) if eps__ is not None else None,
            'bps': float(bps__) if bps__ is not None else None,
            'sps': float(sps__) if sps__ is not None else None,
            'dps': float(dps__) if dps__ is not None else None,
            'profit_growth': float(profit_growth__) if profit_growth__ is not None else None
        },
        'theoretical_valuation': theoretical_valuation__,
        'risk_free_rate': Tool_function_get_shibor_rate__()
    }

    # ========== 4. 股东信息 ==========
    print("[股东信息] 开始获取...")
    try:
        df_holdernumber__ = pro__.stk_holdernumber(ts_code=ts_code__, limit=20)
        df_top_holders__ = pro__.top10_holders(ts_code=ts_code__, limit=10)
        
        Dict_shareholder__ = {}
        
        # 获取总股本（万股），来自估值数据（需要在 try 块内）
        total_share = valuation_data__.get('total_share') if valuation_data__ else None
        
        # 处理股东户数数据
        if df_holdernumber__ is not None and not df_holdernumber__.empty:
            holder_list__ = df_holdernumber__.to_dict('records')
            for item__ in holder_list__:
                # 清理 NaN
                for k, v in item__.items():
                    if pd.isna(v):
                        item__[k] = None
                # 计算户均持股（若原始 avg_share 缺失或需重算）
                if total_share and item__.get('holder_num'):
                    avg_share_calc = (total_share * 10000) / item__['holder_num']
                    item__['avg_share'] = int(avg_share_calc)
                else:
                    # 保留原值或设为 None
                    item__['avg_share'] = item__.get('avg_share')
                    if pd.isna(item__.get('avg_share')):
                        item__['avg_share'] = None
            Dict_shareholder__['holder_num'] = holder_list__
            print(f"[股东信息] 股东户数记录: {len(holder_list__)}")
        else:
            Dict_shareholder__['holder_num'] = []
            print("[股东信息] 股东户数无数据")
        
        # 处理前十大股东数据
        if df_top_holders__ is not None and not df_top_holders__.empty:
            top_list__ = df_top_holders__.to_dict('records')
            for item__ in top_list__:
                for k, v in item__.items():
                    if pd.isna(v):
                        item__[k] = None
            Dict_shareholder__['top_holders'] = top_list__
            print(f"[股东信息] 十大股东记录: {len(top_list__)}")
        else:
            Dict_shareholder__['top_holders'] = []
            print("[股东信息] 十大股东无数据")
        
        if Dict_shareholder__:
            List_result__['shareholder'] = Dict_shareholder__
        else:
            List_result__['shareholder'] = None
            print("[股东信息] 无数据")
    except Exception as e__:
        print(f"[股东信息] 异常: {e__}")
        List_result__['shareholder'] = None

    # ========== 5. 公告信息 ==========
    print("[公告信息] 开始获取...")
    try:
        df_news__ = pro__.disclosure(ts_code=ts_code__, limit=10)
        if df_news__ is not None and not df_news__.empty:
            news_list__ = df_news__.to_dict('records')
            for item__ in news_list__:
                for k, v in item__.items():
                    if pd.isna(v):
                        item__[k] = None
            List_result__['news'] = news_list__
            print(f"[公告信息] 获取记录: {len(news_list__)}")
        else:
            List_result__['news'] = []
            print("[公告信息] 无数据")
    except Exception as e__:
        print(f"[公告信息] 异常: {e__}")
        List_result__['news'] = None

    print(f"{'='*50}\n")
    
    result_to_return = {
        'success': True,
        'data': clean_nan(List_result__)
    }
    return jsonify(result_to_return)

# =========================== 【 AI对话路由 】 ===========================
@app.route('/ai')
def ai_chat():
    code = request.args.get('code', '')
    name = request.args.get('name', '')
    sec_type = request.args.get('type', '股票')
    exchange = request.args.get('exchange', '')
    return render_template('ai_chat.html', code=code, name=name, sec_type=sec_type, exchange=exchange)

@app.route('/ai/init', methods=['POST'])
def ai_init():
    """初始化AI对话，获取证券数据并创建会话"""
    data = request.get_json()
    code = data.get('code')
    name = data.get('name')
    sec_type = data.get('type', '股票')
    exchange = data.get('exchange')

    if not code or not exchange:
        return jsonify({'error': '缺少证券信息'}), 400

    info_tuple = (sec_type, name, code, exchange)
    kline_result = Main_function_Get_security_histinfo_json__(info_tuple, '101', Path_temfile_dir__)
    if kline_result.get('data') is None:
        return jsonify({'error': '获取历史数据失败'}), 500
    klines = kline_result['data'].get('klines', [])

    summary_dict__ = Tool_function_prepare_data_for_ai__(info_tuple, klines)
    if not summary_dict__:
        return jsonify({'error': '数据解析失败'}), 500

    conversation_id__ = str(uuid.uuid4())

    system_prompt__ = """你是一名专业的证券分析师，拥有丰富的股票分析经验。请基于用户提供的证券数据，进行专业的股票分析。

请遵守以下分析规范：
1. 使用专业、严谨、客观的分析语言，避免使用表情符号和特殊字符
2. 分析过程要逻辑清晰，结论明确，建议具体
3. 优先使用段落形式进行阐述，避免使用表格
4. 在分析中引用具体的数据支持观点
5. 根据不同的分析维度组织内容，层次分明
6. 给出明确的投资建议，包括风险提示

请基于用户提供的完整数据进行深入分析，数据包括每日的交易数据和技术指标数据。
"""
    initial_user_message__ = Tool_function_build_initial_prompt__(summary_dict__)

    history__ = [
        {"role": "system", "content": system_prompt__},
        {"role": "user", "content": initial_user_message__}
    ]

    Dict_ai_conversations__[conversation_id__] = {
        'history': history__,
        'security_info': info_tuple,
        'summary': summary_dict__,
        'klines': klines
    }

    return jsonify({
        'conversation_id': conversation_id__,
        'security_info': {
            'name': name,
            'code': code,
            'type': sec_type,
            'exchange': exchange
        },
        'summary': summary_dict__
    })

@app.route('/ai/chat', methods=['POST'])
def ai_chat_send():
    data = request.get_json()
    conversation_id__ = data.get('conversation_id')
    message__ = data.get('message', '').strip()

    if not conversation_id__ or not message__:
        return jsonify({'error': '缺少参数'}), 400

    conversation__ = Dict_ai_conversations__.get(conversation_id__)
    if not conversation__:
        return jsonify({'error': '会话不存在或已过期'}), 404

    history__ = conversation__['history']
    history__.append({"role": "user", "content": message__})

    ai_response__ = Tool_function_send_message_to_ai__(history__)

    history__.append({"role": "assistant", "content": ai_response__})

    if len(history__) > 20:
        history__ = [history__[0], history__[1]] + history__[-18:]

    return jsonify({'response': ai_response__})

@app.route('/ai/clear', methods=['POST'])
def ai_clear():
    data = request.get_json()
    conversation_id__ = data.get('conversation_id')
    if not conversation_id__:
        return jsonify({'error': '缺少会话ID'}), 400

    conversation__ = Dict_ai_conversations__.get(conversation_id__)
    if not conversation__:
        return jsonify({'error': '会话不存在'}), 404

    system_prompt__ = conversation__['history'][0]['content']
    initial_user__ = conversation__['history'][1]['content']
    conversation__['history'] = [
        {"role": "system", "content": system_prompt__},
        {"role": "user", "content": initial_user__}
    ]
    return jsonify({'success': True})

@app.route('/ai/report', methods=['POST'])
def ai_report():
    """生成分析报告"""
    data = request.get_json()
    conversation_id__ = data.get('conversation_id')
    if not conversation_id__:
        return jsonify({'error': '缺少会话ID'}), 400

    conversation__ = Dict_ai_conversations__.get(conversation_id__)
    if not conversation__:
        return jsonify({'error': '会话不存在'}), 404

    summary__ = conversation__['summary']
    security_info__ = conversation__['security_info']
    report_prompt__ = f"""请基于以下证券数据，生成一份专业、详细、规范的证券分析报告。

证券基本信息：
- 证券名称: {security_info__[1]}
- 证券代码: {security_info__[2]}
- 证券种类: {security_info__[0]}
- 交易板块: {security_info__[3]}

数据摘要：
- 数据周期数: {summary__['数据统计']['数据周期数']}个交易日
- 时间范围: {summary__['数据统计']['时间范围']}
- 最新收盘价: {summary__['数据统计']['最新收盘价']}

请生成一份专业的证券分析报告，要求如下：
1. 报告结构清晰，包括以下部分：概要、基本面分析、技术面分析、风险评估、投资建议、结论。
2. 使用专业、严谨的分析语言，避免使用表情符号和特殊字符。
3. 采用段落形式进行阐述，每个部分用清晰的标题分隔，避免使用表格。
4. 在分析中引用具体的数据支持观点，包括价格数据、成交量数据和技术指标数据。
5. 给出明确的投资建议，包括具体的操作建议、风险控制和持仓建议。
6. 报告长度适中，内容详实但不冗长，适合专业投资者阅读。

请基于完整的证券数据进行深入分析，并生成符合专业标准的分析报告。
"""
    temp_history__ = [
        {"role": "system", "content": conversation__['history'][0]['content']},
        {"role": "user", "content": report_prompt__}
    ]
    report__ = Tool_function_send_message_to_ai__(temp_history__)
    return jsonify({'report': report__})

@app.route('/ai/export_data', methods=['POST'])
def ai_export_data():
    """导出证券完整数据为txt文件"""
    data = request.get_json()
    conversation_id__ = data.get('conversation_id')
    if not conversation_id__:
        return jsonify({'error': '缺少会话ID'}), 400

    conversation__ = Dict_ai_conversations__.get(conversation_id__)
    if not conversation__:
        return jsonify({'error': '会话不存在'}), 404

    security_info__ = conversation__['security_info']
    klines__ = conversation__['klines']
    summary__ = conversation__['summary']

    export_data__ = {
        "证券基本信息": {
            "证券名称": security_info__[1],
            "证券代码": security_info__[2],
            "证券种类": security_info__[0],
            "交易板块": security_info__[3]
        },
        "K线原始数据": klines__,
        "数据摘要": summary__,
        "导出时间": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    txt_content__ = repr(export_data__)
    filename__ = f"{security_info__[2]}_{security_info__[1]}_完整证券数据.txt"

    mem_file__ = io.BytesIO()
    mem_file__.write(txt_content__.encode('utf-8'))
    mem_file__.seek(0)

    return send_file(
        mem_file__,
        as_attachment=True,
        download_name=filename__,
        mimetype='text/plain'
    )

# =========================== 【 工具箱路由 】 ===========================
@app.route('/toolbox')
def toolbox():
    """工具箱页面"""
    code = request.args.get('code', '')
    name = request.args.get('name', '')
    return render_template('toolbox.html', code=code, name=name)

# =========================== 【↑ Flask 路由 ↑】 ===========================





if __name__ == '__main__':
    app.run(debug=True, threaded=True)
