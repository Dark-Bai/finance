"""
test_thsdk_integration.py — THSDK 集成单元测试
===============================================
测试内容:
  1. thsdk_service 模块导入与基础功能
  2. 工具函数（convert_to_ths_code / convert_from_ths_code）
  3. 缓存装饰器功能
  4. Flask 路由端点（使用 test_client）
  5. THSDK 实际接口调用（需要连接服务器）

运行方式:
  python -m pytest tests/test_thsdk_integration.py -v
  python -m unittest tests.test_thsdk_integration -v
  
  仅运行单元测试（跳过需要实际连接的测试）:
  python -m pytest tests/test_thsdk_integration.py -v -k "not integration"
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────────────────────────────────────────────
# 单元测试 — 工具函数
# ──────────────────────────────────────────────────────────────────
class TestConvertFunctions(unittest.TestCase):
    """测试代码转换工具函数"""

    def setUp(self):
        from thsdk_service import convert_to_ths_code, convert_from_ths_code
        self.convert_to = convert_to_ths_code
        self.convert_from = convert_from_ths_code

    def test_convert_to_ths_code_shenzhen(self):
        """深市代码转换"""
        result = self.convert_to("300033", "USZA")
        self.assertEqual(result, "USZA300033")

    def test_convert_to_ths_code_shanghai(self):
        """沪市代码转换"""
        result = self.convert_to("600519", "USHA")
        self.assertEqual(result, "USHA600519")

    def test_convert_to_ths_code_already_format(self):
        """已为THS格式不应重复转换"""
        result = self.convert_to("USZA300033", "USZA")
        self.assertEqual(result, "USZA300033")

    def test_convert_to_ths_code_invalid(self):
        """无效代码应抛出异常"""
        with self.assertRaises(ValueError):
            self.convert_to("123", "USZA")

    def test_convert_from_ths_code(self):
        """THS格式转普通格式"""
        market, code = self.convert_from("USZA300033")
        self.assertEqual(market, "USZA")
        self.assertEqual(code, "300033")


# ──────────────────────────────────────────────────────────────────
# 单元测试 — THSDKResult 封装
# ──────────────────────────────────────────────────────────────────
class TestTHSDKResult(unittest.TestCase):
    """测试 THSDKResult 封装类"""

    def test_success_result(self):
        from thsdk_service import THSDKResult
        result = THSDKResult(True, data=[1, 2, 3])
        self.assertTrue(result)
        self.assertEqual(len(result.data), 3)
        self.assertEqual(result.error, "")

    def test_failure_result(self):
        from thsdk_service import THSDKResult
        result = THSDKResult(False, error="连接失败")
        self.assertFalse(result)
        self.assertIsNone(result.data)
        self.assertEqual(result.error, "连接失败")

    def test_bool_conversion(self):
        from thsdk_service import THSDKResult
        self.assertTrue(THSDKResult(True))
        self.assertFalse(THSDKResult(False))


# ──────────────────────────────────────────────────────────────────
# 单元测试 — 缓存装饰器
# ──────────────────────────────────────────────────────────────────
class TestCacheDecorator(unittest.TestCase):
    """测试缓存装饰器功能"""

    def test_cache_hits(self):
        from thsdk_service import cached

        call_count = 0

        @cached(ttl=2)
        def get_data(key):
            nonlocal call_count
            call_count += 1
            return {"key": key, "value": 42}

        # 第一次调用，应执行函数
        result1 = get_data("test")
        self.assertEqual(call_count, 1)
        self.assertEqual(result1["value"], 42)

        # 第二次调用相同参数，应命中缓存
        result2 = get_data("test")
        self.assertEqual(call_count, 1)  # 未增加
        self.assertEqual(result2, result1)

        # 不同参数，应重新执行
        result3 = get_data("other")
        self.assertEqual(call_count, 2)

    def test_cache_expiry(self):
        from thsdk_service import cached

        call_count = 0

        @cached(ttl=1)  # 1秒过期
        def get_data():
            nonlocal call_count
            call_count += 1
            return time.time()

        # 第一次调用
        result1 = get_data()
        self.assertEqual(call_count, 1)

        # 等待缓存过期
        time.sleep(1.1)

        # 应重新执行
        result2 = get_data()
        self.assertEqual(call_count, 2)
        self.assertNotEqual(result1, result2)


# ──────────────────────────────────────────────────────────────────
# 单元测试 — 重试装饰器
# ──────────────────────────────────────────────────────────────────
class TestRetryDecorator(unittest.TestCase):
    """测试重试装饰器"""

    @patch("thsdk_service.logger")
    def test_retry_success_after_failure(self, mock_logger):
        from thsdk_service import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=3, delay=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("临时错误")
            return "success"

        result = flaky_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)

    @patch("thsdk_service.logger")
    def test_retry_exhausted(self, mock_logger):
        from thsdk_service import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=2, delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("持续错误")

        with self.assertRaises(ValueError):
            always_fails()
        self.assertEqual(call_count, 2)


# ──────────────────────────────────────────────────────────────────
# 单元测试 — THSDKService 方法（Mock 模式）
# ──────────────────────────────────────────────────────────────────
class TestTHSDKServiceMocked(unittest.TestCase):
    """使用 Mock 测试 THSDKService 各方法"""

    def setUp(self):
        from thsdk_service import THSDKService, THSDKResult
        self.service = THSDKService()

    @patch("thsdk_service.THSDKService._ensure_connected")
    def test_klines_call(self, mock_connect):
        """测试 klines 方法参数传递"""
        mock_ths = MagicMock()

        # 模拟 Response 返回
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.data = [{"日期": "20240101", "开盘": 100}]
        mock_ths.klines.return_value = mock_response
        mock_connect.return_value = mock_ths

        result = self.service.klines("USZA300033", count=100)
        self.assertTrue(result.success)
        mock_ths.klines.assert_called_once_with(
            "USZA300033", start_time=None, end_time=None,
            adjust="", interval="day", count=100
        )

    @patch("thsdk_service.THSDKService._ensure_connected")
    def test_search_symbols(self, mock_connect):
        """测试 search_symbols 方法"""
        mock_ths = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.data = [{"代码": "300033", "名称": "同花顺"}]
        mock_ths.search_symbols.return_value = mock_response
        mock_connect.return_value = mock_ths

        result = self.service.search_symbols("同花顺")
        self.assertTrue(result.success)
        mock_ths.search_symbols.assert_called_once_with("同花顺", "")

    @patch("thsdk_service.THSDKService._ensure_connected")
    def test_connect_failure(self, mock_connect):
        """测试连接失败场景"""
        mock_connect.side_effect = ConnectionError("无法连接")

        from thsdk_service import THSDKResult
        result = self.service.klines("USZA300033", count=5)
        self.assertFalse(result.success)
        self.assertIn("无法连接", result.error)

    @patch("thsdk_service.THSDKService._ensure_connected")
    def test_method_not_found(self, mock_connect):
        """测试方法不存在场景"""
        mock_ths = MagicMock()
        # 模拟方法不存在
        del mock_ths.nonexistent_method
        mock_connect.return_value = mock_ths

        from thsdk_service import THSDKResult
        result = self.service._call("nonexistent_method")
        self.assertFalse(result.success)
        self.assertIn("不存在", result.error)


# ──────────────────────────────────────────────────────────────────
# 集成测试 — Flask 路由
# ──────────────────────────────────────────────────────────────────
class TestFlaskRoutes(unittest.TestCase):
    """测试 Flask 路由端点（使用 test_client）"""

    @classmethod
    def setUpClass(cls):
        """创建 Flask 测试应用"""
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True

        # 注册 THSDK 蓝图
        from thsdk_routes import thsdk_bp
        app.register_blueprint(thsdk_bp)
        cls.client = app.test_client()

    def test_health_endpoint(self):
        """测试健康检查端点"""
        response = self.client.get("/api/thsdk/health")
        data = response.get_json()
        self.assertIn("success", data)
        self.assertIn("status", data)

    def test_klines_missing_code(self):
        """测试缺少 code 参数"""
        response = self.client.get("/api/thsdk/klines")
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])

    def test_search_missing_pattern(self):
        """测试缺少 pattern 参数"""
        response = self.client.get("/api/thsdk/search")
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])

    def test_klines_with_code(self):
        """测试带 code 参数的 K线请求"""
        response = self.client.get("/api/thsdk/klines?code=300033&count=5")
        # 可能因为没有实际连接而失败，但不应是 400
        self.assertNotEqual(response.status_code, 400)

    def test_ipo_endpoint(self):
        """测试 IPO 端点"""
        response = self.client.get("/api/thsdk/ipo?type=today")
        self.assertIn(response.status_code, [200, 500])

    def test_ipo_wait_endpoint(self):
        """测试待发行IPO端点"""
        response = self.client.get("/api/thsdk/ipo?type=wait")
        self.assertIn(response.status_code, [200, 500])

    def test_news_endpoint(self):
        """测试新闻端点"""
        response = self.client.get("/api/thsdk/news")
        self.assertIn(response.status_code, [200, 500])

    def test_industry_endpoint(self):
        """测试行业列表端点"""
        response = self.client.get("/api/thsdk/industry")
        self.assertIn(response.status_code, [200, 500])

    def test_concept_endpoint(self):
        """测试概念列表端点"""
        response = self.client.get("/api/thsdk/concept")
        self.assertIn(response.status_code, [200, 500])

    def test_complete_code_endpoint(self):
        """测试代码补齐端点"""
        response = self.client.get("/api/thsdk/complete_code?code=300033")
        self.assertIn(response.status_code, [200, 500])

    def test_market_data_endpoint(self):
        """测试行情数据端点"""
        response = self.client.get("/api/thsdk/market_data?code=USZA300033")
        self.assertIn(response.status_code, [200, 500])

    def test_depth_endpoint(self):
        """测试五档行情端点"""
        response = self.client.get("/api/thsdk/depth?code=USZA300033")
        self.assertIn(response.status_code, [200, 500])

    def test_big_order_flow_endpoint(self):
        """测试大单资金流向端点"""
        response = self.client.get("/api/thsdk/big_order_flow?code=USZA300033")
        self.assertIn(response.status_code, [200, 500])

    def test_batch_market_data_endpoint(self):
        """测试批量行情端点"""
        response = self.client.post(
            "/api/thsdk/batch_market_data",
            data=json.dumps({"codes": ["USZA300033", "USHA600519"]}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, [200, 500])

    def test_wencai_missing_condition(self):
        """测试问财缺少 condition 参数"""
        response = self.client.post(
            "/api/thsdk/wencai",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_block_constituents_missing_link_code(self):
        """测试板块成分股缺少 link_code 参数"""
        response = self.client.get("/api/thsdk/block_constituents")
        self.assertEqual(response.status_code, 400)


# ──────────────────────────────────────────────────────────────────
# 集成测试 — 实际连接（需要THSDK服务器可用）
# ──────────────────────────────────────────────────────────────────
@unittest.skipIf(
    os.environ.get("SKIP_INTEGRATION_TESTS", "1") == "1",
    "跳过需要实际连接的集成测试（设置 SKIP_INTEGRATION_TESTS=0 启用）",
)
class TestTHSDKIntegration(unittest.TestCase):
    """需要实际连接 THSDK 服务器的集成测试"""

    @classmethod
    def setUpClass(cls):
        from thsdk_service import thsdk_service
        cls.service = thsdk_service
        result = cls.service.connect()
        if not result.success:
            raise unittest.SkipTest(f"无法连接 THSDK 服务器: {result.error}")

    @classmethod
    def tearDownClass(cls):
        cls.service.disconnect()

    def test_connect(self):
        """测试连接"""
        result = self.service.connect()
        self.assertTrue(result.success)

    def test_klines(self):
        """测试K线数据查询"""
        result = self.service.klines("USZA300033", count=5)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertGreater(len(result.data), 0)

    def test_search_symbols(self):
        """测试证券搜索"""
        result = self.service.search_symbols("同花顺")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_market_data_cn(self):
        """测试A股行情"""
        result = self.service.market_data_cn("USZA300033")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_complete_ths_code(self):
        """测试代码补齐"""
        result = self.service.complete_ths_code("300033")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_ths_industry(self):
        """测试行业列表"""
        result = self.service.ths_industry()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_ths_concept(self):
        """测试概念列表"""
        result = self.service.ths_concept()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_depth(self):
        """测试五档行情"""
        result = self.service.depth("USZA300033")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)

    def test_ipo_today(self):
        """测试今日IPO"""
        result = self.service.ipo_today()
        self.assertTrue(result.success)

    def test_news(self):
        """测试新闻"""
        result = self.service.news()
        self.assertTrue(result.success)

    def test_klines_different_intervals(self):
        """测试不同周期的K线"""
        intervals = ["day", "week", "month"]
        for interval in intervals:
            result = self.service.klines("USZA300033", count=5, interval=interval)
            self.assertTrue(result.success, f"周期 {interval} 失败")

    def test_klines_with_adjust(self):
        """测试复权K线"""
        result = self.service.klines("USZA300033", count=5, adjust="forward")
        self.assertTrue(result.success)

    def test_batch_market_data(self):
        """测试批量行情"""
        codes = ["USZA300033", "USHA600519"]
        results = self.service.batch_market_data(codes)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r.success)


# ──────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)