@echo off
echo ============================================
echo  YouTube Playlist/Video MP3 Downloader
echo ============================================
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please run setup.bat first.
    pause
    exit /b 1
)

REM Check for yt-dlp
python -c "import yt_dlp" >nul 2>&1
if %errorlevel% neq 0 (
    echo yt-dlp is not installed. Please run setup.bat first.
    pause
    exit /b 1
)

REM Run downloader - accept URL as argument or prompt interactively
if "%~1"=="" (
    set /p URL="Enter YouTube URL (video or playlist): "
) else (
    set URL=%~1
)

python "%~dp0downloader.py" "%URL%"

echo.
pause
