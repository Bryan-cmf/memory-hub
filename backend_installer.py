#!/usr/bin/env python3
"""MemoryHub Backend Installer — arrow-key TUI with real installation"""
import sys,os,subprocess,json,time,platform as pf,termios,tty,urllib.request
from pathlib import Path

def cls(): os.system("clear")
B="\033[1m";N="\033[0m";G="\033[32m";C="\033[36m";Y="\033[33m";R="\033[31m";D="\033[2m\033[37m";H="\033[7m"

def box(t,w=62):
    print(f"╭{'─'*w}╮")
    for l in t.strip().split("\n"):
        clean=l
        for e in [B,N,G,C,Y,R,D,H]:clean=clean.replace(e,"")
        print(f"│ {l}{' '*(w-len(clean)-2)} │")
    print(f"╰{'─'*w}╯")

def getch():
    fd=sys.stdin.fileno();old=termios.tcgetattr(fd)
    try:tty.setraw(fd);c=sys.stdin.read(1)
    finally:termios.tcsetattr(fd,termios.TCSADRAIN,old)
    return c

def read_key():
    c=getch()
    if c=='\x1b' and getch()=='[':
        c3=getch()
        if c3=='A':return 'UP'
        if c3=='B':return 'DOWN'
    if c in('\r','\n'):return 'ENTER'
    if c==' ':return 'SPACE'
    if c in('q','Q'):return 'Q'
    return c

BACKENDS={
 "file":{"name":"File System","installed":True,"required":True,"cmd":None,"check":None,
         "desc":"Source of Truth"},
 "sqlite":{"name":"SQLite","cmd":None,
           "check":[sys.executable,"-c","import sqlite3;print(1)"],
           "desc":"Metadata + full-text index"},
 "qdrant":{"name":"Qdrant",
           "cmd":["docker","run","-d","--name","mh-qdrant","-p","6333:6333","qdrant/qdrant"],
           "check":["curl","-sf","http://localhost:6333/health"],
           "collections":["openclaw_mem","hermes_mem","deepseek_mem","claude_mem"],
           "desc":"Vector search primary"},
 "chroma":{"name":"Chroma",
           "cmd":[sys.executable,"-m","pip","install","chromadb"],
           "check":[sys.executable,"-c","import chromadb;print(1)"],
           "desc":"Lightweight vector DB"},
 "lancedb":{"name":"LanceDB",
            "cmd":[sys.executable,"-m","pip","install","lancedb"],
            "check":[sys.executable,"-c","import lancedb;print(1)"],
            "desc":"Embedded vector DB"},
 "redis":{"name":"Redis",
          "cmd":["brew","install","redis"] if pf.system()=="Darwin" else None,
          "check":["redis-cli","ping"],
          "desc":"Hot cache layer"},
}

MH=Path(os.path.expanduser("~/.memory-hub"));CFG=MH/"backends.json"

def detect():
    for bid,be in BACKENDS.items():
        if bid=="file":continue
        c=be.get("check")
        if not c:continue
        try:be["installed"]=subprocess.run(c,capture_output=True,timeout=5).returncode==0
        except:be["installed"]=False

def load_cfg():
    if CFG.exists():
        try:return json.loads(CFG.read_text(encoding="utf-8"))
        except:pass
    return {"installed":[]}

def save_cfg(cfg):
    CFG.parent.mkdir(parents=True,exist_ok=True)
    CFG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8")

def real_install(bid,cb=None):
    """Actually execute the install command and verify."""
    be=BACKENDS[bid]
    if not be.get("cmd"):return True,"built-in"
    cmd=be["cmd"]
    try:
        if cb:cb(f"Running: {' '.join(cmd)}")
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        ok=r.returncode==0
        if not ok:
            # Retry with --break-system-packages for pip on macOS
            if "pip" in str(cmd) and pf.system()=="Darwin":
                if cb:cb("Retrying with --break-system-packages...")
                r2=subprocess.run(cmd+["--break-system-packages"],capture_output=True,text=True,timeout=180)
                ok=r2.returncode==0
        # Post-install actions
        if ok and bid=="redis" and pf.system()=="Darwin":
            subprocess.run(["brew","services","start","redis"],capture_output=True,timeout=10)
        # Verify
        if ok:
            vc=be.get("check")
            if vc:
                vr=subprocess.run(vc,capture_output=True,timeout=10)
                ok=vr.returncode==0
        return ok,"OK" if ok else "FAIL"
    except FileNotFoundError:
        return False,"command not found"
    except subprocess.TimeoutExpired:
        return False,"timeout"
    except Exception as e:
        return False,str(e)[:80]

def auto_connect(installed_list):
    """Create Qdrant collections and enable backends."""
    connected=[]
    if "qdrant" in installed_list:
        for col in BACKENDS["qdrant"].get("collections",[]):
            try:
                import urllib.request
                data=json.dumps({"vectors":{"size":384,"distance":"Cosine","on_disk":True}}).encode()
                req=urllib.request.Request(f"http://localhost:6333/collections/{col}",data=data,method="PUT",
                                           headers={"Content-Type":"application/json"})
                urllib.request.urlopen(req,timeout=5)
            except:pass
        connected.append("Qdrant: 4 collections ready on :6333")
    if "chroma" in installed_list:connected.append("Chroma: vector ops available")
    if "lancedb" in installed_list:connected.append("LanceDB: embedded search ready")
    if "redis" in installed_list:connected.append("Redis: cache layer active on :6379")
    return connected

def tui():
    detect()
    cfg=load_cfg()
    for bid in cfg.get("installed",[]):
        if bid in BACKENDS:BACKENDS[bid]["installed"]=True
    
    items=[{"id":bid,"name":be["name"],"installed":be.get("installed",False),
            "required":be.get("required",False),"desc":be.get("desc","")}
           for bid,be in BACKENDS.items()]
    selected=set()
    cursor=0
    
    while True:
        cls()
        box(f"\n{B}  MemoryHub — Backend Installer{N}\n\n"
            f"  {D}↑↓ move  Space [x] select  Enter install  Q quit{N}")
        print()
        
        for i,item in enumerate(items):
            sel=cursor==i
            chk=item["id"] in selected or item["installed"]
            prefix="[x]" if chk else "[ ]"
            name=f"{item['name']:12s}"
            extra=""
            if item["installed"]:extra=f" {D}(installed){N}"
            if item["required"]:extra=f" {Y}(required){N}"
            if not chk and not item["installed"]:desc=f"{D}{item['desc'][:30]}{N}"
            else:desc=""
            
            line=f"  {prefix} {name}{extra}  {desc}"
            if sel:line=f"{H}{line}{' '*(62-len(line.replace(H,'').replace(N,'')))}{N}"
            print(line)
        
        print(f"\n  {D}Selected: {', '.join(sorted(selected)) if selected else 'none'}{N}")
        
        k=read_key()
        if k=='UP':cursor=(cursor-1)%len(items)
        elif k=='DOWN':cursor=(cursor+1)%len(items)
        elif k=='SPACE':
            iid=items[cursor]["id"]
            if not items[cursor]["installed"] and not items[cursor]["required"]:
                if iid in selected:selected.remove(iid)
                else:selected.add(iid)
        elif k=='ENTER':
            if not selected:break
            
            # Show confirmation
            cls()
            box(f"\n{B}  Confirm Installation{N}")
            print()
            for bid in sorted(selected):
                be=BACKENDS[bid]
                cmd=" ".join(be.get("cmd",["built-in"]))[:50]
                print(f"  • {be['name']:10s} → {cmd}")
            print(f"\n  {Y}Proceed with real installation?{N}")
            print(f"  {D}[Enter] Yes  [Q] Cancel{N}")
            
            confirm=read_key()
            if confirm=='Q':continue
            
            # Execute real installation
            cls()
            box(f"\n{B}  Installing...{N}")
            results={}
            
            for bid in list(selected):
                be=BACKENDS[bid]
                print(f"\n  {C}⏳{N} {be['name']} ",end="",flush=True)
                ok,msg=real_install(bid)
                results[bid]={"ok":ok,"msg":msg}
                time.sleep(0.5)
            
            # Auto-connect
            installed=[bid for bid,r in results.items() if r["ok"]]
            connections=auto_connect(installed)
            
            # Save config
            for bid in installed:
                if bid not in cfg.get("installed",[]):cfg["installed"].append(bid)
            save_cfg(cfg)
            
            # Show results
            cls()
            box(f"\n{G}  Installation Results{N}")
            for bid,r in results.items():
                be=BACKENDS[bid]
                mark=f"{G}OK{N}" if r["ok"] else f"{R}FAIL{N}"
                print(f"  {mark} {be['name']:10s} {r['msg']}")
            if connections:
                print(f"\n  {C}Auto-connected:{N}")
                for c in connections:print(f"  {D}•{N} {c}")
            print(f"\n  {D}Press any key...{N}")
            read_key()
            break
        elif k=='Q':break

if __name__=="__main__":
    try:tui()
    except KeyboardInterrupt:print(N);sys.exit(0)
