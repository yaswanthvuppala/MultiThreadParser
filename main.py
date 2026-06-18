import argparse
import json
import sys
from parser import crawl

def main():
    parser = argparse.ArgumentParser(description="Multi-threaded BFS Web Crawler")
    parser.add_argument("seed", help="The starting seed URL to crawl")
    parser.add_argument("--depth", type=int, default=2, help="Maximum traversal depth (default: 2)")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP request timeout in seconds")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent worker threads (default: 5)")
    
    args = parser.parse_args()
    
    print(f"Starting crawl at: {args.seed}")
    print(f"Configuration: Depth Limit = {args.depth}, Timeout = {args.timeout}s, Workers = {args.workers}\n")
    
    try:
        results = crawl(args.seed, max_depth=args.depth, timeout=args.timeout, num_workers=args.workers)
        
        print(f"\nCrawl complete. Successfully crawled {len(results)} pages:")
        for url, links in results.items():
            print(f"- {url} (found {len(links)} internal links)")
            
    except KeyboardInterrupt:
        print("\nCrawl interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during crawl execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
