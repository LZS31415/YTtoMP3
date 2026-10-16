@echo off
chcp 65001 >nul
echo ============================================
echo  YouTube Video / Playlist MP3 Downloader
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto :no_setup
python -c "import yt_dlp" >nul 2>&1
if errorlevel 1 goto :no_setup

REM The link is read by Python, not by "set /p": YouTube links contain "&",
REM which cmd treats as a command separator.
python "%~dp0downloader.py" %*
goto :end

:no_setup
echo Python or yt-dlp is missing. Run setup.bat first.

:end
echo.
pause
