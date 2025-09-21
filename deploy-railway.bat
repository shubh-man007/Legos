@echo off
echo 🚀 Railway Deployment Helper
echo ============================

echo ✅ Cloud Run files removed
echo ✅ Railway configuration added
echo.

echo 🎯 Next Steps:
echo ==============
echo.
echo 1. 📤 Push to GitHub:
echo    git add .
echo    git commit -m "Ready for Railway deployment"
echo    git push origin main
echo.
echo 2. 🖥️  Deploy Backend (Railway):
echo    • Go to: https://railway.app
echo    • Sign up with GitHub
echo    • Click "New Project" → "Deploy from GitHub repo"
echo    • Select your repository
echo    • Set root directory to: backend
echo    • Click "Deploy"
echo.
echo 3. 🗄️  Add Database:
echo    • In Railway project: "New" → "Database" → "PostgreSQL"
echo    • Copy connection string
echo    • Add to backend environment variables as DATABASE_URL
echo.
echo 4. 🌐 Deploy Frontend (Vercel):
echo    • Go to: https://vercel.com
echo    • Sign up with GitHub
echo    • "New Project" → Import from GitHub
echo    • Select your repository
echo    • Set root directory to: frontend
echo    • Add environment variable: VITE_API_BASE_URL=https://your-backend-url.railway.app
echo    • Click "Deploy"
echo.
echo 5. ⚙️  Add Environment Variables:
echo    Backend (Railway):
echo    - DATABASE_URL (from PostgreSQL service)
echo    - GCS_BUCKET=legos-ai-storage
echo    - GOOGLE_APPLICATION_CREDENTIALS (your JSON key)
echo    - PORT=8000
echo.
echo 📚 Full guide: See RAILWAY_DEPLOYMENT.md
echo.
echo 🎉 Ready to deploy in 5 minutes!
pause
