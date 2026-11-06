"""手机网页版用的 https 证书（10-23）：iPhone 的网页、添加到主屏幕、离线缓存都要“受信任”的证书，
App 用的那张自签证书（证书.pem）iPhone 网页不认，所以另做一套：
- 本机证书机构（证书机构.pem / .key）：十年，只做一次。iPhone 上装一次（Safari 打开 /m/cert → 设置里安装描述文件 → 证书信任设置里打开）。
- 网页证书（网页证书.pem / .key）：由上面签，写上这台 Mac 的名字（xxx.local）和局域网 IP；iPhone 要求不超过 825 天，这里 800 天，
  快到期、或者 Mac 名字 / IP 变了，启动时自动重签（不用重装，iPhone 信任的是证书机构）。
App 的证书不动，App 照常连 18766；网页版走 18767。"""
import datetime,json,os,secrets,subprocess,tempfile
from pathlib import Path
from 存取公共 import data_dir
OPENSSL='/usr/bin/openssl'
def folder(root):p=data_dir(root)/'手机连接';p.mkdir(parents=True,exist_ok=True);return p
def names():
 import 跨平台
 return 跨平台.host_name(),跨平台.lan_ips()+['127.0.0.1']
def ensure(root):
 """返回 (网页证书, 网页私钥, 证书机构)。缺了、快过期、名字或 IP 变了就重做。用纯 Python 生成，Windows 不用装 openssl。"""
 import 跨平台
 f=folder(root);ca,cakey=f/'证书机构.pem',f/'证书机构.key';cert,key,info=f/'网页证书.pem',f/'网页证书.key',f/'网页证书.json'
 host,ips=names()
 try:跨平台.read_key(cakey.read_text(encoding='ascii'));ok=ca.exists()
 except Exception:ok=False
 if not ok:
  c,k=跨平台.make_ca('Coda Local CA (%s)'%host.removesuffix('.local'));ca.write_text(c,encoding='ascii');跨平台.write_private(cakey,k);cert.unlink(missing_ok=True)
 try:old=json.loads(info.read_text(encoding='utf-8'))
 except Exception:old={}
 fresh=old.get('host')==host and set(ips)<=set(old.get('ips',[])) and old.get('expires','')>str(datetime.date.today()+datetime.timedelta(days=60))
 if not (fresh and cert.exists() and key.exists()):
  c,k=跨平台.make_leaf(ca.read_text(encoding='ascii'),cakey.read_text(encoding='ascii'),host,ips);cert.write_text(c,encoding='ascii');跨平台.write_private(key,k)
  info.write_text(json.dumps({'host':host,'ips':ips,'expires':str(datetime.date.today()+datetime.timedelta(days=800))},ensure_ascii=False),encoding='utf-8')
 return cert,key,ca
def urls(root,port):
 """手机上打开的网址：先用 Mac 名字（换 Wi-Fi 也不变），IP 备用。"""
 host,ips=names()
 by_ip=['https://%s:%d'%(i,port) for i in ips if i!='127.0.0.1'];by_name=['https://%s:%d'%(host,port)]
 return by_ip+by_name if __import__('os').name=='nt' else by_name+by_ip  # Windows 的名字手机不一定找得到
