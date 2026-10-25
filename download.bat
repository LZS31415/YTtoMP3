@echo off
chcp 65001 >nul
echo ============================================
echo  YouTube / TikTok / Douyin MP3 Downloader
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto :no_setup
python -c "import yt_dlp" >nul 2>&1
if errorlevel 1 goto :no_setup

REM Links are read by Python, not by "set /p": YouTube links contain "&" and
REM Douyin share text contains Chinese, both of which break cmd.
python "%~dp0downloader.py" %*
goto :end

:no_setup
echo Python or yt-dlp is missing. Run setup.bat first.

:end
echo.
pause
