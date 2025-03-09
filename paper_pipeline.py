import os
import json
import yaml
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from logger_config import get_logger
from sm_ms_uploader import SMmsUploader

# Import project modules
from papers_with_code import (
    Base,
    Paper,
    scrape_papers_with_pagination,
    save_papers_to_db,
)
from ranking import get_random_papers, get_chatgpt_ranking, create_prompt
from get_pdf import download_pdf
from get_markdown_doc2x import convert_to_markdown as convert_to_markdown_doc2x
from get_markdown_mistral import convert_to_markdown as convert_to_markdown_mistral
from summarize_paper import summarize_paper

# Initialize logger
logger = get_logger(__name__)


def load_config():
    """Load configuration from config.yaml or use defaults if not available"""
    try:
        with open("config.yaml", "r") as config_file:
            return yaml.safe_load(config_file)
    except Exception as e:
        logger.error(f"Error loading config.yaml: {str(e)}")
        return {
            "paper_fetch": {"limit": 30},
            "paper_ranking": {"default_limit": 3, "fallback_limit": 1},
            "pdf_to_markdown": {"converter": "mistral_ocr"},
            "output_dir": "./data",
        }


# Global config
config = load_config()


class PaperInfo:
    """Data class to store paper information"""

    def __init__(
        self, id, title, github_link, paper_link, code_link, stars, arxiv_link=None
    ):
        self.id = id
        self.title = title
        self.github_link = github_link
        self.paper_link = paper_link
        self.code_link = code_link
        self.stars = stars
        self.arxiv_link = arxiv_link


@contextmanager
def session_scope():
    """Creates a context manager for database sessions to ensure proper handling"""
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def setup_database():
    """Set up and return a database session (legacy function, use session_scope instead)"""
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def fetch_latest_papers(limit=100):
    """Fetch latest papers from Papers With Code and save to database"""
    logger.info("Starting to fetch latest papers...")
    base_url = "https://paperswithcode.com/latest"
    papers = scrape_papers_with_pagination(base_url, target_count=limit)

    with session_scope() as session:
        new_count, updated_count = save_papers_to_db(papers, session)
        logger.info(f"New papers added: {new_count}")
        logger.info(f"Papers updated: {updated_count}")
        total_count = session.query(Paper).count()
        logger.info(f"Total papers in database: {total_count}")

    return new_count + updated_count


def rank_and_select_papers(limit=3):
    """Rank papers using AI and select the top ones up to the specified limit"""
    logger.info("Starting paper ranking...")

    with session_scope() as session:
        papers = get_random_papers(session)
        if not papers:
            logger.error("No unread papers in the database")
            return []

        prompt = create_prompt(papers)
        ranked_paper_ids = get_chatgpt_ranking(prompt)

        if not ranked_paper_ids:
            logger.error("Ranking process didn't return any paper IDs")
            return []

        # Process only valid paper IDs up to the limit
        valid_ids = [pid for pid in ranked_paper_ids if isinstance(pid, int)][:limit]

        top_papers = []
        logger.info("Top recommended papers:")

        for rank, paper_id in enumerate(valid_ids, 1):
            paper = session.query(Paper).filter_by(id=paper_id).first()
            if paper:
                paper_info = PaperInfo(
                    id=paper.id,
                    title=paper.title,
                    github_link=paper.github_link,
                    paper_link=paper.paper_link,
                    code_link=paper.code_link,
                    stars=paper.stars,
                    arxiv_link=paper.arxiv_link,
                )

                top_papers.append(paper_info)
                logger.info(f"{rank}. [ID: {paper.id}] {paper.title}")
                logger.info(f"   GitHub: {paper.github_link}")
                logger.info(f"   Paper: {paper.arxiv_link or paper.paper_link}\n")

                # Mark paper as read
                paper.thoroughly_read = True

    return top_papers


def get_latest_pdf():
    """Helper function to get the most recently downloaded PDF file"""
    pdf_files = [f for f in os.listdir(".") if f.endswith(".pdf")]
    if not pdf_files:
        return None
    return sorted(pdf_files, key=lambda x: os.path.getmtime(x), reverse=True)[0]


def process_paper(paper_info):
    """Process a single paper: download PDF, convert to Markdown, summarize and handle images"""
    logger.info(f"Starting to process paper: {paper_info.title}")

    # Use arXiv link if available, otherwise use paper_link
    paper_url = (
        paper_info.arxiv_link if paper_info.arxiv_link else paper_info.paper_link
    )

    if not paper_url:
        logger.error("Paper has no available PDF link")
        return None

    logger.info(f"Downloading paper PDF: {paper_url}")
    try:
        output_dir = config.get("output_dir", "./data")
        download_result = download_pdf(paper_url, output_file_dir=output_dir)

        # Unpack results - returns (filename, arxiv_url)
        if isinstance(download_result, tuple) and len(download_result) == 2:
            latest_pdf, arxiv_url = download_result
        else:
            # Backward compatibility
            latest_pdf = download_result
            arxiv_url = None

        if not latest_pdf:
            logger.error("Downloaded PDF file not found")
            return None

        latest_pdf = os.path.join(output_dir, latest_pdf)
        logger.info(f"Converting PDF to Markdown: {latest_pdf}")

        # Get converter from config
        converter = config.get("pdf_to_markdown", {}).get("converter", "mistral_ocr")

        # Create directory for paper images
        date = datetime.now().strftime("%Y-%m-%d")
        paper_id = paper_info.id
        image_dir = f"images_{paper_id}_{date}"
        os.makedirs(os.path.join(output_dir, image_dir), exist_ok=True)

        # Initialize image hosting service
        try:
            smms_uploader = SMmsUploader()
            logger.info("Initialized SM.MS uploader")
        except Exception as e:
            logger.error(f"Failed to initialize SM.MS uploader: {str(e)}")
            smms_uploader = None

        # Track image URLs for local to online path mapping
        image_url_map = {}

        if converter == "doc2x":
            logger.info("Using doc2x for PDF to Markdown conversion")
            convert_to_markdown_doc2x(latest_pdf)

            try:
                with open("result.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pages_info = data["pages"]

                content = "".join(page["md"] for page in pages_info)
            except Exception as e:
                logger.error(f"Error processing doc2x output: {str(e)}")
                return None

        else:  # Default to mistral_ocr
            logger.info("Using Mistral OCR for PDF to Markdown conversion")
            convert_to_markdown_mistral(latest_pdf)

            try:
                with open("result.json", "r", encoding="utf-8") as f:
                    ocr_response = json.load(f)

                content = ""
                image_refs = set()  # Track image references to avoid duplicates

                # Process each page in the OCR response
                for page in ocr_response["pages"]:
                    if not page.get("markdown"):
                        continue

                    page_content = page["markdown"]

                    # Process images in this page
                    for img in page.get("images", []):
                        img_id = img["id"]
                        if img_id in image_refs:
                            continue  # Skip duplicate image references

                        # Create descriptive filename for the image
                        img_filename = os.path.join(output_dir, image_dir, img_id)

                        # Handle base64 encoded images
                        if img.get("image_base64"):
                            import base64

                            try:
                                # Remove the data:image/jpeg;base64, prefix
                                image_base64 = img["image_base64"].replace(
                                    "data:image/jpeg;base64,", ""
                                )
                                img_data = base64.b64decode(image_base64)
                                with open(img_filename, "wb") as img_file:
                                    img_file.write(img_data)
                                logger.info(f"Saved base64 image to: {img_filename}")

                                # Upload to image hosting service if available
                                if smms_uploader:
                                    try:
                                        response = smms_uploader.upload_image(
                                            img_filename
                                        )
                                        image_url = response["data"]["url"]
                                        image_url_map[img_filename] = image_url
                                        logger.info(
                                            f"Uploaded image to SM.MS: {image_url}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to upload image to SM.MS: {str(e)}"
                                        )
                            except Exception as e:
                                logger.error(f"Error saving base64 image: {str(e)}")
                                continue
                        else:
                            # Handle file-based images
                            source_path = img_id
                            if os.path.exists(source_path):
                                import shutil

                                shutil.copy2(source_path, img_filename)
                                logger.info(
                                    f"Copied image from {source_path} to {img_filename}"
                                )

                                # Upload to image hosting service if available
                                if smms_uploader:
                                    try:
                                        response = smms_uploader.upload_image(
                                            img_filename
                                        )
                                        image_url = response["data"]["url"]
                                        image_url_map[img_filename] = image_url
                                        logger.info(
                                            f"Uploaded image to SM.MS: {image_url}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to upload image to SM.MS: {str(e)}"
                                        )
                            else:
                                logger.warning(f"Image file not found: {source_path}")
                                continue

                        # Update image references in the markdown
                        page_content = page_content.replace(
                            f"![{img_id}]({img_id})",
                            f"![Figure from paper]({img_filename})",
                        )

                        image_refs.add(img_id)
                        logger.info(f"Processed image: {img_id}")

                    content += page_content

                if not content:
                    logger.error("No content extracted from OCR response")
                    return None

            except Exception as e:
                logger.error(f"Error processing Mistral OCR output: {str(e)}")
                import traceback

                logger.error(traceback.format_exc())
                return None

        # Select best available paper link
        paper_link_to_use = arxiv_url or paper_info.arxiv_link or paper_info.paper_link

        # Add paper metadata to content
        paper_metadata = f"""
# {paper_info.title}

## Metadata
- **GitHub**: {paper_info.github_link}
- **Paper**: {paper_link_to_use}
- **Code**: {paper_info.code_link}
- **Stars**: {paper_info.stars}

"""
        content = paper_metadata + content

        # Generate AI summary
        summary = summarize_paper(content)

        # Replace local image paths with online URLs
        processed_summary = summary

        # Enhanced replacement logic to handle different path formats
        def normalize_path(path):
            """Normalize path by removing leading './' and ensuring consistent format"""
            return path.lstrip("./")

        # Create a map with multiple path variants for each image
        enhanced_image_map = {}
        for local_path, online_url in image_url_map.items():
            # Original path
            enhanced_image_map[local_path] = online_url

            # Path without leading ./
            normalized_path = normalize_path(local_path)
            if normalized_path != local_path:
                enhanced_image_map[normalized_path] = online_url

            # Path with leading ./ if not present
            if not local_path.startswith("./"):
                enhanced_image_map[f"./{local_path}"] = online_url

            # Log all path variants
            logger.info(f"Image path variants for {local_path} -> {online_url}:")
            for variant in enhanced_image_map.keys():
                if enhanced_image_map[variant] == online_url:
                    logger.info(f"  - {variant}")

        # Perform multiple passes of replacement to ensure all variants are caught
        for local_path, online_url in enhanced_image_map.items():
            logger.info(
                f"Replacing local image path with online URL: {local_path} -> {online_url}"
            )
            processed_summary = processed_summary.replace(local_path, online_url)

        # Additional pass using regex to catch paths with different directory structures
        import re

        for local_path, online_url in image_url_map.items():
            # Extract the image filename from the path
            filename = os.path.basename(local_path)
            # Create a pattern that matches the filename in various directory structures
            pattern = re.escape(filename)
            # Find all matches of the filename in the summary
            for match in re.finditer(
                f"(\\./)?(?:data/)?images_[^/]+/{pattern}", processed_summary
            ):
                matched_path = match.group(0)
                if (
                    matched_path in processed_summary
                    and matched_path not in enhanced_image_map
                ):
                    logger.info(
                        f"Regex replacing path variant: {matched_path} -> {online_url}"
                    )
                    processed_summary = processed_summary.replace(
                        matched_path, online_url
                    )

        # Save summary to file
        filename = f"summary_{paper_info.id}_{date}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(processed_summary)

        logger.info(f"Paper summary saved to: {filename}")
        return filename

    except Exception as e:
        logger.error(f"Error downloading PDF: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())

    return None


def main():
    """Main pipeline function that orchestrates the paper processing workflow"""
    load_dotenv()  # Load environment variables

    # Load configuration
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
            paper_fetch_limit = config.get("paper_fetch", {}).get("limit", 100)
            default_ranking_limit = config.get("paper_ranking", {}).get(
                "default_limit", 3
            )
            fallback_ranking_limit = config.get("paper_ranking", {}).get(
                "fallback_limit", 1
            )
            logger.info(f"Loaded configuration: paper_fetch_limit={paper_fetch_limit}")
    except Exception as e:
        logger.warning(f"Failed to load configuration from {config_path}: {str(e)}")
        logger.warning("Using default values")
        paper_fetch_limit = 100
        default_ranking_limit = 3
        fallback_ranking_limit = 1

    # Step 1: Get latest papers
    paper_count = fetch_latest_papers(limit=paper_fetch_limit)

    # Step 2: Rank papers and make selection
    with session_scope() as session:
        # Check if there are any unread papers in the database
        unread_papers_exist = (
            session.query(Paper).filter_by(thoroughly_read=False).first() is not None
        )

    if paper_count == 0 and not unread_papers_exist:
        logger.info(
            "No new papers and all existing papers have been read, pipeline complete"
        )
        return

    # When no new papers, limit to just 1 most interesting paper
    limit = fallback_ranking_limit if paper_count == 0 else default_ranking_limit
    top_papers = rank_and_select_papers(limit=limit)

    if not top_papers:
        logger.info("No papers worth reading were selected, pipeline complete")
        return

    if paper_count == 0 and top_papers:
        logger.info(
            f"Selected 1 most interesting paper from database: {top_papers[0].title}"
        )

    # Step 3: Process selected papers
    summary_files = [
        summary_file for paper in top_papers if (summary_file := process_paper(paper))
    ]

    logger.info(f"Total summary files generated: {len(summary_files)}")


if __name__ == "__main__":
    main()
