"""部署目標。唯一的上線路徑是 Cloudflare Pages。

    cd app && npm run build && npx wrangler pages deploy dist \
        --project-name mstr-capital-structure --branch master

專案名就是下面這個常數。Workers 專案 master-capital-structure 不是部署目標。
它的 Git 整合要在 Cloudflare 後台關掉；這個倉庫改不了後台設定。
"""

DEPLOY_PROJECT = "mstr-capital-structure"
