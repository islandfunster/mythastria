@echo off
setlocal
cd /d "%~dp0"
echo Mythastria - the OLD training table (Rust WebAssembly engine, deprecated 2026-10-20)
echo For real play use Start_Mythastria.bat: Python is the rules authority.
echo Open http://127.0.0.1:8769/training.html in your browser.
echo Press Ctrl+C in this window to stop the local server.
start "" "http://127.0.0.1:8769/training.html"
py -3 -m http.server 8769 --bind 127.0.0.1 --directory "%~dp0dist"
if errorlevel 1 pause
endlocal
