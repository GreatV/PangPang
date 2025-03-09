import requests
import argparse
import os
import json
from typing import Optional, Dict, Any
import dotenv

dotenv.load_dotenv()

class SMmsUploader:
    """A client for uploading images to SM.MS and retrieving markdown links."""
    
    BASE_URL = "https://sm.ms/api/v2"
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize the SM.MS uploader.
        
        Args:
            token: Your SM.MS API token. If not provided, looks for SMMS_API_KEY environment variable.
        """
        self.token = token or os.environ.get("SMMS_API_KEY")
        if not self.token:
            raise ValueError("API token required. Set SMMS_API_KEY environment variable or pass token parameter.")
        
        self.headers = {
            "Authorization": self.token
        }
    
    def upload_image(self, image_path: str) -> Dict[str, Any]:
        """
        Upload an image to SM.MS.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Response data from the API
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        upload_url = f"{self.BASE_URL}/upload"
        
        with open(image_path, 'rb') as image_file:
            files = {'smfile': image_file}
            response = requests.post(
                upload_url,
                files=files,
                headers=self.headers
            )
        
        response_data = response.json()
        
        if response.status_code != 200 or response_data.get('success') is False:
            error_msg = response_data.get('message', 'Unknown error')
            raise Exception(f"Upload failed: {error_msg}")
        
        return response_data
    
    def get_markdown_link(self, response_data: Dict[str, Any]) -> str:
        """
        Extract the markdown link from the API response.
        
        Args:
            response_data: Response data from upload_image
            
        Returns:
            Markdown formatted link to the image
        """
        data = response_data.get('data', {})
        url = data.get('url')
        filename = data.get('filename')
        
        if not url or not filename:
            raise ValueError("Missing URL or filename in response data")
        
        return f"![{filename}]({url})"

def main():
    parser = argparse.ArgumentParser(description="Upload images to SM.MS and get markdown links")
    parser.add_argument("image_path", help="Path to the image file to upload")
    parser.add_argument("-t", "--token", help="SM.MS API token (alternatively, set SMMS_TOKEN environment variable)")
    
    args = parser.parse_args()
    
    try:
        uploader = SMmsUploader(args.token)
        response = uploader.upload_image(args.image_path)
        markdown_link = uploader.get_markdown_link(response)
        
        print("Upload successful!")
        print("\nMarkdown Link:")
        print(markdown_link)
        
        # Also print detailed response data
        print("\nDetailed Response Data:")
        print(json.dumps(response, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 