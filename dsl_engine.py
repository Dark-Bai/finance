# -*- coding: utf-8 -*-
"""
=====================================================================
DSL 选股语言翻译引擎（架构图 · 阶段二 · 任务4）
---------------------------------------------------------------------
将用户编写的"类 SQL 选股表达式"自动翻译为数据库查询语言。
当前落地方言：DuckDB；预留 Doris 方言适配层（任务6 的挂接点）。

文法（EBNF）：
    expr       := or_expr
    or_expr    := and_expr ( (OR | "或" | "||") and_expr )*
    and_expr   := not_expr ( (AND | "与" | "&&") not_expr )*
    not_expr   := (NOT | "非" | "!") not_expr | comparison
    comparison := add_expr ( cmp_op add_expr
                           | IN "(" literal (, literal)* ")"
                           | "包含" add_expr )?
    add_expr   := mul_expr ( ("+"|"-") mul_expr )*
    mul_expr   := unary    ( ("*"|"/") unary )*
    unary      := "-" unary | primary
    primary    := NUMBER | STRING | func_call | field | "(" expr ")"
    func_call  := IDENT "(" arg (, arg)* ")"

示例：
    行业 = "银行" AND 市盈率 < 8 AND 市净率 < 1
    MA(收盘价, 5) > MA(收盘价, 20) AND NOT ST
    创新高(120) AND 成交额 > 30000
=====================================================================
"""

import re
import math


# =========================== 【异常定义】 ===========================
class DSLError(Exception):
    """DSL 词法/语法/语义错误。pos 为源串中的字符下标（0 起），供前端光标定位。"""

    def __init__(self, message, pos=None):
        super().__init__(message)
        self.message = message
        self.pos = pos

    def __str__(self):
        if self.pos is not None:
            return f'{self.message}（第 {self.pos + 1} 个字符）'
        return self.message


# =========================== 【词库：字段】 ===========================
# 数值型当日指标 -> (SQL 表达式, 单位)。s = "当日信息表" 别名
NUMERIC_FIELDS = {
    '开盘价':   ('{s_open}', '元'),
    '收盘价':   ('{s_close}', '元'),
    '最高价':   ('{s_high}', '元'),
    '最低价':   ('{s_low}', '元'),
    '成交量':   ('{s_vol}', '手'),
    '成交额':   ('{s_amount} / 10', '万元'),     # 库中为千元，换算为万元
    '涨跌幅':   ('{s_pct_chg}', '%'),
    '涨跌额':   ('{s_change}', '元'),
    '振幅':     ('{s_amp}', '%'),
    '换手率':   ('{s_turnover}', '%'),
    '市盈率':   ('{s_pe}', '倍'),
    '动态市盈率': ('{s_pe}', '倍'),
    '市盈率TTM': ('{s_pe_ttm}', '倍'),
    '市净率':   ('{s_pb}', '倍'),
    '市销率':   ('{s_ps}', '倍'),
    '市销率TTM': ('{s_ps_ttm}', '倍'),
    '总市值':   ('{s_total_mv} / 10000', '亿元'),  # 库中为万元，换算为亿元
    '流通市值': ('{s_circ_mv} / 10000', '亿元'),
    '总股本':   ('{s_total_share}', '万股'),
    '流通股本': ('{s_float_share}', '万股'),
    '股息率':   ('{s_dv_ratio}', '%'),
    '股息率TTM': ('{s_dv_ttm}', '%'),
    '量比':     ('{s_volume_ratio}', ''),
}

# 文本型板块属性 -> SQL 表达式。b = "基本信息表" 别名
STRING_FIELDS = {
    '名称':   '{b_name}',
    '股票名称': '{b_name}',
    '代码':   '{b_symbol}',
    '股票代码': '{b_symbol}',
    '行业':   '{b_industry}',
    '地域':   '{b_area}',
    '板块':   '{b_sector}',
    '交易所': '{b_exchange}',
}

# 布尔型属性 -> SQL 条件表达式（可直接作为条件，也可被 NOT 修饰）
BOOL_FIELDS = {
    'ST':    '{b_name} LIKE \'%ST%\'',
    'ST股':  '{b_name} LIKE \'%ST%\'',
    '风险警示': '{b_name} LIKE \'%ST%\'',
    '*ST':   '{b_name} LIKE \'%*ST%\'',
    '*ST股': '{b_name} LIKE \'%*ST%\'',
}

# 交易所取值别名 -> 库中代码
EXCHANGE_ALIASES = {
    '上证': 'SSE', '上海': 'SSE', '沪': 'SSE',
    '深证': 'SZSE', '深圳': 'SZSE', '深': 'SZSE',
    '北证': 'BSE', '北京': 'BSE',
}

# =========================== 【词库：历史函数】 ===========================
# MA() 允许的历史行情字段 -> 日度信息表列
MA_FIELDS = {
    '收盘价': 'close', '开盘价': 'open', '最高价': 'high',
    '最低价': 'low', '成交量': 'vol', '成交额': 'amount',
}

HIST_FUNC_DESCS = {
    'MA':     'MA(指标, N)：N 日移动平均。指标可取 收盘价/开盘价/最高价/最低价/成交量/成交额',
    '区间涨幅': '区间涨幅(N)：最新收盘价相对 N 个交易日前的涨跌幅（%）',
    'N日最高': 'N日最高(N)：最近 N 个交易日的最高价最大值（元）',
    'N日最低': 'N日最低(N)：最近 N 个交易日的最低价最小值（元）',
    '连涨':    '连涨(N)：最近 N 个交易日涨跌幅全部大于 0（不足 N 日按实际天数）',
    '连跌':    '连跌(N)：最近 N 个交易日涨跌幅全部小于 0（不足 N 日按实际天数）',
    '创新高':  '创新高(N)：最新收盘价达到最近 N 个交易日收盘价最高值',
    '创新低':  '创新低(N)：最新收盘价跌至最近 N 个交易日收盘价最低值',
}

_FUNC_ALIASES = {'N日涨幅': '区间涨幅'}
_MAX_WINDOW = 250   # 历史函数允许的最大 N


# =========================== 【方言层（任务6 挂接点）】 ===========================
class Dialect:
    """SQL 方言基类：迁移 Doris 时只需补充/覆写此处差异点。"""
    name = 'base'
    quote_char = '"'

    def quote(self, ident):
        return f'{self.quote_char}{ident}{self.quote_char}'

    def table_name(self, cn_name):
        """中文表名 -> 当前方言的表名。基类默认原样返回（DuckDB 用中文表名）。"""
        return cn_name

    def concat(self, a, b):
        """字符串拼接表达式。基类默认 DuckDB 的 || 语法。"""
        return f'{a} || {b}'


class DuckDBDialect(Dialect):
    name = 'duckdb'
    quote_char = '"'


class DorisDialect(Dialect):
    """Doris 方言（MySQL 协议）。CTE / 窗口函数 / 分组聚合语法与本引擎生成结构兼容，
    主要差异为标识符引号、中文表名映射、字符串拼接。"""
    name = 'doris'
    quote_char = '`'

    def table_name(self, cn_name):
        from db import TABLE_MAP
        return TABLE_MAP.get(cn_name, cn_name)

    def concat(self, a, b):
        return f'CONCAT({a}, {b})'


_DIALECTS = {d.name: d for d in (DuckDBDialect, DorisDialect)}


# =========================== 【词法分析】 ===========================
_TOKEN_RE = re.compile(r"""
    (?P<NUMBER>\d+(?:\.\d+)?)
  | (?P<STRING>"[^"\n]*"|'[^'\n]*')
  | (?P<STAR_ST>\*ST股?)
  | (?P<OP>>=|<=|!=|<>|==|&&|\|\||[=><+\-*/(),!])
  | (?P<IDENT>[A-Za-z_一-鿿][A-Za-z0-9_一-鿿]*)
  | (?P<SKIP>[ \t\r\n]+)
  | (?P<MISMATCH>.)
""", re.VERBOSE)


class Token:
    __slots__ = ('type', 'value', 'pos')

    def __init__(self, type_, value, pos):
        self.type = type_
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f'Token({self.type}, {self.value!r}, @{self.pos})'


def _tokenize(text):
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        value = m.group()
        pos = m.start()
        if kind == 'SKIP':
            continue
        if kind == 'MISMATCH':
            raise DSLError(f'无法识别的字符 {value!r}', pos)
        if kind == 'STAR_ST':
            kind = 'IDENT'   # *ST 作为布尔型字段名（KEY 在 BOOL_FIELDS）
        if kind == 'NUMBER':
            value = float(value)
        elif kind == 'STRING':
            value = value[1:-1]   # 去掉首尾引号（不支持转义）
        tokens.append(Token(kind, value, pos))
    tokens.append(Token('EOF', '', len(text)))
    return tokens


# =========================== 【语法分析（递归下降）】 ===========================
_KW_AND = ('AND', '与')
_KW_OR = ('OR', '或')
_KW_NOT = ('NOT', '非')
_KW_IN = ('IN',)
_KW_CONTAINS = ('包含',)


class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def advance(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def _at_kw(self, kws):
        tok = self.peek()
        return tok.type == 'IDENT' and (tok.value in kws or
                                        (isinstance(tok.value, str) and tok.value.upper() in kws))

    def _at_op(self, *ops):
        tok = self.peek()
        return tok.type == 'OP' and tok.value in ops

    def parse(self):
        node = self.parse_or()
        tok = self.peek()
        if tok.type != 'EOF':
            raise DSLError(f'这里有多余的内容 {tok.value!r}，表达式应已结束', tok.pos)
        return node

    # ---- 逻辑层 ----
    def parse_or(self):
        parts = [self.parse_and()]
        while self._at_kw(_KW_OR) or self._at_op('||'):
            self.advance()
            parts.append(self.parse_and())
        return parts[0] if len(parts) == 1 else ('or', parts)

    def parse_and(self):
        parts = [self.parse_not()]
        while self._at_kw(_KW_AND) or self._at_op('&&'):
            self.advance()
            parts.append(self.parse_not())
        return parts[0] if len(parts) == 1 else ('and', parts)

    def parse_not(self):
        if self._at_kw(_KW_NOT) or self._at_op('!'):
            tok = self.advance()
            return ('not', self.parse_not(), tok.pos)
        return self.parse_comparison()

    # ---- 比较层 ----
    def parse_comparison(self):
        left = self.parse_add()
        tok = self.peek()
        if tok.type == 'OP' and tok.value in ('=', '==', '!=', '<>', '>', '>=', '<', '<='):
            self.advance()
            right = self.parse_add()
            return ('cmp', tok.value, left, right, tok.pos)
        if self._at_kw(_KW_IN):
            self.advance()
            if not self._at_op('('):
                raise DSLError('IN 后面应跟括号列表，例如：行业 IN ("银行", "证券")', self.peek().pos)
            self.advance()
            items = [self.parse_add()]
            while self._at_op(','):
                self.advance()
                items.append(self.parse_add())
            if not self._at_op(')'):
                raise DSLError('IN 列表缺少右括号 )', self.peek().pos)
            self.advance()
            return ('in', left, items, tok.pos)
        if self._at_kw(_KW_CONTAINS):
            self.advance()
            right = self.parse_add()
            return ('contains', left, right, tok.pos)
        return left

    # ---- 算术层 ----
    def parse_add(self):
        node = self.parse_mul()
        while self._at_op('+', '-'):
            tok = self.advance()
            node = ('bin', tok.value, node, self.parse_mul(), tok.pos)
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self._at_op('*', '/'):
            tok = self.advance()
            node = ('bin', tok.value, node, self.parse_unary(), tok.pos)
        return node

    def parse_unary(self):
        if self._at_op('-'):
            tok = self.advance()
            return ('neg', self.parse_unary(), tok.pos)
        return self.parse_primary()

    # ---- 原子层 ----
    def parse_primary(self):
        tok = self.peek()
        if tok.type == 'NUMBER':
            self.advance()
            return ('num', tok.value, tok.pos)
        if tok.type == 'STRING':
            self.advance()
            return ('str', tok.value, tok.pos)
        if tok.type == 'IDENT':
            # 关键字若出现在不该出现的位置，给出友好提示
            if tok.value in _KW_AND[1:] + _KW_OR[1:] + _KW_NOT[1:] or \
               (isinstance(tok.value, str) and tok.value.upper() in ('AND', 'OR', 'NOT', 'IN')):
                raise DSLError(f'关键字 {tok.value!r} 不能出现在这里', tok.pos)
            self.advance()
            if self._at_op('('):   # 函数调用
                self.advance()
                args = []
                if not self._at_op(')'):
                    args.append(self.parse_or())
                    while self._at_op(','):
                        self.advance()
                        args.append(self.parse_or())
                if not self._at_op(')'):
                    raise DSLError(f'函数 {tok.value}() 缺少右括号 )', self.peek().pos)
                self.advance()
                return ('call', tok.value, args, tok.pos)
            return ('field', tok.value, tok.pos)
        if self._at_op('('):
            self.advance()
            node = self.parse_or()
            if not self._at_op(')'):
                raise DSLError('缺少右括号 )', self.peek().pos)
            self.advance()
            return node
        if tok.type == 'EOF':
            raise DSLError('表达式在这里意外结束，似乎少了一个条件或数值', tok.pos)
        raise DSLError(f'这里不应该出现 {tok.value!r}', tok.pos)


# =========================== 【语义分析与 SQL 生成】 ===========================
_TYPE_CN = {'number': '数值', 'string': '文本', 'bool': '条件（布尔值）'}
_CMP_SQL = {'=': '=', '==': '=', '!=': '<>', '<>': '<>', '>': '>', '>=': '>=', '<': '<', '<=': '<='}


class _Generator:
    def __init__(self, dialect, limit):
        self.d = dialect
        self.limit = limit
        self.hist_cols = {}      # 历史聚合列: 别名 -> SELECT 表达式
        self.max_n = 1           # 用过的最大窗口（决定 ranked 子查询的 rn 上限）
        self.used_funcs = []     # 供日志展示

    # ---------- 字段引用 ----------
    def _col(self, alias, col):
        return f'{alias}.{self.d.quote(col)}'

    def _field_sql(self, template, mapping=None):
        """把词库模板里的占位符（如 {s_close}）替换为带方言引号的列引用。"""
        return template.format(**{
            ph: self._col(ph.split('_', 1)[0], ph.split('_', 1)[1])
            for ph in re.findall(r'\{(\w+)\}', template)
        })

    # ---------- 历史聚合列登记 ----------
    def _hist(self, alias, expr, window_n):
        if alias not in self.hist_cols:
            self.hist_cols[alias] = expr
        self.max_n = max(self.max_n, window_n)
        return f'h.{self.d.quote(alias)}'

    def _hist_col_ref(self, base_col, n, agg, cmp_op=None):
        """生成 MAX/MIN(CASE WHEN rn <= n THEN col END) 形式的聚合列并返回引用。"""
        qcol = self.d.quote(base_col)
        alias = f'f_{agg.lower()}_{base_col}_{n}'
        expr = f'{agg}(CASE WHEN rn <= {n} THEN {qcol} END)'
        return self._hist(alias, expr, n)

    # ---------- 主入口 ----------
    def gen(self, node):
        kind = node[0]
        handler = getattr(self, f'_gen_{kind}', None)
        if handler is None:
            raise DSLError(f'内部错误：未知节点 {kind}')
        return handler(node)

    def _gen_num(self, node):
        v = node[1]
        text = str(int(v)) if float(v).is_integer() else repr(v)
        return text, 'number', node[2]

    def _gen_str(self, node):
        return f"'{self._esc_str_lit(node[1])}'", 'string', node[2]

    def _esc_str_lit(self, s):
        """转义 SQL 字符串字面量内容。Doris（MySQL 协议）字符串里反斜杠是转义符，需双倍。"""
        if self.d.name == 'doris':
            s = s.replace('\\', '\\\\')
        return s.replace("'", "''")

    def _gen_field(self, node):
        name, pos = node[1], node[2]
        if name.lower() in ('true', 'false'):   # 布尔字面量，供布尔字段比较：ST = true / ST = false
            return name.upper(), 'bool', pos
        if name in NUMERIC_FIELDS:
            return self._field_sql(NUMERIC_FIELDS[name][0], None), 'number', pos
        if name in STRING_FIELDS:
            return self._field_sql(STRING_FIELDS[name], None), 'string', pos
        if name in BOOL_FIELDS:
            # LIKE 表达式必须自带括号：Doris 中 = 优先级高于 LIKE，
            # 不加括号时 `x LIKE 'a' = TRUE` 会被解析为 `x LIKE ('a' = TRUE)`
            return f'({self._field_sql(BOOL_FIELDS[name], None)})', 'bool', pos
        # 用户可能把函数名当字段用了
        if name in HIST_FUNC_DESCS or name in _FUNC_ALIASES:
            raise DSLError(f'{name} 是函数，需要带参数调用，例如：{name}(20)', pos)
        raise DSLError(
            f'不认识的字段 {name!r}。可用字段请点"语法帮助"查看词库', pos)

    def _gen_neg(self, node):
        sql, typ, _ = self.gen(node[1])
        if typ != 'number':
            raise DSLError('负号只能用于数值', node[2])
        return f'(-{sql})', 'number', node[2]

    def _gen_bin(self, node):
        op = node[1]
        lsql, lt, _ = self.gen(node[2])
        rsql, rt, _ = self.gen(node[3])
        if lt != 'number' or rt != 'number':
            raise DSLError(f'运算符 {op} 两边都必须是数值', node[4])
        if op == '/':
            return f'({lsql} / NULLIF({rsql}, 0))', 'number', node[4]
        return f'({lsql} {op} {rsql})', 'number', node[4]

    def _exchange_alias(self, node):
        """交易所字段与文本常量比较时，把 上证/深证/北证 等别名映射为库内代码。"""
        if node[0] == 'str':
            mapped = EXCHANGE_ALIASES.get(node[1])
            if mapped:
                return ('str', mapped, node[2])
        return node

    def _gen_cmp(self, node):
        op, lnode, rnode, pos = node[1], node[2], node[3], node[4]
        # 交易所别名映射
        if lnode[0] == 'field' and lnode[1] == '交易所':
            rnode = self._exchange_alias(rnode)
        lsql, lt, _ = self.gen(lnode)
        rsql, rt, _ = self.gen(rnode)
        if lt != rt:
            raise DSLError(
                f'比较两边类型不一致：左边是{_TYPE_CN[lt]}，右边是{_TYPE_CN[rt]}', pos)
        if lt == 'bool' and op not in ('=', '==', '!=', '<>'):
            raise DSLError('条件（布尔值）只支持 = 与 != 比较', pos)
        return f'({lsql} {_CMP_SQL[op]} {rsql})', 'bool', pos

    def _gen_in(self, node):
        lnode, items, pos = node[1], node[2], node[3]
        if lnode[0] == 'field' and lnode[1] == '交易所':
            items = [self._exchange_alias(it) for it in items]
        lsql, lt, _ = self.gen(lnode)
        sqls = []
        for it in items:
            isql, ityp, ipos = self.gen(it)
            if ityp != lt:
                raise DSLError(
                    f'IN 列表里的值类型应均为{_TYPE_CN[lt]}', ipos)
            sqls.append(isql)
        return f'({lsql} IN ({", ".join(sqls)}))', 'bool', pos

    def _gen_contains(self, node):
        lsql, lt, _ = self.gen(node[1])
        rnode = node[2]
        rsql, rt, rpos = self.gen(rnode)
        if lt != 'string' or rt != 'string':
            raise DSLError('"包含" 两边都必须是文本（字段如 名称/行业，常量如 "银行"）', node[3])
        kw = rnode[1].replace('%', '').replace('_', '') if rnode[0] == 'str' else None
        if kw is not None:
            kw_esc = self._esc_str_lit(kw)
            return f"({lsql} LIKE '%{kw_esc}%')", 'bool', node[3]
        return f"({lsql} LIKE " + self.d.concat("'%'", self.d.concat(rsql, "'%'")) + ")", 'bool', node[3]

    def _gen_and(self, node):
        parts = []
        for sub in node[1]:
            sql, typ, spos = self.gen(sub)
            if typ != 'bool':
                raise DSLError(
                    f'AND 连接的每一项都必须是条件，这里却是{_TYPE_CN[typ]}。'
                    f'请写成比较形式，例如：收盘价 > 10', spos)
            parts.append(sql)
        return '(' + ' AND '.join(parts) + ')', 'bool', node[1][0][-1] if node[1] else 0

    def _gen_or(self, node):
        parts = []
        for sub in node[1]:
            sql, typ, spos = self.gen(sub)
            if typ != 'bool':
                raise DSLError(
                    f'OR 连接的每一项都必须是条件，这里却是{_TYPE_CN[typ]}。'
                    f'请写成比较形式，例如：收盘价 > 10', spos)
            parts.append(sql)
        return '(' + ' OR '.join(parts) + ')', 'bool', node[1][0][-1] if node[1] else 0

    def _gen_not(self, node):
        sql, typ, _ = self.gen(node[1])
        if typ != 'bool':
            raise DSLError('NOT 后面必须是一个条件', node[2])
        return f'(NOT {sql})', 'bool', node[2]

    # ---------- 历史函数 ----------
    def _require_int_n(self, node, fname):
        if node[0] != 'num' or not float(node[1]).is_integer():
            raise DSLError(f'{fname}() 的天数参数必须是正整数，例如：{fname}(20)', node[-1])
        n = int(node[1])
        if n < 1 or n > _MAX_WINDOW:
            raise DSLError(f'{fname}() 的天数须在 1~{_MAX_WINDOW} 之间', node[-1])
        return n

    def _gen_call(self, node):
        fname, args, pos = node[1], node[2], node[3]
        fname = _FUNC_ALIASES.get(fname, fname)
        if fname not in HIST_FUNC_DESCS:
            raise DSLError(
                f'不认识的函数 {node[1]}()。可用函数：' + '、'.join(HIST_FUNC_DESCS), pos)

        if fname == 'MA':
            if len(args) != 2:
                raise DSLError('MA() 需要两个参数：MA(指标, 天数)，例如：MA(收盘价, 20)', pos)
            field_node = args[0]
            if field_node[0] != 'field' or field_node[1] not in MA_FIELDS:
                raise DSLError(
                    'MA() 的第一个参数必须是历史行情字段：'
                    + '、'.join(MA_FIELDS), field_node[-1])
            n = self._require_int_n(args[1], fname)
            base_col = MA_FIELDS[field_node[1]]
            ref = self._hist_col_ref(base_col, n, 'AVG')
            if base_col == 'amount':   # 成交额单位换算：千元 -> 万元
                ref = f'({ref} / 10)'
            self.used_funcs.append(f'MA({field_node[1]},{n})')
            return ref, 'number', pos

        # 单参数函数
        if len(args) != 1:
            raise DSLError(f'{fname}() 只需要一个天数参数，例如：{fname}(20)', pos)
        n = self._require_int_n(args[0], fname)
        self.used_funcs.append(f'{fname}({n})')

        last_close = self._hist('f_last_close',
                                f'MAX(CASE WHEN rn = 1 THEN {self.d.quote("close")} END)', 1)
        if fname == '区间涨幅':
            ref_n = self._hist(f'f_ref_close_{n}',
                               f'MAX(CASE WHEN rn = {n + 1} THEN {self.d.quote("close")} END)', n + 1)
            return f'(({last_close} / NULLIF({ref_n}, 0) - 1) * 100)', 'number', pos
        if fname == 'N日最高':
            return self._hist_col_ref('high', n, 'MAX'), 'number', pos
        if fname == 'N日最低':
            return self._hist_col_ref('low', n, 'MIN'), 'number', pos
        if fname == '连涨':
            ref = self._hist_col_ref('pct_chg', n, 'MIN')
            return f'({ref} > 0)', 'bool', pos
        if fname == '连跌':
            ref = self._hist_col_ref('pct_chg', n, 'MAX')
            return f'({ref} < 0)', 'bool', pos
        if fname == '创新高':
            ref = self._hist_col_ref('close', n, 'MAX')
            return f'({last_close} >= {ref})', 'bool', pos
        if fname == '创新低':
            ref = self._hist_col_ref('close', n, 'MIN')
            return f'({last_close} <= {ref})', 'bool', pos
        raise DSLError(f'内部错误：未实现的函数 {fname}', pos)

    # ---------- 组装完整 SELECT ----------
    def build_select(self, where_sql):
        q = self.d.quote
        latest_cte = f'latest AS (\n    SELECT MAX({q("trade_date")}) AS d FROM {q(self.d.table_name("当日信息表"))}\n)'
        hist_cte = ''
        hist_join = ''
        if self.hist_cols:
            cols = ',\n           '.join(
                f'{expr} AS {q(alias)}' for alias, expr in self.hist_cols.items())
            ranked_cols = ', '.join(q(c) for c in
                                    ('ts_code', 'trade_date', 'open', 'close', 'high', 'low', 'vol', 'amount', 'pct_chg'))
            hist_cte = (
                f',\nhist AS (\n'
                f'    SELECT {q("ts_code")},\n'
                f'           {cols}\n'
                f'    FROM (\n'
                f'        SELECT {ranked_cols},\n'
                f'               ROW_NUMBER() OVER (PARTITION BY {q("ts_code")} '
                f'ORDER BY {q("trade_date")} DESC) AS rn\n'
                f'        FROM {q(self.d.table_name("日度信息表"))}\n'
                f'    ) ranked\n'
                f'    WHERE rn <= {self.max_n + 1}\n'
                f'    GROUP BY {q("ts_code")}\n'
                f')'
            )
            hist_join = f'\nLEFT JOIN hist h ON h.{q("ts_code")} = b.{q("ts_code")}'
        return (
            f'WITH {latest_cte}{hist_cte}\n'
            f'SELECT b.{q("name")}     AS name,\n'
            f'       b.{q("symbol")}   AS symbol,\n'
            f'       b.{q("ts_code")}  AS ts_code,\n'
            f'       b.{q("exchange")} AS exchange,\n'
            f'       b.{q("sector")}   AS sector,\n'
            f'       s.{q("close")}    AS close,\n'
            f'       s.{q("pe")}       AS pe,\n'
            f'       s.{q("pb")}       AS pb,\n'
            f'       s.{q("total_mv")} AS total_mv,\n'
            f'       s.{q("circ_mv")}  AS circ_mv\n'
            f'FROM {q(self.d.table_name("基本信息表"))} b\n'
            f'JOIN {q(self.d.table_name("当日信息表"))} s ON s.{q("ts_code")} = b.{q("ts_code")}\n'
            f'JOIN latest ON s.{q("trade_date")} = latest.d'
            f'{hist_join}\n'
            f'WHERE {where_sql}\n'
            f'ORDER BY b.{q("symbol")}\n'
            f'LIMIT {self.limit}'
        )


# =========================== 【对外接口】 ===========================
def translate(text, dialect='duckdb', limit=10000):
    """把 DSL 文本翻译为 SQL。返回 {'sql', 'where', 'used_functions', 'dialect'}。
    语法/语义错误抛出 DSLError（含字符位置）。"""
    if not text or not text.strip():
        raise DSLError('指令为空。请输入选股条件，例如：市盈率 < 20 AND 行业 = "银行"', 0)
    dialect_cls = _DIALECTS.get(dialect)
    if dialect_cls is None:
        raise DSLError(f'未知方言 {dialect!r}，当前支持：' + '、'.join(_DIALECTS))
    d = dialect_cls()
    tokens = _tokenize(text)
    ast = _Parser(tokens).parse()
    gen = _Generator(d, limit)
    where_sql, typ, _ = gen.gen(ast)
    if typ != 'bool':
        raise DSLError(
            f'整个表达式的结果必须是条件，当前是{_TYPE_CN[typ]}。'
            f'请写成比较形式，例如：收盘价 > 10', 0)
    return {
        'sql': gen.build_select(where_sql),
        'where': where_sql,
        'used_functions': gen.used_funcs,
        'dialect': dialect,
    }


def _num(v, scale=1.0):
    if v is None:
        return 'None'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 'None'
    if math.isnan(f):
        return 'None'
    return round(f * scale, 2)


def execute_dsl(text, db_path=None, dialect=None, limit=10000):
    """翻译并在数据库上执行，返回与现有筛选结果同构的行数据。
    返回 {'rows', 'count', 'sql', 'used_functions', 'dialect'}。
   dialec 未指定时从 db.DB_TYPE 自动推断；db_path 保留参数只为向后兼容。"""
    from db import db_connect, fetchdf as _fetchdf, DB_TYPE
    if dialect is None:
        dialect = DB_TYPE
    tr = translate(text, dialect, limit=limit)
    conn = db_connect()
    try:
        if DB_TYPE == 'doris':
            cursor = conn.cursor()
            cursor.execute(tr['sql'])
            df = _fetchdf(cursor)
        else:
            df = conn.execute(tr['sql']).fetchdf()
    finally:
        conn.close()
    rows = []
    for _, r in df.iterrows():
        rows.append({
            '证券种类': '股票',
            '证券名称': r.get('name', ''),
            '证券代码': r.get('symbol', ''),
            '交易所码': r.get('exchange', ''),
            '交易板块': r.get('sector', '') or '',
            '最近收盘价': _num(r.get('close')),
            '动态市盈率': _num(r.get('pe')),
            '市净率': _num(r.get('pb')),
            '总市值（亿元）': _num(r.get('total_mv'), 1 / 10000),
            '流通市值（亿元）': _num(r.get('circ_mv'), 1 / 10000),
        })
    return {'rows': rows, 'count': len(rows), **tr}


def get_dsl_help():
    """词库与语法帮助（供前端"语法帮助"面板渲染）。"""
    return {
        'intro': '用"字段 运算符 阈值"写条件，用 AND / OR / NOT 组合；'
                 '支持 + - * / 与括号；文本常量用英文双引号括起。',
        'numeric_fields': [
            {'name': k, 'unit': v[1]} for k, v in NUMERIC_FIELDS.items()
        ],
        'string_fields': [
            {'name': '名称', 'note': '股票简称，可配合"包含"做关键字筛选'},
            {'name': '代码', 'note': '6 位股票代码，如 "600519"'},
            {'name': '行业', 'note': '如 "银行"、"白酒"，可用 IN 指定多个'},
            {'name': '地域', 'note': '省份，如 "广东"、"北京"'},
            {'name': '板块', 'note': '如 "科创板"、"创业板"、"上证主板"'},
            {'name': '交易所', 'note': '可写 "上证"/"深证"/"北证"（自动映射 SSE/SZSE/BSE）'},
        ],
        'bool_fields': [
            {'name': 'ST', 'note': '风险警示股（含 ST 与 *ST）。排除写法：NOT ST（或 非 ST）'},
            {'name': '*ST', 'note': '纯 *ST 股。纯 ST 写法：ST AND NOT *ST'},
        ],
        'functions': [
            {'sig': 'MA(指标, N)', 'desc': HIST_FUNC_DESCS['MA'],
             'example': 'MA(收盘价, 5) > MA(收盘价, 20)'},
            {'sig': '区间涨幅(N)', 'desc': HIST_FUNC_DESCS['区间涨幅'],
             'example': '区间涨幅(20) > 15'},
            {'sig': 'N日最高(N) / N日最低(N)', 'desc': HIST_FUNC_DESCS['N日最高'],
             'example': '收盘价 >= N日最高(60) * 0.98'},
            {'sig': '连涨(N) / 连跌(N)', 'desc': HIST_FUNC_DESCS['连涨'],
             'example': '连涨(3) AND 换手率 > 5'},
            {'sig': '创新高(N) / 创新低(N)', 'desc': HIST_FUNC_DESCS['创新高'],
             'example': '创新高(120) AND 成交额 > 30000'},
        ],
        'operators': [
            {'sig': '= != > >= < <=', 'desc': '比较。文本与数值均可（= 也可写成 ==）'},
            {'sig': 'AND OR NOT（与/或/非，&& || !）', 'desc': '逻辑组合，可用括号改变优先级'},
            {'sig': 'IN ("a", "b")', 'desc': '多值匹配，常用于 行业/地域/板块'},
            {'sig': '包含', 'desc': '文本包含，如：名称 包含 "茅台"'},
            {'sig': '+ - * /', 'desc': '算术运算，如：总市值 / 收盘价 > 50'},
        ],
        'examples': [
            {'title': '低估值银行', 'dsl': '行业 = "银行" AND 市盈率 < 8 AND 市净率 < 1'},
            {'title': '均线多头排列', 'dsl': 'MA(收盘价, 5) > MA(收盘价, 20) AND MA(收盘价, 20) > MA(收盘价, 60)'},
            {'title': '近期强势股', 'dsl': '区间涨幅(20) > 20 AND 换手率 > 3 AND NOT ST'},
            {'title': '突破创新高', 'dsl': '创新高(120) AND 成交额 > 30000 AND 非 ST'},
            {'title': '连跌后观察', 'dsl': '连跌(5) AND 市盈率 > 0 AND 市盈率 < 20'},
            {'title': '大盘蓝筹高股息', 'dsl': '总市值 > 2000 AND 股息率 > 2'},
            {'title': '金融板块集合', 'dsl': '行业 IN ("银行", "证券", "保险") AND 地域 = "上海"'},
            {'title': '名称关键字', 'dsl': '名称 包含 "科技" AND 收盘价 < 30'},
        ],
        'notes': [
            '条件引用某指标时，该指标为空的股票会被排除（如 市盈率 < 20 会排除市盈率为空的股票）；不被条件引用的空值不影响入选',
            '名称 包含 的关键字中 % 和 _ 会被忽略（防止 LIKE 通配符注入）',
            '历史函数基于日度信息表按交易日计算，N 上限 250',
            '总市值/流通市值单位为亿元，成交额为万元，成交量为手',
        ],
    }
