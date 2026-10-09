"""Check published dashboard data against the exact build artifact."""
import argparse,json,time,urllib.request
from .quality import fingerprint

def main():
    p=argparse.ArgumentParser();p.add_argument("url");p.add_argument("manifest");args=p.parse_args()
    manifest=json.load(open(args.manifest,encoding="utf-8"))
    for attempt in range(8):
        try:
            url=args.url.rstrip("/")+"/data/triton.json"
            with urllib.request.urlopen(url,timeout=30) as response: source=response.read().decode()
            payload=json.loads(source)
            if fingerprint(payload)!=manifest["sha256"]: raise ValueError("Published data differs from this build")
            print(f"Published dashboard data matches build: {manifest['collected_at']} ({manifest['npu_points']} NPU points)")
            return
        except Exception as exc:
            print("Verification attempt",attempt+1,str(exc),flush=True)
            if attempt==7: raise
            time.sleep(20)

if __name__=="__main__": main()
