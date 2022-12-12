all:

.PHONY: test
test:
	docker build -t wes-device-labeler .
	docker run --rm --entrypoint=sh wes-device-labeler -c 'coverage run -m unittest -v test.py; coverage report'
