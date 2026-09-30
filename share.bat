@echo off
REM Start the ground station and share it over a free Cloudflare tunnel.
REM Prints a public https://....trycloudflare.com link (new each run). Close this window to stop sharing.
cd /d "%~dp0"
set CF=cloudflared
where cloudflared >nul 2>nul || set CF=.tools\cloudflared.exe
if "%CF%"==".tools\cloudflared.exe" if not exist .tools\cloudflared.exe (
  echo ==^> Downloading cloudflared
  if not exist .tools mkdir .tools
  curl -sSL -o .tools\cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe || exit /b 1
)
powershell -NoProfile -Command "try { Invoke-WebRequest http://localhost:8000/api/health -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo ==^> Starting ground station in a new window
  start "Ground Station" cmd /k run.bat
  powershell -NoProfile -Command "for ($i=0; $i -lt 180; $i++) { try { Invoke-WebRequest http://localhost:8000/api/health -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep 1 } }; exit 1"
  if errorlevel 1 ( echo Ground station did not start, check the other window & exit /b 1 )
)
echo.
echo ==^> Opening tunnel. Share the https://....trycloudflare.com link printed below.
echo     Testers sign in with their own account. Ctrl+C or close this window to stop sharing.
echo.
"%CF%" tunnel --no-autoupdate --url http://localhost:8000
