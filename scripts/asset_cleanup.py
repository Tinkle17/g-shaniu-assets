#!/data/data/com.termux/files/usr/bin/python3
import argparse, json
from asset_sync import clean_local

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--days",type=int,default=7)
    args=ap.parse_args()
    removed=clean_local(args.days)
    print(json.dumps({"status":"ok","retention_days":args.days,"removed":removed},ensure_ascii=False))

if __name__=="__main__":
    main()
