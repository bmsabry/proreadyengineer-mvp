#!/bin/bash
# Deployment script for ProReadyEngineer MVP
# Run this script to push code to GitHub

echo "🚀 ProReadyEngineer Deployment Script"
echo "======================================"
echo ""

# Check if git is configured
if [ -z "$(git config --global user.email)" ]; then
    echo "⚠️  Git user email not set"
    read -p "Enter your GitHub email: " GIT_EMAIL
    git config --global user.email "$GIT_EMAIL"
fi

if [ -z "$(git config --global user.name)" ]; then
    echo "⚠️  Git user name not set"
    read -p "Enter your GitHub username: " GIT_NAME
    git config --global user.name "$GIT_NAME"
fi

# Get GitHub credentials
echo ""
echo "GitHub Credentials Required"
echo "---------------------------"
read -p "Enter your GitHub username: " GITHUB_USER
read -s -p "Enter your GitHub Personal Access Token: " GITHUB_TOKEN
echo ""

# Repository name
REPO_NAME="proreadyengineer-mvp"

# Create repository via API
echo ""
echo "📦 Creating GitHub repository..."
RESPONSE=$(curl -s -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"$REPO_NAME\",\"description\":\"ProReadyEngineer - B2B Engineering Services Marketplace\",\"private\":false}")

if echo "$RESPONSE" | grep -q '"id":'; then
    echo "✅ Repository created successfully!"
    REPO_URL=$(echo "$RESPONSE" | grep -o '"html_url": "[^"]*"' | head -1 | cut -d'"' -f4)
    echo "   URL: $REPO_URL"
else
    echo "⚠️  Repository may already exist or there was an error"
    echo "   Response: $(echo "$RESPONSE" | grep -o '"message": "[^"]*"' | head -1)"
fi

# Set remote and push
echo ""
echo "📤 Pushing code to GitHub..."
git remote remove origin 2>/dev/null
git remote add origin "https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"

# Push to main branch
if git push -u origin main; then
    echo "✅ Code pushed successfully!"
    echo ""
    echo "🎉 DEPLOYMENT READY!"
    echo "====================="
    echo ""
    echo "Next steps:"
    echo "1. Go to https://dashboard.render.com/blueprints"
    echo "2. Click 'New Blueprint Instance'"
    echo "3. Connect your GitHub account"
    echo "4. Select the '$REPO_NAME' repository"
    echo "5. Render will automatically detect render.yaml and deploy!"
    echo ""
    echo "Repository URL: https://github.com/$GITHUB_USER/$REPO_NAME"
else
    echo "❌ Push failed. Please check your credentials and try again."
fi
