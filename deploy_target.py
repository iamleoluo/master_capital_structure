"""部署目標的專案名。CI 與文件只讀這個常數。

兩個 Cloudflare 專案都維持原狀。這裡不呼叫 wrangler，也不改任何設定。
主人選定之後只改 DEPLOY_PROJECT。空字串代表還沒選。
"""

DEPLOY_PROJECT = ""
