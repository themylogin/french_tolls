FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/french-tolls.conf
RUN nginx -t

RUN rm -rf /usr/share/nginx/html/*
COPY index.html index.js style.css /usr/share/nginx/html/

# Stamp each asset's own checksum into the URL the page asks for.
RUN set -eu; \
    d=/usr/share/nginx/html; \
    js=$(sha256sum "$d/index.js" | cut -c1-12); \
    css=$(sha256sum "$d/style.css" | cut -c1-12); \
    sed -i "s#\"./style.css\"#\"./style.css?$css\"#; s#\"./index.js\"#\"./index.js?$js\"#" "$d/index.html"; \
    grep -q "style.css?$css" "$d/index.html"; \
    grep -q "index.js?$js" "$d/index.html"; \
    grep -oE '(style\.css|index\.js)\?[0-9a-f]+' "$d/index.html"
