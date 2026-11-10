1.Dans un terminal PowerShell à la racine de finguard :

PowerShell
docker compose up -d
//
2. Démarrer le Backend FastAPI
Dans le même terminal (ou un nouvel onglet) :

PowerShell
$env:PYTHONPATH="backend"
$env:DATABASE_URL="postgresql+psycopg://finguard:finguard@localhost:5432/finguard"
$env:FINGUARD_JWT_SECRET="local-dev-secret-key-must-be-at-least-32-chars-long"
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
Le backend sera accessible sur http://127.0.0.1:8000.
Tu peux déjà tester les routes directement sur la documentation interactive Swagger : http://127.0.0.1:8000/docs.
//
3. Démarrer le Dashboard Frontend React
Ouvre un deuxième terminal PowerShell dans VS Code (Terminal > New Terminal) :

PowerShell
npm --prefix frontend run dev
Vite affichera l'URL locale, généralement http://localhost:5173