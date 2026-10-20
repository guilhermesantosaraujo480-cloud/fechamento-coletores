@echo off
REM Liga o agente da bipagem. Deixe esta janela aberta enquanto o site estiver mandando lotes.
cd /d "%~dp0"
python -m bipagem.agente
pause
