#!/data/data/com.termux/files/usr/bin/python3
import threading
import signal
import argparse, json, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse

HOME=Path.home()
_WAKE_EVENT = threading.Event()

def _handle_wake_signal(_signum, _frame):
    _WAKE_EVENT.set()

def _realtime_wake_healthy(max_age_seconds=45.0):
    flag=HOME/".g-shaniu/realtime-wake/healthy.flag"
    try:
        return flag.exists() and (time.time()-flag.stat().st_mtime) <= max_age_seconds
    except OSError:
        return False

WORKER_ID="device-mi6-fast-v1"
TARGET="device-mi6"
RISH="/data/data/com.termux/files/usr/bin/rish"
ALLOWED={"battery","wifi","open_app","home","open_url","shizuku_status","shizuku_ensure","top_app","back","wake","unlock","root_status","stack_ensure","force_stop_app","app_running","screen_status","screen_off","lock","device_health","storage_status","memory_status","phone_dial","phone_call"}
APPS = {'wechat': ['am', 'start', '-n', 'com.tencent.mm/.ui.LauncherUI'], 'settings': ['am', 'start', '-a', 'android.settings.SETTINGS'], 'xiaohongshu': ['am', 'start', '-n', 'com.xingin.xhs/.index.v2.IndexActivityV2']}
sys.path.insert(0,str(HOME/".hermes/scripts"))
import bridge_worker
import device_cap8
import root_broker_client

def run(argv, timeout=8):
    import os, signal
    env=os.environ.copy()
    env.setdefault("HOME",str(HOME))
    env.setdefault("PREFIX","/data/data/com.termux/files/usr")
    env["PATH"]="/data/data/com.termux/files/usr/bin:"+env.get("PATH","")
    p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    try:
        out,err=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid, signal.SIGKILL)
        except Exception: pass
        out,err=p.communicate()
        raise RuntimeError("command_timeout")
    return {"returncode":p.returncode,"stdout":out[-12000:],"stderr":err[-4000:]}


def rish_call(command, timeout=8, allow_failure=False):
    p=run([RISH,"-c",command], timeout=timeout)
    out=((p.get("stdout") or "")+"\n"+(p.get("stderr") or "")).strip()
    if p.get("returncode")!=0 and not allow_failure:
        raise RuntimeError("shizuku_failed:"+out[-1000:])
    return p,out

def broker_call(action, timeout=8):
    return root_broker_client.call(action, timeout=timeout)

def handle(name,payload):
    if name not in ALLOWED:
        raise ValueError("device_action_not_allowed")
    if name=="battery":
        try:
            p=run(["/data/data/com.termux/files/usr/bin/termux-battery-status"], timeout=4)
            if p["returncode"]==0 and p["stdout"].strip():
                return json.loads(p["stdout"])
        except Exception:
            pass
        base=Path("/sys/class/power_supply/battery")
        def rd(name):
            try: return (base/name).read_text().strip()
            except Exception: return None
        pct=rd("capacity")
        temp=rd("temp")
        return {
            "percentage": int(pct) if pct and pct.isdigit() else None,
            "temperature": (int(temp)/10.0) if temp and temp.lstrip("-").isdigit() else None,
            "status": rd("status"),
            "source": "sysfs_fallback"
        }
    if name=="wifi":
        p=run(["termux-wifi-connectioninfo"])
        if p["returncode"]!=0: raise RuntimeError(p["stderr"] or "wifi_failed")
        return json.loads(p["stdout"])
    if name=="home":
        return run(["am","start","-a","android.intent.action.MAIN","-c","android.intent.category.HOME"])
    if name=="open_app":
        app=str(payload.get("app","")).lower()
        argv=APPS.get(app)
        if not argv: raise ValueError("app_not_allowed")
        return run(argv)
    if name=="open_url":
        url=str(payload.get("url",""))
        if len(url)>2048: raise ValueError("url_too_long")
        u=urlparse(url)
        if u.scheme not in ("http","https") or not u.netloc:
            raise ValueError("url_not_allowed")
        return run(["am","start","-a","android.intent.action.VIEW","-d",url])
    if name=="root_status":
        data=broker_call("status", timeout=5)
        data["backend"]="root-broker"
        return data
    if name=="shizuku_ensure":
        data=broker_call("shizuku.ensure", timeout=8)
        data["backend"]="root-broker"
        return data
    if name=="stack_ensure":
        data=broker_call("stack.ensure", timeout=8)
        data["backend"]="root-broker"
        return data
    if name=="shizuku_status":
        p,out=rish_call("id", timeout=5, allow_failure=True)
        available=p.get("returncode")==0 and ("uid=2000(shell)" in out or "uid=0(root)" in out)
        if not available:
            try:
                broker_call("shizuku.ensure", timeout=8)
                time.sleep(1)
                p,out=rish_call("id", timeout=5, allow_failure=True)
                available=p.get("returncode")==0 and "uid=2000(shell)" in out
            except Exception:
                pass
        return {"available":available,"returncode":p.get("returncode"),"identity":out[-1000:],"backend":"shizuku","self_heal_attempted":not (p.get("returncode")==0 and ("uid=2000(shell)" in out or "uid=0(root)" in out))}
    if name=="top_app":
        p,out=rish_call("dumpsys activity activities | grep mResumedActivity", timeout=6, allow_failure=True)
        if p.get("returncode")!=0:
            try:
                broker_call("shizuku.ensure", timeout=8)
                time.sleep(1)
                p,out=rish_call("dumpsys activity activities | grep mResumedActivity", timeout=6, allow_failure=True)
            except Exception:
                pass
        if p.get("returncode")!=0 or not out.strip():
            p,out=rish_call("dumpsys window windows | grep mCurrentFocus", timeout=6, allow_failure=True)
        if p.get("returncode")!=0:
            raise RuntimeError("shizuku_top_app_failed:"+out[-1000:])
        return {"raw":out[-2000:],"backend":"shizuku"}
    if name=="back":
        rish_call("input keyevent KEYCODE_BACK", timeout=5)
        return {"ok":True,"backend":"shizuku"}
    if name=="wake":
        try:
            data=broker_call("wake", timeout=5)
            data["backend"]="root-broker"
            return data
        except Exception:
            rish_call("input keyevent KEYCODE_WAKEUP", timeout=5)
            return {"ok":True,"backend":"shizuku-fallback"}
    if name=="unlock":
        data=broker_call("unlock", timeout=8)
        data["backend"]="root-broker"
        return data
    if name=="lock":
        try:
            data=broker_call("lock", timeout=6)
            data["backend"]="root-broker"
            return data
        except Exception:
            pass
    if name=="screen_off":
        try:
            data=broker_call("lock", timeout=6)
            data["backend"]="root-broker"
            data["screen"]="off"
            return data
        except Exception:
            pass
    if name=="screen_status":
        try:
            data=broker_call("status", timeout=5)
            return {"screen":data.get("screen","unknown"),"locked":data.get("locked"),"pin_configured":data.get("pin_configured"),"backend":"root-broker"}
        except Exception:
            pass
    extra=device_cap8.handle(name,payload,rish_call,handle)
    if extra is not None: return extra
    raise ValueError("unsupported")

def post(obj):
    old_url=getattr(bridge_worker,"BRIDGE_URL",None)
    bridge_worker.BRIDGE_URL="https://kmpdlizvwzdxplbarhcv.supabase.co/functions/v1/device-bridge"
    try:
        raw=bridge_worker.post(obj)
    finally:
        if old_url is not None:
            bridge_worker.BRIDGE_URL=old_url
    if isinstance(raw,dict):
        return raw
    if isinstance(raw,tuple) and len(raw)==2:
        status,body=raw
        try:
            data=json.loads(body) if isinstance(body,str) else body
        except Exception:
            raise RuntimeError(f"bridge_bad_json:{status}")
        if not isinstance(data,dict):
            raise RuntimeError(f"bridge_bad_response:{status}")
        return data
    if isinstance(raw,str):
        try:
            data=json.loads(raw)
        except Exception:
            raise RuntimeError("bridge_bad_json")
        if isinstance(data,dict):
            return data
    raise RuntimeError("bridge_bad_response")

def once():
    r=post({"op":"claim","target":TARGET,"worker_id":WORKER_ID,"lease_seconds":120})
    task=r.get("task") if r.get("ok") else None
    if not task:
        return False
    tid=task.get("id")
    logp=HOME/".g-shaniu/device/device-worker-state.log"
    try:
        logp.write_text(f"claimed {tid} {task.get('action')}\n")
        if task.get("action")!="fast_inspect":
            raise ValueError("transport_action_not_allowed")
        payload=task.get("payload") or {}
        if not isinstance(payload,dict):
            raise ValueError("invalid_payload")
        name=str(payload.get("device_action",""))
        data=handle(name,payload)
        with logp.open("a") as f: f.write(f"handled {tid} {name}\n")
        complete_msg={"op":"complete","id":tid,"worker_id":WORKER_ID,
                      "result":{"ok":True,"device_action":name,"data":data,"worker_id":WORKER_ID}}
        if task.get("claim_token"):
            complete_msg["claim_token"]=task.get("claim_token")
        post(complete_msg)
        with logp.open("a") as f: f.write(f"completed {tid}\n")
    except Exception as e:
        try:
            with logp.open("a") as f: f.write(f"error {tid} {type(e).__name__}:{e}\n")
        except Exception:
            pass
        fail_msg={"op":"fail","id":tid,"worker_id":WORKER_ID,"error":str(e)[:1000]}
        if task.get("claim_token"):
            fail_msg["claim_token"]=task.get("claim_token")
        post(fail_msg)
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true")
    ap.add_argument("--loop",action="store_true")
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--action", choices=["battery","wifi","open_app","home","open_url","shizuku_status","shizuku_ensure","top_app","back","wake","unlock","root_status","stack_ensure","force_stop_app","app_running","screen_status","screen_off","lock","device_health","storage_status","memory_status","phone_dial","phone_call"])
    ap.add_argument("--app", choices=["wechat","settings"])
    ap.add_argument("--url")
    ap.add_argument("--number")
    ap.add_argument("--approval-verified",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        out={"worker_id":WORKER_ID,"allowed":sorted(ALLOWED),"shell_access":False,
             "battery":handle("battery",{})}
        print(json.dumps(out,ensure_ascii=False))
        return
    if args.action:
        payload={}
        if args.action in ("open_app","force_stop_app","app_running"):
            if not args.app: raise SystemExit("--app required")
            payload["app"]=args.app
        elif args.action=="open_url":
            if not args.url: raise SystemExit("--url required")
            payload["url"]=args.url
        elif args.action in ("phone_dial","phone_call"):
            if not args.number: raise SystemExit("--number required")
            payload["number"]=args.number
            if args.action=="phone_call":
                payload["approval_verified"]=bool(args.approval_verified)
        out=handle(args.action,payload)
        print(json.dumps({"ok":True,"device_action":args.action,"data":out},ensure_ascii=False))
        return
    if args.once:
        once(); return
    if args.loop:
        signal.signal(signal.SIGUSR1, _handle_wake_signal)
        idle_sleep=1.5
        production_flag=HOME/".g-shaniu/realtime-wake/production.enabled"
        while True:
            try:
                did=once()
                production=production_flag.exists()
                if did:
                    idle_sleep=1.5
                else:
                    if production:
                        max_idle=60.0 if _realtime_wake_healthy() else 5.0
                    else:
                        max_idle=15.0
                    woke=_WAKE_EVENT.wait(min(idle_sleep,max_idle))
                    _WAKE_EVENT.clear()
                    if woke:
                        idle_sleep=1.5
                    else:
                        idle_sleep=min(max_idle,idle_sleep*1.6)
            except Exception as e:
                idle_sleep=1.5
                try:
                    lp=HOME/".g-shaniu/device/device-worker-state.log"
                    with lp.open("a") as f:
                        f.write(f"loop_error {type(e).__name__}:{e}\n")
                except Exception:
                    pass
                _WAKE_EVENT.wait(3.0)
                _WAKE_EVENT.clear()
        return
    ap.print_help()

if __name__=="__main__":
    main()
