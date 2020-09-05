deploy:
	docker build . -t ghcr.io/russss/dsn_status:latest
	docker push ghcr.io/russss/dsn_status:latest
