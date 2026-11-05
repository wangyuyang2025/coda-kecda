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
 try:host=subprocess.check_output(['/usr/sbin/scutil','--get','LocalHostName'],text=True).strip()+'.local'
 except Exception:host='localhost'
 ips=[]
 for iface in ('en0','en1','en2'):
  ip=subprocess.run(['/usr/sbin/ipconfig','getifaddr',iface],capture_output=True,text=True).stdout.strip()
  if ip and ip not in ips:ips.append(ip)
 return host,ips+['127.0.0.1']
def config(host,ips):
 san=','.join(['DNS:'+host]+['IP:'+i for i in ips])
 return ('[req]\ndistinguished_name=dn\n[dn]\n'
  '[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n'
  '[leaf]\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n'
  'subjectAltName='+san+'\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
def run(*args):subprocess.run([OPENSSL,*args],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
def ensure(root):
 """返回 (网页证书, 网页私钥, 证书机构)。缺了、快过期、名字或 IP 变了就重做。"""
 f=folder(root);ca,cakey=f/'证书机构.pem',f/'证书机构.key';cert,key,info=f/'网页证书.pem',f/'网页证书.key',f/'网页证书.json'
 host,ips=names()
 with tempfile.TemporaryDirectory() as tmp:
  cfg=Path(tmp)/'openssl.cnf';cfg.write_text(config(host,ips))
  if not ca.exists() or not cakey.exists():
   run('req','-x509','-newkey','rsa:2048','-sha256','-nodes','-keyout',str(cakey),'-out',str(ca),'-days','3650',
       '-subj','/CN=Coda Local CA (%s)'%host.removesuffix('.local'),'-config',str(cfg),'-extensions','ca')
   cakey.chmod(0o600);cert.unlink(missing_ok=True)
  try:old=json.loads(info.read_text())
  except Exception:old={}
  fresh=old.get('host')==host and set(ips)<=set(old.get('ips',[])) and old.get('expires','')>str(datetime.date.today()+datetime.timedelta(days=60))
  if not (fresh and cert.exists() and key.exists()):
   csr=Path(tmp)/'web.csr'
   run('req','-new','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(csr),'-subj','/CN='+host,'-config',str(cfg))
   run('x509','-req','-in',str(csr),'-CA',str(ca),'-CAkey',str(cakey),'-set_serial','0x'+secrets.token_hex(8),'-out',str(cert),
       '-days','800','-sha256','-extfile',str(cfg),'-extensions','leaf')
   key.chmod(0o600)
   info.write_text(json.dumps({'host':host,'ips':ips,'expires':str(datetime.date.today()+datetime.timedelta(days=800))},ensure_ascii=False))
 return cert,key,ca
def urls(root,port):
 """手机上打开的网址：先用 Mac 名字（换 Wi-Fi 也不变），IP 备用。"""
 host,ips=names()
 return ['https://%s:%d'%(host,port)]+['https://%s:%d'%(i,port) for i in ips if i!='127.0.0.1']
