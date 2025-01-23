import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


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


def get_pdf_url(url):
    try:
        # Send request to get page content
        response = requests.get(url)
        response.raise_for_status()

        # Parse PDF link
        pdf_url = extract_pdf_link(response.text)
        if pdf_url:
            # Ensure returning complete URL
            return urljoin(url, pdf_url)
        else:
            print("No PDF link found")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the page: {e}")
        return None


def download_pdf(url):
    # Get PDF URL
    pdf_url = get_pdf_url(url)
    if not pdf_url:
        return

    try:
        # Download PDF
        print(f"Downloading PDF from: {pdf_url}")
        response = requests.get(pdf_url)
        response.raise_for_status()

        # Extract original filename from URL
        filename = pdf_url.split("/")[-1]
        if not filename.endswith(".pdf"):
            filename = "paper.pdf"  # fallback to default name if no PDF extension

        # Save PDF with original filename
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"Successfully downloaded paper as {filename}")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading PDF: {e}")


# Usage example
if __name__ == "__main__":
    url = "https://paperswithcode.com/paper/addressing-multilabel-imbalance-with-an"
    download_pdf(url)
