Start FastAPI (Backend)
Execute:
cd C:\Users\user\finguard\backend
Then:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
//
Start React (Frontend)
Open a third terminal in VS Code.

Execute:
cd C:\Users\user\finguard\frontend

Then:
npm.cmd run devcd
//
Verify Everything Is Connected
Open another PowerShell terminal and execute:
Invoke-RestMethod -Uri "http://localhost:5173/api/health"

Expected:
status
------
ok