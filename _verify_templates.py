# -*- coding: utf-8 -*-
"""临时验证脚本：确认 index/detail/fundamental 模板可正常渲染，并检查关键元素。"""
import sys
sys.path.insert(0, r'c:\Users\A\Desktop\sql_work\work')

try:
    from app import app
except Exception as e:
    print("IMPORT_FAIL:", repr(e))
    sys.exit(1)

client = app.test_client()

checks = [
    ("/", ["选股指令", "btnDslHelp", "btnDslRun", "dslHelpPanel", "dslError", "指标筛选"]),
    ("/detail?code=600519&name=贵州茅台&type=股票&exchange=上证主板", ["证券详情", "btn-fundamental", "canvas-kline"]),
    ("/fundamental?code=600519&name=贵州茅台&type=股票&exchange=上证主板", ["基本面信息", "financial-table", "tab-bar"]),
]

ok = True
for path, subs in checks:
    resp = client.get(path)
    status = resp.status_code
    body = resp.data.decode("utf-8", errors="replace")
    missing = [s for s in subs if s not in body]
    present_dangling = []
    # 确认已移除的辅助筛选元素不存在
    if path == "/":
        for bad in ["辅助筛选", "riskOpts", "nameKw", "renderRisk", "RISK_OPTIONS", "窗口2"]:
            if bad in body:
                present_dangling.append(bad)
    print(f"[{status}] {path}")
    if missing:
        print("   缺少:", missing); ok = False
    if present_dangling:
        print("   残留(应已移除):", present_dangling); ok = False
    # 确认无旧蓝色主题残留
    if path == "/" and ("#007bff" in body or "var(--green)" in body):
        print("   残留旧主题色"); ok = False

print("OK" if ok else "FAIL")
