from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from database import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_domain(url: str) -> str:
    """Extracts the netloc domain from a URL in lowercase."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""

def is_same_domain(url: str, base_domain: str) -> bool:
    """Checks if the domain of the URL matches or is a subdomain of base_domain."""
    domain = get_domain(url)
    if not domain or not base_domain:
        return False
    return domain == base_domain or domain.endswith("." + base_domain)

def download_page(url: str, timeout: float = 5.0) -> str | None:
    """Downloads an HTML page using the requests library.
    
    Handles timeouts, connection errors, and checks for HTML Content-Type.
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        # Verify Content-Type to avoid downloading binaries (PDFs, images, etc.)
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            logger.warning(f"Skipping non-HTML URL: {url} (Content-Type: {content_type})")
            return None
            
        return response.text
    except requests.Timeout as e:
        logger.error(f"Timeout occurred when downloading {url}: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None

def extract_links(html_content: str, base_url: str) -> list[str]:
    """Parses hyperlinks from HTML content using BeautifulSoup.
    
    Resolves relative links to absolute URLs and removes URL fragments.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        
        # Filter out empty anchors, fragments, and javascript protocols
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
            
        # Resolve relative URLs
        absolute_url = urljoin(base_url, href)
        
        # Normalize URL by removing fragments
        try:
            parsed = urlparse(absolute_url)
            normalized_url = parsed._replace(fragment="").geturl()
            links.append(normalized_url)
        except Exception as e:
            logger.warning(f"Error normalizing URL {absolute_url}: {e}")
            
    return links

def extract_title(html_content: str) -> str | None:
    """Extracts the title tag content from HTML if it exists."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception as e:
        logger.warning(f"Error extracting title: {e}")
    return None

def crawl(seed_url: str, max_depth: int = 2, timeout: float = 5.0, 
          db_manager: DatabaseManager = None, num_workers: int = 5) -> dict[str, list[str]]:
    """Performs a multi-threaded BFS crawl starting from a seed URL.
    
    Crawls up to the specified max_depth (default 2) using a ThreadPoolExecutor 
    with a default of 5 threads, avoids duplicate crawls with a thread-safe visited 
    set, and stores crawled metadata using a thread-safe DatabaseManager.
    """
    parsed_seed = urlparse(seed_url)
    base_domain = parsed_seed.netloc.lower()
    if not base_domain:
        logger.error(f"Invalid seed URL: {seed_url}")
        return {}

    # Initialize DatabaseManager if not provided
    if db_manager is None:
        db_manager = DatabaseManager()

    # Thread-safe collections
    url_queue = queue.Queue()
    visited = {seed_url}
    visited_lock = threading.Lock()
    
    # Results dictionary protection lock
    results = {}
    results_lock = threading.Lock()

    # Put the seed in the queue
    url_queue.put((seed_url, 0))

    shutdown_event = threading.Event()

    def worker():
        while not shutdown_event.is_set():
            try:
                # Poll the queue with a timeout to allow checking shutdown_event
                url, depth = url_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if depth > max_depth:
                    continue

                logger.info(f"Processing URL (Depth {depth}/{max_depth}): {url}")
                
                # Gracefully handle network errors and timeouts within the worker thread
                try:
                    html = download_page(url, timeout=timeout)
                except Exception as e:
                    logger.error(f"Unexpected network or parsing exception for {url}: {e}")
                    html = None

                if html is None:
                    continue

                # Extract title and save page metadata to SQLite
                title = extract_title(html)
                db_manager.save_page(url, title)
                
                all_links = extract_links(html, url)
                
                # Filter out external domains
                internal_links = []
                for link in all_links:
                    if is_same_domain(link, base_domain):
                        internal_links.append(link)

                # Thread-safe save to results dict
                with results_lock:
                    results[url] = internal_links

                # Enqueue discovered links if we haven't reached max_depth
                if depth < max_depth:
                    for link in internal_links:
                        with visited_lock:
                            if link not in visited:
                                visited.add(link)
                                url_queue.put((link, depth + 1))
            except Exception as e:
                logger.error(f"Unhandled exception in crawler worker thread for {url}: {e}")
            finally:
                url_queue.task_done()

    # Run the worker threads inside a ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit workers to the pool
        futures = [executor.submit(worker) for _ in range(num_workers)]
        
        # Block until all tasks in the queue (including dynamically added ones) are complete
        url_queue.join()
        
        # Signal workers to terminate their loops
        shutdown_event.set()
        
    return results
