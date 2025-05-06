FROM public.ecr.aws/lambda/python:3.11-x86_64

# Install poppler utilities using Amazon Linux's package manager
RUN yum update -y && \
    yum install -y \
      poppler \
      poppler-utils \
      && yum clean all

# Copy requirements.txt and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ] 