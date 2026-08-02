@echo off
chcp 65001 >nul
cd /d "c:\Users\A\Desktop\sql_work\t_work\dsl-stock-screener"

echo ====== Git Remote ======
git remote -v

echo.
echo ====== Git Status ======
git status --short

echo.
echo ====== Recent Commits ======
git log --oneline -5

echo.
echo ====== Adding files... ======
git add app.py static/js/detail.js static/css/detail.css templates/detail.html templates/results.html templates/index.html

echo.
echo ====== Committing... ======
git commit -m "feat: 统一UI风格、修复K线图表样式、修复横向滚动条和时间轴拖动问题

- 统一 detail.js K线图颜色方案为主页红色主题
- 添加网格线、右侧价格轴标签、MA图例等视觉增强
- 重构 detail.css 使用CSS变量系统，红色主题与主页一致
- 移除 overflow:hidden 释放滚动条交互
- 修复时间轴滑块点击区域过小、事件丢失、光标反馈缺失问题
- 添加触摸事件支持移动端时间轴拖动"

echo.
echo ====== Pushing... ======
git push

echo.
echo ====== Done! ======
pause