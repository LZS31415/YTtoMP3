@echo off
setlocal
REM Note for editors: never put ( or ) inside an echo within an if-block in
REM this file. cmd treats ")" as the end of the block and the whole script
REM crashes instantly. That is exactly the bug the old version had.
echo ============================================
echo  YouTube / TikTok / Douyin MP3 Downloader - Setup
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto :install_python
echo [OK] Python found.

echo Installing / updating yt-dlp, its JavaScript runtime and browser impersonation. This can take a minute...
python -m pip install --upgrade pip --quiet
python -m pip install --upgrade -r "%~dp0requirements.txt"
if errorlevel 1 goto :pip_failed
echo [OK] yt-dlp and Deno installed.

where ffmpeg >nul 2>&1
if errorlevel 1 goto :install_ffmpeg
echo [OK] ffmpeg found.
goto :done

:install_python
echo Python not found. Installing it with winget...
winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
echo.
echo Python installed. Close this window and run setup.bat again.
goto :end

:install_ffmpeg
echo ffmpeg not found. Installing it with winget...
winget install Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :ffmpeg_failed
echo [OK] ffmpeg installed. Close this window and open download.bat in a NEW window.
goto :done

:ffmpeg_failed
echo.
echo Could not install ffmpeg automatically. Install it manually:
echo   1. Go to https://www.gyan.dev/ffmpeg/builds/
echo   2. Download ffmpeg-release-essentials.zip and extract it
echo   3. Add its bin folder to your PATH
goto :end

:pip_failed
echo.
echo ERROR: installing Python packages failed. Scroll up for the reason.
goto :end

:done
echo.
echo ============================================
echo  Setup complete. Run download.bat to use it.
echo ============================================

:end
echo.
pause
