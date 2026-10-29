import sys
import argparse
from src.knowledge.ingestion.spider_ingestor import SpiderIngestor

def main():
    parser = argparse.ArgumentParser(description="CG-SQL Knowledge Base Ingestion")
    parser.add_argument('--dataset', type=str, default='spider', choices=['spider'], help="Dataset to ingest")
    parser.add_argument('--spider-path', type=str, default='spider_data', help="Path to spider_data directory")
    parser.add_argument('--limit', type=int, default=None, help="Limit number of databases to ingest")
    
    args = parser.parse_args()
    
    print(f"Starting ingestion for {args.dataset}...")
    
    if args.dataset == 'spider':
        ingestor = SpiderIngestor(spider_path=args.spider_path)
    else:
        print(f"Dataset {args.dataset} not supported yet.")
        sys.exit(1)
        
    count = ingestor.discover()
    print(f"Discovered {count} databases.")
    
    print("Ingesting...")
    ingestor.ingest(limit=args.limit)
    
    print("\n" + "="*50)
    print("INGESTION REPORT")
    print("="*50)
    for k, v in ingestor.report().items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
