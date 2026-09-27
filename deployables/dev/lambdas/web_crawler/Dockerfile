FROM public.ecr.aws/lambda/python:3.12

COPY backend/app ${LAMBDA_TASK_ROOT}/backend/app
COPY deployables/dev/lambdas/web_crawler/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
