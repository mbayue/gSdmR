# Start both backend and frontend in parallel
Start-Process -NoNewWindow -FilePath "backend\venv\Scripts\uvicorn" -ArgumentList "main:app --reload --port 8000" -WorkingDirectory "backend"
Set-Location frontend
npm run dev
