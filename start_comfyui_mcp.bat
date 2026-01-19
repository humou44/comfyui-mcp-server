@echo off
echo ========================================
echo   ComfyUI + MCP Server Launcher
echo ========================================

echo.
echo [1/2] Starting ComfyUI...
start "ComfyUI" cmd /c "cd /d D:\stable-diffusion\ComfyUI && python main.py --listen 127.0.0.1 --port 8188"

echo Waiting for ComfyUI to initialize...
timeout /t 10 /nobreak > nul

echo.
echo [2/2] Starting MCP Server...
cd /d C:\Users\1\.gemini\antigravity\scratch\comfyui-mcp-server
python server.py
