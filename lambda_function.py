import json
import base64
import os
import tempfile
import zipfile
import urllib.request
import subprocess
from pdf2image import convert_from_path
from io import BytesIO

def lambda_handler(event, context):
    """
    AWS Lambda function that converts a PDF to JPEGs using a Docker container.
    
    Expected input:
    - PDF file content as base64 in the request body
    OR
    - A URL to a PDF file in the request body as {"pdf_url": "https://example.com/file.pdf"}
    
    Returns:
    - Base64 encoded ZIP file containing the JPEGs
    """
    # Print initial environment for debugging
    print("Lambda environment:")
    print(f"PATH: {os.environ.get('PATH', 'Not set')}")
    print(f"LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', 'Not set')}")
    
    # Check poppler installation
    try:
        result = subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True)
        print(f"pdftoppm version: {result.stderr}")
    except Exception as e:
        print(f"Error checking pdftoppm: {e}")
    
    try:
        # Extract the input from the event
        if 'body' not in event:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'No body found in request'})
            }
        
        # Determine if we have a URL or direct PDF content
        pdf_content = None
        pdf_path = None
        
        body = event['body']
        
        # If the body is a JSON string, parse it to check for a URL
        if isinstance(body, str):
            try:
                # Try to parse as JSON to check for a URL
                body_json = json.loads(body)
                if isinstance(body_json, dict) and 'pdf_url' in body_json:
                    # We have a URL to download
                    pdf_url = body_json['pdf_url']
                    # Generate a unique filename to avoid collisions
                    pdf_path = "/tmp/input.pdf"
                    # Download the PDF from the URL
                    print(f"Downloading PDF from URL: {pdf_url}")
                    urllib.request.urlretrieve(pdf_url, pdf_path)
                else:
                    # Assume it's a base64 encoded PDF
                    pdf_content = base64.b64decode(body)
            except json.JSONDecodeError:
                # Not JSON, assume it's a base64 encoded PDF
                pdf_content = base64.b64decode(body)
        else:
            # Direct invocation might send binary
            pdf_content = body
        
        # Convert PDF to images
        with tempfile.TemporaryDirectory() as path:

            # Create a temporary PDF file if we have content
            if pdf_content:
                temp_pdf = "/tmp/input.pdf"
                with open(temp_pdf, 'wb') as f:
                    f.write(pdf_content)
                pdf_path = temp_pdf
            
            print(f"Converting PDF: {pdf_path}")
            
            # Convert PDF to JPEG using pdf2image (which will use the system's pdftoppm)
            images = convert_from_path(
                pdf_path,
                dpi=150,
                output_folder=path,
                fmt='jpeg',
                thread_count=2
            )
            
            print(f"Successfully converted {len(images)} pages")
            
            # Create a ZIP file containing all the JPEGs
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                for i, image in enumerate(images):
                    img_buffer = BytesIO()
                    image.save(img_buffer, format='JPEG')
                    img_buffer.seek(0)
                    zip_file.writestr(f'page_{i+1}.jpg', img_buffer.getvalue())
            
            zip_buffer.seek(0)
            zip_data = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/zip',
                    'Content-Disposition': 'attachment; filename=pdf_images.zip'
                },
                'body': zip_data,
                'isBase64Encoded': True
            }
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': str(e),
                'details': 'Check CloudWatch logs for more information'
            })
        } 