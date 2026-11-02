@echo off
setlocal
rem 2026-10-19 (GM): Mythastria: play on this one PC. Starts the simulator service with the Mythastria pages and opens Play
rem live in the browser (2026-10-20: Python live play is the default; it starts empty until a fight is chosen).
rem GM 2026-10-25 ("make Mythastria start from wherever it is cloned"): the folders are found from this file's own place:
rem   the engine:     this file's folder
rem   the pages:      ..\isles-table\dist        (the layout of the mythastria-table repository: engine\ beside isles-table\)
rem   the adventures: ..\adventures              (adventure packs, if there are any)
rem A local_settings.cmd beside this file (never shared: .gitignore) may set TABLE, PACKS, PORT, PLAYERS_PORT and
rem PLAYERS_HOST (a public name a tunnel gives the players' door). Each line of this window says the full folder it uses.
title Mythastria

set "ENGINE=%~dp0"
set "ENGINE=%ENGINE:~0,-1%"
if not defined TABLE set "TABLE=%ENGINE%\..\isles-table\dist"
if not defined PACKS set "PACKS=%ENGINE%\..\adventures"
if not defined PORT set "PORT=8772"
if not defined PLAYERS_PORT set "PLAYERS_PORT=8782"
if exist "%ENGINE%\local_settings.cmd" call "%ENGINE%\local_settings.cmd"
for %%I in ("%TABLE%") do set "TABLE=%%~fI"
for %%I in ("%PACKS%") do set "PACKS=%%~fI"

if not exist "%ENGINE%\tools\sim_service.py" goto no_service
if not exist "%TABLE%\stage.html" goto no_table
rem RELEASE-01: a downloaded release carries its own Python in ..\python; a clone uses the Python on this PC
set "BUNDLED=%ENGINE%\..\python\python.exe"
set "RUN=py -3"
if exist "%BUNDLED%" set RUN="%BUNDLED%"
if exist "%BUNDLED%" goto have_python
where py >nul 2>nul
if errorlevel 1 goto no_python
:have_python
netstat -ano -p TCP | "%SystemRoot%\System32\findstr.exe" /R /C:"127.0.0.1:%PORT% .*LISTENING" >nul
if not errorlevel 1 goto already_running

set "PACKARG="
if exist "%PACKS%\" set PACKARG=--adventure-packs "%PACKS%"
set "HOSTARG="
if defined PLAYERS_HOST set "HOSTARG=--players-host %PLAYERS_HOST%"

cd /d "%ENGINE%"
echo.
echo  MYTHASTRIA
echo.
echo  Play live (opens first): http://127.0.0.1:%PORT%/play.html
echo  The Stage:            http://127.0.0.1:%PORT%/stage.html
echo  Simulator fights:     http://127.0.0.1:%PORT%/replay.html
echo  Play an adventure:    http://127.0.0.1:%PORT%/adventure.html  (the big button on the start page)
if defined PACKARG echo  Adventures:           %PACKS%
if not defined PACKARG echo  Adventures:           none found in %PACKS%
echo  Chat and dice: the Chat button on every page
if defined PLAYERS_HOST echo  Players' door:         https://%PLAYERS_HOST%/  (players anywhere, through your tunnel)
echo  Players' door here:    http://127.0.0.1:%PLAYERS_PORT%/  (players ask to join; you let them in on Play live, Players...)
echo  Engine:               %ENGINE%
echo  Pages:                %TABLE%
echo  Leave this window open while you play. Close it (or Ctrl+C) to stop.
echo  Everything below is also saved in %ENGINE%\logs
echo.
if not defined MYTHASTRIA_NO_BROWSER start "" "http://127.0.0.1:%PORT%/"
%RUN% "%ENGINE%\tools\run_logged.py" "%ENGINE%\tools\sim_service.py" --table "%TABLE%" %PACKARG% --port %PORT% --players-port %PLAYERS_PORT% %HOSTARG%
set "SIM_EXIT=%ERRORLEVEL%"
echo.
echo Simulator service stopped. Exit code: %SIM_EXIT%
if not defined MYTHASTRIA_NO_BROWSER pause
exit /b %SIM_EXIT%

:already_running
echo Mythastria is already running in another window (port %PORT% is in use).
if not defined MYTHASTRIA_NO_BROWSER start "" "http://127.0.0.1:%PORT%/"
pause
exit /b 0

:no_service
echo Not found: "%ENGINE%\tools\sim_service.py"
pause
exit /b 1

:no_table
echo Not found: "%TABLE%\stage.html"
echo The pages are expected in isles-table\dist next to the engine folder (a clone of mythastria-table has both),
echo or set TABLE in "%ENGINE%\local_settings.cmd".
pause
exit /b 1

:no_python
echo Python 3 (py) was not found. Install Python 3.12 or newer from python.org (tick "py launcher"), then try again.
pause
exit /b 1

