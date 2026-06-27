@echo off
echo ============================================
echo  YouTube MP3 Downloader - Setup
echo ============================================
echo.

REM Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing via winget...
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo Python installed. Please close and reopen this window, then run setup.bat again.
    pause
    exit /b
)

echo Python found.
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install yt-dlp
echo Installing yt-dlp...
python -m pip install yt-dlp --upgrade --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install yt-dlp.
    pause
    exit /b 1
)

REM Check for Node.js (required by yt-dlp for YouTube extraction)
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Node.js not found. Installing via winget (required by yt-dlp)...
    winget install OpenJS.NodeJS --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo ERROR: Could not install Node.js. Please install it manually from https://nodejs.org
        pause
        exit /b 1
    )
    echo Node.js installed. Refreshing PATH...
    call refreshenv >nul 2>&1
    echo.
) else (
    echo Node.js found.
)

REM Check for ffmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ffmpeg not found. Installing via winget...
    winget install Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo Could not auto-install ffmpeg. Please install it manually:
        echo   1. Go to https://ffmpeg.org/download.html
        echo   2. Download a Windows build
        echo   3. Extract and add the bin folder to your PATH
        echo.
    ) else (
        echo ffmpeg installed successfully.
    )
) else (
    echo ffmpeg found.
)

echo.
echo ============================================
echo  Setup complete! Run download.bat to use.
echo ============================================
pause
