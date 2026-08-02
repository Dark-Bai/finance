"""
thsdk_service.py — THSDK 接口服务封装层
============================================
功能:
  1. 封装 THSDK 所有实用接口，提供统一的调用入口
  2. 添加完整的错误处理、重试机制、日志记录
  3. 提供数据缓存（内存缓存，自动过期）
  4. 连接池管理（自动连接/断开）

接入方式:
  from thsdk_service import thsdk_service
  result = thsdk_service.klines("USZA300033", count=100)
"""

import functools
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Union

# ──────────────────────────────────────────────────────────────────
# 日志配置
# ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("thsdk_service")
logger.setLevel(logging.DEBUG)

# 控制台 Handler
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s/%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
_console_handler.setFormatter(_console_formatter)
logger.addHandler(_console_handler)

# 文件 Handler（写入 logs/thsdk_service.log）
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_file_handler = logging.FileHandler(
    os.path.join(_log_dir, "thsdk_service.log"), encoding="utf-8", mode="a"
)
_file_handler.setLevel(logging.DEBUG)
_file_formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s/%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_file_handler.setFormatter(_file_formatter)
logger.addHandler(_file_handler)

# ──────────────────────────────────────────────────────────────────
# 尝试导入 THSDK，若失败则记录错误
# ──────────────────────────────────────────────────────────────────
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "thsdk-main", "src"))
    from thsdk import THS, Response
    _THSDK_AVAILABLE = True
    logger.info("✅ THSDK 库导入成功")
except ImportError as e:
    _THSDK_AVAILABLE = False
    THS = None
    Response = None
    logger.error(f"❌ THSDK 库导入失败: {e}")

# ──────────────────────────────────────────────────────────────────
# 常量定义
# ──────────────────────────────────────────────────────────────────
DEFAULT_CACHE_TTL = 60  # 默认缓存过期时间（秒）
MAX_RETRIES = 3         # 最大重试次数
RETRY_DELAY = 1.0       # 重试间隔（秒）

# 市场代码常量
MARKET_SHA = "USHA"  # 上海A股
MARKET_SZA = "USZA"  # 深圳A股
MARKET_BJ = "USTM"   # 北交所
MARKET_SHI = "USHI"  # 上海指数
MARKET_SZI = "USZI"  # 深圳指数
MARKET_HK = "UHKG"   # 港股


# ──────────────────────────────────────────────────────────────────
# 自定义异常
# ──────────────────────────────────────────────────────────────────
class THSDKServiceError(Exception):
    """THSDK 服务层异常基类"""
    pass


class THSDKConnectionError(THSDKServiceError):
    """连接异常"""
    pass


class THSDKDataError(THSDKServiceError):
    """数据查询异常"""
    pass


class THSDKNotAvailableError(THSDKServiceError):
    """THSDK 库不可用"""
    pass


# ──────────────────────────────────────────────────────────────────
# 缓存装饰器
# ──────────────────────────────────────────────────────────────────
def cached(ttl: int = DEFAULT_CACHE_TTL):
    """带 TTL 的简单内存缓存装饰器"""
    def decorator(func: Callable):
        cache: dict[str, tuple[Any, float]] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            now = time.time()
            if cache_key in cache:
                cached_value, cached_time = cache[cache_key]
                if now - cached_time < ttl:
                    logger.debug(f"缓存命中: {cache_key}")
                    return cached_value

            result = func(*args, **kwargs)
            cache[cache_key] = (result, now)
            logger.debug(f"缓存写入: {cache_key}")
            return result

        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────
# 重试装饰器
# ──────────────────────────────────────────────────────────────────
def retry_on_failure(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """失败重试装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"第 {attempt}/{max_retries} 次调用 {func.__name__} 失败: {e}"
                    )
                    if attempt < max_retries:
                        time.sleep(delay * attempt)  # 指数退避
            logger.error(
                f"调用 {func.__name__} 失败 {max_retries} 次: {last_error}"
            )
            raise last_error
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────
# 响应结果封装
# ──────────────────────────────────────────────────────────────────
class THSDKResult:
    """统一的 THSDK 调用结果封装"""

    def __init__(self, success: bool, data=None, error: str = "", raw_response=None):
        self.success = success
        self.data = data
        self.error = error
        self.raw_response = raw_response
        self.timestamp = datetime.now()

    def __bool__(self):
        return self.success

    def __repr__(self) -> str:
        status = "✅ 成功" if self.success else "❌ 失败"
        data_info = f"数据量: {len(self.data)}" if isinstance(self.data, (list, dict)) else ""
        return f"THSDKResult({status}, {data_info}, error={self.error!r})"

    @property
    def df(self):
        """获取 Pandas DataFrame 格式的数据"""
        if self.raw_response and hasattr(self.raw_response, "df"):
            return self.raw_response.df
        return None


# ──────────────────────────────────────────────────────────────────
# 主服务类
# ──────────────────────────────────────────────────────────────────
class THSDKService:
    """THSDK 服务封装类，提供统一的接口调用入口"""

    def __init__(self):
        self._ths: Optional[THS] = None
        self._connected = False

    # ── 连接管理 ──────────────────────────────────────────────

    @retry_on_failure(max_retries=2, delay=0.5)
    def connect(self) -> THSDKResult:
        """连接到 THSDK 行情服务器"""
        if not _THSDK_AVAILABLE:
            return THSDKResult(False, error="THSDK 库不可用，请检查安装")

        if self._connected and self._ths:
            logger.info("已连接，复用现有连接")
            return THSDKResult(True, data="已连接")

        try:
            self._ths = THS()
            response = self._ths.connect()
            if response and response.success:
                self._connected = True
                logger.info("✅ 成功连接到 THSDK 行情服务器")
                return THSDKResult(True, data="连接成功", raw_response=response)
            else:
                err_msg = response.error if response else "未知错误"
                logger.error(f"❌ 连接失败: {err_msg}")
                self._connected = False
                return THSDKResult(False, error=err_msg, raw_response=response)
        except Exception as e:
            logger.error(f"❌ 连接异常: {e}")
            self._connected = False
            raise

    def disconnect(self):
        """断开连接"""
        if self._ths and self._connected:
            try:
                self._ths.disconnect()
            except Exception as e:
                logger.warning(f"断开连接时出错: {e}")
        self._connected = False
        self._ths = None
        logger.info("已断开 THSDK 连接")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def _ensure_connected(self) -> THS:
        """确保已连接，返回 THS 实例"""
        if not _THSDK_AVAILABLE:
            raise THSDKNotAvailableError("THSDK 库不可用")

        if not self._connected or not self._ths:
            result = self.connect()
            if not result.success:
                raise THSDKConnectionError(f"无法连接: {result.error}")
        return self._ths

    def _call(self, method_name: str, *args, **kwargs) -> THSDKResult:
        """通用调用方法"""
        try:
            ths = self._ensure_connected()
            method = getattr(ths, method_name, None)
            if method is None:
                return THSDKResult(False, error=f"方法 {method_name} 不存在")

            response = method(*args, **kwargs)
            if response is None:
                return THSDKResult(False, error="返回空响应")

            if response.success:
                return THSDKResult(True, data=response.data, raw_response=response)
            else:
                return THSDKResult(False, error=response.error, raw_response=response)
        except THSDKConnectionError:
            raise
        except THSDKNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"调用 {method_name} 异常: {e}", exc_info=True)
            return THSDKResult(False, error=str(e))

    # ── 核心业务接口 ──────────────────────────────────────────

    @cached(ttl=30)
    def klines(
        self,
        ths_code: str,
        count: int = 180,
        interval: str = "day",
        adjust: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> THSDKResult:
        """
        获取K线数据

        参数:
            ths_code: THS格式证券代码（如 USZA300033）
            count: 获取条数（默认180，约6个月）
            interval: 周期 day/week/month/1m/5m/15m/30m/60m
            adjust: 复权类型 forward/backward
            start_time/end_time: 起止时间（与count二选一）
        """
        params = {"ths_code": ths_code, "interval": interval, "adjust": adjust}
        if count > 0:
            params["count"] = count
        if start_time and end_time:
            params["start_time"] = start_time
            params["end_time"] = end_time
        return self._call("klines", ths_code, start_time=start_time, end_time=end_time,
                          adjust=adjust, interval=interval, count=count)

    @cached(ttl=60)
    def market_data_cn(self, ths_code: str, query_key: str = "基础数据") -> THSDKResult:
        """
        获取A股实时行情数据

        参数:
            ths_code: THS格式证券代码
            query_key: 查询类型（基础数据/基础数据2/扩展1/扩展2/汇总）
        返回字段:
            代码, 名称, 价格, 涨幅, 涨跌, 成交量, 总金额,
            开盘价, 最高价, 最低价, 昨收价, 换手率, 市盈率, 市净率等
        """
        return self._call("market_data_cn", ths_code, query_key=query_key)

    @cached(ttl=300)
    def search_symbols(self, pattern: str, needmarket: str = "") -> THSDKResult:
        """
        模糊搜索证券

        参数:
            pattern: 搜索关键词（名称或代码）
            needmarket: 市场限制（如 "SH,SZ" 或 "NQ"）
        """
        return self._call("search_symbols", pattern, needmarket)

    @cached(ttl=3600)
    def stock_cn_lists(self) -> THSDKResult:
        """获取A股全量股票列表"""
        return self._call("stock_cn_lists")

    @cached(ttl=3600)
    def ths_industry(self) -> THSDKResult:
        """获取同花顺行业分类列表"""
        return self._call("ths_industry")

    @cached(ttl=3600)
    def ths_concept(self) -> THSDKResult:
        """获取同花顺概念分类列表"""
        return self._call("ths_concept")

    @cached(ttl=3600)
    def block_constituents(self, link_code: str) -> THSDKResult:
        """
        获取板块成分股

        参数:
            link_code: 板块链接代码（如 "URFI886037"）
        """
        return self._call("block_constituents", link_code)

    @cached(ttl=300)
    def complete_ths_code(self, code: Union[str, list]) -> THSDKResult:
        """
        补齐证券代码为THS格式

        参数:
            code: 单个代码字符串或代码列表
        示例:
            complete_ths_code("300033") -> USZA300033
            complete_ths_code(["300033", "600519"]) -> [USZA300033, USHA600519]
        """
        return self._call("complete_ths_code", code)

    @cached(ttl=60)
    def depth(self, ths_code: str) -> THSDKResult:
        """
        获取五档行情（买卖盘口）

        参数:
            ths_code: THS格式证券代码
        """
        return self._call("depth", ths_code)

    @cached(ttl=300)
    def news(self, text_id: int = 0x3814, code: str = "1A0001", market: str = "USHI") -> THSDKResult:
        """
        获取新闻资讯

        参数:
            text_id: 文本ID（0x3814=快讯, 0x2001=重要新闻, 0x3805=公告, 0x3806=研报, 0x3808=社区）
            code: 证券代码
            market: 市场代码
        """
        return self._call("news", text_id=text_id, code=code, market=market)

    @cached(ttl=3600)
    def ipo_today(self) -> THSDKResult:
        """获取今日IPO信息"""
        return self._call("ipo_today")

    @cached(ttl=3600)
    def ipo_wait(self) -> THSDKResult:
        """获取待发行IPO列表"""
        return self._call("ipo_wait")

    @cached(ttl=60)
    def big_order_flow(self, ths_code: str) -> THSDKResult:
        """
        获取大单资金流向

        参数:
            ths_code: THS格式证券代码（仅A股）
        """
        return self._call("big_order_flow", ths_code)

    @cached(ttl=300)
    def wencai_nlp(self, condition: str) -> THSDKResult:
        """
        问财自然语言查询

        参数:
            condition: 查询条件语句，多个条件用分号分隔
        示例:
            wencai_nlp("龙头行业;国资委;所属行业")
        """
        return self._call("wencai_nlp", condition)

    @cached(ttl=60)
    def intraday_data(self, ths_code: str) -> THSDKResult:
        """
        获取日内分时数据

        参数:
            ths_code: THS格式证券代码
        """
        return self._call("intraday_data", ths_code)

    @cached(ttl=60)
    def call_auction(self, ths_code: str) -> THSDKResult:
        """
        获取集合竞价数据

        参数:
            ths_code: THS格式证券代码
        """
        return self._call("call_auction", ths_code)

    @cached(ttl=3600)
    def call_auction_anomaly(self, market: str = "USHA") -> THSDKResult:
        """
        获取集合竞价异动

        参数:
            market: 市场代码（如 USHA/USZA/USTM）
        """
        return self._call("call_auction_anomaly", market)

    @cached(ttl=3600)
    def corporate_action(self, ths_code: str) -> THSDKResult:
        """
        获取权息资料（分红、送转等）

        参数:
            ths_code: THS格式证券代码
        """
        return self._call("corporate_action", ths_code)

    @cached(ttl=60)
    def market_data_index(self, ths_code: str, query_key: str = "基础数据") -> THSDKResult:
        """
        获取指数行情数据

        参数:
            ths_code: 指数代码（如 USHI1A0001）
            query_key: 查询类型
        """
        return self._call("market_data_index", ths_code, query_key=query_key)

    @cached(ttl=60)
    def market_data_hk(self, ths_code: str, query_key: str = "基础数据") -> THSDKResult:
        """获取港股行情数据"""
        return self._call("market_data_hk", ths_code, query_key=query_key)

    @cached(ttl=60)
    def market_data_us(self, ths_code: str, query_key: str = "基础数据") -> THSDKResult:
        """获取美股行情数据"""
        return self._call("market_data_us", ths_code, query_key=query_key)

    @cached(ttl=300)
    def tick_level1(self, ths_code: str) -> THSDKResult:
        """
        获取Level1逐笔成交

        参数:
            ths_code: THS格式证券代码
        """
        return self._call("tick_level1", ths_code)

    @cached(ttl=300)
    def min_snapshot(self, ths_code: str, date: Optional[str] = None) -> THSDKResult:
        """
        获取分钟快照

        参数:
            ths_code: THS格式证券代码
            date: 日期 YYYYMMDD
        """
        return self._call("min_snapshot", ths_code, date=date)

    # ── 批量查询 ──────────────────────────────────────────────

    def batch_market_data(self, ths_codes: list[str], query_key: str = "基础数据") -> list[THSDKResult]:
        """批量查询多只A股行情"""
        results = []
        for code in ths_codes:
            try:
                result = self.market_data_cn(code, query_key)
                results.append(result)
            except Exception as e:
                results.append(THSDKResult(False, error=f"查询 {code} 失败: {e}"))
        return results


# ──────────────────────────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────────────────────────
thsdk_service = THSDKService()

# ──────────────────────────────────────────────────────────────────
# 便捷函数
# ──────────────────────────────────────────────────────────────────
def convert_to_ths_code(code: str, market: str = "USZA") -> str:
    """
    将普通股票代码转换为THS格式

    参数:
        code: 6位股票代码（如 "300033"）
        market: 市场代码（USZA=深市, USHA=沪市, USTM=北交所）
    """
    code = code.strip()
    if len(code) == 10 and code[:4] in {"USHA", "USZA", "USTM", "USHI", "USZI"}:
        return code  # 已经是THS格式
    if len(code) != 6:
        raise ValueError(f"无效的股票代码: {code}")
    return f"{market}{code}"


def convert_from_ths_code(ths_code: str) -> tuple[str, str]:
    """
    将THS格式代码转换为普通格式

    返回: (市场, 6位代码)
    """
    if len(ths_code) != 10:
        return ("", ths_code)
    return ths_code[:4], ths_code[4:]


# ── 快速测试入口 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("THSDK 服务层快速测试")
    print("=" * 60)

    with thsdk_service as svc:
        # 测试K线
        print("\n1. 测试K线查询...")
        result = svc.klines("USZA300033", count=5)
        print(f"   结果: {result}")

        # 测试搜索
        print("\n2. 测试证券搜索...")
        result = svc.search_symbols("同花顺")
        print(f"   结果: {result}")

        # 测试行情
        print("\n3. 测试A股行情...")
        result = svc.market_data_cn("USZA300033")
        print(f"   结果: {result}")

        # 测试补齐代码
        print("\n4. 测试代码补齐...")
        result = svc.complete_ths_code("300033")
        print(f"   结果: {result}")