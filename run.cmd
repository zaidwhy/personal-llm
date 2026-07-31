@echo off
REM One-click run parity (PROJECT-GENESIS.md Tier 6 item 43): starts the chat UI locally
REM and opens the browser, mirroring this project's "chat UI" (default) action in
REM jarvis-launcher's jarvis.config.json so the launcher and this repo never drift.
REM That action sets no env var, so this script does not invent one either.
setlocal

set "ROOT=%~dp0"

start "Personal LLM - Chat" /D "%ROOT%" cmd /k "venv\Scripts\python -m streamlit run src/personal_llm/interfaces/app.py"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(30); while((Get-Date) -lt $deadline) { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8501' -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process 'http://localhost:8501'"

endlocal
