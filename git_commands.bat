@echo off
cd /d "c:\Users\A\Desktop\sql_work\t_work\dsl-stock-screener"
echo === git remote -v ===
git remote -v
echo.
echo === git status ===
git status --short
echo.
echo === git log -3 ===
git log --oneline -3
echo.
echo Done.
pause