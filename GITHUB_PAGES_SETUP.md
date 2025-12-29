# GitHub Pages Setup Guide for HyperView Documentation

This guide will help you enable and deploy the HyperView documentation website to GitHub Pages.

## Quick Start

Your documentation is ready to deploy! Just follow these 3 simple steps:

### Step 1: Enable GitHub Pages

1. Go to your repository: https://github.com/HackerRoomAI/HyperView
2. Click **Settings** (top right)
3. Click **Pages** (left sidebar, under "Code and automation")
4. Under **Build and deployment**:
   - **Source**: Select `GitHub Actions` from the dropdown
5. Click **Save** (if there's a save button)

That's it! No other configuration needed.

### Step 2: Merge the PR

Once this PR is merged to the `main` branch, the GitHub Actions workflow will automatically:

- ✅ Build the documentation using MkDocs
- ✅ Deploy it to GitHub Pages
- ✅ Make it available at: **https://hackerroomai.github.io/HyperView**

### Step 3: Verify Deployment

After merging:

1. Go to the **Actions** tab in your repository
2. You should see a workflow run called "Deploy Documentation"
3. Wait for it to complete (usually 1-2 minutes)
4. Go back to **Settings** > **Pages**
5. You should see: "Your site is live at https://hackerroomai.github.io/HyperView"
6. Click the link to view your documentation! 🎉

## What's Been Set Up

### Documentation Structure

Your documentation now includes:

- **Home Page**: Overview and features
- **Getting Started**: Installation, quick start, API guide
- **User Guide**: Datasets, embeddings, visualization
- **Concepts**: Why hyperbolic space, architecture
- **Interactive Demo**: Live Poincaré disk visualization
- **API Reference**: Complete API documentation
- **Development**: Contributing guide, frontend development

### Automatic Deployment

The GitHub Actions workflow (`.github/workflows/docs.yml`) will:

- Run automatically on every push to `main`
- Build the documentation with MkDocs
- Deploy to GitHub Pages
- Update your site within minutes

### Technology Stack

- **MkDocs**: Static site generator
- **Material Theme**: Modern, responsive design
- **GitHub Pages**: Free hosting with GitHub domain
- **GitHub Actions**: Automated deployment

## Local Development

To preview the documentation locally:

```bash
# Install MkDocs
pip install mkdocs-material

# Serve with live reload
mkdocs serve

# Open http://127.0.0.1:8000 in your browser
```

To build the site locally:

```bash
mkdocs build
# Output in site/ directory
```

## Customization

### Site Configuration

Edit `mkdocs.yml` to customize:

- Site name and description
- Navigation structure
- Theme colors
- Plugins and extensions

### Content

Add or edit documentation files in the `docs/` directory:

```
docs/
├── index.md                 # Home page
├── getting-started/         # Getting started guides
├── guide/                   # User guides
├── concepts/                # Conceptual documentation
└── development/             # Development guides
```

### Styling

Add custom CSS in `docs/assets/custom.css`.

## Custom Domain (Optional)

To use a custom domain like `docs.hyperview.ai`:

1. **Add CNAME file**:
   ```bash
   echo "docs.hyperview.ai" > docs/CNAME
   ```

2. **Configure DNS** with your domain provider:
   - Add a CNAME record: `docs` → `hackerroomai.github.io`

3. **Update mkdocs.yml**:
   ```yaml
   site_url: https://docs.hyperview.ai
   ```

4. **Enable in GitHub**:
   - Go to Settings > Pages
   - Enter your custom domain
   - Click Save

## Troubleshooting

### Documentation not showing up

**Check:**
1. Is the workflow running? (Actions tab)
2. Did it complete successfully?
3. Is GitHub Pages enabled? (Settings > Pages)
4. Wait 2-3 minutes for propagation

### Workflow failing

**Common issues:**
- Missing dependencies: The workflow installs `mkdocs-material` automatically
- Build errors: Check the workflow logs in the Actions tab
- Permissions: Ensure repository has Pages write permissions

### 404 errors

**Fixes:**
1. Ensure the workflow deployed successfully
2. Check that `site_url` in `mkdocs.yml` matches your GitHub Pages URL
3. Clear your browser cache

## Next Steps

After deployment:

1. **Share the link**: https://hackerroomai.github.io/HyperView
2. **Add to README**: Update the main README.md with a link to the docs
3. **Customize**: Adjust theme colors, add more content
4. **Monitor**: Check the Actions tab after each push to main

## Support

For more information:

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material Theme Docs](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Pages Docs](https://docs.github.com/en/pages)

---

**Ready to deploy? Just merge this PR and GitHub will handle the rest!** 🚀
