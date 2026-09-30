FROM public.ecr.aws/lambda/python:3.12

COPY deployables/prod/lambdas/web_crawler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt

COPY backend/app ${LAMBDA_TASK_ROOT}/backend/app
COPY deployables/prod/lambdas/web_crawler/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
