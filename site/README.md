# Site

Static files for **https://aiup.neuman.dev**.

The hostname is not live until DNS points here (GitHub Pages or Cloudflare Pages). Root of the deploy is this directory (`site/`). `CNAME` contains `aiup.neuman.dev`.

GitHub Actions workflow `.github/workflows/pages.yml` publishes this folder to GitHub Pages. Point a CNAME at the Pages target when the DNS record exists.
