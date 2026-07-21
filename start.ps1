# Start backend (auto-reload) and frontend (HMR) together
Start-Process -NoNewWindow -FilePath "backend\venv\Scripts\uvicorn" -ArgumentList "main:app --reload --port 8000" -WorkingDirectory "backend"
Set-Location frontend
bun dev
