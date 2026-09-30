@echo off
REM Windows one-command start. Serves the dashboard on http://localhost:8000
cd /d "%~dp0"
if not exist backend\.venv (
  echo ==^> Creating Python virtualenv
  python -m venv backend\.venv
)
backend\.venv\Scripts\pip install -q -r backend\requirements.txt
if not exist frontend\node_modules (
  pushd frontend & call npm install --no-audit --no-fund & popd
)
if not exist frontend\dist\index.html (
  pushd frontend & call npm run build & popd
)
echo ==^> Ground station running at http://localhost:8000
cd backend
.venv\Scripts\uvicorn groundstation.main:app --host 0.0.0.0 --port 8000
