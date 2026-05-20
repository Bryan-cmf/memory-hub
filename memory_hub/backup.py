#!/usr/bin/env python3
"""MemoryHub Backup Daemon — 三層定時備份 (hourly/daily/weekly) + 一鍵恢復"""
import json,os,sys,tarfile,shutil,subprocess,time
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
MH=Path(os.path.expanduser("~/.memory-hub"))
BACKUP_ROOT=MH/"backups"
STATE_FILE=MH/"backup_state.json"

TIERS={"hourly":{"keep":24,"desc":"每小時熱備份"},
       "daily":{"keep":30,"desc":"每日備份"},
       "weekly":{"keep":12,"desc":"每週備份"}}

def load_state():
 if STATE_FILE.exists():
  try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
  except Exception: pass
 return {"last_hourly":None,"last_daily":None,"last_weekly":None,"total_backups":0,"errors":[]}

def save_state(s): STATE_FILE.parent.mkdir(parents=True,exist_ok=True);STATE_FILE.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")

def backup_qdrant(tier_dir):
 try:
  import urllib.request
  for col in ["openclaw_mem","hermes_mem","deepseek_mem","claude_mem","shared_mem"]:
   try:
    req=urllib.request.Request(f"http://localhost:6333/collections/{col}/snapshots",method="POST")
    urllib.request.urlopen(req,timeout=5)
   except Exception: pass
 except Exception: pass

def backup_files(tier_dir):
 mem_dirs=[Path(os.path.expanduser("~/.openclaw/workspace/memory")),
           Path(os.path.expanduser("~/.hermes/workspace/memory"))]
 for md in mem_dirs:
  if md.exists():
   tf=tier_dir/f"memory_{md.parent.parent.name}_{datetime.now(HKT).strftime('%Y%m%d_%H%M')}.tar.gz"
   with tarfile.open(tf,"w:gz") as tar:
    for f in md.rglob("*"):
     if f.is_file(): tar.add(f,arcname=str(f.relative_to(md.parent.parent)))
 tar_mh=tier_dir/f"memory_hub_{datetime.now(HKT).strftime('%Y%m%d_%H%M')}.tar.gz"
 with tarfile.open(tar_mh,"w:gz") as tar:
  for d in [MH/"captured",MH/"memories",MH/"hooks"]:
   if d.exists():
    for f in d.rglob("*"):
     if f.is_file(): tar.add(f,arcname=str(f.relative_to(MH)))

def backup_configs(tier_dir):
 for f in [MH/"capture_offsets.json",MH/"capture_daemon_state.json",
           MH/"scan_state.json",MH/"backends.json",MH/"config.json",
           MH/"backup_state.json"]:
  if f.exists(): shutil.copy2(f,tier_dir/f.name)

def create_backup(tier="hourly"):
 st=load_state()
 ts=datetime.now(HKT).strftime("%Y%m%d_%H%M")
 tier_dir=BACKUP_ROOT/tier/ts
 tier_dir.mkdir(parents=True,exist_ok=True)
 errors=[]
 try: backup_qdrant(tier_dir)
 except Exception as e: errors.append(f"qdrant:{e}")
 try: backup_files(tier_dir)
 except Exception as e: errors.append(f"files:{e}")
 try: backup_configs(tier_dir)
 except Exception as e: errors.append(f"configs:{e}")
 files=list(tier_dir.rglob("*"))
 total_size=sum(f.stat().st_size for f in files if f.is_file())
 if total_size==0: errors.append("backup_empty")
 st[f"last_{tier}"]=ts
 st["total_backups"]+=1
 if errors: st["errors"].append({"tier":tier,"time":ts,"errors":errors})
 save_state(st)
 cleanup_old(tier)
 return {"ok":len(errors)==0,"tier":tier,"time":ts,"files":len(files),"size_mb":total_size/1024/1024,"errors":errors}

def cleanup_old(tier):
 keep=TIERS[tier]["keep"]
 td=BACKUP_ROOT/tier
 if not td.exists(): return
 dirs=sorted(td.iterdir(),reverse=True)
 for d in dirs[keep:]:
  if d.is_dir(): shutil.rmtree(d)

def restore_backup(tier,num=0):
 td=BACKUP_ROOT/tier
 if not td.exists(): return {"ok":False,"msg":"No backups found"}
 dirs=sorted(td.iterdir(),reverse=True)
 if not dirs: return {"ok":False,"msg":"No backups"}
 if num>=len(dirs): num=0
 src=dirs[num]
 create_backup("hourly")
 restored=0
 for tf in src.glob("*.tar.gz"):
  try:
   with tarfile.open(tf) as tar: tar.extractall("/")
   restored+=1
  except Exception as e: return {"ok":False,"msg":f"Restore failed: {e}"}
 return {"ok":True,"msg":f"Restored {restored} archives from {src.name}","source":str(src)}

def status():
 st=load_state();s=[]
 for tier,cfg in TIERS.items():
  td=BACKUP_ROOT/tier
  dirs=sorted(td.iterdir(),reverse=True) if td.exists() else []
  s.append({"tier":tier,"desc":cfg["desc"],"keep":cfg["keep"],
            "last":st.get(f"last_{tier}"),"count":len(dirs),"total":st.get("total_backups",0)})
 return s

def tui():
 os.system("clear")
 while True:
  print("="*60);print("  🛡️  MemoryHub Backup & Recovery");print("="*60)
  ss=status()
  for s in ss:
   m="✅" if s["last"] else "⚠️"
   print(f"  {m} {s['desc']}: {s['last'] or 'Never'} ({s['count']} kept)")
  print("\n  [B] Backup Now   [R] Restore   [C] Clean   [Q] Quit")
  c=input("  > ").strip().lower()
  if c=="q":break
  if c=="b":
   print("  Tier (hourly/daily/weekly):",end=" ");t=input().strip() or "hourly"
   r=create_backup(t)
   print(f"  {'✅' if r['ok'] else '❌'} {r['files']} files, {r['size_mb']:.1f}MB")
  if c=="r":
   print("  Tier (hourly/daily/weekly):",end=" ");t=input().strip() or "daily"
   r=restore_backup(t)
   print(f"  {'✅' if r['ok'] else '❌'} {r['msg']}")
  if c=="c":
   for t in TIERS: cleanup_old(t)
   print("  ✅ Old backups cleaned")
  input("\n  Press Enter...")

if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser()
 p.add_argument("--tier",choices=["hourly","daily","weekly"],default="hourly")
 p.add_argument("--tui",action="store_true")
 a=p.parse_args()
 if a.tui: tui()
 else: print(json.dumps(create_backup(a.tier),ensure_ascii=False,indent=2))
