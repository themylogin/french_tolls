FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/french-tolls.conf
RUN nginx -t

RUN rm -rf /usr/share/nginx/html/*
COPY index.html index.js style.css /usr/share/nginx/html/
