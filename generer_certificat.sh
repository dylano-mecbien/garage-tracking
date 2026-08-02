

docker run --rm \
  -v garage-tracking_certbot_certs:/etc/letsencrypt \
  -v garage-tracking_certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d garage.laprudenceplus-cm.com \
  --email contact@laprudenceplus-cm.com --agree-tos --no-eff-email


