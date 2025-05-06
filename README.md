# Lambda PDF Converter

Transform PDF files into high-quality JPEG images with this AWS Lambda function. Designed for seamless integration with automation tools like n8n, this solution delivers converted images as a convenient ZIP archive at a fraction of the cost of commercial API services.

## AWS Services

- **AWS Lambda**:

  - Runs containerized PDF conversion function
  - Scales automatically with demand
  - Pay-per-use pricing model

- **Amazon ECR**:

  - Stores Docker container image
  - Manages container versions
  - Integrates with Lambda service

- **IAM**:
  - Secure execution role for Lambda
  - Least-privilege permission model
  - Integration with external services

## Docker-based Lambda Functions

This project uses a Docker-based approach for AWS Lambda, which offers several advantages:

**What is a Docker-based Lambda?**

- Instead of uploading code files directly, we package our function in a Docker container
- This container includes all necessary dependencies, including poppler for PDF conversion
- AWS runs this container when the Lambda function is invoked

**Advantages of the Docker approach:**

- **Simplified Dependencies**: No need to create separate Lambda Layers - everything is in one container
- **Consistent Environment**: The exact same environment runs locally and in AWS
- **Easier Debugging**: You can test the container locally before deploying
- **No Library Path Issues**: Avoids common problems with shared libraries often encountered with Lambda Layers
- **Larger Size Limit**: Docker images can be up to 10GB, compared to 250MB for regular Lambda deployments

**How it works:**

1. We create a Dockerfile that includes Python, poppler utilities, and our code
2. The build script builds this Docker image and pushes it to Amazon ECR (container registry)
3. Our Lambda function runs this container image when invoked

## Getting Started

### Prerequisites

- AWS Account
- AWS CLI configured
- Docker installed and running
- Python 3.12+ installed
- Basic knowledge of AWS Lambda
- n8n workflow automation tool (optional)

### Quick Deployment

For a fully automated deployment to AWS Lambda, use the provided deployment script:

```bash
# Make the deployment script executable
chmod +x build_and_deploy.sh

# Run the deployment script
./build_and_deploy.sh
```

This script will:

1. Check if a Lambda execution role exists and create one if needed
2. Create an ECR repository for the Docker image if it doesn't exist
3. Build and tag the Docker image with all dependencies included
4. Push the Docker image to Amazon ECR
5. Create or update the Lambda function to use this Docker image
6. Configure proper memory, timeout, and other settings

By default, it creates a Lambda function named `pdf-to-jpg-converter` in the `eu-west-2` region. You can edit the script variables to customize these settings.

### Testing Locally

You can test the Docker container locally before deploying:

```bash
# Build the Docker image
docker build -t pdf-converter .

# Run the container with a test PDF
docker run -p 9000:8080 pdf-converter
```

In another terminal:

```bash
# Invoke the local function with a test event
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"pdf_url":"https://example.com/document.pdf"}'
```

### Setting Up Least Privilege AWS Credentials

For security best practices, create an IAM user with only the minimum permissions needed:

1. **Create a new IAM Policy:**

   - Go to AWS IAM Console → Policies → Create Policy
   - Choose JSON and paste the following:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": ["arn:aws:lambda:*:*:function:pdf-to-jpg-converter"]
    }
  ]
}
```

- Replace `pdf-to-jpg-converter` with your function name
- Name the policy something like `n8n-pdf-converter-policy`

2. **Create a new IAM User:**

   - Go to AWS IAM Console → Users → Add User
   - Enter a name like `n8n-pdf-converter`
   - Select "Access key - Programmatic access"
   - Click "Next: Permissions"
   - Choose "Attach existing policies directly"
   - Search for and select your `n8n-pdf-converter-policy`
   - Complete user creation and save the access key ID and secret

3. **Use these credentials in n8n:**
   - When setting up your AWS credentials in n8n, use these limited access keys
   - This restricts n8n to only invoke this specific Lambda function
   - No other AWS resources or actions will be available to n8n

### Setting Up in n8n

1. In your n8n workflow, add an **AWS Lambda** node
2. Configure AWS credentials in n8n:
   - Access Key ID (from limited IAM user)
   - Secret Access Key (from limited IAM user)
   - Region (must match your Lambda function's region)
3. In the Lambda node configuration:
   - Function Name: `pdf-to-jpg-converter` (or your chosen name)
   - Invocation Type: `RequestResponse`

## Alternative Approach: Lambda Layers

While this project uses a Docker-based approach, another common method is to use Lambda Layers. Here's a brief overview:

### What are Lambda Layers?

Lambda Layers are a way to package code and dependencies that can be shared across multiple Lambda functions.

**In simple terms:**

- Layers are packages of libraries or runtime components
- They get "attached" to your Lambda function when it runs
- They save you from having to include common dependencies in every function

**Layer Structure for Python:**

```
layer.zip
│
└── python/
    └── lib/
        └── python3.12/
            └── site-packages/
                └── [your packages and modules]
```

**For binary dependencies (like poppler):**

```
layer.zip
│
└── bin/               # Executable files
└── lib/               # Shared libraries
└── include/           # Header files
```

You can learn more about this approach in AWS documentation if needed.

## 📄 License

MIT
