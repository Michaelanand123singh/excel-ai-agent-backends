@echo off
echo 🚀 Starting Elasticsearch for Ultra-Fast Bulk Search
echo ==================================================

echo 📦 Checking Docker Desktop...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Desktop is not running!
    echo Please start Docker Desktop first, then run this script again.
    pause
    exit /b 1
)

echo ✅ Docker Desktop is running

echo 🐳 Starting Elasticsearch container...
docker run -d --name elasticsearch-bulk-search -p 9200:9200 -p 9300:9300 -e "discovery.type=single-node" -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" elasticsearch:8.11.0

if %errorlevel% neq 0 (
    echo ❌ Failed to start Elasticsearch container
    echo The container might already be running. Checking...
    docker ps --filter name=elasticsearch-bulk-search
    pause
    exit /b 1
)

echo ✅ Elasticsearch container started successfully!

echo ⏳ Waiting for Elasticsearch to be ready...
timeout /t 30 /nobreak >nul

echo 🔍 Testing Elasticsearch connection...
curl -s http://localhost:9200 >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Elasticsearch is starting up, please wait a bit more...
    echo You can test it manually with: curl http://localhost:9200
) else (
    echo ✅ Elasticsearch is running and ready!
    echo 📊 Elasticsearch is available at: http://localhost:9200
)

echo.
echo 🎉 Setup Complete!
echo ==================
echo Next steps:
echo 1. Start your backend server: python run.py
echo 2. Sync data: curl -X POST "http://localhost:8000/api/v1/query-elasticsearch/sync-all-to-elasticsearch"
echo 3. Test performance: python test_bulk_performance.py
echo.
pause

