import requests
from bs4 import BeautifulSoup
import re
from sqlalchemy import create_engine, Column, String, Integer, UniqueConstraint, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError
from logger_config import get_logger
import time

# Get logger for the current module
logger = get_logger(__name__)

Base = declarative_base()


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True)
    github_link = Column(String)
    abstract = Column(String)
    stars = Column(Integer)
    paper_link = Column(String)
    paper_download = Column(String)
    code_link = Column(String)
    arxiv_link = Column(String)
    thoroughly_read = Column(Boolean, default=False)

    # Add composite unique constraint
    __table_args__ = (UniqueConstraint("title", "paper_link", name="_title_paper_uc"),)


def parse_paper_card(card):
    # Extract title and paper link
    title_elem = card.find("h1").find("a")
    title = title_elem.text.strip()
    paper_link = "https://paperswithcode.com" + title_elem["href"]

    # Extract Github URL
    github_link = card.find("span", {"class": "item-github-link"}).find("a")
    github_link = github_link["href"] if github_link else ""

    # Extract abstract
    abstract_elem = card.find("p", {"class": "item-strip-abstract"})
    abstract = abstract_elem.text.strip() if abstract_elem else ""

    # Extract star count
    stars_elem = card.find("span", {"class": "badge-secondary"})
    stars = re.search(r"\d+", stars_elem.text).group() if stars_elem else "0"

    # Extract paper and code links
    paper_download = ""
    code_link = ""
    arxiv_link = ""

    for link in card.find_all("a", {"class": "badge"}):
        if "Paper" in link.text:
            paper_download = "https://paperswithcode.com" + link["href"]
        elif "Code" in link.text:
            code_link = "https://paperswithcode.com" + link["href"]

    # Try to find arXiv link directly in main page
    for link in card.find_all("a"):
        href = link.get("href", "")
        if "arxiv.org" in href:
            arxiv_link = href
            break

    return {
        "title": title,
        "github_link": github_link,
        "abstract": abstract,
        "stars": stars,
        "paper_link": paper_link,
        "paper_download": paper_download,
        "code_link": code_link,
        "arxiv_link": arxiv_link,
    }


def scrape_papers(base_url, page=1):
    url = f"{base_url}?page={page}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # Find all paper cards
    paper_cards = soup.find_all("div", {"class": "row infinite-item item paper-card"})

    # Parse information from each card
    papers = []
    for card in paper_cards:
        paper_info = parse_paper_card(card)
        papers.append(paper_info)

    return papers


def scrape_papers_with_pagination(base_url, target_count=None, max_pages=100):
    all_papers = []
    page = 1

    while True:
        # Break if we've reached target count
        if target_count and len(all_papers) >= target_count:
            break

        # Break if we've reached max pages
        if page > max_pages:
            break

        papers = scrape_papers(base_url, page)

        # Break if no papers found on current page
        if not papers:
            break

        all_papers.extend(papers)
        logger.info(f"Scraped page {page}, total papers so far: {len(all_papers)}")
        page += 1

        # Add a 2-second delay to avoid hitting the server too quickly
        time.sleep(2)

    return all_papers[:target_count] if target_count else all_papers


def save_papers_to_db(papers, session):
    new_count = 0
    updated_count = 0

    for paper_info in papers:
        title = paper_info["title"]
        paper_link = paper_info["paper_link"]

        # Look for existing paper in the database by title and paper link
        paper = session.query(Paper).filter_by(title=title).first()

        if paper:
            # Update existing paper
            paper.github_link = paper_info["github_link"]
            paper.abstract = paper_info["abstract"]
            paper.stars = int(paper_info["stars"])
            paper.paper_link = paper_link
            paper.paper_download = paper_info["paper_download"]
            paper.code_link = paper_info["code_link"]
            paper.arxiv_link = paper_info.get("arxiv_link", "")
            updated_count += 1
        else:
            # Create new paper
            try:
                new_paper = Paper(
                    title=title,
                    github_link=paper_info["github_link"],
                    abstract=paper_info["abstract"],
                    stars=int(paper_info["stars"]),
                    paper_link=paper_link,
                    paper_download=paper_info["paper_download"],
                    code_link=paper_info["code_link"],
                    arxiv_link=paper_info.get("arxiv_link", ""),
                    thoroughly_read=False,
                )
                session.add(new_paper)
                new_count += 1
            except IntegrityError:
                session.rollback()
                logger.warning(f"Paper already exists: {title}")
                continue

    # Commit all changes
    session.commit()
    return new_count, updated_count


def main():
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    base_url = "https://paperswithcode.com/latest"
    # Scrape papers with target count (e.g., 100 papers)
    papers = scrape_papers_with_pagination(base_url, target_count=100)

    # Save results to database with deduplication
    new_count, updated_count = save_papers_to_db(papers, session)
    logger.info(f"Added {new_count} new papers")
    logger.info(f"Updated {updated_count} existing papers")

    # Print total count in database
    total_count = session.query(Paper).count()
    logger.info(f"Total papers in database: {total_count}")

    session.close()


if __name__ == "__main__":
    main()
