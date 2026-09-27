import os

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("PROJECT_NAME", "llms_txt")
os.environ.setdefault("APPLICATION_S3_BUCKET", "dev-llms-txt-s3-test")
os.environ.setdefault(
    "CRAWL_QUEUE_URL",
    "https://sqs.us-east-1.amazonaws.com/123456789012/dev_llms_txt_crawl_sqs",
)
os.environ.setdefault("COGNITO_USER_POOL_ID", "us-east-1_testpool")
os.environ.setdefault("COGNITO_APP_CLIENT_ID", "test-client")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
