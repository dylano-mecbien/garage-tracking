docker run --rm \
  -v $(pwd)/certbot_certs:/etc/letsencrypt \
  -v $(pwd)/certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d garage.laprudenceplus-cm.com \
  --email dylanogold@gmail.com --agree-tos --no-eff-email