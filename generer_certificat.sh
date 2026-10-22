

docker run --rm \
  -v garage-tracking_certbot_certs:/etc/letsencrypt \
  -v garage-tracking_certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d garage.laprudenceplus-cm.com \
  --email contact@laprudenceplus-cm.com --agree-tos --no-eff-email


docker run --rm \
  -v garage-tracking_certbot_certs_test:/etc/letsencrypt \
  -v garage-tracking_certbot_www_test:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d dev.laprudenceplus-cm.com \
  --email dylanogold@gmail.com --agree-tos --no-eff-email


