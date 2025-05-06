import subprocess
import sys
import time
import json
import base64
import boto3
import os # Import os module
from dotenv import load_dotenv # Import dotenv
from botocore.exceptions import ClientError

# --- Configuration ---
# Read from environment variables, falling back to defaults if not set
LAMBDA_FUNCTION_NAME = os.getenv("LAMBDA_FUNCTION_NAME", "pdf-to-jpg-converter")
ECR_REPOSITORY_NAME = os.getenv("ECR_REPOSITORY_NAME", "pdf-to-jpg-converter")
LAMBDA_ROLE_NAME = os.getenv("LAMBDA_ROLE_NAME", "lambda-execution-role")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
LAMBDA_TIMEOUT = int(os.getenv("LAMBDA_TIMEOUT", 30)) # Convert to int
LAMBDA_MEMORY_SIZE = int(os.getenv("LAMBDA_MEMORY_SIZE", 1024)) # Convert to int
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", 7)) # Convert to int
# --- End Configuration ---

# --- Colors for output ---
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m' # No Color
# --- End Colors ---

# --- AWS Clients ---
try:
    sts_client = boto3.client('sts', region_name=AWS_REGION)
    iam_client = boto3.client('iam', region_name=AWS_REGION)
    ecr_client = boto3.client('ecr', region_name=AWS_REGION)
    lambda_client = boto3.client('lambda', region_name=AWS_REGION)
    logs_client = boto3.client('logs', region_name=AWS_REGION)
    AWS_ACCOUNT_ID = sts_client.get_caller_identity()["Account"]
except Exception as e:
    print(f"{RED}Failed to initialize AWS clients or get Account ID: {e}{NC}")
    sys.exit(1)
# --- End AWS Clients ---

ECR_REPOSITORY_URI = f"{AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/{ECR_REPOSITORY_NAME}"
IMAGE_URI = f"{ECR_REPOSITORY_URI}:latest"
LOG_GROUP_NAME = f"/aws/lambda/{LAMBDA_FUNCTION_NAME}"

def run_command(command, check=True, shell=False, capture_output=False, text=False, stdin_input=None):
    """Helper function to run shell commands."""
    print(f"{YELLOW}Running command: {' '.join(command)}{NC}")
    try:
        process = subprocess.run(
            command,
            check=check,
            shell=shell,
            capture_output=capture_output,
            text=text,
            input=stdin_input
        )
        if capture_output:
            return process.stdout.strip() if process.stdout else ""
        return True
    except subprocess.CalledProcessError as e:
        print(f"{RED}Command failed: {' '.join(command)}{NC}")
        print(f"{RED}Error: {e}{NC}")
        if e.stderr:
            print(f"{RED}Stderr: {e.stderr.decode()}{NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}An unexpected error occurred while running command: {' '.join(command)}{NC}")
        print(f"{RED}Error: {e}{NC}")
        sys.exit(1)

def check_or_create_iam_role():
    """Checks if the Lambda execution role exists, creates it if not."""
    global LAMBDA_ROLE_ARN
    print(f"{YELLOW}Checking if Lambda execution role exists: {LAMBDA_ROLE_NAME}{NC}")
    try:
        response = iam_client.get_role(RoleName=LAMBDA_ROLE_NAME)
        LAMBDA_ROLE_ARN = response['Role']['Arn']
        print(f"{GREEN}Lambda execution role already exists: {LAMBDA_ROLE_ARN}{NC}")
        return LAMBDA_ROLE_ARN
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"{YELLOW}Creating Lambda execution role: {LAMBDA_ROLE_NAME}{NC}")
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            try:
                role_response = iam_client.create_role(
                    RoleName=LAMBDA_ROLE_NAME,
                    AssumeRolePolicyDocument=json.dumps(trust_policy)
                )
                LAMBDA_ROLE_ARN = role_response['Role']['Arn']
                print(f"{YELLOW}Attaching AWSLambdaBasicExecutionRole policy...{NC}")
                iam_client.attach_role_policy(
                    RoleName=LAMBDA_ROLE_NAME,
                    PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
                )
                print(f"{YELLOW}Waiting for role to propagate (10 seconds)...{NC}")
                time.sleep(10)
                print(f"{GREEN}Lambda execution role created successfully: {LAMBDA_ROLE_ARN}{NC}")
                return LAMBDA_ROLE_ARN
            except ClientError as create_error:
                print(f"{RED}Failed to create Lambda execution role: {create_error}{NC}")
                sys.exit(1)
        else:
            print(f"{RED}Error checking IAM role: {e}{NC}")
            sys.exit(1)

def check_or_create_ecr_repo():
    """Checks if the ECR repository exists, creates it if not."""
    print(f"{YELLOW}Checking if ECR repository exists: {ECR_REPOSITORY_NAME}{NC}")
    try:
        ecr_client.describe_repositories(repositoryNames=[ECR_REPOSITORY_NAME])
        print(f"{GREEN}ECR repository already exists.{NC}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'RepositoryNotFoundException':
            print(f"{YELLOW}Creating ECR repository: {ECR_REPOSITORY_NAME}{NC}")
            try:
                ecr_client.create_repository(repositoryName=ECR_REPOSITORY_NAME)
                print(f"{GREEN}ECR repository created successfully.{NC}")
            except ClientError as create_error:
                print(f"{RED}Failed to create ECR repository: {create_error}{NC}")
                sys.exit(1)
        else:
            print(f"{RED}Error checking ECR repository: {e}{NC}")
            sys.exit(1)

def ecr_login():
    """Authenticates Docker to ECR."""
    print(f"{YELLOW}Authenticating Docker to ECR...{NC}")
    try:
        response = ecr_client.get_authorization_token()
        auth_data = response['authorizationData'][0]
        token = base64.b64decode(auth_data['authorizationToken']).decode('utf-8')
        username, password = token.split(':')
        endpoint = auth_data['proxyEndpoint']

        run_command(
            ['docker', 'login', '--username', username, '--password-stdin', endpoint],
            stdin_input=password.encode('utf-8')
        )
        print(f"{GREEN}Docker authenticated to ECR successfully.{NC}")
    except ClientError as e:
        print(f"{RED}Failed to get ECR authorization token: {e}{NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Failed during Docker login process: {e}{NC}")
        sys.exit(1)

def build_tag_push_docker():
    """Builds, tags, and pushes the Docker image to ECR."""
    local_platform_tag = f"{ECR_REPOSITORY_NAME}:latest-amd64" # Temporary local tag

    # Build with a platform-specific local tag AND disable provenance
    print(f"{YELLOW}Building Docker image for linux/amd64 (provenance disabled)...{NC}")
    run_command(['docker', 'build', '--platform', 'linux/amd64', '--provenance=false', '-t', local_platform_tag, '.'])

    # Tag the specific amd64 build with the ECR latest tag
    print(f"{YELLOW}Tagging specific amd64 build as ECR latest...{NC}")
    run_command(['docker', 'tag', local_platform_tag, IMAGE_URI])

    # Push the ECR latest tag (which now points only to the amd64 image)
    print(f"{YELLOW}Pushing Docker image to ECR...{NC}")
    run_command(['docker', 'push', IMAGE_URI])

    # Optional: Clean up the temporary local tag
    try:
        print(f"{YELLOW}Cleaning up local tag {local_platform_tag}...{NC}")
        run_command(['docker', 'rmi', local_platform_tag], check=False) # Don't exit if cleanup fails
    except Exception as cleanup_error:
        print(f"{YELLOW}Warning: Failed to remove local tag {local_platform_tag}: {cleanup_error}{NC}")

    print(f"{GREEN}Docker image pushed successfully.{NC}")

def deploy_lambda():
    """Creates or updates the Lambda function."""
    print(f"{YELLOW}Checking if Lambda function exists: {LAMBDA_FUNCTION_NAME}{NC}")
    try:
        lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        print(f"{YELLOW}Updating existing Lambda function...{NC}")
        try:
            lambda_client.update_function_code(
                FunctionName=LAMBDA_FUNCTION_NAME,
                ImageUri=IMAGE_URI,
                Publish=True
            )
            # Optionally update configuration too if needed
            # lambda_client.update_function_configuration(...)
            print(f"{GREEN}Lambda function updated successfully.{NC}")
        except ClientError as update_error:
            print(f"{RED}Failed to update Lambda function: {update_error}{NC}")
            sys.exit(1)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"{YELLOW}Creating new Lambda function...{NC}")
            try:
                lambda_client.create_function(
                    FunctionName=LAMBDA_FUNCTION_NAME,
                    Role=LAMBDA_ROLE_ARN,
                    Code={'ImageUri': IMAGE_URI},
                    PackageType='Image',
                    Timeout=LAMBDA_TIMEOUT,
                    MemorySize=LAMBDA_MEMORY_SIZE,
                    Publish=True
                )
                print(f"{GREEN}Lambda function created successfully.{NC}")

                # Set up CloudWatch Logs
                print(f"{YELLOW}Creating CloudWatch Logs log group: {LOG_GROUP_NAME}{NC}")
                try:
                    logs_client.create_log_group(logGroupName=LOG_GROUP_NAME)
                except ClientError as log_error:
                    # Ignore if log group already exists
                    if log_error.response['Error']['Code'] != 'ResourceAlreadyExistsException':
                        print(f"{YELLOW}Warning: Could not create log group (might already exist): {log_error}{NC}")
                try:
                    print(f"{YELLOW}Setting log retention policy ({LOG_RETENTION_DAYS} days)...{NC}")
                    logs_client.put_retention_policy(
                        logGroupName=LOG_GROUP_NAME,
                        retentionInDays=LOG_RETENTION_DAYS
                    )
                    print(f"{GREEN}Log retention policy set.{NC}")
                except ClientError as retention_error:
                    print(f"{RED}Failed to set log retention policy: {retention_error}{NC}")
                    # Don't exit, creation might still be successful overall

            except ClientError as create_error:
                print(f"{RED}Failed to create Lambda function: {create_error}{NC}")
                sys.exit(1)
        else:
            print(f"{RED}Error checking Lambda function: {e}{NC}")
            sys.exit(1)

def main():
    """Main execution flow."""
    print(f"{YELLOW}Starting Docker-based Lambda deployment...{NC}")

    check_or_create_iam_role()
    check_or_create_ecr_repo()
    ecr_login()
    build_tag_push_docker()
    deploy_lambda()

    # Get final function ARN for output
    try:
        function_data = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        function_arn = function_data['Configuration']['FunctionArn']
        print(f"{GREEN}Docker-based Lambda function deployed successfully!{NC}")
        print(f"{GREEN}Function ARN: {function_arn}{NC}")
        print(f"{GREEN}You can invoke this Lambda directly using the AWS CLI or SDK:{NC}")
        print(f"{GREEN}aws lambda invoke --function-name {LAMBDA_FUNCTION_NAME} --payload '<base64-encoded-pdf-or-url-json>' output.txt --cli-binary-format raw-in-base64-out{NC}") # Added cli-binary-format hint
        print(f"{GREEN}Deployment complete!{NC}")
    except ClientError as e:
        print(f"{RED}Failed to get final function ARN: {e}{NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()