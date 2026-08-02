"""
thsdk_routes.py — THSDK 接口 Flask 路由集成
=============================================
在 app.py 基础上添加 THSDK 数据接口路由，提供：
  - /api/thsdk/klines        — K线数据
  - /api/thsdk/market_data   — A股实时行情
  - /api/thsdk/search        — 证券搜索
  - /api/thsdk/complete_code — 代码补齐
  - /api/thsdk/industry      — 行业列表
  - /api/thsdk/concept       — 概念列表
  - /api/thsdk/block_constituents — 板块成分股
  - /api/thsdk/news          — 新闻资讯
  - /api/thsdk/ipo           — IPO信息
  - /api/thsdk/depth         — 五档行情
  - /api/thsdk/big_order_flow — 大单资金流向
  - /api/thsdk/wencai        — 问财自然语言查询
  - /api/thsdk/health        — 连接状态检查
"""

import logging
import traceback
from datetime import datetime

from flask import Blueprint, jsonify, request

from thsdk_service import thsdk_service, THSDKResult, convert_to_ths_code

logger = logging.getLogger("thsdk_routes")

# ──────────────────────────────────────────────────────────────────
# 创建蓝图
# ──────────────────────────────────────────────────────────────────
thsdk_bp = Blueprint("thsdk", __name__, url_prefix="/api/thsdk")


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────
def _response(result: THSDKResult) -> tuple:
    """将 THSDKResult 封装为 Flask JSON 响应"""
    if result.success:
        return jsonify({
            "success": True,
            "data": result.data,
            "count": len(result.data) if isinstance(result.data, (list, dict)) else None,
        })
    else:
        return jsonify({
            "success": False,
            "error": result.error,
        }), 500


def _safe_call(func, *args, **kwargs) -> tuple:
    """安全调用 thsdk 接口，处理异常"""
    try:
        result = func(*args, **kwargs)
        return _response(result)
    except Exception as e:
        logger.error(f"接口调用异常: {e}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": f"服务异常: {str(e)}",
        }), 500


# ──────────────────────────────────────────────────────────────────
# 健康检查
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/health", methods=["GET"])
def health():
    """检查 THSDK 连接状态"""
    try:
        result = thsdk_service.connect()
        if result.success:
            return jsonify({"success": True, "status": "connected", "message": "THSDK 服务正常"})
        else:
            return jsonify({"success": False, "status": "disconnected", "message": result.error})
    except Exception as e:
        logger.error(f"健康检查异常: {e}")
        return jsonify({"success": False, "status": "disconnected", "message": f"THSDK 不可用: {str(e)}"})


# ──────────────────────────────────────────────────────────────────
# K线数据
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/klines", methods=["GET"])
def api_thsdk_klines():
    """获取K线数据"""
    code = request.args.get("code", "")
    count = request.args.get("count", 180, type=int)
    interval = request.args.get("interval", "day")
    adjust = request.args.get("adjust", "")

    if not code:
        return jsonify({"success": False, "error": "缺少参数 code"}), 400

    # 自动补齐THS格式
    if len(code) == 6:
        if code.startswith(("60", "68")):
            code = convert_to_ths_code(code, "USHA")
        elif code.startswith(("00", "30")):
            code = convert_to_ths_code(code, "USZA")
        elif code.startswith(("8", "4")):
            code = convert_to_ths_code(code, "USTM")
        else:
            code = convert_to_ths_code(code, "USZA")

    return _safe_call(thsdk_service.klines, code, count=count, interval=interval, adjust=adjust)


# ──────────────────────────────────────────────────────────────────
# A股实时行情
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/market_data", methods=["GET"])
def api_thsdk_market_data():
    """获取A股实时行情"""
    code = request.args.get("code", "")
    query_key = request.args.get("query_key", "基础数据")

    if not code:
        return jsonify({"success": False, "error": "缺少参数 code"}), 400

    return _safe_call(thsdk_service.market_data_cn, code, query_key=query_key)


# ──────────────────────────────────────────────────────────────────
# 证券搜索
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/search", methods=["GET"])
def api_thsdk_search():
    """模糊搜索证券"""
    pattern = request.args.get("pattern", "")
    market = request.args.get("market", "")

    if not pattern:
        return jsonify({"success": False, "error": "缺少参数 pattern"}), 400

    return _safe_call(thsdk_service.search_symbols, pattern, market)


# ──────────────────────────────────────────────────────────────────
# 代码补齐
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/complete_code", methods=["GET", "POST"])
def api_thsdk_complete_code():
    """补齐证券代码为THS格式"""
    if request.method == "POST":
        data = request.get_json()
        code = data.get("code", "")
    else:
        code = request.args.get("code", "")

    if not code:
        return jsonify({"success": False, "error": "缺少参数 code"}), 400

    if isinstance(code, str):
        code = [c.strip() for c in code.split(",") if c.strip()]
        if len(code) == 1:
            code = code[0]

    return _safe_call(thsdk_service.complete_ths_code, code)


# ──────────────────────────────────────────────────────────────────
# 行业/概念列表
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/industry", methods=["GET"])
def api_thsdk_industry():
    """获取同花顺行业分类列表"""
    return _safe_call(thsdk_service.ths_industry)


@thsdk_bp.route("/concept", methods=["GET"])
def api_thsdk_concept():
    """获取同花顺概念分类列表"""
    return _safe_call(thsdk_service.ths_concept)


# ──────────────────────────────────────────────────────────────────
# 板块成分股
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/block_constituents", methods=["GET"])
def api_thsdk_block_constituents():
    """获取板块成分股"""
    link_code = request.args.get("link_code", "")
    if not link_code:
        return jsonify({"success": False, "error": "缺少参数 link_code"}), 400
    return _safe_call(thsdk_service.block_constituents, link_code)


# ──────────────────────────────────────────────────────────────────
# 新闻资讯
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/news", methods=["GET"])
def api_thsdk_news():
    """获取新闻资讯"""
    text_id = request.args.get("text_id", "0x3814")
    code = request.args.get("code", "1A0001")
    market = request.args.get("market", "USHI")

    # 转换十六进制字符串
    if isinstance(text_id, str) and text_id.startswith("0x"):
        text_id = int(text_id, 16)
    else:
        text_id = int(text_id)

    return _safe_call(thsdk_service.news, text_id=text_id, code=code, market=market)


# ──────────────────────────────────────────────────────────────────
# IPO信息
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/ipo", methods=["GET"])
def api_thsdk_ipo():
    """获取IPO信息"""
    ipo_type = request.args.get("type", "today")  # today 或 wait
    if ipo_type == "wait":
        return _safe_call(thsdk_service.ipo_wait)
    return _safe_call(thsdk_service.ipo_today)


# ──────────────────────────────────────────────────────────────────
# 五档行情
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/depth", methods=["GET"])
def api_thsdk_depth():
    """获取五档行情"""
    code = request.args.get("code", "")
    if not code:
        return jsonify({"success": False, "error": "缺少参数 code"}), 400
    return _safe_call(thsdk_service.depth, code)


# ──────────────────────────────────────────────────────────────────
# 大单资金流向
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/big_order_flow", methods=["GET"])
def api_thsdk_big_order_flow():
    """获取大单资金流向数据"""
    code = request.args.get("code", "")
    if not code:
        return jsonify({"success": False, "error": "缺少参数 code"}), 400
    return _safe_call(thsdk_service.big_order_flow, code)


# ──────────────────────────────────────────────────────────────────
# 问财自然语言查询
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/wencai", methods=["POST"])
def api_thsdk_wencai():
    """问财自然语言查询"""
    data = request.get_json()
    condition = data.get("condition", "")
    if not condition:
        return jsonify({"success": False, "error": "缺少参数 condition"}), 400
    return _safe_call(thsdk_service.wencai_nlp, condition)


# ──────────────────────────────────────────────────────────────────
# 批量行情查询
# ──────────────────────────────────────────────────────────────────
@thsdk_bp.route("/batch_market_data", methods=["POST"])
def api_thsdk_batch_market():
    """批量查询A股行情"""
    data = request.get_json()
    codes = data.get("codes", [])
    if not codes or not isinstance(codes, list):
        return jsonify({"success": False, "error": "缺少参数 codes（数组）"}), 400

    results = thsdk_service.batch_market_data(codes)
    return jsonify({
        "success": True,
        "results": [
            {
                "success": r.success,
                "data": r.data,
                "error": r.error,
            }
            for r in results
        ],
    })


# ──────────────────────────────────────────────────────────────────
# 注册蓝图（在 app.py 中调用此函数）
# ──────────────────────────────────────────────────────────────────
def register_thsdk_routes(app):
    """在 Flask 应用中注册 THSDK 路由"""
    app.register_blueprint(thsdk_bp)
    logger.info("✅ THSDK 路由已注册")
    return app