import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from logger_config import get_logger
import time

# Get logger
logger = get_logger(__name__)

def get_proxies():
    """Get proxy settings from environment variables"""
    proxies = {}
    if os.environ.get('HTTP_PROXY'):
        proxies['http'] = os.environ.get('HTTP_PROXY')
    if os.environ.get('HTTPS_PROXY'):
        proxies['https'] = os.environ.get('HTTPS_PROXY')
    
    # Also check for lowercase versions
    if not proxies.get('http') and os.environ.get('http_proxy'):
        proxies['http'] = os.environ.get('http_proxy')
    if not proxies.get('https') and os.environ.get('https_proxy'):
        proxies['https'] = os.environ.get('https_proxy')
    
    # Check if proxy should be bypassed
    if os.environ.get('NO_PROXY') == '1' or os.environ.get('no_proxy') == '1':
        logger.info("Proxy is disabled by environment variable")
        return None
    
    if proxies:
        logger.info(f"Using proxy settings: {proxies}")
    
    return proxies or None


def extract_pdf_link(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Method 1: Find links with PDF badge
    pdf_badges = soup.find_all("a", class_="badge badge-light")
    for badge in pdf_badges:
        if badge.find("span", string="PDF"):
            return badge.get("href")

    # Method 2: Find all links containing .pdf
    all_links = soup.find_all("a")
    pdf_links = [
        link.get("href")
        for link in all_links
        if link.get("href") and ".pdf" in link.get("href")
    ]
    if pdf_links:
        return pdf_links[0]

    return None


def get_pdf_url(url, timeout=10):
    try:
        # Get proxy settings
        proxies = get_proxies()
        
        # Send request to get page content with proxies
        logger.info(f"Fetching URL: {url}")
        response = requests.get(url, proxies=proxies, timeout=timeout)
        response.raise_for_status()

        # Parse PDF link
        pdf_url = extract_pdf_link(response.text)
        if pdf_url:
            # Ensure returning complete URL
            return urljoin(url, pdf_url)
        else:
            logger.warning("No PDF link found")
            return None

    except requests.exceptions.Timeout:
        logger.error(f"Timeout while fetching the page (after {timeout}s)")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching the page: {e}")
        return None


def download_pdf(url, max_retries=3, timeout=30):
    # Get PDF URL
    pdf_url = get_pdf_url(url)
    if not pdf_url:
        return

    # Try with and without proxy if needed
    for attempt in range(1, max_retries + 1):
        try:
            # Get proxy settings
            proxies = None if attempt > 1 else get_proxies()
            proxy_status = "with proxy" if proxies else "without proxy"
            
            # Download PDF with proxies and timeout
            logger.info(f"Downloading PDF from: {pdf_url} (Attempt {attempt}/{max_retries} {proxy_status})")
            
            # Stream the response to avoid loading the entire file into memory
            with requests.get(pdf_url, proxies=proxies, timeout=timeout, stream=True) as response:
                response.raise_for_status()
                
                # Extract original filename from URL
                filename = pdf_url.split("/")[-1]
                if not filename.endswith(".pdf"):
                    filename = "paper.pdf"  # fallback to default name if no PDF extension
                
                # Save PDF with original filename
                total_size_in_bytes = int(response.headers.get('content-length', 0))
                block_size = 8192  # 8 Kilobytes
                downloaded = 0
                
                with open(filename, "wb") as f:
                    start_time = time.time()
                    for chunk in response.iter_content(chunk_size=block_size):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Log progress for large files
                            if total_size_in_bytes > 0 and downloaded % (5 * block_size) == 0:
                                progress = (downloaded / total_size_in_bytes) * 100
                                elapsed = time.time() - start_time
                                if elapsed > 0:
                                    speed = downloaded / (1024 * elapsed)
                                    logger.info(f"Download progress: {progress:.1f}% - {speed:.1f} KB/s")
                
                logger.info(f"Successfully downloaded paper as {filename}")
                return filename

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while downloading PDF (after {timeout}s)")
            if attempt < max_retries:
                logger.info(f"Retrying with {'no proxy' if attempt == 1 else 'increased timeout'}")
                timeout *= 1.5  # Increase timeout for next attempt
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying download with {'no proxy' if attempt == 1 else 'different settings'}")
    
    logger.error(f"Failed to download PDF after {max_retries} attempts")
    return None


# Usage example
if __name__ == "__main__":
    url = "https://paperswithcode.com/paper/interactive-gadolinium-free-mri-synthesis-a"
    download_pdf(url)
